# core_analytics_engine/market_regime_engine_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

import logging
from datetime import datetime, time
from typing import Dict, Any, Optional, List, Union

import pandas as pd # type: ignore
import numpy as np # type: ignore

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class MarketRegimeEngineV2_5:
    '''
    Classifies the prevailing market environment for EOTS V2.5.
    Uses v2.5 metrics, ticker context, and dynamic thresholds to determine the market regime.
    '''

    def __init__(self, config_manager_v2_5_instance: Any):
        self.logger = logger.getChild(self.__class__.__name__)

        if not hasattr(config_manager_v2_5_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5. Critical failure.")
            class DummyCM:
                def get_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    return default_value_to_return
                def get_resolved_path_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    return None # Or a sensible path-like string if needed
            self.config_manager = DummyCM() # type: ignore
        else:
            self.config_manager = config_manager_v2_5_instance

        self.logger.info(f"Initializing MarketRegimeEngineV2_5...")
        self._load_config_settings()
        self.logger.info("MarketRegimeEngineV2_5 Initialized.")

    def _load_config_settings(self):
        '''Loads settings specific to the Market Regime Engine.'''
        self.logger.debug("Loading MRE specific configurations...")
        # These paths MUST align with config_v2_5.json structure
        base_path = ["market_regime_engine_settings"]

        # Default regime if no rules match
        self.default_regime: str = self.config_manager.get_setting(*base_path, "default_regime", default_value_to_return="REGIME_UNDEFINED_V2_5")

        # Order in which regime rules are evaluated (critical)
        # This will be fetched per symbol context in determine_market_regime_v2_5
        # self.regime_evaluation_order_default: List[str] = self.config_manager.get_setting(*base_path, "regime_evaluation_order", default_value_to_return=[])

        # All regime rules definitions
        # This will also be fetched per symbol context
        # self.all_regime_rules_default: Dict[str, Any] = self.config_manager.get_setting(*base_path, "regime_rules", default_value_to_return={})

        # Time of day definitions (e.g., for session-specific regime logic)
        # Assuming similar structure to v2.4, needs path confirmation for v2.5
        self.time_of_day_definitions: Dict[str, Any] = self.config_manager.get_setting(*base_path, "time_of_day_definitions", default_value_to_return={})

        self.logger.debug(f"MRE default regime: {self.default_regime}")


    def _check_condition(self, metric_value: Any, condition_key: str, condition_value: Any, dynamic_thresholds: Dict) -> bool:
        '''Checks a single metric condition against its value.'''
        # Resolve dynamic threshold if condition_value is a string like "dynamic_threshold:key_name"
        if isinstance(condition_value, str) and condition_value.startswith("dynamic_threshold:"):
            threshold_key = condition_value.split(":")[1]
            if threshold_key in dynamic_thresholds:
                condition_value = dynamic_thresholds[threshold_key]
            else:
                self.logger.warning(f"Dynamic threshold key '{threshold_key}' not found in resolved thresholds. Condition will likely fail or be misinterpreted.")
                return False # Or handle as error

        # Ensure metric_value is numeric if condition implies numeric comparison
        # Allow string comparisons for specific conditions (e.g., _eq for ticker context flags)
        is_numeric_comparison = any(op in condition_key for op in ['_lt', '_gt', '_lte', '_gte'])

        if is_numeric_comparison:
            if not isinstance(metric_value, (int, float, np.number)) or pd.isna(metric_value):
                # self.logger.debug(f"Metric value '{metric_value}' is not numeric or is NaN for numeric comparison '{condition_key}'. Condition False.")
                return False
            if not isinstance(condition_value, (int, float, np.number)) or pd.isna(condition_value):
                self.logger.warning(f"Condition value '{condition_value}' for numeric comparison '{condition_key}' is not numeric or NaN. Condition False.")
                return False
            metric_value = float(metric_value)
            condition_value = float(condition_value)

        try:
            if condition_key.endswith("_lt"): return metric_value < condition_value
            if condition_key.endswith("_lte"): return metric_value <= condition_value
            if condition_key.endswith("_gt"): return metric_value > condition_value
            if condition_key.endswith("_gte"): return metric_value >= condition_value
            if condition_key.endswith("_eq"):
                if isinstance(metric_value, str) and isinstance(condition_value, str): # Case insensitive for strings
                    return metric_value.lower() == condition_value.lower()
                return metric_value == condition_value
            if condition_key.endswith("_ne"): return metric_value != condition_value
            if condition_key.endswith("_in_list"): return metric_value in condition_value # condition_value should be a list
            if condition_key.endswith("_not_in_list"): return metric_value not in condition_value
            if condition_key.endswith("_abs_gt"): return abs(metric_value) > condition_value
            if condition_key.endswith("_abs_lt"): return abs(metric_value) < condition_value
            # Add more conditions as needed (e.g., _contains for strings)
        except TypeError: # Handles comparison between incompatible types if not caught by numeric check
            # self.logger.debug(f"TypeError comparing metric value '{metric_value}' ({type(metric_value)}) with condition value '{condition_value}' ({type(condition_value)}) for key '{condition_key}'. Condition False.")
            return False

        self.logger.warning(f"Unknown condition key suffix: {condition_key}")
        return False

    def _evaluate_single_regime_rules(self, rules_for_regime: Dict[str, Any],
                                     underlying_metrics: Dict[str, Any],
                                     strike_level_metrics_summary: Dict[str, Any], # Potential summary, e.g. count of strikes meeting a criteria
                                     ticker_context: Dict[str, Any],
                                     current_time_dt: datetime,
                                     dynamic_thresholds: Dict) -> bool:
        '''Evaluates all conditions for a single regime definition.'''

        conditions_to_evaluate: List[Dict[str, Any]] = []
        min_conditions_to_activate = rules_for_regime.get("_min_conditions_to_activate", len(rules_for_regime)) # Default to all

        # Handle simple list of conditions or complex _any_of structure
        if "_any_of" in rules_for_regime:
            # For _any_of, if any sub-group of conditions is met, the regime rule is true.
            # This part requires careful implementation if _any_of contains groups of _all_of.
            # For now, assuming _any_of is a list of condition blocks, and any block being true makes it pass.
            # This simplified _any_of is more like an OR of condition blocks.
            # Proper _any_of with _min_conditions_to_activate on sub-groups is more complex.
            # For now, let's assume _any_of is a list of individual conditions, and min_conditions_to_activate applies to them.
            # Or, more simply, if _any_of exists, it means any single condition in that list being true is enough.

            # A more robust _any_of would be a list of rule-blocks.
            # This simplified version: if _any_of is present, any condition within it makes the regime true.
            # This might not be the v2.4 intent.
            # Let's assume rules_for_regime contains conditions directly, or under an _all_of key by default.
            pass # Deferring full _any_of / _all_of for now, assuming flat list of conditions.


        num_conditions_met = 0
        num_conditions_total = 0

        for condition_key_full, condition_target_value in rules_for_regime.items():
            if condition_key_full.startswith("_"): continue # Skip special keys like _min_conditions_to_activate, _any_of

            num_conditions_total += 1
            metric_name_in_key = condition_key_full.split("_")[0] # e.g., "GIB.OI.based.Und_lt" -> "GIB.OI.based.Und"
            # This parsing of metric_name_in_key needs to be robust if metric names have underscores.
            # A better way is to have config define "metric_name" and "condition_operator" separately.
            # For now, assume metric name is before the last underscore of the operator.

            # Determine where to get the metric_value from (underlying, strike summary, ticker_context, time)
            actual_metric_value: Any = None
            source_found = False

            if metric_name_in_key.lower() == "current_time": # Special time condition
                # Example: "current_time_gt": "10:00:00"
                try:
                    target_time_obj = datetime.strptime(str(condition_target_value), "%H:%M:%S").time()
                    actual_metric_value = current_time_dt.time() # Compare time objects
                    source_found = True
                except ValueError:
                    self.logger.warning(f"Invalid time format for 'current_time' condition: {condition_target_value}")
                    continue
            elif metric_name_in_key in underlying_metrics:
                actual_metric_value = underlying_metrics[metric_name_in_key]
                source_found = True
            elif metric_name_in_key in strike_level_metrics_summary: # If we pass summaries
                actual_metric_value = strike_level_metrics_summary[metric_name_in_key]
                source_found = True
            elif metric_name_in_key in ticker_context: # For flags like "is_0DTE"
                actual_metric_value = ticker_context[metric_name_in_key]
                source_found = True

            if not source_found:
                # self.logger.debug(f"Metric '{metric_name_in_key}' for regime rule not found in provided data sources.")
                continue # Condition cannot be met if metric not found

            if self._check_condition(actual_metric_value, condition_key_full, condition_target_value, dynamic_thresholds):
                num_conditions_met += 1
            # else:
                # self.logger.debug(f"Condition False: {condition_key_full} (Val: {actual_metric_value}) vs {condition_target_value}")


        if num_conditions_total == 0 and not rules_for_regime.get("_allow_empty_rules", False): # If no conditions, it's not a valid rule unless specified
            return False
        if num_conditions_total == 0 and rules_for_regime.get("_allow_empty_rules", False): # If empty rules allowed, it's true by default
            return True

        return num_conditions_met >= min_conditions_to_activate


    def determine_market_regime_v2_5(self,
                                     underlying_data_enriched_obj: Dict[str, Any],
                                     # df_strike_level_metrics: pd.DataFrame, # Full strike DF might be too much here
                                     # For MRE, we might pass a summary of strike data or key strike values
                                     strike_level_metrics_summary: Optional[Dict[str, Any]], # Placeholder for aggregated strike insights
                                     current_processing_datetime: datetime,
                                     resolved_dynamic_thresholds: Dict[str, Any], # Pre-calculated by Orchestrator
                                     ticker_context_dict: Dict[str, Any] # From TickerContextAnalyzerV2_5
                                     ) -> str:
        '''
        Determines the market regime based on v2.5 metrics, context, and dynamic thresholds.
        '''
        symbol = underlying_data_enriched_obj.get(self.config_manager.get_setting("column_name_mappings", "underlying_fields", "symbol_col", default_value_to_return="symbol"), "UNKNOWN")
        self.logger.info(f"Determining Market Regime for {symbol} at {current_processing_datetime.isoformat()}...")

        # Fetch symbol-specific or DEFAULT MRE settings
        # These paths need to be accurate for config_v2_5.json
        mre_base_path_cfg = ["market_regime_engine_settings"]

        regime_evaluation_order: List[str] = self.config_manager.get_setting(
            *mre_base_path_cfg, "regime_evaluation_order",
            symbol_context=symbol, default_value_to_return=[]
        )
        all_regime_rules: Dict[str, Any] = self.config_manager.get_setting(
            *mre_base_path_cfg, "regime_rules",
            symbol_context=symbol, default_value_to_return={}
        )

        if not regime_evaluation_order or not all_regime_rules:
            self.logger.error(f"Market regime evaluation order or rules not found for symbol {symbol} (or DEFAULT). Returning default regime: {self.default_regime}")
            return self.default_regime

        # Prepare a flat dictionary of all available metrics/context for easy lookup
        # This should include underlying_data_enriched_obj, relevant parts of ticker_context_dict,
        # and any summaries from strike_level_metrics.

        # For now, primarily using underlying_data_enriched_obj and ticker_context_dict directly.
        # strike_level_metrics_summary is a placeholder for how strike data might be passed if needed.
        # E.g., count of strikes above/below a certain A-MSPI value, etc.
        if strike_level_metrics_summary is None:
            strike_level_metrics_summary = {}


        for regime_name in regime_evaluation_order:
            if regime_name not in all_regime_rules:
                self.logger.warning(f"Regime '{regime_name}' from evaluation order not found in rules definitions for {symbol}. Skipping.")
                continue

            rules_for_this_regime = all_regime_rules[regime_name]
            self.logger.debug(f"Evaluating regime: {regime_name} for {symbol}...")

            if self._evaluate_single_regime_rules(rules_for_this_regime,
                                                 underlying_data_enriched_obj,
                                                 strike_level_metrics_summary,
                                                 ticker_context_dict,
                                                 current_processing_datetime,
                                                 resolved_dynamic_thresholds):
                self.logger.info(f"Market Regime for {symbol} classified as: {regime_name}")
                return regime_name

        self.logger.info(f"No specific regime rules matched for {symbol}. Defaulting to: {self.default_regime}")
        return self.default_regime

    def shutdown(self):
        self.logger.info(f"MarketRegimeEngineV2_5 ({self.__class__.__name__}) shutdown called.")
