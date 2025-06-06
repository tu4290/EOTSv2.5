# data_management/initial_processor_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import pandas as pd # type: ignore
import numpy as np # type: ignore

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class InitialDataProcessorV2_5:
    '''
    Processes raw options chain and underlying data bundles for EOTS V2.5.
    1. Validates and prepares raw inputs from fetchers.
    2. Invokes MetricsCalculatorV2_5 for all detailed metric calculations. (Stubbed for now)
    3. Packages original prepared data and metric-rich outputs into a comprehensive bundle.
    '''

    def __init__(self,
                 config_manager_v2_5_instance: Any,
                 metrics_calculator_v2_5_instance: Any
                 ):
        self.logger = logger.getChild(self.__class__.__name__)
        self.initialization_failed = False

        if not hasattr(config_manager_v2_5_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5. Critical failure.")
            self.initialization_failed = True
            class DummyCM:
                def get_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    return default_value_to_return
                # Adding a dummy get_resolved_path_setting for completeness, though not directly used by this class from its dummy
                def get_resolved_path_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    return None # Or a sensible path-like string if needed for basic functionality
            self.config_manager = DummyCM() # type: ignore
        else:
            self.config_manager = config_manager_v2_5_instance

        self.logger.info(f"Initializing InitialDataProcessorV2_5...")

        if metrics_calculator_v2_5_instance is None or not hasattr(metrics_calculator_v2_5_instance, 'orchestrate_all_metric_calculations_v2_5'):
            self.logger.warning("MetricsCalculatorV2_5 instance or its method is not available. Operating in stubbed mode for metrics.")
            class DummyMetricsCalculator:
                def orchestrate_all_metric_calculations_v2_5(self, options_df_prepared, underlying_data_prepared, current_time_dt, symbol):
                    logger.warning("DummyMetricsCalculator: orchestrate_all_metric_calculations_v2_5 called (STUBBED).")
                    return options_df_prepared.copy() if options_df_prepared is not None else pd.DataFrame(),                            pd.DataFrame(),                            underlying_data_prepared.copy() if underlying_data_prepared is not None else {}
            self.metrics_calculator = DummyMetricsCalculator()
        else:
            self.metrics_calculator = metrics_calculator_v2_5_instance

        self._initialize_column_names_from_config_v2_5()

        self.logger.info("InitialDataProcessorV2_5 Initialized (MetricsCalculator may be stubbed).")


    def _initialize_column_names_from_config_v2_5(self) -> None:
        '''Initializes commonly used column names from the v2.5 config.'''
        input_chain_map_path = ["column_name_mappings", "input_chain_fields"]
        self.col_strike_cfg: str = self.config_manager.get_setting(*input_chain_map_path, "strike_col", default_value_to_return="strike")
        self.col_opt_kind_cfg: str = self.config_manager.get_setting(*input_chain_map_path, "option_kind_col", default_value_to_return="opt_kind")
        self.col_expiration_cfg: str = self.config_manager.get_setting(*input_chain_map_path, "expiration_col_raw", default_value_to_return="expiration_days_from_epoch_calc")
        self.col_multiplier_cfg: str = self.config_manager.get_setting(*input_chain_map_path, "multiplier_col", default_value_to_return="multiplier")
        self.default_multiplier_val: float = float(self.config_manager.get_setting("strategy_settings", "contract_multiplier_default_value", default_value_to_return=100.0))

        und_fields_map_path = ["column_name_mappings", "underlying_fields"]
        self.col_underlying_price_cfg: str = self.config_manager.get_setting(*und_fields_map_path, "price_col", default_value_to_return="price")
        self.col_und_symbol_cfg: str = self.config_manager.get_setting(*und_fields_map_path, "symbol_col", default_value_to_return="symbol")

        self.base_required_option_cols_from_fetcher: List[str] = list(set([
            self.col_strike_cfg, self.col_opt_kind_cfg, self.col_expiration_cfg, self.col_multiplier_cfg
        ] + self.config_manager.get_setting(*input_chain_map_path, "other_required_raw_cols", default_value_to_return=['oi', 'price', 'volatility'])))
        self.logger.debug(f"InitialDataProcessorV2_5 column names initialized. Base required: {self.base_required_option_cols_from_fetcher}")

    def _validate_and_prepare_raw_data_bundle(
        self,
        raw_options_df: Optional[pd.DataFrame],
        raw_underlying_dict_combined: Optional[Dict[str, Any]],
        symbol_context: str,
        current_time_dt: datetime
        ) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]], Optional[str]]:
        prep_logger = self.logger.getChild("ValidatePrepareRawBundle")
        symbol_upper = symbol_context.upper()

        if not isinstance(raw_underlying_dict_combined, dict) or not raw_underlying_dict_combined:
            err = f"Combined underlying data for {symbol_upper} is missing or not a dictionary."
            prep_logger.error(err); return None, None, err

        und_data_prepared = raw_underlying_dict_combined.copy()
        und_data_prepared[self.col_und_symbol_cfg] = symbol_upper

        current_und_price = und_data_prepared.get(self.col_underlying_price_cfg)
        if current_und_price is None or not isinstance(current_und_price, (int, float)) or current_und_price <= 0 or pd.isna(current_und_price):
            err = f"Underlying price ('{self.col_underlying_price_cfg}') for {symbol_upper} missing/invalid: {current_und_price}."
            prep_logger.error(err); return None, und_data_prepared, err
        und_data_prepared[self.col_underlying_price_cfg] = float(current_und_price)
        und_data_prepared[self.col_multiplier_cfg] = None

        if not isinstance(raw_options_df, pd.DataFrame) or raw_options_df.empty:
            prep_logger.warning(f"Raw options chain for {symbol_upper} is empty/invalid.")
            empty_df_cols = list(set(self.base_required_option_cols_from_fetcher + ["underlying_price_at_fetch", "current_time_dt", "processing_time_dt_obj", self.col_und_symbol_cfg]))
            return pd.DataFrame(columns=empty_df_cols), und_data_prepared, None

        df_prepared = raw_options_df.copy()
        missing_base_cols = [col for col in self.base_required_option_cols_from_fetcher if col not in df_prepared.columns]
        if missing_base_cols:
            err = f"Raw options chain for {symbol_upper} missing columns: {missing_base_cols}."
            prep_logger.error(err); return df_prepared, und_data_prepared, err

        if self.col_multiplier_cfg in df_prepared.columns:
            multipliers_series = pd.to_numeric(df_prepared[self.col_multiplier_cfg], errors='coerce')
            unique_multipliers = multipliers_series.dropna().unique()
            if len(unique_multipliers) == 1:
                consistent_multiplier = float(unique_multipliers[0])
                if consistent_multiplier <= 0:
                    err = f"Invalid multiplier ({consistent_multiplier}) in chain for {symbol_upper}."
                    prep_logger.error(err); return df_prepared, und_data_prepared, err
                und_data_prepared[self.col_multiplier_cfg] = consistent_multiplier
                df_prepared[self.col_multiplier_cfg] = consistent_multiplier
            elif len(unique_multipliers) > 1:
                prep_logger.warning(f"Multiple multipliers for {symbol_upper}: {unique_multipliers}. Using first: {unique_multipliers[0]}.")
                consistent_multiplier = float(unique_multipliers[0])
                if consistent_multiplier <=0 : consistent_multiplier = self.default_multiplier_val
                und_data_prepared[self.col_multiplier_cfg] = consistent_multiplier
                df_prepared[self.col_multiplier_cfg] = consistent_multiplier
            else:
                prep_logger.error(f"Multiplier '{self.col_multiplier_cfg}' all NaN/missing for {symbol_upper}. Using default: {self.default_multiplier_val}.")
                und_data_prepared[self.col_multiplier_cfg] = self.default_multiplier_val
                df_prepared[self.col_multiplier_cfg] = self.default_multiplier_val
        else:
            err = f"Critical: Multiplier column '{self.col_multiplier_cfg}' missing from raw chain for {symbol_upper}."
            prep_logger.error(err); return df_prepared, und_data_prepared, err

        df_prepared["underlying_price_at_fetch"] = float(current_und_price)
        df_prepared["current_time_dt"] = current_time_dt
        df_prepared["processing_time_dt_obj"] = current_time_dt
        if self.col_und_symbol_cfg not in df_prepared.columns:
             df_prepared[self.col_und_symbol_cfg] = symbol_upper

        prep_logger.debug(f"Raw data bundle for {symbol_upper} validated. Options DF shape: {df_prepared.shape}.")
        return df_prepared, und_data_prepared, None

    def process_raw_data_bundle_v2_5(
        self,
        raw_options_df: Optional[pd.DataFrame],
        raw_underlying_dict_combined: Optional[Dict[str, Any]],
        current_time_dt: datetime,
        symbol: str
        ) -> Dict[str, Any]:

        proc_main_logger = self.logger.getChild("ProcessRawBundle_v2.5")
        symbol_upper = symbol.upper()

        if self.initialization_failed:
            err_msg = f"InitialDataProcessorV2_5 for {symbol_upper} cannot process: Class initialization failed."
            proc_main_logger.critical(err_msg)
            return {"symbol": symbol_upper, "status": "ERROR_INITIALIZATION", "error_message": err_msg,
                    "options_df_with_metrics_obj": pd.DataFrame(), "df_strike_level_metrics_obj": pd.DataFrame(),
                    "underlying_data_enriched_obj": {}}

        fetch_ts_original_cv = raw_underlying_dict_combined.get("fetch_timestamp_payload_cv") if isinstance(raw_underlying_dict_combined, dict) else None
        fetch_ts_original_tradier = raw_underlying_dict_combined.get("fetch_timestamp_payload_tradier") if isinstance(raw_underlying_dict_combined, dict) else None

        proc_main_logger.info(f"--- InitialProcessorV2_5 START for: {symbol_upper} at {current_time_dt.strftime('%Y-%m-%d %H:%M:%S')} ---")

        options_df_prepared_for_metrics, underlying_data_prepared_for_metrics, prep_error_msg =             self._validate_and_prepare_raw_data_bundle(
                raw_options_df, raw_underlying_dict_combined, symbol_upper, current_time_dt
            )

        options_df_output_metrics: pd.DataFrame = pd.DataFrame()
        strike_df_output_metrics: pd.DataFrame = pd.DataFrame()
        underlying_data_output_enriched: Dict[str, Any] = underlying_data_prepared_for_metrics.copy() if underlying_data_prepared_for_metrics else {}
        metrics_calc_error_msg: Optional[str] = None

        if prep_error_msg:
            proc_main_logger.error(f"Error during preparation for {symbol_upper}: {prep_error_msg}")
        elif options_df_prepared_for_metrics is None or underlying_data_prepared_for_metrics is None :
            metrics_calc_error_msg = "Critical internal error: Prepared data is None after validation."
            proc_main_logger.error(metrics_calc_error_msg)
        else:
            try:
                proc_main_logger.info(f"Invoking MetricsCalculatorV2_5 for {symbol_upper}. Options input shape: {options_df_prepared_for_metrics.shape}")

                options_df_calc_out, strike_df_calc_out, und_data_enriched_from_calc =                     self.metrics_calculator.orchestrate_all_metric_calculations_v2_5(
                        options_df_prepared=options_df_prepared_for_metrics,
                        underlying_data_prepared=underlying_data_prepared_for_metrics,
                        current_time_dt=current_time_dt,
                        symbol=symbol_upper
                    )

                options_df_output_metrics = options_df_calc_out if isinstance(options_df_calc_out, pd.DataFrame) else options_df_prepared_for_metrics.copy()
                strike_df_output_metrics = strike_df_calc_out if isinstance(strike_df_calc_out, pd.DataFrame) else pd.DataFrame()

                if isinstance(und_data_enriched_from_calc, dict):
                    underlying_data_output_enriched.update(und_data_enriched_from_calc)

                if options_df_output_metrics.empty and not options_df_prepared_for_metrics.empty :
                     proc_main_logger.warning(f"Metrics calculation for {symbol_upper} resulted in empty options_df_output_metrics.")

            except Exception as e_mc_call:
                metrics_calc_error_msg = f"Exception during MetricsCalculatorV2_5 call for {symbol_upper}: {type(e_mc_call).__name__} - {str(e_mc_call)}"
                proc_main_logger.error(metrics_calc_error_msg, exc_info=True)

        final_error_message = prep_error_msg or metrics_calc_error_msg
        status = "ERROR" if final_error_message else "SUCCESS"
        if status == "SUCCESS" and options_df_output_metrics.empty and (raw_options_df is None or raw_options_df.empty):
            status = "SUCCESS_NO_OPTIONS_DATA"

        processed_data_bundle = {
            "symbol": symbol_upper, "status": status, "error_message": final_error_message,
            "processing_timestamp_initial_processor_v2_5": datetime.now().isoformat(),
            "fetch_timestamp_original_cv": fetch_ts_original_cv,
            "fetch_timestamp_original_tradier": fetch_ts_original_tradier,
            "options_df_input_to_metrics_calc_obj": options_df_prepared_for_metrics if options_df_prepared_for_metrics is not None else pd.DataFrame(),
            "underlying_data_input_to_metrics_calc_obj": underlying_data_prepared_for_metrics if underlying_data_prepared_for_metrics is not None else {},
            "options_df_with_metrics_obj": options_df_output_metrics,
            "df_strike_level_metrics_obj": strike_df_output_metrics,
            "underlying_data_enriched_obj": underlying_data_output_enriched,
        }

        log_fn = proc_main_logger.error if "ERROR" in status else proc_main_logger.info
        log_fn(f"--- InitialProcessorV2_5 END for: {symbol_upper}. Status: {status}. Error: {final_error_message or 'None'} ---")

        return processed_data_bundle
