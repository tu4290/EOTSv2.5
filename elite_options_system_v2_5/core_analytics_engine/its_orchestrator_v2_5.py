# core_analytics_engine/its_orchestrator_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Union

import pandas as pd # type: ignore
# Assuming Pydantic models are accessible
try:
    from pydantic_models_v2_5 import (
        RawDataBundleV2_5, ProcessedDataBundleV2_5,
        TradeRecommendationV2_5, ATIFTradeIdeaDirectiveV2_5,
        KeyLevelV2_5, SignalPayloadV2_5, TickerContextOutputV2_5,
        UnderlyingDataEnrichedV2_5 # For type hinting the final bundle content
    )
    import pydantic_models_v2_5 as pdm # For isinstance checks
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # Fallback placeholders
    class RawDataBundleV2_5(dict): pass
    class ProcessedDataBundleV2_5(dict): pass # type: ignore
    class TradeRecommendationV2_5(dict): pass # type: ignore
    class ATIFTradeIdeaDirectiveV2_5(dict): pass # type: ignore
    class KeyLevelV2_5(dict): pass
    class SignalPayloadV2_5(dict): pass
    class TickerContextOutputV2_5(dict): pass # type: ignore
    class UnderlyingDataEnrichedV2_5(dict): pass # type: ignore
    logger_pydantic_fallback = logging.getLogger(__name__)
    logger_pydantic_fallback.warning("Orchestrator: Pydantic models not found, using dict placeholders. Data integrity checks will be limited.")


# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class ITSOrchestratorV2_5:
    '''
    Main operational controller for the EOTS V2.5 system.
    Manages the entire analysis cycle, component interactions,
    stateful recommendation management, and data bundle preparation.
    '''

    def __init__(self,
                 config_manager_v2_5: Any,
                 convex_value_fetcher_v2_5: Any,
                 tradier_fetcher_v2_5: Any,
                 initial_processor_v2_5: Any, # Contains MetricsCalculatorV2_5
                 historical_data_manager_v2_5: Any,
                 performance_tracker_v2_5: Any,
                 ticker_context_analyzer_v2_5: Any,
                 market_regime_engine_v2_5: Any,
                 key_level_identifier_v2_5: Any,
                 signal_generator_v2_5: Any,
                 adaptive_trade_idea_framework_v2_5: Any,
                 trade_parameter_optimizer_v2_5: Any
                ):
        self.logger = logger.getChild(self.__class__.__name__)
        self.logger.info(f"Initializing ITSOrchestratorV2_5...")

        self.config_manager = config_manager_v2_5
        self.cv_fetcher = convex_value_fetcher_v2_5
        self.tradier_fetcher = tradier_fetcher_v2_5
        self.initial_processor = initial_processor_v2_5 # This has the metrics_calculator
        self.historical_data_mgr = historical_data_manager_v2_5
        self.performance_tracker = performance_tracker_v2_5
        self.ticker_context_analyzer = ticker_context_analyzer_v2_5
        self.market_regime_engine = market_regime_engine_v2_5
        self.key_level_identifier = key_level_identifier_v2_5
        self.signal_generator = signal_generator_v2_5
        self.atif = adaptive_trade_idea_framework_v2_5
        self.tpo = trade_parameter_optimizer_v2_5

        self._active_recommendations: Dict[str, List[TradeRecommendationV2_5]] = {} # Symbol -> List of Recos
        self._resolved_dynamic_thresholds_cache: Dict[str, Any] = {} # Cache for current cycle per symbol

        self._load_config_settings()
        self.logger.info("ITSOrchestratorV2_5 Initialized with all component instances.")

    def _load_config_settings(self):
        '''Loads settings specific to the Orchestrator.'''
        self.logger.debug("Loading Orchestrator specific configurations...")
        # Example: Default DTEs/Range for fetchers if not overridden by user input
        fetch_cfg_path = ["data_fetcher_settings", "default_fetch_params"] # Example path
        self.default_fetch_dte_list: List[int] = self.config_manager.get_setting(*fetch_cfg_path, "default_dte_list", default_value_to_return=[0,1,7,14,30])
        self.default_fetch_price_range_pct: float = float(self.config_manager.get_setting(*fetch_cfg_path, "default_price_range_pct", default_value_to_return=10.0))

        # Dynamic threshold configuration
        self.metrics_for_dyn_thresh_tracking: List[str] = self.config_manager.get_setting(
            "system_settings", "metrics_for_dynamic_threshold_distribution_tracking", default_value_to_return=[]
        )
        self.dyn_thresh_history_days: int = int(self.config_manager.get_setting(
            "system_settings", "dynamic_threshold_history_days", default_value_to_return=60
        ))
        self.dyn_thresh_min_data_points: int = int(self.config_manager.get_setting(
            "system_settings", "min_days_for_dynamic_threshold_activation", default_value_to_return=20 # From HDM config
        ))
        # Definitions of how to calculate dynamic thresholds (e.g., "gib_extreme_neg_thresh_spy": {"metric": "GIB_OI_based_Und", "percentile": 10})
        # This would be a more complex structure in config.
        self.dynamic_threshold_definitions: Dict[str, Dict[str,Any]] = self.config_manager.get_setting(
            "market_regime_engine_settings", "dynamic_threshold_definitions", # Example path
            symbol_context=None, # These are general definitions
            default_value_to_return={}
        )


    def _fetch_raw_data_for_symbol(self, symbol: str, current_datetime_utc: datetime, user_fetch_params: Optional[Dict] = None) -> RawDataBundleV2_5:
        '''Fetches raw data from ConvexValue and Tradier, combines them.'''
        self.logger.info(f"Orchestrator: Fetching raw data for {symbol}...")
        user_fetch_params = user_fetch_params or {}
        dte_list = user_fetch_params.get("dte_list", self.default_fetch_dte_list)
        price_range_pct = user_fetch_params.get("price_range_pct", self.default_fetch_price_range_pct)

        # 1. Fetch ConvexValue Data
        # The fetch_market_data_bundle_cv returns a dict keyed by symbol.
        cv_bundle_dict = self.cv_fetcher.fetch_market_data_bundle_cv(
            symbols=[symbol], dte_list_override=dte_list, price_range_pct_override=price_range_pct
        )
        cv_data_for_symbol = cv_bundle_dict.get(symbol, {})
        raw_options_df_cv = cv_data_for_symbol.get("options_chain_df_raw_cv", pd.DataFrame())
        underlying_data_raw_cv = cv_data_for_symbol.get("underlying_data_raw_cv", {"symbol": symbol}) # Ensure symbol key
        error_cv = cv_data_for_symbol.get("error_details_cv")

        # 2. Fetch Tradier Data (e.g., current quote for OHLCV snapshot, IV approximations)
        # This data will enrich/override parts of underlying_data_raw_cv
        # For simplicity, assume underlying_data_raw_cv will be the base and we add to it.
        # A more robust way is to define a Pydantic model for the combined underlying data.

        raw_underlying_dict_combined = underlying_data_raw_cv.copy() # Start with CV data
        raw_underlying_dict_combined["fetch_timestamp_payload_cv"] = underlying_data_raw_cv.get("fetch_timestamp_payload_cv")
        error_tradier = None

        try:
            tradier_quote = self.tradier_fetcher.get_underlying_quote(symbol)
            if tradier_quote and not tradier_quote.get("error"):
                raw_underlying_dict_combined["fetch_timestamp_payload_tradier"] = datetime.now().isoformat() # Add Tradier fetch time
                # Selectively update/add fields from Tradier to the combined dict
                # Prioritize more real-time values from Tradier if available (e.g. 'last' price)
                if tradier_quote.get("last") is not None: raw_underlying_dict_combined["price"] = tradier_quote["last"] # Override CV price if Tradier has live last
                raw_underlying_dict_combined["tradier_open"] = tradier_quote.get("open")
                raw_underlying_dict_combined["tradier_high"] = tradier_quote.get("high")
                raw_underlying_dict_combined["tradier_low"] = tradier_quote.get("low")
                raw_underlying_dict_combined["tradier_close"] = tradier_quote.get("close") # This is 'last' during market hours
                raw_underlying_dict_combined["tradier_prev_close"] = tradier_quote.get("prevclose")
                raw_underlying_dict_combined["tradier_volume"] = tradier_quote.get("volume")
                # Add other fields as needed by v2.5 logic (e.g. specific IV from Tradier)
                # Example: Fetch and add IV5 approximation
                # iv_approx = self.tradier_fetcher.get_iv_approximation(symbol, target_dte=5) # Configurable DTE
                # if iv_approx and iv_approx.get("iv5_approx_smv_avg") is not None:
                #    raw_underlying_dict_combined["tradier_iv5_approx_smv_avg"] = iv_approx["iv5_approx_smv_avg"]
            elif tradier_quote and tradier_quote.get("error"):
                error_tradier = f"Tradier quote error: {tradier_quote.get('error')}"
                self.logger.warning(f"Tradier fetch error for {symbol}: {error_tradier}")
        except Exception as e_trad_fetch:
            error_tradier = f"Exception fetching Tradier data for {symbol}: {str(e_trad_fetch)}"
            self.logger.error(error_tradier, exc_info=True)

        # Package into RawDataBundleV2_5 (or dict if Pydantic fails)
        # Convert DataFrame to list of dicts for Pydantic model
        raw_options_data_list_of_dicts = raw_options_df_cv.to_dict(orient='records') if not raw_options_df_cv.empty else []

        bundle_payload = {
            "symbol": symbol,
            "raw_options_df_data": raw_options_data_list_of_dicts,
            "raw_underlying_dict_combined_data": raw_underlying_dict_combined,
            "fetch_timestamp_bundle_master": current_datetime_utc, # Overall bundle time
            "error_details_cv": error_cv,
            "error_details_tradier": error_tradier
        }
        if PYDANTIC_AVAILABLE:
            return RawDataBundleV2_5(**bundle_payload)
        return bundle_payload # type: ignore


    def _resolve_all_dynamic_thresholds_for_cycle(self, symbol:str, current_datetime_utc: datetime) -> Dict[str, Any]:
        '''Calculates all configured dynamic thresholds for the current symbol and cycle.'''
        self.logger.debug(f"Orchestrator: Resolving dynamic thresholds for {symbol}...")
        resolved_thresholds: Dict[str, Any] = {}

        # Get symbol-specific dynamic threshold definitions, fallback to general if any
        # This part needs robust config structure for dynamic threshold definitions.
        # Example: {"threshold_name": {"metric_key": "GIB_OI_based_Und", "percentile": 10, "days": 60}, ...}

        # For each defined dynamic threshold in self.dynamic_threshold_definitions:
        for thresh_name, defn in self.dynamic_threshold_definitions.items():
            metric_key_to_query = defn.get("metric_key")
            days_hist = int(defn.get("days", self.dyn_thresh_history_days))
            calc_type = defn.get("calculation_type", "percentile") # e.g., percentile, mean_std_factor
            calc_param = defn.get("calculation_param") # e.g., 10 for 10th percentile, or [1.5] for 1.5 std devs

            if not metric_key_to_query or calc_param is None:
                self.logger.warning(f"Invalid definition for dynamic threshold '{thresh_name}'. Skipping.")
                continue

            hist_series = self.historical_data_mgr.get_metric_distribution_for_threshold(
                symbol=symbol, # Symbol specific history
                metric_key=metric_key_to_query,
                days_history=days_hist,
                current_trading_date=current_datetime_utc.date()
            )

            if hist_series.empty or len(hist_series) < self.dyn_thresh_min_data_points:
                self.logger.warning(f"Not enough historical data for metric '{metric_key_to_query}' for {symbol} to calculate dynamic threshold '{thresh_name}'. Need {self.dyn_thresh_min_data_points}, got {len(hist_series)}.")
                resolved_thresholds[thresh_name] = None # Mark as unresolvable
                continue

            try:
                if calc_type == "percentile":
                    resolved_thresholds[thresh_name] = np.percentile(hist_series, float(calc_param))
                elif calc_type == "mean_std_factor":
                    mean_val = hist_series.mean()
                    std_val = hist_series.std()
                    factor = float(calc_param[0]) if isinstance(calc_param, list) else float(calc_param)
                    resolved_thresholds[thresh_name] = mean_val + (factor * std_val)
                # ... add other calculation types ...
                else:
                    self.logger.warning(f"Unknown dynamic threshold calculation type '{calc_type}' for '{thresh_name}'.")
                    resolved_thresholds[thresh_name] = None
            except Exception as e_dyn_thresh:
                self.logger.error(f"Error calculating dynamic threshold '{thresh_name}' for {symbol}: {e_dyn_thresh}", exc_info=True)
                resolved_thresholds[thresh_name] = None

        self.logger.info(f"Orchestrator: Resolved {len(resolved_thresholds)} dynamic thresholds for {symbol}.")
        self._resolved_dynamic_thresholds_cache[symbol] = resolved_thresholds # Cache for this cycle
        return resolved_thresholds


    def _manage_active_recommendations(self, symbol:str, current_full_market_data_bundle_dict: Dict, ticker_context: TickerContextOutputV2_5) -> List[TradeRecommendationV2_5]:
        '''Manages active recommendations: checks for exits, adjustments using ATIF directives.'''
        self.logger.debug(f"Orchestrator: Managing active recommendations for {symbol}...")
        active_recos_for_symbol = self._active_recommendations.get(symbol, [])
        updated_recos_for_symbol: List[TradeRecommendationV2_5] = []

        for reco_pydantic_model in active_recos_for_symbol:
            # Convert Pydantic model to dict if ATIF expects dict, or ensure ATIF handles Pydantic
            reco_dict = reco_pydantic_model.model_dump(by_alias=False) if PYDANTIC_AVAILABLE and isinstance(reco_pydantic_model, pdm.EOTSBaseModel) else reco_pydantic_model # type: ignore

            management_directive = self.atif.get_management_directives_for_active_recommendation(
                active_recommendation_payload=reco_dict, # Pass as dict
                current_full_market_data_bundle=current_full_market_data_bundle_dict, # Pass full bundle for context
                ticker_context_dict=ticker_context.model_dump(by_alias=False) if PYDANTIC_AVAILABLE and isinstance(ticker_context, pdm.EOTSBaseModel) else ticker_context # type: ignore
            )

            if management_directive:
                action = management_directive.get("action")
                self.logger.info(f"ATIF Management Directive for Reco ID {reco_dict.get('recommendation_id')}: {action} - Reason: {management_directive.get('reason')}")
                if action == "EXIT":
                    reco_dict["status"] = f"EXITED_ATIF_{management_directive.get('reason','MANUAL')[:15]}"
                    reco_dict["exit_timestamp_actual"] = datetime.now().isoformat() # Actual execution time would be different
                    # TODO: Calculate PnL (needs fill price if simulated)
                    self.performance_tracker.record_recommendation_outcome(reco_dict) # Record outcome
                    # Do not add to updated_recos_for_symbol as it's closed
                    continue
                elif action == "ADJUST_STOPLOSS":
                    reco_dict["current_stop_loss_underlying"] = management_directive.get("new_stop_loss")
                    reco_dict["status_update_reason"] = management_directive.get("reason")
                    reco_dict["status"] = "ACTIVE_SL_ADJUSTED"
                # ... handle other directives like ADJUST_TARGET, PARTIAL_PROFIT_TAKE ...

            # Re-create Pydantic model if it was converted, or update if mutable
            if PYDANTIC_AVAILABLE:
                try: updated_recos_for_symbol.append(TradeRecommendationV2_5(**reco_dict))
                except Exception as e_reco_recreate: self.logger.error(f"Error re-creating TradeRecommendationV2_5 model: {e_reco_recreate}")
            else: # type: ignore
                updated_recos_for_symbol.append(reco_dict) # type: ignore

        self._active_recommendations[symbol] = updated_recos_for_symbol
        return updated_recos_for_symbol


    def run_analysis_cycle_v2_5(self, symbol: str, current_datetime_utc: datetime,
                                user_fetch_params: Optional[Dict] = None
                               ) -> Dict[str, Any]: # Returns the final_analysis_bundle (as dict)
        '''Main orchestration method for a single analysis cycle for a symbol.'''
        self.logger.info(f"===== EOTS V2.5 Orchestrator: START Analysis Cycle for {symbol} at {current_datetime_utc.isoformat()} =====")

        # 1. Fetch Raw Data (ConvexValue + Tradier)
        raw_data_bundle_obj = self._fetch_raw_data_for_symbol(symbol, current_datetime_utc, user_fetch_params)
        # Convert Pydantic to dict if necessary for InitialProcessor, or ensure InitialProcessor handles Pydantic
        raw_options_df = pd.DataFrame(raw_data_bundle_obj.get("raw_options_df_data", [])) # Assuming list of dicts
        raw_underlying_combined = raw_data_bundle_obj.get("raw_underlying_dict_combined_data", {"symbol": symbol})

        if raw_data_bundle_obj.get("error_details_cv") or raw_data_bundle_obj.get("error_details_tradier"):
            self.logger.error(f"Orchestrator: Errors during raw data fetching for {symbol}. CV: {raw_data_bundle_obj.get('error_details_cv')}, Tradier: {raw_data_bundle_obj.get('error_details_tradier')}")
            # Return an error bundle early if critical fetch error
            return {"symbol": symbol, "status": "ERROR_FETCH",
                    "error_message": f"CV: {raw_data_bundle_obj.get('error_details_cv')}; Tradier: {raw_data_bundle_obj.get('error_details_tradier')}",
                    "underlying_data_enriched_obj": UnderlyingDataEnrichedV2_5(symbol=symbol) if PYDANTIC_AVAILABLE else {"symbol":symbol} # type: ignore
                   }

        # 2. Initial Processing (includes Metrics Calculation via injected MetricsCalculatorV2_5)
        # InitialProcessor expects the MetricsCalculator instance to be passed to its __init__
        # The Orchestrator should have already initialized InitialProcessor with MetricsCalculator.
        processed_data_bundle_dict = self.initial_processor.process_raw_data_bundle_v2_5(
            raw_options_df, raw_underlying_combined, current_datetime_utc, symbol
        )
        # Extract components from processed_data_bundle_dict for subsequent steps
        # These are already DataFrames or Dicts as per InitialProcessor's output spec
        options_df_with_metrics = processed_data_bundle_dict.get("options_df_with_metrics_obj", pd.DataFrame())
        df_strike_level_metrics = processed_data_bundle_dict.get("df_strike_level_metrics_obj", pd.DataFrame())
        underlying_data_enriched = processed_data_bundle_dict.get("underlying_data_enriched_obj", {"symbol": symbol})

        if processed_data_bundle_dict.get("status", "").startswith("ERROR"):
            self.logger.error(f"Orchestrator: Errors during initial processing/metrics calculation for {symbol}: {processed_data_bundle_dict.get('error_message')}")
            # Return current bundle, it already contains error status
            return processed_data_bundle_dict

        current_price = underlying_data_enriched.get(self.config_manager.get_setting("column_name_mappings", "underlying_fields", "price_col", default_value_to_return="price"))
        if current_price is None: self.logger.error(f"CRITICAL: Current price not found in enriched underlying data for {symbol}. Subsequent steps may fail."); current_price = 0 # Avoid None error

        # 3. Ticker Context Analysis
        ticker_context_output = self.ticker_context_analyzer.determine_ticker_context(
            symbol, current_datetime_utc, underlying_data_enriched, options_df_with_metrics, self.historical_data_mgr
        )
        # Add to underlying_data_enriched (Pydantic model or dict)
        ticker_context_dict_for_bundle = ticker_context_output.model_dump(by_alias=False) if PYDANTIC_AVAILABLE and isinstance(ticker_context_output, pdm.EOTSBaseModel) else ticker_context_output # type: ignore
        underlying_data_enriched["ticker_context_dict_v2_5"] = ticker_context_dict_for_bundle


        # 4. Resolve Dynamic Thresholds (for MRE, SignalGen)
        resolved_dyn_thresholds = self._resolve_all_dynamic_thresholds_for_cycle(symbol, current_datetime_utc)
        underlying_data_enriched["resolved_dynamic_thresholds_applied_v2_5"] = resolved_dyn_thresholds # For reference/debug

        # 5. Market Regime Classification
        market_regime_str = self.market_regime_engine.determine_market_regime_v2_5(
            underlying_data_enriched, df_strike_level_metrics, current_datetime_utc,
            resolved_dyn_thresholds, ticker_context_dict_for_bundle
        )
        underlying_data_enriched["current_market_regime_v2_5"] = market_regime_str
        # Pass regime to metrics_calculator if it needs it for a second pass on adaptive metrics (advanced)
        # For now, assume TCA and MRE run after one full metrics calc.

        # 6. Key Level Identification
        key_levels_list_pydantic = self.key_level_identifier.identify_key_levels_v2_5(
            df_strike_level_metrics, underlying_data_enriched, float(current_price)
        )
        # Convert list of Pydantic KeyLevelV2_5 to list of dicts for bundle if not using Pydantic throughout
        key_levels_list_for_bundle = [kl.model_dump(by_alias=False) if PYDANTIC_AVAILABLE and isinstance(kl, pdm.EOTSBaseModel) else kl for kl in key_levels_list_pydantic] # type: ignore


        # 7. Signal Generation
        signals_output_dict_of_lists = self.signal_generator.generate_all_signals_v2_5(
            df_strike_level_metrics, underlying_data_enriched, market_regime_str,
            ticker_context_dict_for_bundle, resolved_dyn_thresholds, key_levels_list_pydantic # Pass Pydantic list here
        )
        # Convert list of Pydantic SignalPayloadV2_5 to list of dicts if needed for bundle
        signals_final_for_bundle: Dict[str, List[Any]] = {}
        for category, sig_list_pydantic in signals_output_dict_of_lists.items():
            signals_final_for_bundle[category] = [s.model_dump(by_alias=False) if PYDANTIC_AVAILABLE and isinstance(s, pdm.EOTSBaseModel) else s for s in sig_list_pydantic] # type: ignore


        # --- Manage Active Recommendations (before generating new ones for this cycle) ---
        # This needs the most current market data bundle (what we've built so far)
        temp_current_market_bundle_for_mgmt = {
            "symbol": symbol, "status": "MANAGEMENT_PHASE",
            "options_df_with_metrics_obj": options_df_with_metrics, # Pass as DF
            "df_strike_level_metrics_obj": df_strike_level_metrics, # Pass as DF
            "underlying_data_enriched_obj": underlying_data_enriched, # This is a dict
            "key_levels_data_v2_5": key_levels_list_for_bundle, # List of dicts
            "signals_output_v2_5": signals_final_for_bundle # Dict of lists of dicts
        }
        active_recos_after_mgmt = self._manage_active_recommendations(symbol, temp_current_market_bundle_for_mgmt, ticker_context_output) # type: ignore


        # --- ATIF - New Recommendation Formulation ---
        new_atif_trade_idea_directives: List[ATIFTradeIdeaDirectiveV2_5] = self.atif.generate_trade_recommendations_v2_5( # type: ignore
            symbol, signals_output_dict_of_lists, # Pass list of Pydantic SignalPayloads
            market_regime_str, ticker_context_dict_for_bundle,
            underlying_data_enriched, # Contains current price, ATR etc.
            # options_df_with_metrics, # Full chain for TPO's contract selection context
            key_levels_list_pydantic # Pass list of Pydantic KeyLevels
        )

        newly_parameterized_recos: List[TradeRecommendationV2_5] = []
        if new_atif_trade_idea_directives:
            for atif_directive_pydantic in new_atif_trade_idea_directives:
                final_reco_pydantic = self.tpo.optimize_and_select_contract_parameters(
                    atif_directive_pydantic, # Pass Pydantic ATIF directive
                    options_df_with_metrics, # Full chain for contract selection
                    underlying_data_enriched,
                    key_levels_list_pydantic # Pass Pydantic KeyLevels
                )
                if final_reco_pydantic:
                    newly_parameterized_recos.append(final_reco_pydantic)

        # Add newly parameterized recommendations to the active list for this symbol
        current_active_recos = self._active_recommendations.get(symbol, [])
        current_active_recos.extend(newly_parameterized_recos)
        self._active_recommendations[symbol] = current_active_recos

        # Convert final active recos to list of dicts for the bundle
        active_recos_for_bundle = [r.model_dump(by_alias=False) if PYDANTIC_AVAILABLE and isinstance(r, pdm.EOTSBaseModel) else r for r in self._active_recommendations.get(symbol, [])] # type: ignore


        # 8. Store Daily Aggregate Metrics (selected ones)
        # Example: self.historical_data_mgr.store_daily_metric_value(symbol, current_datetime_utc.date(), "GIB_OI_based_Und", underlying_data_enriched.get("GIB_OI_based_Und"))
        # ... store other key v2.5 metrics like VAPI_FA_ZScore_Und etc. ...
        # ... store market_regime_str ...
        # ... store key ticker_context flags ...

        # 9. Final Analysis Bundle Packaging
        final_analysis_bundle = {
            "symbol": symbol,
            "orchestration_timestamp_utc": current_datetime_utc.isoformat(),
            "status": processed_data_bundle_dict.get("status", "UNKNOWN_BUNDLE_STATUS"), # From InitialProcessor/MetricsCalc
            "error_message": processed_data_bundle_dict.get("error_message"), # From InitialProcessor/MetricsCalc

            # Key Dataframes (can be converted to list of dicts for JSON, or kept as DF for Dash if using specific Dash components)
            # For now, assume they are objects that Dash callbacks might handle or convert.
            "options_df_with_metrics_obj": options_df_with_metrics, # pd.DataFrame
            "df_strike_level_metrics_obj": df_strike_level_metrics, # pd.DataFrame

            # Enriched Underlying Data (already a dict, should be Pydantic model UnderlyingDataEnrichedV2_5 ideally)
            "underlying_data_enriched_obj": underlying_data_enriched,

            "key_levels_data_v2_5": key_levels_list_for_bundle, # List of dicts
            "signals_output_v2_5": signals_final_for_bundle,     # Dict of lists of dicts
            "active_recommendations_v2_5": active_recos_for_bundle # List of dicts
        }

        self.logger.info(f"===== EOTS V2.5 Orchestrator: END Analysis Cycle for {symbol}. Status: {final_analysis_bundle['status']} =====")
        return final_analysis_bundle

    def get_active_recommendations_for_symbol(self, symbol: str) -> List[TradeRecommendationV2_5]: # type: ignore
        '''Returns current active recommendations for a symbol.'''
        return self._active_recommendations.get(symbol, [])

    def shutdown(self):
        self.logger.info(f"ITSOrchestratorV2_5 ({self.__class__.__name__}) shutdown sequence started.")
        # Call shutdown on all managed components if they have one
        if hasattr(self.cv_fetcher, 'shutdown'): self.cv_fetcher.shutdown()
        if hasattr(self.tradier_fetcher, 'shutdown'): self.tradier_fetcher.shutdown()
        # InitialProcessor typically doesn't have state to save beyond what MetricsCalculator does
        if hasattr(self.initial_processor, 'shutdown'): self.initial_processor.shutdown() # If it had one
        if hasattr(self.historical_data_mgr, 'shutdown'): self.historical_data_mgr.shutdown()
        if hasattr(self.performance_tracker, 'shutdown'): self.performance_tracker.shutdown()
        if hasattr(self.ticker_context_analyzer, 'shutdown'): self.ticker_context_analyzer.shutdown()
        if hasattr(self.market_regime_engine, 'shutdown'): self.market_regime_engine.shutdown()
        if hasattr(self.key_level_identifier, 'shutdown'): self.key_level_identifier.shutdown()
        if hasattr(self.signal_generator, 'shutdown'): self.signal_generator.shutdown()
        if hasattr(self.atif, 'shutdown'): self.atif.shutdown()
        if hasattr(self.tpo, 'shutdown'): self.tpo.shutdown()
        self.logger.info("ITSOrchestratorV2_5 shutdown complete.")
