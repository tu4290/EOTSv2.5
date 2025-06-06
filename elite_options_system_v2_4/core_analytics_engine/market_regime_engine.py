# core_analytics_engine/market_regime_engine.py
# (Elite Version 2.4 - Co-Pilot - Canonical Market Regime Engine - Phase 6 Revamp)

# Standard Library Imports
import logging
import os
from typing import Dict, Any, Optional, List, Union, Callable, Tuple
from datetime import time, datetime, date
import math
import re # For parsing complex metric keys

# Third-Party Imports
import pandas as pd # type: ignore
import numpy as np # type: ignore

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

# --- Constants ---
EPSILON_MRE = 1e-9 # Epsilon specific to MRE to avoid collision if imported elsewhere

class MarketRegimeEngineV2_4_Superior:
    """
    Classifies the current market regime based on a wide array of input metrics
    and highly configurable, expressive rules. The output regime string is a
    critical input for subsequent system components in EOTS V2.4.
    """

    def __init__(self, config_manager_instance: Any): # Expecting a ConfigManager instance
        self.logger = logger.getChild(self.__class__.__name__)
        
        if not hasattr(config_manager_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager. Critical failure.")
            class DummyCM:
                def get_setting(self, *args, **kwargs): return kwargs.get('default_value_to_return') # Match expected param
            self.config_manager = DummyCM() # type: ignore
            self.initialization_failed = True
        else:
            self.config_manager = config_manager_instance
            self.initialization_failed = False
        
        self.logger.info(f"Initializing MarketRegimeEngineV2_4_Superior (ConfigManager Integrated, Phase 6)...")
        
        # --- CORRECTED CONFIG LOADING ---
        if self.initialization_failed:
            self.logger.error("MarketRegimeEngine: Initialization aborted due to invalid ConfigManager.")
            # Set defaults for critical attributes to prevent crashes if methods are somehow called
            self.regime_rules = {}
            self.default_regime = "REGIME_SYSTEM_ERROR_MRE_INIT_FAIL"
            self.regime_evaluation_order = []
            self.compiled_time_definitions = {}
            self.near_dte_threshold_days = 1
            return # Stop further initialization if ConfigManager is bad

        # Base path for all MRE settings in the config_v2_4.json
        mre_base_config_path = "market_regime_engine_settings"

        # Fetch each specific setting using ConfigManager.get_setting with the correct keyword
        self.regime_rules: Dict[str, Union[Dict[str, Any], List[Dict[str, Any]]]] = \
            self.config_manager.get_setting(
                [mre_base_config_path, "regime_rules"], 
                default_value_to_return={}
            )
        
        self.default_regime: str = \
            self.config_manager.get_setting(
                [mre_base_config_path, "default_regime"], 
                default_value_to_return="REGIME_UNCLEAR_LOW_CONVICTION"
            )
            
        # If regime_evaluation_order is not explicitly set, use the keys from regime_rules
        # This needs self.regime_rules to be loaded first.
        default_eval_order = list(self.regime_rules.keys()) if isinstance(self.regime_rules, dict) else []
        self.regime_evaluation_order: List[str] = \
            self.config_manager.get_setting(
                [mre_base_config_path, "regime_evaluation_order"], 
                default_value_to_return=default_eval_order
            )
            
        time_defs_from_config: Dict[str, str] = \
            self.config_manager.get_setting(
                [mre_base_config_path, "time_of_day_definitions"], 
                default_value_to_return={}
            )
        self.compiled_time_definitions: Dict[str, Optional[time]] = self._compile_time_definitions(time_defs_from_config)
            
        self.near_dte_threshold_days: int = \
            int(self.config_manager.get_setting(
                [mre_base_config_path, "near_dte_threshold_days"], 
                default_value_to_return=1 # Default from config example
            ))

        # Column names from strategy_settings needed for some selectors (e.g., @MAX_OI)
        s_cfg_base_path = "strategy_settings"
        self.strike_col_name: str = self.config_manager.get_setting(
            [s_cfg_base_path, "strike_col_name"], default_value_to_return="strike"
        )
        self.oi_col_name_for_selectors: str = self.config_manager.get_setting(
            [s_cfg_base_path, "oi_col_name"], default_value_to_return="oi"
        )
        self.gex_col_name_for_selectors: str = self.config_manager.get_setting(
            [s_cfg_base_path, "gamma_exposure_source_col"], default_value_to_return="gxoi"
        )
        self.nvp_col_name_for_selectors: str = "nvp_strike" # This is an output name, typically not configurable as input key
        
        # Conceptual names for call/put sums if selectors need them.
        # These are not directly fetched from config as they are conceptual targets for selector logic.
        self.call_oi_sum_col_conceptual: str = "call_oi_sum_strike" 
        self.put_oi_sum_col_conceptual: str = "put_oi_sum_strike"   
        self.call_gex_sum_col_conceptual: str = "call_gex_sum_strike" 
        self.put_gex_sum_col_conceptual: str = "put_gex_sum_strike"   

        self.logger.info(f"MarketRegimeEngineV2_4_Superior initialized. {len(self.regime_rules)} rules loaded. Default: '{self.default_regime}'.")
        if not self.regime_rules or not self.regime_evaluation_order:
            self.logger.warning("MarketRegimeEngine: No regime rules or evaluation order defined after init. Engine will likely always return default_regime.")
            # If these are critical and still empty, might set self.initialization_failed = True here too.
        
        # Per-cycle state, initialized here or in determine_market_regime
        self.current_processing_symbol: Optional[str] = None # Set by caller


    def _get_config_setting_mre(self, key_path: Union[str, List[str]], default_val_param: Any = None, quiet:bool=False) -> Any:
        """ Convenience wrapper for ConfigManager get_setting for MRE. """
        # This method ensures that when MRE itself wants a config value, it uses the correct parameter name
        # for the default value when calling the ConfigManager.
        return self.config_manager.get_setting(key_path, default_value_to_return=default_val_param, quiet=quiet)

    def _compile_time_definitions(self, time_defs_cfg: Dict[str, str]) -> Dict[str, Optional[time]]:
        compiled: Dict[str, Optional[time]] = {}
        if not isinstance(time_defs_cfg, dict):
            self.logger.error("MRE Config: 'time_of_day_definitions' is not a dictionary. Time conditions will fail.")
            return compiled
        for key, time_str_val in time_defs_cfg.items():
            if not isinstance(time_str_val, str):
                self.logger.error(f"MRE Config: Time string for '{key}' is not a string ('{time_str_val}'). Skipping.")
                compiled[key] = None; continue
            try:
                compiled[key] = time.fromisoformat(time_str_val) # Expects HH:MM:SS or HH:MM
            except ValueError:
                self.logger.error(f"MRE Config: Invalid time format for '{key}: {time_str_val}'. Expected HH:MM:SS. This definition will be unusable.")
                compiled[key] = None
        self.logger.debug(f"Compiled time definitions: {compiled}")
        return compiled

    def _get_metric_value_for_rule(self, metric_key_full: str, 
                                   und_data_aggregates: Dict[str, Any], 
                                   df_strike_level_metrics: Optional[pd.DataFrame],
                                   current_und_price: Optional[float]
                                   ) -> Any:
        """
        Retrieves a metric value. Handles complex keys with selectors (e.g., @ATM, [AGG=...]).
        """
        # Check for selectors first
        if '@' in metric_key_full or '[' in metric_key_full:
            if df_strike_level_metrics is None or df_strike_level_metrics.empty:
                self.logger.debug(f"MRE MetricValue: df_strike_level_metrics is None/empty for strike-specific key '{metric_key_full}'.")
                return None
            # Pass self.current_processing_symbol for logging within _get_strike_specific_metric_value
            return self._get_strike_specific_metric_value(metric_key_full, df_strike_level_metrics, current_und_price, self.current_processing_symbol)
        else: # Simple key from underlying aggregates
            return und_data_aggregates.get(metric_key_full)

    def _get_strike_specific_metric_value(self, metric_key_with_selector: str, 
                                          df_strike_level_metrics: pd.DataFrame, 
                                          current_und_price: Optional[float], 
                                          symbol_for_log: Optional[str]) -> Optional[Union[float, int, str, bool]]:
        mre_ssm_logger = self.logger.getChild(f"StrikeMetricResolver.{symbol_for_log or 'N/A'}")
        
        base_metric_name = metric_key_with_selector 
        selector_type: Optional[str] = None; selector_subtype: Optional[str] = None 
        agg_func: Optional[str] = None; percentile_val: Optional[float] = None

        match_selector = re.match(r"([a-zA-Z0-9_]+)@([A-Z_]+)(?:\.([A-Z]+))?", metric_key_with_selector) # Allows optional subtype like .CALL
        match_agg = re.match(r"([a-zA-Z0-9_]+)\[AGG=([a-zA-Z_]+)\]", metric_key_with_selector)
        match_percentile = re.match(r"([a-zA-Z0-9_]+)\[PERCENTILE=([\d\.]+)\]", metric_key_with_selector)

        if match_selector:
            base_metric_name = match_selector.group(1)
            selector_type = match_selector.group(2).upper()
            if match_selector.group(3): selector_subtype = match_selector.group(3).upper()
        elif match_agg:
            base_metric_name = match_agg.group(1); agg_func = match_agg.group(2).lower()
        elif match_percentile:
            base_metric_name = match_percentile.group(1)
            try: percentile_val = float(match_percentile.group(2))
            except ValueError: mre_ssm_logger.warning(f"Invalid percentile value in '{metric_key_with_selector}'."); return None
        
        if base_metric_name not in df_strike_level_metrics.columns:
            mre_ssm_logger.debug(f"Base metric '{base_metric_name}' (from key '{metric_key_with_selector}') not in df_strike_level_metrics columns: {df_strike_level_metrics.columns.tolist()}.")
            return None
        
        # Perform selection or aggregation
        if selector_type:
            if self.strike_col_name not in df_strike_level_metrics.columns:
                mre_ssm_logger.warning(f"Strike column '{self.strike_col_name}' not found for selector '{metric_key_with_selector}'."); return None

            temp_df_for_select = df_strike_level_metrics.copy() # Work on a copy
            temp_df_for_select[self.strike_col_name] = pd.to_numeric(temp_df_for_select[self.strike_col_name], errors='coerce')
            temp_df_for_select = temp_df_for_select.dropna(subset=[self.strike_col_name])
            if temp_df_for_select.empty: mre_ssm_logger.debug(f"No valid strikes after coercing for selector {selector_type}."); return None

            if selector_type == "ATM":
                if current_und_price is None or pd.isna(current_und_price): mre_ssm_logger.warning("Current und price None/NaN for @ATM."); return None
                try:
                    atm_idx = (temp_df_for_select[self.strike_col_name] - current_und_price).abs().idxmin()
                    return temp_df_for_select.loc[atm_idx, base_metric_name]
                except ValueError: mre_ssm_logger.warning("@ATM: Could not find ATM strike."); return None

            # For MAX_OI, MAX_GEX, etc.
            # Determine target column for max/min operation based on selector_type and selector_subtype
            col_to_evaluate_for_max: Optional[str] = None
            if selector_type == "MAX_OI":
                col_to_evaluate_for_max = self.call_oi_sum_col_conceptual if selector_subtype == "CALL" else \
                                         (self.put_oi_sum_col_conceptual if selector_subtype == "PUT" else self.oi_col_name_for_selectors)
            elif selector_type == "MAX_GEX":
                col_to_evaluate_for_max = self.call_gex_sum_col_conceptual if selector_subtype == "CALL" else \
                                         (self.put_gex_sum_col_conceptual if selector_subtype == "PUT" else self.gex_col_name_for_selectors)
            elif selector_type in ["MAX_NVP_SUPPORT", "MAX_NVP_RESISTANCE"]:
                col_to_evaluate_for_max = self.nvp_col_name_for_selectors # e.g., "nvp_strike"
            
            if not col_to_evaluate_for_max or col_to_evaluate_for_max not in temp_df_for_select.columns:
                mre_ssm_logger.warning(f"Target column '{col_to_evaluate_for_max}' for selector '{selector_type}{'.' + selector_subtype if selector_subtype else ''}' not found in strike data."); return None

            numeric_target_series = pd.to_numeric(temp_df_for_select[col_to_evaluate_for_max], errors='coerce')
            if numeric_target_series.notna().sum() == 0: mre_ssm_logger.debug(f"Target column '{col_to_evaluate_for_max}' for {selector_type} is all NaN or empty."); return None
            
            idx_selected: Any = None # Needs to be Any to accept potential index types from idxmax/idxmin
            if selector_type == "MAX_NVP_SUPPORT":
                positive_values = numeric_target_series[numeric_target_series > 0]
                if not positive_values.empty: idx_selected = positive_values.idxmax()
            elif selector_type == "MAX_NVP_RESISTANCE":
                negative_values = numeric_target_series[numeric_target_series < 0]
                if not negative_values.empty: idx_selected = negative_values.idxmin() # min for most negative (smallest value)
            elif selector_type in ["MAX_OI", "MAX_GEX"]: # These are typically positive magnitudes
                idx_selected = numeric_target_series.idxmax()
            
            if idx_selected is not None and pd.notna(idx_selected) and idx_selected in temp_df_for_select.index: # Check if idx is valid for loc
                return temp_df_for_select.loc[idx_selected, base_metric_name]
            else: mre_ssm_logger.debug(f"No valid strike found for {selector_type} (subtype: {selector_subtype}) using target column {col_to_evaluate_for_max}.")
            return None

        elif agg_func:
            series_to_agg = pd.to_numeric(df_strike_level_metrics[base_metric_name], errors='coerce').dropna()
            if series_to_agg.empty: mre_ssm_logger.debug(f"Series for AGG '{agg_func}' on '{base_metric_name}' is empty."); return None
            if agg_func == "mean": return series_to_agg.mean()
            if agg_func == "sum": return series_to_agg.sum()
            if agg_func == "std": return series_to_agg.std()
            if agg_func == "median": return series_to_agg.median()
            if agg_func == "max": return series_to_agg.max()
            if agg_func == "min": return series_to_agg.min()
            mre_ssm_logger.warning(f"Unknown aggregation func '{agg_func}' in '{metric_key_with_selector}'."); return None
        elif percentile_val is not None:
            series_to_pct = pd.to_numeric(df_strike_level_metrics[base_metric_name], errors='coerce').dropna()
            if series_to_pct.empty: mre_ssm_logger.debug(f"Series for PERCENTILE on '{base_metric_name}' is empty."); return None
            if 0 <= percentile_val <= 100: return np.percentile(series_to_pct, percentile_val)
            mre_ssm_logger.warning(f"Invalid percentile '{percentile_val}' in '{metric_key_with_selector}'."); return None
        
        mre_ssm_logger.warning(f"Could not resolve metric key '{metric_key_with_selector}' (fallthrough).")
        return None # Should not be reached if logic is exhaustive

    def _resolve_condition_value(self, condition_val_config: Any, metric_name_for_log: str,
                                 resolved_dynamic_thresholds_this_cycle: Dict[str, Any]
                                 ) -> Any:
        """Resolves condition value, using pre-resolved dynamic thresholds if key matches."""
        if isinstance(condition_val_config, str):
            if condition_val_config.startswith("config_threshold:"): # Dynamic threshold from strategy_settings.thresholds
                threshold_key = condition_val_config.split(":", 1)[1]
                if threshold_key in resolved_dynamic_thresholds_this_cycle:
                    resolved_val = resolved_dynamic_thresholds_this_cycle[threshold_key]
                    self.logger.debug(f"MRE Resolved dynamic threshold (from strategy_settings) '{threshold_key}' to {resolved_val} for '{metric_name_for_log}'")
                    return resolved_val
                else:
                    self.logger.warning(f"MRE Dynamic threshold key '{threshold_key}' (from strategy_settings) for '{metric_name_for_log}' not in resolved_dynamic_thresholds. Condition will fail.")
                    return None # This None will cause condition to fail
            elif condition_val_config.startswith("dynamic_threshold:"): # Dynamic threshold from MRE specific config
                threshold_key = condition_val_config.split(":", 1)[1]
                if threshold_key in resolved_dynamic_thresholds_this_cycle: # This dict should contain all resolved dynamic thresholds
                    resolved_val = resolved_dynamic_thresholds_this_cycle[threshold_key]
                    self.logger.debug(f"MRE Resolved dynamic threshold (from MRE settings) '{threshold_key}' to {resolved_val} for '{metric_name_for_log}'")
                    return resolved_val
                else:
                    self.logger.warning(f"MRE Dynamic threshold key '{threshold_key}' (from MRE settings) for '{metric_name_for_log}' not in resolved_dynamic_thresholds. Condition will fail.")
                    return None
        return condition_val_config # Static value (numeric, bool, or string)

    def _check_metric_condition(
        self, metric_value: Optional[Union[float, int, bool, str]], condition_op_suffix: str, 
        condition_val_resolved: Any, metric_name_for_log: str
    ) -> bool:
        if metric_value is None or pd.isna(metric_value): # Treat pandas NA as None
            # self.logger.debug(f"MRE Metric '{metric_name_for_log}' is None/NaN, condition '{condition_op_suffix}' check is False.")
            return False
        if condition_val_resolved is None: # If dynamic threshold failed to resolve or static val was None
            self.logger.debug(f"MRE Condition value for '{metric_name_for_log}' is None (e.g., failed dynamic resolve), condition '{condition_op_suffix}' check is False.")
            return False

        op_result = False
        try:
            # Handle boolean metric values directly
            if isinstance(metric_value, bool):
                condition_val_bool: Optional[bool] = None
                if isinstance(condition_val_resolved, bool):
                    condition_val_bool = condition_val_resolved
                elif isinstance(condition_val_resolved, str):
                    if condition_val_resolved.lower() == 'true': condition_val_bool = True
                    elif condition_val_resolved.lower() == 'false': condition_val_bool = False
                
                if condition_val_bool is None:
                    self.logger.warning(f"MRE: Cannot compare bool metric '{metric_name_for_log}' ({metric_value}) with non-bool/non-str_bool condition value '{condition_val_resolved}'."); return False

                if condition_op_suffix == "_eq": op_result = (metric_value == condition_val_bool)
                elif condition_op_suffix == "_ne": op_result = (metric_value != condition_val_bool)
                else: self.logger.warning(f"MRE: Unsupported op '{condition_op_suffix}' for bool metric '{metric_name_for_log}'."); return False
            
            # Handle string metric values directly
            elif isinstance(metric_value, str):
                condition_val_str = str(condition_val_resolved) # Ensure comparison is string to string
                metric_value_lower = metric_value.lower()
                condition_val_str_lower = condition_val_str.lower()
                
                if condition_op_suffix == "_eq": op_result = (metric_value_lower == condition_val_str_lower)
                elif condition_op_suffix == "_ne": op_result = (metric_value_lower != condition_val_str_lower)
                elif condition_op_suffix == "_in_list": # condition_val_resolved should be a list of strings
                    if isinstance(condition_val_resolved, list):
                        op_result = metric_value_lower in [str(v).lower() for v in condition_val_resolved]
                    else: self.logger.warning(f"MRE: '{condition_op_suffix}' expects list for condition value, got {type(condition_val_resolved)} for '{metric_name_for_log}'."); return False
                elif condition_op_suffix == "_not_in_list":
                    if isinstance(condition_val_resolved, list):
                        op_result = metric_value_lower not in [str(v).lower() for v in condition_val_resolved]
                    else: self.logger.warning(f"MRE: '{condition_op_suffix}' expects list for condition value, got {type(condition_val_resolved)} for '{metric_name_for_log}'."); return False
                else: self.logger.warning(f"MRE: Unsupported op '{condition_op_suffix}' for str metric '{metric_name_for_log}'."); return False

            # Handle numeric metric values (attempt float conversion)
            else:
                metric_val_num = float(metric_value)
                condition_val_num = float(condition_val_resolved)

                if condition_op_suffix == "_lt": op_result = metric_val_num < condition_val_num
                elif condition_op_suffix == "_le": op_result = metric_val_num <= condition_val_num
                elif condition_op_suffix == "_gt": op_result = metric_val_num > condition_val_num
                elif condition_op_suffix == "_ge": op_result = metric_val_num >= condition_val_num
                elif condition_op_suffix == "_eq": op_result = math.isclose(metric_val_num, condition_val_num, rel_tol=EPSILON_MRE, abs_tol=EPSILON_MRE)
                elif condition_op_suffix == "_ne": op_result = not math.isclose(metric_val_num, condition_val_num, rel_tol=EPSILON_MRE, abs_tol=EPSILON_MRE)
                elif condition_op_suffix == "_abs_gt": op_result = abs(metric_val_num) > condition_val_num # condition_val_num is the threshold for abs value
                elif condition_op_suffix == "_abs_ge": op_result = abs(metric_val_num) >= condition_val_num
                elif condition_op_suffix == "_abs_lt": op_result = abs(metric_val_num) < condition_val_num
                elif condition_op_suffix == "_abs_le": op_result = abs(metric_val_num) <= condition_val_num
                else: self.logger.warning(f"MRE: Unknown numeric op '{condition_op_suffix}' for '{metric_name_for_log}'."); return False
        
        except (ValueError, TypeError) as e_type_comp:
            self.logger.warning(f"MRE: Type error during condition check for '{metric_name_for_log}' (Val:{metric_value}, Type:{type(metric_value).__name__}) "
                                f"vs condition_val '{condition_val_resolved}' (Type:{type(condition_val_resolved).__name__}) with op '{condition_op_suffix}': {e_type_comp}. Condition fails.")
            return False
        
        return op_result

    def _check_time_condition(self, condition_key_full_time: str, current_time_dt_obj: datetime) -> bool:
        current_market_time_obj = current_time_dt_obj.time()
        # Key mapping for time definitions from config (self.compiled_time_definitions)
        time_condition_map = { 
            "Time_is_final_hour_eq": ("final_hour_start_time", None), # >= start
            "Time_is_morning_session_eq": ("morning_start_time", "morning_end_time"), # >= start AND < end
            "Time_is_midday_session_eq": ("midday_start_time", "midday_end_time"), # >= start AND < end
            "Time_is_afternoon_session_eq": ("afternoon_start_time", "final_hour_start_time"), # >= start AND < end (assuming final_hour_start is effectively afternoon end)
            "Time_after_eod_pressure_calc_time_eq": ("eod_pressure_calc_time", None) # >= calc_time
            # Add more specific time conditions as needed, e.g., Time_before_midday_start_eq
        }

        if condition_key_full_time not in time_condition_map:
            self.logger.warning(f"MRE TimeCond: Unknown key '{condition_key_full_time}'."); return False

        mapped_keys = time_condition_map[condition_key_full_time]
        
        start_time_key: Optional[str] = None
        end_time_key: Optional[str] = None

        if isinstance(mapped_keys, tuple):
            start_time_key, end_time_key = mapped_keys
        else: # Single key implies a "greater than or equal to" check
            start_time_key = mapped_keys

        t_start: Optional[time] = self.compiled_time_definitions.get(start_time_key) if start_time_key else None
        t_end: Optional[time] = self.compiled_time_definitions.get(end_time_key) if end_time_key else None

        if start_time_key and t_start is None:
            self.logger.debug(f"MRE TimeCond: Start time definition '{start_time_key}' for condition '{condition_key_full_time}' not found or invalid in config. Condition fails.")
            return False
        if end_time_key and t_end is None: # Only an error if end_time_key was specified (i.e., range check)
            self.logger.debug(f"MRE TimeCond: End time definition '{end_time_key}' for condition '{condition_key_full_time}' not found or invalid in config. Condition fails.")
            return False

        if t_start and t_end: # Range check: start <= current < end
            return t_start <= current_market_time_obj < t_end
        elif t_start: # Single point check: current >= start
            return current_market_time_obj >= t_start
        
        self.logger.warning(f"MRE TimeCond: Logic error for '{condition_key_full_time}'. Both start/end times were None after lookup."); return False


    def _check_dte_condition(self, condition_key_full_dte: str, current_processing_dte_val: Optional[int]) -> bool:
        if current_processing_dte_val is None or not isinstance(current_processing_dte_val, int): 
            # self.logger.debug(f"MRE DTECond: current_processing_dte_val ({current_processing_dte_val}) is None or not int for '{condition_key_full_dte}'.")
            return False # If DTE is not available, DTE-based conditions are false.
        
        if condition_key_full_dte == "is_near_dte_eq": 
            return 0 <= current_processing_dte_val <= self.near_dte_threshold_days
        if condition_key_full_dte == "is_0dte_eq": 
            return current_processing_dte_val == 0
        
        # Example for a specific DTE range, if needed in config like "is_dte_1_to_5_eq": true
        match_range = re.match(r"is_dte_(\d+)_to_(\d+)_eq", condition_key_full_dte)
        if match_range:
            try:
                dte_low = int(match_range.group(1))
                dte_high = int(match_range.group(2))
                return dte_low <= current_processing_dte_val <= dte_high
            except ValueError: pass # Fall through if parsing fails

        self.logger.warning(f"MRE DTECond: Unknown DTE condition key '{condition_key_full_dte}'."); return False


    def _evaluate_condition_group(self, condition_group_rules: Dict[str, Any],
                                 current_und_data_aggregates: Dict[str, Any],
                                 current_df_strike_level_metrics: Optional[pd.DataFrame],
                                 current_datetime_obj: datetime,
                                 current_underlying_price_val: Optional[float],
                                 current_symbol_for_log: Optional[str],
                                 current_regime_name_for_log: str,
                                 all_resolved_dynamic_thresholds: Dict[str,Any]
                                 ) -> Tuple[bool, List[str]]:
        group_eval_logger = self.logger.getChild(f"EvalGroup.{current_regime_name_for_log}")
        condition_eval_logs: List[str] = [] # To store individual condition results for this group

        min_conditions_needed = int(condition_group_rules.get("_min_conditions_to_activate", 0))
        relevant_metrics_for_min_check = condition_group_rules.get("_relevant_metrics_for_min_check", [])
        # If _relevant_metrics_for_min_check is empty, _min_conditions_to_activate applies to all non-special conditions in the group.
        # If _relevant_metrics_for_min_check is specified, _min_conditions_to_activate applies ONLY to those keys.

        any_of_groups_list = condition_group_rules.get("_any_of", []) # List of sub-dictionaries for OR logic

        # Primary conditions (those not starting with '_' and not part of a specific _relevant_metrics_for_min_check if that's active)
        primary_conditions_in_group = {
            k: v for k, v in condition_group_rules.items() 
            if not k.startswith("_") and (not relevant_metrics_for_min_check or k not in relevant_metrics_for_min_check)
        }
        
        # --- Step 1: Evaluate primary AND conditions ---
        all_primary_conditions_met_flag = True
        for cond_key, cond_value_config in primary_conditions_in_group.items():
            metric_name_part: Optional[str] = None; op_suffix: Optional[str] = None
            is_special_cond_type = False # For time, dte conditions

            possible_ops_list = ["_lt", "_le", "_gt", "_ge", "_eq", "_ne", "_abs_gt", "_abs_ge", "_abs_lt", "_abs_le", "_in_list", "_not_in_list"]
            op_found_in_key = False
            for op_s in sorted(possible_ops_list, key=len, reverse=True): # Check longer ops first
                if cond_key.endswith(op_s):
                    metric_name_part = cond_key[:-len(op_s)]; op_suffix = op_s; op_found_in_key = True; break
            
            if not op_found_in_key: # Not a metric_op_val rule, check for special conditions
                if cond_key.lower().startswith("time_") or cond_key.lower().startswith("is_"): # Time_is_final_hour_eq, is_0dte_eq
                    is_special_cond_type = True; metric_name_part = cond_key # Use full key as metric_name
                else:
                    group_eval_logger.warning(f"Could not parse operator from primary condition key '{cond_key}'. Condition fails.")
                    all_primary_conditions_met_flag = False; condition_eval_logs.append(f"ParseFail:'{cond_key}'->F"); break
            
            condition_result_this_iter = False
            if is_special_cond_type and metric_name_part:
                expected_bool_state = bool(str(cond_value_config).lower() == 'true')
                actual_bool_state = False
                if metric_name_part.lower().startswith("time_"):
                    actual_bool_state = self._check_time_condition(metric_name_part, current_datetime_obj)
                    condition_eval_logs.append(f"TimeCond:'{metric_name_part}'(Exp:{expected_bool_state}|Act:{actual_bool_state})->{actual_bool_state == expected_bool_state}")
                elif metric_name_part.lower().startswith("is_"): # DTE condition
                    # DTE context needs to be passed or available. Assume it's in und_data_aggregates
                    current_dte_for_eval = current_und_data_aggregates.get('current_processing_dte_context') # This key standardized in MRE input
                    actual_bool_state = self._check_dte_condition(metric_name_part, current_dte_for_eval)
                    condition_eval_logs.append(f"DTECond:'{metric_name_part}'(Exp:{expected_bool_state}|DTE:{current_dte_for_eval}|Act:{actual_bool_state})->{actual_bool_state == expected_bool_state}")
                condition_result_this_iter = (actual_bool_state == expected_bool_state)
            elif metric_name_part and op_suffix: # Standard metric condition
                metric_current_value = self._get_metric_value_for_rule(metric_name_part, current_und_data_aggregates, current_df_strike_level_metrics, current_underlying_price_val)
                resolved_condition_target_value = self._resolve_condition_value(cond_value_config, metric_name_part, all_resolved_dynamic_thresholds)
                
                if resolved_condition_target_value is None and isinstance(cond_value_config, str) and (cond_value_config.startswith("config_threshold:") or cond_value_config.startswith("dynamic_threshold:")):
                    condition_result_this_iter = False # Dynamic threshold resolution failed
                    condition_eval_logs.append(f"DynThreshFail:'{cond_value_config}' for '{metric_name_part}'->F")
                else:
                    condition_result_this_iter = self._check_metric_condition(metric_current_value, op_suffix, resolved_condition_target_value, metric_name_part)
                    metric_val_str_log = f"{metric_current_value:.4g}" if isinstance(metric_current_value, (float,int)) and pd.notna(metric_current_value) else str(metric_current_value)
                    cond_val_str_log = f"{resolved_condition_target_value:.4g}" if isinstance(resolved_condition_target_value, (float,int)) and pd.notna(resolved_condition_target_value) else str(resolved_condition_target_value)
                    condition_eval_logs.append(f"MetricCond:'{metric_name_part}{op_suffix}{cond_val_str_log}'(Val:{metric_val_str_log})->{condition_result_this_iter}")

            if not condition_result_this_iter: all_primary_conditions_met_flag = False; break
        
        if not all_primary_conditions_met_flag: return False, condition_eval_logs # Short-circuit if primary ANDs fail

        # --- Step 2: Evaluate _any_of conditions (OR logic) if present ---
        if any_of_groups_list:
            if not isinstance(any_of_groups_list, list): # Ensure it's a list of dicts
                group_eval_logger.warning(f"'_any_of' field is not a list for regime '{current_regime_name_for_log}'. Skipping _any_of.")
            else:
                any_one_subgroup_met = False
                any_of_sub_logs: List[str] = []
                for i, sub_group_dict_rules in enumerate(any_of_groups_list):
                    if not isinstance(sub_group_dict_rules, dict):
                        any_of_sub_logs.append(f"AnyOfGroup[{i}]_InvalidNotDict->F"); continue
                    
                    sub_group_result, sub_group_eval_log = self._evaluate_condition_group( # Recursive call
                        sub_group_dict_rules, current_und_data_aggregates, current_df_strike_level_metrics,
                        current_datetime_obj, current_underlying_price_val, current_symbol_for_log,
                        f"{current_regime_name_for_log}._any_of[{i}]", all_resolved_dynamic_thresholds
                    )
                    any_of_sub_logs.append(f"AnyOfGroup[{i}]:[{'; '.join(sub_group_eval_log)}]->{sub_group_result}")
                    if sub_group_result: any_one_subgroup_met = True; break # One OR group met is enough
                
                condition_eval_logs.extend(any_of_sub_logs)
                if not any_one_subgroup_met: return False, condition_eval_logs # All OR sub-groups failed

        # --- Step 3: Evaluate _min_conditions_in_group if specified ---
        if min_conditions_needed > 0 and isinstance(relevant_metrics_for_min_check, list) and relevant_metrics_for_min_check:
            conditions_met_in_min_group_count = 0
            min_group_sub_logs: List[str] = []
            
            for min_check_cond_key_full in relevant_metrics_for_min_check:
                if min_check_cond_key_full not in condition_group_rules:
                    min_group_sub_logs.append(f"MinCheckItemKeyMissing:'{min_check_cond_key_full}'->F"); continue

                min_check_cond_value_config = condition_group_rules[min_check_cond_key_full]
                # Evaluate this single condition from the _relevant_metrics_for_min_check list
                # Effectively, create a mini-group of one for evaluation
                mini_group_for_this_item = {min_check_cond_key_full: min_check_cond_value_config}
                
                item_met_result, item_eval_log = self._evaluate_condition_group( # Recursive call
                    mini_group_for_this_item, current_und_data_aggregates, current_df_strike_level_metrics,
                    current_datetime_obj, current_underlying_price_val, current_symbol_for_log,
                    f"{current_regime_name_for_log}._min_check_item({min_check_cond_key_full})", all_resolved_dynamic_thresholds
                )
                min_group_sub_logs.append(f"MinCheckItem:[{'; '.join(item_eval_log)}]->{item_met_result}")
                if item_met_result: conditions_met_in_min_group_count += 1
            
            condition_eval_logs.extend(min_group_sub_logs)
            min_group_check_passed = (conditions_met_in_min_group_count >= min_conditions_needed)
            condition_eval_logs.append(f"MinCondsCheck(Need:{min_conditions_needed}|Got:{conditions_met_in_min_group_count}|From:{len(relevant_metrics_for_min_check)} items)->{min_group_check_passed}")
            if not min_group_check_passed: return False, condition_eval_logs
        elif min_conditions_needed > 0 and (not isinstance(relevant_metrics_for_min_check, list) or not relevant_metrics_for_min_check) :
            # _min_conditions_to_activate applies to all primary_conditions_in_group if _relevant_metrics_for_min_check is empty
            # This logic path needs careful implementation if desired. For now, assume _relevant_metrics_for_min_check must be specified if min_conditions_needed > 0
            group_eval_logger.warning(f"Regime '{current_regime_name_for_log}': _min_conditions_to_activate is {min_conditions_needed} but _relevant_metrics_for_min_check is empty or invalid. Min check skipped.")


        return True, condition_eval_logs # All checks passed

    def _pre_resolve_all_dynamic_thresholds(self, current_trading_date: date, symbol_context: Optional[str]) -> Dict[str, Any]:
        """
        Pre-resolves all dynamic thresholds defined in config for the current cycle.
        This avoids repeatedly calling HistoricalDataManager for the same threshold within rule evaluations.
        Dynamic thresholds can be defined in strategy_settings.thresholds or MRE-specific settings.
        """
        resolved_thresholds: Dict[str, Any] = {}
        dynamic_thresh_logger = self.logger.getChild("DynamicThresholdResolver")

        # 1. Resolve from strategy_settings.thresholds
        strategy_thresholds_cfg = self._get_config_setting_mre("strategy_settings.thresholds", {})
        if isinstance(strategy_thresholds_cfg, dict):
            for thresh_key, thresh_def in strategy_thresholds_cfg.items():
                if isinstance(thresh_def, dict) and thresh_def.get("type") in ["relative_percentile", "relative_mean_factor"]:
                    history_key_for_metric = thresh_def.get("history_key")
                    if history_key_for_metric:
                        # Here, self._resolve_dynamic_threshold would be a conceptual helper method
                        # It encapsulates the logic to call HDM and calculate the value.
                        # For now, let's assume we have it, or this is where it's called.
                        # resolved_val = self.call_actual_dynamic_threshold_resolver_utility(...)
                        # This is where the utility function that uses self.historical_data_manager
                        # and the logic from your previous _resolve_dynamic_threshold would be called.
                        # For now, placeholder:
                        # resolved_thresholds[thresh_key] = self._get_some_dynamic_value(history_key_for_metric, thresh_def, current_trading_date, symbol_context)
                        # This logic is now part of _evaluate_condition_group's call to _resolve_condition_value
                        # So, this pre-resolution step is more about identifying which keys *are* dynamic.
                        # The actual resolution is deferred.
                        pass # Actual resolution happens in _resolve_condition_value
                    else:
                        dynamic_thresh_logger.warning(f"Dynamic threshold definition for '{thresh_key}' in strategy_settings is missing 'history_key'.")
        
        # 2. Resolve from market_regime_engine_settings.dynamic_threshold_references_for_mre
        mre_dyn_thresh_refs = self.mre_settings.get("dynamic_threshold_references_for_mre", {})
        if isinstance(mre_dyn_thresh_refs, dict):
            for new_var_name, metric_hist_ref_str in mre_dyn_thresh_refs.items():
                if isinstance(metric_hist_ref_str, str):
                    # Parse 'metric_key[OP=VAL]' e.g., 'GIB_OI_based_Und[PERCENTILE=10]'
                    match_dyn_ref = re.match(r"([a-zA-Z0-9_]+)\[([A-Z]+)=([\d\._A-Z]+)\]", metric_hist_ref_str) # Updated regex
                    if match_dyn_ref:
                        hist_metric_key = match_dyn_ref.group(1)
                        op_type = match_dyn_ref.group(2)
                        op_val_str = match_dyn_ref.group(3)
                        
                        # Construct a threshold_definition dict compatible with _resolve_dynamic_threshold
                        temp_thresh_def: Dict[str, Any] = {"history_key": hist_metric_key, "fallback_value": 0.0} # Add a sensible fallback
                        if op_type == "PERCENTILE":
                            temp_thresh_def["type"] = "relative_percentile"
                            try: temp_thresh_def["percentile"] = float(op_val_str)
                            except ValueError: dynamic_thresh_logger.warning(f"Invalid percentile value '{op_val_str}' in MRE dynamic ref '{new_var_name}'."); continue
                        elif op_type == "MEAN_FACTOR": # Needs refinement based on how factors are used
                            temp_thresh_def["type"] = "relative_mean_factor"
                            try: temp_thresh_def["factor"] = float(op_val_str)
                            except ValueError: dynamic_thresh_logger.warning(f"Invalid factor value '{op_val_str}' in MRE dynamic ref '{new_var_name}'."); continue
                        # Add more op_types if needed (e.g., STD_FACTOR)
                        else: dynamic_thresh_logger.warning(f"Unknown op_type '{op_type}' in MRE dynamic ref '{new_var_name}'."); continue
                        
                        # Placeholder: This is where the actual call to HDM via a resolver utility would happen
                        # For now, we mark it conceptually. This dict is used by _resolve_condition_value
                        # resolved_thresholds[new_var_name] = self.call_actual_dynamic_threshold_resolver_utility(...)
                        # For now, this pre-resolution step is conceptual. The actual values are resolved
                        # JIT by _resolve_condition_value using this structure.
                        # Store the definition for later resolution.
                        resolved_thresholds[new_var_name] = temp_thresh_def # Store the definition itself for JIT resolution
                    else:
                        dynamic_thresh_logger.warning(f"Could not parse MRE dynamic threshold reference: '{metric_hist_ref_str}' for var '{new_var_name}'.")

        dynamic_thresh_logger.debug(f"Pre-identified dynamic threshold definitions for MRE cycle: {list(resolved_thresholds.keys())}")
        return resolved_thresholds # This dict contains *definitions* to be resolved JIT


    def determine_market_regime_v2_4(
        self,
        und_data_aggregates: Dict[str, Any],
        df_strike_level_metrics: Optional[pd.DataFrame],
        current_time_dt: datetime,
        resolved_dynamic_thresholds_from_orchestrator: Dict[str, Any], # Moved before optional args
        symbol_context: Optional[str] = None                         # Now optional arg is last
    ) -> str:
        mre_main_logger = self.logger.getChild(f"DetermineRegime.{symbol_context or 'GENERAL'}")
        
        if self.initialization_failed:
            error_regime_to_return = getattr(self, 'default_regime', "REGIME_SYSTEM_ERROR_MRE_INIT_FAIL_ATTR")
            if not isinstance(error_regime_to_return, str) or not error_regime_to_return:
                 error_regime_to_return = "REGIME_SYSTEM_ERROR_MRE_INIT_FAIL_TYPE"
            mre_main_logger.error(f"MarketRegimeEngine initialization failed previously. Returning default: {error_regime_to_return}")
            return error_regime_to_return

        current_und_price_val: Optional[float] = None
        current_processing_dte: Optional[int] = None

        if isinstance(und_data_aggregates, dict):
            # Use _get_config_setting_mre for consistency within this class
            price_key_from_cfg = self._get_config_setting_mre(["strategy_settings", "underlying_price_col_name"], "price")
            raw_price = und_data_aggregates.get(price_key_from_cfg)
            if raw_price is not None:
                try: current_und_price_val = float(raw_price)
                except (ValueError, TypeError): mre_main_logger.warning(f"MRE: Could not convert und_price '{raw_price}' to float.")
            
            current_processing_dte = und_data_aggregates.get('current_processing_dte_context')
            if current_processing_dte is not None and not isinstance(current_processing_dte, int):
                 try: current_processing_dte = int(current_processing_dte)
                 except: current_processing_dte = None; mre_main_logger.warning("Could not convert 'current_processing_dte_context' to int.")

        # Directly use the pre-resolved thresholds from the orchestrator
        # The call to self._pre_resolve_all_dynamic_thresholds is removed.
        all_resolved_dynamic_thresholds_for_eval = resolved_dynamic_thresholds_from_orchestrator

        for regime_name_ordered in self.regime_evaluation_order:
            if regime_name_ordered not in self.regime_rules: 
                mre_main_logger.debug(f"Regime '{regime_name_ordered}' from eval order not in regime_rules. Skipping.")
                continue
            
            current_ruleset_config = self.regime_rules[regime_name_ordered]
            regime_conditions_met = False
            eval_log_details_for_regime: List[str] = []

            if not current_ruleset_config: # Empty rule dict {} means true
                regime_conditions_met = True 
                eval_log_details_for_regime.append("EmptyRuleSet->True")
            elif isinstance(current_ruleset_config, dict): # Single group
                regime_conditions_met, group_log = self._evaluate_condition_group(
                    current_ruleset_config, und_data_aggregates, df_strike_level_metrics, 
                    current_time_dt, current_und_price_val, symbol_context, 
                    regime_name_ordered, 
                    all_resolved_dynamic_thresholds_for_eval # Pass the orchestrator-resolved thresholds
                )
                eval_log_details_for_regime.extend(group_log)
            elif isinstance(current_ruleset_config, list): # List of OR'd groups
                for i, or_condition_group in enumerate(current_ruleset_config):
                    if not isinstance(or_condition_group, dict):
                        mre_main_logger.warning(f"Regime '{regime_name_ordered}' OR_Group[{i}] is not a dict. Skipping."); continue
                    
                    group_met_this_or, group_log_this_or = self._evaluate_condition_group(
                        or_condition_group, und_data_aggregates, df_strike_level_metrics, 
                        current_time_dt, current_und_price_val, symbol_context,
                        f"{regime_name_ordered}.OR_Group[{i}]", 
                        all_resolved_dynamic_thresholds_for_eval # Pass the orchestrator-resolved thresholds
                    )
                    eval_log_details_for_regime.append(f"OR_Group[{i}]:[{';'.join(group_log_this_or)}]->{group_met_this_or}")
                    if group_met_this_or: regime_conditions_met = True; break 
            else: 
                mre_main_logger.error(f"Regime '{regime_name_ordered}' ruleset has invalid type: {type(current_ruleset_config)}. Skipping."); continue
            
            if eval_log_details_for_regime and mre_main_logger.getEffectiveLevel() <= logging.DEBUG:
                mre_main_logger.debug(f"Detailed Eval for Regime '{regime_name_ordered}': {'; '.join(eval_log_details_for_regime)}. Overall Met: {regime_conditions_met}")

            if regime_conditions_met: 
                mre_main_logger.info(f"MARKET REGIME CLASSIFIED for '{symbol_context or 'GENERAL'}': *** {regime_name_ordered} ***")
                return regime_name_ordered
        
        mre_main_logger.info(f"No specific regime conditions met for '{symbol_context or 'GENERAL'}'. Defaulting to: {self.default_regime}")
        return self.default_regime

# --- Main Test Block (Example Usage - Copied from your provided file, with minor adjustments) ---
if __name__ == '__main__': # pragma: no cover
    import sys 
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, 
                            format='[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S")
    
    main_test_logger = logging.getLogger(__name__)
    main_test_logger.info("MarketRegimeEngineV2_4_Superior - Standalone test execution started.")

    # Test ConfigManager (simplified mock for this test scope)
    class TestCMForMRE:
        _cfg: Dict[str, Any]
        def __init__(self, test_config_dict): self._cfg = test_config_dict
        def get_setting(self, key_path: Union[str, List[str]], default: Any = None, quiet: bool = False) -> Any:
            keys = key_path.split('.') if isinstance(key_path, str) else key_path; val = self._cfg
            try:
                for k in keys: val = val[k]
                return val if val is not None else default
            except KeyError: return default
            except TypeError: return default # If path tries to index a non-dict

    # Use the example config from your provided MRE file
    test_config_mre_dict = {
        "strategy_settings": { # Used for some column names like strike_col_name
            "strike_col_name": "strike", "option_kind_col_name": "opt_kind",
            "oi_col_name": "oi_total_strike", "gamma_exposure_source_col": "gex_total_strike",
            "call_oi_sum_strike_col_name": "call_oi_sum", "put_oi_sum_strike_col_name": "put_oi_sum",
             # Adding underlying_price_col_name mapping for MRE's _get_metric_value_for_rule
            "underlying_price_col_name": "price",
            "market_regime_engine_settings": { # Moved MRE settings under strategy_settings as per previous structure
                "default_regime": "REGIME_NEUTRAL_LOW_CONFIDENCE",
                "near_dte_threshold_days": 1, # Changed from 2 to 1 for more specific test
                "regime_evaluation_order": [
                    "REGIME_0DTE_PIN_RISK_HIGH_VCI", 
                    "REGIME_EXTREME_NEG_GIB_TRENDING_DOWN",
                    "REGIME_ATM_TDPI_SIGNIFICANT",
                    "REGIME_STRIKE_METRIC_PERCENTILE_EXAMPLE",
                    "REGIME_AGG_METRIC_EXAMPLE",
                    "REGIME_NEUTRAL_LOW_CONFIDENCE" # Ensure default can be hit
                ],
                "regime_rules": {
                    "REGIME_0DTE_PIN_RISK_HIGH_VCI": { "is_0dte_eq": True, "Time_is_final_hour_eq": True, "vci_0dte_agg_gt": "config_threshold:vci_pin_thresh" },
                    "REGIME_EXTREME_NEG_GIB_TRENDING_DOWN": { "_any_of": [
                        { "GIB_OI_based_Und_lt": "config_threshold:gib_extreme_neg_thresh", "NetValueFlow_30m_Und_lt": -100e6, "ARFI_Overall_Und_lt": 0.5 },
                        { "GIB_OI_based_Und_lt": "config_threshold:gib_very_neg_thresh", "NetValueFlow_60m_Und_lt": -200e6, "price_vs_vwap_pct_lt": -0.005 }
                    ]},
                    "REGIME_ATM_TDPI_SIGNIFICANT": { "tdpi@ATM_abs_gt": 500000 },
                    "REGIME_STRIKE_METRIC_PERCENTILE_EXAMPLE": { "mspi[PERCENTILE=95]_gt": 0.8 },
                    "REGIME_AGG_METRIC_EXAMPLE": { "sdag_multiplicative[AGG=mean]_lt": -0.1 },
                    "REGIME_NEUTRAL_LOW_CONFIDENCE": {} # Empty rule, always true if reached
                },
                "time_of_day_definitions": {
                    "morning_start_time": "09:30:00", "morning_end_time": "11:00:00", 
                    "midday_start_time": "11:00:01", "midday_end_time": "13:59:59", # Ensure no gap
                    "afternoon_start_time": "14:00:00", "final_hour_start_time":"15:00:00",
                    "eod_pressure_calc_time": "15:30:00", "market_close_time": "16:00:00"
                }
            }
        }
        # Minimal other settings MRE might touch (via _get_config_value_mre)
        # For this test, HDM not directly used by MRE, but by a utility that MRE would call
        # to resolve dynamic thresholds. We pass pre-resolved thresholds.
    }
    
    test_cm_mre = TestCMForMRE(test_config_dict=test_config_mre_dict)
    engine = MarketRegimeEngineV2_4_Superior(config_manager_instance=test_cm_mre)

    # --- Test Case Data ---
    mock_und_data_base = {
        "price": 4500.0,  # This is used for @ATM
        "GIB_OI_based_Und": -60e9, 
        "NetValueFlow_30m_Und": -150e6, 
        "ARFI_Overall_Und": 0.4, 
        "NetValueFlow_60m_Und": -100e6, 
        "price_vs_vwap_pct": 0.001,
        "current_processing_dte_context": 1, # General DTE context for this data snapshot
        "vci_0dte_agg": 0.2 
    }
    mock_df_strikes_base = pd.DataFrame({
        "strike": [4490.0, 4500.0, 4510.0, 4520.0, 4530.0], # Ensure float for ATM comparison
        "tdpi": [1e5, 6e5, 4e5, 2e5, 1e5], 
        "mspi": [0.1, 0.3, 0.85, 0.6, 0.2], 
        "sdag_multiplicative": [-0.05, -0.15, 0.0, 0.05, -0.08] 
    })
    # Pre-resolved dynamic thresholds (as if ITSOrchestrator prepared this)
    mock_resolved_thresholds_dict = {
        "vci_pin_thresh": 0.35,
        "gib_extreme_neg_thresh": -50e9,
        "gib_very_neg_thresh": -70e9 
        # Add more if your rules use more config_threshold keys
    }
    
    main_test_logger.info("\n--- MRE Test Cases ---")
    # Test 1: REGIME_EXTREME_NEG_GIB_TRENDING_DOWN (via first OR group)
    test_time1 = datetime(2023, 10, 27, 14, 0, 0) # Midday
    und_data_t1 = {**mock_und_data_base}
    regime1 = engine.determine_market_regime_v2_4(und_data_t1, mock_df_strikes_base, test_time1, "SPY_T1", mock_resolved_thresholds_dict)
    main_test_logger.info(f"Test 1 Result: {regime1} (Expected: REGIME_EXTREME_NEG_GIB_TRENDING_DOWN)")
    assert regime1 == "REGIME_EXTREME_NEG_GIB_TRENDING_DOWN"

    # Test 2: REGIME_0DTE_PIN_RISK_HIGH_VCI
    und_data_t2 = {**mock_und_data_base, "current_processing_dte_context": 0, "vci_0dte_agg": 0.40} # Make it 0DTE and VCI high
    test_time2 = datetime(2023, 10, 27, 15, 30, 0) # Final hour
    regime2 = engine.determine_market_regime_v2_4(und_data_t2, mock_df_strikes_base, test_time2, "SPY_T2", mock_resolved_thresholds_dict)
    main_test_logger.info(f"Test 2 Result: {regime2} (Expected: REGIME_0DTE_PIN_RISK_HIGH_VCI)")
    assert regime2 == "REGIME_0DTE_PIN_RISK_HIGH_VCI"
    
    # Test 3: REGIME_ATM_TDPI_SIGNIFICANT
    und_data_t3 = {**mock_und_data_base, "GIB_OI_based_Und": 0} # Make GIB rule fail
    test_time3 = datetime(2023, 10, 27, 11, 30, 0) # Not final hour
    regime3 = engine.determine_market_regime_v2_4(und_data_t3, mock_df_strikes_base, test_time3, "SPY_T3", mock_resolved_thresholds_dict)
    main_test_logger.info(f"Test 3 Result: {regime3} (Expected: REGIME_ATM_TDPI_SIGNIFICANT)")
    assert regime3 == "REGIME_ATM_TDPI_SIGNIFICANT"

    # Test 4: REGIME_STRIKE_METRIC_PERCENTILE_EXAMPLE
    df_strikes_t4 = mock_df_strikes_base.copy()
    df_strikes_t4.loc[df_strikes_t4['strike'] == 4500.0, 'tdpi'] = 10000 # Make ATM TDPI rule fail
    und_data_t4 = {**und_data_t3} # Inherits failed GIB
    regime4 = engine.determine_market_regime_v2_4(und_data_t4, df_strikes_t4, test_time3, "SPY_T4", mock_resolved_thresholds_dict)
    main_test_logger.info(f"Test 4 Result: {regime4} (Expected: REGIME_STRIKE_METRIC_PERCENTILE_EXAMPLE)")
    assert regime4 == "REGIME_STRIKE_METRIC_PERCENTILE_EXAMPLE"

    # Test 5: Fallback to default if all prior fail
    df_strikes_t5 = df_strikes_t4.copy()
    df_strikes_t5['mspi'] = 0.1 # Make percentile rule fail (95th percentile of 0.1 is 0.1, not > 0.8)
    # sdag_multiplicative mean is -0.046, rule "lt: -0.1" fails.
    und_data_t5 = {**und_data_t4}
    regime5 = engine.determine_market_regime_v2_4(und_data_t5, df_strikes_t5, test_time3, "SPY_T5", mock_resolved_thresholds_dict)
    main_test_logger.info(f"Test 5 Result: {regime5} (Expected: {engine.default_regime} as AGG and others fail)")
    assert regime5 == engine.default_regime # It should hit REGIME_NEUTRAL_LOW_CONFIDENCE as it has an empty rule {}

    # Test 6: Ensure REGIME_NEUTRAL_LOW_CONFIDENCE (empty rule set) is hit if others fail
    empty_rules_config = { # Config with only the default and an empty rule for neutral
         "strategy_settings": {
             "strike_col_name": "strike", "option_kind_col_name": "opt_kind", "underlying_price_col_name": "price",
            "market_regime_engine_settings": {
                "default_regime": "REGIME_ERROR_SHOULD_NOT_HIT_THIS",
                "regime_evaluation_order": ["REGIME_FAILING_RULE", "REGIME_NEUTRAL_TEST"],
                "regime_rules": {
                    "REGIME_FAILING_RULE": {"some_metric_gt": 99999999},
                    "REGIME_NEUTRAL_TEST": {} # Empty rule, should be true
                },
                "time_of_day_definitions": test_config_mre_dict["strategy_settings"]["market_regime_engine_settings"]["time_of_day_definitions"]
            }
        }
    }
    engine_empty_test = MarketRegimeEngineV2_4_Superior(config_manager_instance=TestCMForMRE(empty_rules_config))
    regime6 = engine_empty_test.determine_market_regime_v2_4(mock_und_data_base, mock_df_strikes_base, test_time1, "SPY_T6", {})
    main_test_logger.info(f"Test 6 Result: {regime6} (Expected: REGIME_NEUTRAL_TEST due to empty rule)")
    assert regime6 == "REGIME_NEUTRAL_TEST"


    main_test_logger.info("MarketRegimeEngineV2_4_Superior - Standalone tests finished.")