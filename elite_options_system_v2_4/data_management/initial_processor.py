# data_management/initial_processor.py
# (Elite Version 2.4 - Co-Pilot - Phase 4: Refined Initial Data Processing)

# Standard Library Imports
import os
import json
import traceback
import logging
from datetime import datetime, date, time, timedelta
from typing import Dict, Any, Optional, List, Union, Tuple
import sys

# Third-Party Imports
import pandas as pd # type: ignore
import numpy as np # type: ignore

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

JSON_CONVERSION_ERROR_PLACEHOLDER_PROC: str = "JSON_CONVERSION_ERROR_NON_SERIALIZABLE"

class InitialDataProcessorV2_4:
    """
    Processes raw options chain and underlying data bundles from DataFetcherV2_4.
    1. Validates and prepares raw inputs.
    2. Invokes MetricsCalculatorV2_4 for all detailed metric calculations.
    3. Packages original prepared data and metric-rich outputs into a comprehensive bundle.
    """

    def __init__(self, 
                 config_manager_instance: Any, # Expecting a ConfigManager instance
                 metrics_calculator_instance: Any # Expecting a MetricsCalculatorV2_4 compatible instance
                 # historical_data_manager_instance is NOT directly used by InitialProcessor.
                 # It's used BY MetricsCalculator. MetricsCalculator should get it via its own init.
                 ):
        self.logger = logger.getChild(self.__class__.__name__)
        self.initialization_failed = False # Assume success initially

        if not hasattr(config_manager_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager. Critical failure.")
            self.initialization_failed = True
            # In a real app, might raise an error or have a more robust dummy.
            # For this flow, we'll let it proceed but it will likely fail on get_setting.
            class DummyCM:
                def get_setting(self, *args, **kwargs): return kwargs.get('default')
            self.config_manager = DummyCM() # type: ignore
        else:
            self.config_manager = config_manager_instance

        self.logger.info(f"Initializing InitialDataProcessorV2_4 (ConfigManager Integrated, Phase 4)...")
        
        if metrics_calculator_instance is None or not hasattr(metrics_calculator_instance, 'orchestrate_all_metric_calculations'):
            self.logger.critical("A valid MetricsCalculatorV2_4 instance with 'orchestrate_all_metric_calculations' method is required. Initialization failed.")
            self.initialization_failed = True
            raise ValueError("MetricsCalculatorV2_4 instance is missing, invalid, or lacks the required method.")
        self.metrics_calculator = metrics_calculator_instance
        
        self._initialize_column_names_from_config()
        
        if not self.initialization_failed:
            self.logger.info("InitialDataProcessorV2_4 Initialized successfully.")
        else:
            self.logger.error("InitialDataProcessorV2_4 initialization encountered critical errors.")

    def _initialize_column_names_from_config(self) -> None:
        """Initializes commonly used column names from the config for validation and preparation."""
        s_cfg_path = "strategy_settings" # Base path for strategy settings in config
        
        self.col_strike_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.strike_col_name", "strike")
        self.col_opt_kind_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.option_kind_col_name", "opt_kind")
        self.col_expiration_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.expiration_col_name", "expiration_days_from_epoch_calc") # From your config
        self.col_oi_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.oi_col_name", "oi")
        self.col_option_price_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.option_price_col_name", "price")
        self.col_option_volatility_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.option_volatility_col_name", "volatility")
        self.col_multiplier_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.contract_multiplier_col_name", "multiplier") # From config
        self.default_multiplier_val: float = float(self.config_manager.get_setting(f"{s_cfg_path}.contract_multiplier_default_value", 100.0))

        self.col_underlying_price_cfg: str = self.config_manager.get_setting(f"{s_cfg_path}.underlying_price_col_name", "price") # For underlying_data_raw
        
        # These are for validating the input options_chain_df_raw from Fetcher
        self.base_required_option_cols_from_fetcher: List[str] = [
            self.col_strike_cfg, self.col_opt_kind_cfg, self.col_expiration_cfg,
            self.col_oi_cfg, self.col_option_price_cfg, self.col_option_volatility_cfg,
            self.col_multiplier_cfg # Multiplier comes from chain data
        ]
        self.logger.debug(f"InitialDataProcessor column names initialized from config. Base required from chain: {self.base_required_option_cols_from_fetcher}")

    def _validate_and_prepare_input_data(
        self, 
        options_chain_df_raw: Optional[pd.DataFrame], 
        underlying_data_raw: Optional[Dict[str, Any]],
        symbol_context: str,
        current_time_dt: datetime
        ) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]], Optional[str]]:
        prep_logger = self.logger.getChild("ValidatePrepareInput")
        symbol_upper = symbol_context.upper()

        # 1. Validate Underlying Data (from get_und, passed by Fetcher)
        if not isinstance(underlying_data_raw, dict) or not underlying_data_raw:
            err = f"Underlying data for {symbol_upper} is missing or not a dictionary."
            prep_logger.error(err); return None, None, err
        
        und_data_prepared = underlying_data_raw.copy()
        und_data_prepared["symbol_context_override"] = symbol_upper # Ensure consistent symbol

        current_und_price = und_data_prepared.get(self.col_underlying_price_cfg)
        if current_und_price is None or not isinstance(current_und_price, (int, float)) or current_und_price <= 0 or pd.isna(current_und_price):
            err = f"Underlying price ('{self.col_underlying_price_cfg}') for {symbol_upper} missing, invalid, or NaN in underlying_data_raw: {current_und_price}."
            prep_logger.error(err); return None, und_data_prepared, err
        und_data_prepared[self.col_underlying_price_cfg] = float(current_und_price) # Ensure float

        # Multiplier for underlying_data_raw:
        # Get_und doesn't provide it. It comes from chain. So, it's added to und_data_prepared later.
        # However, ensure the key exists from config for later use.
        if self.col_multiplier_cfg not in und_data_prepared: # It won't be there from get_und
            und_data_prepared[self.col_multiplier_cfg] = None # Placeholder, will be filled from chain


        # 2. Validate Options Chain DataFrame (from get_chain_as_rows, passed by Fetcher)
        if not isinstance(options_chain_df_raw, pd.DataFrame) or options_chain_df_raw.empty:
            # This might be acceptable if the API returned no options (e.g., for an index with no weeklies on a certain day)
            prep_logger.warning(f"Input options chain DataFrame for {symbol_upper} is empty or not a DataFrame. Proceeding with empty options data if underlying data is valid.")
            # Return an empty DataFrame, but the underlying data might still be processable for some _Und level metrics
            return pd.DataFrame(columns=self.base_required_option_cols_from_fetcher + ["underlying_price_at_fetch", "current_time_dt", "processing_time_dt_obj", self.config_manager.get_setting("strategy_settings.underlying_symbol_col_name")]), \
                   und_data_prepared, None # No error string if only options are missing

        df_prepared = options_chain_df_raw.copy()

        missing_base_cols = [col for col in self.base_required_option_cols_from_fetcher if col not in df_prepared.columns]
        if missing_base_cols:
            err = f"Options chain for {symbol_upper} missing base required columns from fetcher output: {missing_base_cols}. Available: {df_prepared.columns.tolist()}"
            prep_logger.error(err); return df_prepared, und_data_prepared, err
        
        # Extract and validate a single, consistent multiplier from the options chain
        # This multiplier will be used for all calculations and added to und_data_prepared
        if self.col_multiplier_cfg in df_prepared.columns:
            unique_multipliers = df_prepared[self.col_multiplier_cfg].dropna().unique()
            if len(unique_multipliers) == 1:
                consistent_multiplier = float(unique_multipliers[0])
                if consistent_multiplier <= 0:
                    err = f"Invalid contract multiplier ({consistent_multiplier}) found in chain for {symbol_upper}."
                    prep_logger.error(err); return df_prepared, und_data_prepared, err
                und_data_prepared[self.col_multiplier_cfg] = consistent_multiplier # Add to und_data
                df_prepared[self.col_multiplier_cfg] = consistent_multiplier # Ensure all rows have it
                prep_logger.debug(f"Using consistent contract multiplier {consistent_multiplier} for {symbol_upper} from chain data.")
            elif len(unique_multipliers) > 1:
                prep_logger.warning(f"Multiple different multipliers found in chain for {symbol_upper}: {unique_multipliers}. Using first valid one or default: {unique_multipliers[0]}")
                # This case should be rare for standard options of one underlying. Using first valid.
                consistent_multiplier = float(unique_multipliers[0]) # Or mode, or log error
                if consistent_multiplier <=0 : consistent_multiplier = self.default_multiplier_val
                und_data_prepared[self.col_multiplier_cfg] = consistent_multiplier
                df_prepared[self.col_multiplier_cfg] = consistent_multiplier
            else: # All multipliers are NaN or column is empty after dropna
                prep_logger.error(f"Contract multiplier ('{self.col_multiplier_cfg}') is all NaN or missing in chain for {symbol_upper}. Using default from config: {self.default_multiplier_val}.")
                und_data_prepared[self.col_multiplier_cfg] = self.default_multiplier_val
                df_prepared[self.col_multiplier_cfg] = self.default_multiplier_val # Propagate default
        else: # Should not happen if base_required_option_cols_from_fetcher is correct
            err = f"Critical: Contract multiplier column '{self.col_multiplier_cfg}' missing from prepared chain for {symbol_upper}."
            prep_logger.error(err); return df_prepared, und_data_prepared, err

        # Add context columns needed by MetricsCalculator
        df_prepared["underlying_price_at_fetch"] = float(current_und_price) # From get_und
        df_prepared["current_time_dt"] = current_time_dt # System time
        df_prepared["processing_time_dt_obj"] = current_time_dt # Alias for clarity, or could be different if there's a delay
        
        underlying_symbol_col_name_in_df = self.config_manager.get_setting("strategy_settings.underlying_symbol_col_name", "underlying_symbol")
        if underlying_symbol_col_name_in_df not in df_prepared.columns:
            df_prepared[underlying_symbol_col_name_in_df] = symbol_upper
        
        prep_logger.debug(f"Input data for {symbol_upper} validated. Options DF shape for MetricsCalc: {df_prepared.shape}. Und data updated with multiplier.")
        return df_prepared, und_data_prepared, None

    def _convert_scalar_to_json_safe(self, scalar_data: Any) -> Any:
        if pd.isna(scalar_data) or scalar_data is None: return None
        if isinstance(scalar_data, (datetime, date, pd.Timestamp)): return scalar_data.isoformat()
        if isinstance(scalar_data, time): return scalar_data.strftime('%H:%M:%S.%f')
        if isinstance(scalar_data, pd.Timedelta): return scalar_data.total_seconds()
        if isinstance(scalar_data, (np.integer, int)): return int(scalar_data)
        if isinstance(scalar_data, (np.floating, float)):
            if np.isinf(scalar_data) or np.isnan(scalar_data): return None 
            return float(scalar_data)
        if isinstance(scalar_data, np.bool_): return bool(scalar_data)
        try: json.dumps(scalar_data); return scalar_data
        except TypeError: return JSON_CONVERSION_ERROR_PLACEHOLDER_PROC # str(scalar_data) could be too verbose
        except Exception: return JSON_CONVERSION_ERROR_PLACEHOLDER_PROC

    def _convert_to_json_safe(self, data_to_convert: Any) -> Any:
        if isinstance(data_to_convert, pd.DataFrame):
            # Create a copy for modification
            df_copy = data_to_convert.copy()
            # Handle numpy types that are not directly JSON serializable by first converting to Python native types
            for col in df_copy.columns:
                if df_copy[col].dtype == 'datetime64[ns]' or isinstance(df_copy[col].dtype, pd.DatetimeTZDtype):
                    df_copy[col] = df_copy[col].apply(lambda x: x.isoformat() if pd.notna(x) else None)
                elif df_copy[col].dtype == 'timedelta64[ns]':
                     df_copy[col] = df_copy[col].apply(lambda x: x.total_seconds() if pd.notna(x) else None)
                elif np.issubdtype(df_copy[col].dtype, np.integer):
                    df_copy[col] = df_copy[col].astype(object).apply(lambda x: int(x) if pd.notna(x) else None) # Convert to Python int
                elif np.issubdtype(df_copy[col].dtype, np.floating):
                    df_copy[col] = df_copy[col].astype(object).apply(lambda x: float(x) if pd.notna(x) and np.isfinite(x) else None) # Convert to Python float, handle inf/nan
                elif np.issubdtype(df_copy[col].dtype, np.bool_):
                     df_copy[col] = df_copy[col].astype(object).apply(lambda x: bool(x) if pd.notna(x) else None) # Convert to Python bool
            # Replace any remaining NaNs with None for JSON serialization
            return [self._convert_to_json_safe(record) for record in df_copy.where(pd.notnull(df_copy), None).to_dict(orient="records")]
        elif isinstance(data_to_convert, pd.Series):
            series_safe = data_to_convert.replace([np.inf, -np.inf], np.nan).where(pd.notnull(data_to_convert), None)
            return [self._convert_scalar_to_json_safe(item) for item in series_safe.tolist()]
        elif isinstance(data_to_convert, dict):
            return {str(k): self._convert_to_json_safe(v) for k, v in data_to_convert.items()}
        elif isinstance(data_to_convert, (list, tuple, set, np.ndarray)): # Add np.ndarray
            return [self._convert_to_json_safe(item) for item in data_to_convert]
        else:
            return self._convert_scalar_to_json_safe(scalar_data=data_to_convert)


    def _package_processed_results(
        self, symbol: str, fetch_timestamp_original: Optional[str],
        options_df_prepared_input: Optional[pd.DataFrame], 
        underlying_data_prepared_input: Optional[Dict[str, Any]],
        options_df_with_all_metrics: Optional[pd.DataFrame], 
        df_strike_level_all_metrics: Optional[pd.DataFrame],
        und_data_enriched_with_metrics: Optional[Dict[str, Any]],
        error_message: Optional[str]
        ) -> Dict[str, Any]:
        package_logger = self.logger.getChild("PackageResults")
        symbol_upper = symbol.upper()
        package_logger.info(f"Processor ({symbol_upper}): Packaging final V2.4 results bundle...")
        
        current_status = "ERROR" if error_message else "SUCCESS"
        # If options DFs are empty but no specific error, it might be a valid "no options data" scenario
        if current_status == "SUCCESS" and (options_df_with_all_metrics is None or options_df_with_all_metrics.empty):
            package_logger.info(f"Processor ({symbol_upper}): Output options data is empty, but no explicit error. Marking as SUCCESS_EMPTY_OPTIONS.")
            # current_status = "SUCCESS_EMPTY_OPTIONS" # Or keep as SUCCESS

        final_bundle: Dict[str, Any] = {
            "symbol": symbol_upper,
            "fetch_timestamp_original_data": fetch_timestamp_original,
            "processing_timestamp_initial_processor": datetime.now().isoformat(),
            "processor_version": "InitialDataProcessorV2_4_Phase4",
            "status": current_status,
            "error_message": error_message,
            
            "options_df_input_to_metrics_calc_obj": options_df_prepared_input if isinstance(options_df_prepared_input, pd.DataFrame) else pd.DataFrame(),
            "underlying_data_input_to_metrics_calc_obj": underlying_data_prepared_input if isinstance(underlying_data_prepared_input, dict) else {},
            "options_df_with_metrics_obj": options_df_with_all_metrics if isinstance(options_df_with_all_metrics, pd.DataFrame) else pd.DataFrame(),
            "df_strike_level_metrics_obj": df_strike_level_all_metrics if isinstance(df_strike_level_all_metrics, pd.DataFrame) else pd.DataFrame(),
            "underlying_data_enriched_obj": und_data_enriched_with_metrics if isinstance(und_data_enriched_with_metrics, dict) else {},
            
            "json_safe_data": { # Initialize for safety
                "options_chain_metrics_list": [], 
                "strike_level_metrics_list": [],  
                "underlying_enriched_dict": {}    
            }
        }
        
        try:
            final_bundle["json_safe_data"]["options_chain_metrics_list"] = self._convert_to_json_safe(options_df_with_all_metrics)
            final_bundle["json_safe_data"]["strike_level_metrics_list"] = self._convert_to_json_safe(df_strike_level_all_metrics)
            final_bundle["json_safe_data"]["underlying_enriched_dict"] = self._convert_to_json_safe(und_data_enriched_with_metrics)
            
            if JSON_CONVERSION_ERROR_PLACEHOLDER_PROC in str(final_bundle["json_safe_data"]): # Check for placeholder
                err_text_json = "JSON conversion encountered non-serializable types (marked with placeholder)."
                final_bundle["error_message"] = f"{final_bundle.get('error_message','')} | {err_text_json}".strip(" | ")
                final_bundle["status"] = "ERROR_JSON_CONVERSION" # More specific error status
                package_logger.error(f"Processor ({symbol_upper}): {err_text_json}")

        except Exception as e_pkg_json:
            err_text_json = f"Critical error during JSON conversion: {type(e_pkg_json).__name__} - {e_pkg_json}"
            package_logger.error(f"Processor ({symbol_upper}): {err_text_json}", exc_info=True)
            final_bundle["error_message"] = f"{final_bundle.get('error_message','')} | {err_text_json}".strip(" | ")
            final_bundle["status"] = "ERROR_JSON_CONVERSION"

        log_fn = package_logger.error if "ERROR" in final_bundle["status"] else package_logger.info
        log_fn(f"Processor ({symbol_upper}): Packaging finished. Status: {final_bundle['status']}. Message: {str(final_bundle.get('error_message','N/A'))[:150]}")
        
        return final_bundle

    def process_option_chain_snapshot_v2_4(
        self, 
        options_df_raw: Optional[pd.DataFrame], 
        underlying_data_raw: Optional[Dict[str, Any]], 
        current_time_dt: datetime,
        symbol: str 
        ) -> Dict[str, Any]:
        proc_main_logger = self.logger.getChild("ProcessSnapshot")
        symbol_upper = symbol.upper()
        
        if self.initialization_failed:
            err_msg = f"InitialDataProcessor for {symbol_upper} cannot process: Class initialization failed."
            proc_main_logger.critical(err_msg)
            return self._package_processed_results(symbol_upper, None, None, None, None, None, None, err_msg)

        fetch_ts_original = underlying_data_raw.get("fetch_timestamp_payload") if isinstance(underlying_data_raw, dict) else \
                            (options_df_raw["fetch_timestamp"].iloc[0] if isinstance(options_df_raw, pd.DataFrame) and not options_df_raw.empty and "fetch_timestamp" in options_df_raw.columns else None)
        if fetch_ts_original and not isinstance(fetch_ts_original, str): fetch_ts_original = str(fetch_ts_original)


        proc_main_logger.info(f"--- InitialProcessor START for: {symbol_upper} at {current_time_dt.strftime('%Y-%m-%d %H:%M:%S')} (Orig Fetch TS: {fetch_ts_original or 'N/A'}) ---")

        df_prepared, und_data_prepared, prep_error = self._validate_and_prepare_input_data(
            options_df_raw, underlying_data_raw, symbol_upper, current_time_dt
        )
        
        if prep_error is None and (df_prepared is None or df_prepared.empty):
             proc_main_logger.warning(f"InitialProcessor for {symbol_upper}: Options data is empty after preparation. Proceeding to calculate underlying-only metrics if possible.")
             if df_prepared is None: 
                 df_prepared = pd.DataFrame(columns=self.base_required_option_cols_from_fetcher + ["underlying_price_at_fetch", "current_time_dt", "processing_time_dt_obj", self.config_manager.get_setting("strategy_settings.underlying_symbol_col_name")])


        if prep_error or und_data_prepared is None: 
            final_err_msg = prep_error or "Unknown critical error during data validation/preparation of underlying data."
            proc_main_logger.error(f"InitialProcessor END for {symbol_upper}. Error: {final_err_msg}")
            return self._package_processed_results(symbol_upper, fetch_ts_original, 
                                                 df_prepared, und_data_prepared, 
                                                 None, None, None, final_err_msg)
        
        if df_prepared is None:
            df_prepared = pd.DataFrame() 
            proc_main_logger.error(f"InitialProcessor for {symbol_upper}: df_prepared became None unexpectedly after validation. Using empty DF.")


        df_chain_all_metrics: Optional[pd.DataFrame] = pd.DataFrame()
        df_strike_all_metrics: Optional[pd.DataFrame] = pd.DataFrame()
        und_data_enriched: Dict[str, Any] = und_data_prepared.copy() 
        calc_error_str: Optional[str] = None
        
        try:
            # --- CORRECTED LINE ---
            df_chain_all_metrics_calc, df_strike_all_metrics_calc, und_data_enriched_from_calc = \
                self.metrics_calculator.orchestrate_all_metric_calculations(
                    options_df_raw=df_prepared,             # Corrected: options_df -> options_df_raw
                    und_data_api_raw=und_data_prepared,   # Corrected: underlying_data -> und_data_api_raw
                    current_time_dt=current_time_dt,          # Corrected: current_processing_time_dt -> current_time_dt
                    symbol=symbol_upper                     # Corrected: symbol_context -> symbol
                )
            # --- END OF CORRECTION ---
            
            df_chain_all_metrics = df_chain_all_metrics_calc if isinstance(df_chain_all_metrics_calc, pd.DataFrame) else pd.DataFrame()
            df_strike_all_metrics = df_strike_all_metrics_calc if isinstance(df_strike_all_metrics_calc, pd.DataFrame) else pd.DataFrame()

            if isinstance(und_data_enriched_from_calc, dict):
                und_data_enriched.update(und_data_enriched_from_calc)
            elif und_data_enriched_from_calc is not None: 
                proc_main_logger.warning(f"MetricsCalculator for {symbol_upper} returned non-dict for enriched underlying data. Type: {type(und_data_enriched_from_calc)}. Not updating.")
        
            if df_chain_all_metrics.empty and df_strike_all_metrics.empty and not df_prepared.empty:
                proc_main_logger.warning(f"Metric calculation for {symbol_upper} resulted in empty metric DataFrames (chain and strike), though input options_df was not empty.")
        
        except Exception as e_metrics_calc:
            calc_error_str = f"Error during MetricsCalculatorV2_4 execution for {symbol_upper}: {type(e_metrics_calc).__name__} - {e_metrics_calc}"
            proc_main_logger.error(calc_error_str, exc_info=True)
        
        final_bundle = self._package_processed_results(
            symbol_upper, fetch_ts_original,
            df_prepared, und_data_prepared, 
            df_chain_all_metrics, df_strike_all_metrics, und_data_enriched,
            error_message=calc_error_str 
        )
        
        if calc_error_str:
            proc_main_logger.error(f"--- InitialProcessor END for: {symbol_upper} WITH METRIC CALCULATION ERRORS. ---")
        else:
            proc_main_logger.info(f"--- InitialProcessor END for: {symbol_upper}. Processing successful. ---")
        return final_bundle

# --- Main Test Block (Conceptual) ---
if __name__ == '__main__': # pragma: no cover
    if not logging.getLogger("EOTS_SystemRunnerV2.4").handlers and not logging.getLogger(__name__).handlers:
        test_handler = logging.StreamHandler(sys.stdout) 
        test_formatter = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s - L%(lineno)d - %(message)s')
        test_handler.setFormatter(test_formatter)
        logging.getLogger().addHandler(test_handler); logging.getLogger().setLevel(logging.DEBUG)

    main_test_logger = logging.getLogger(f"{__name__}_TestMain")
    main_test_logger.info("--- InitialDataProcessorV2_4 Standalone Test (Phase 4 Refined) ---")

    class MockTestConfigManagerForProc:
        _cfg = {
            "strategy_settings": {
                "strike_col_name": "strike", "option_kind_col_name": "opt_kind",
                "expiration_col_name": "expiration_days_from_epoch_calc", "oi_col_name": "oi",
                "option_price_col_name": "opt_price", "option_volatility_col_name": "iv",
                "contract_multiplier_col_name": "multiplier", "contract_multiplier_default_value": 100.0,
                "underlying_price_col_name": "und_price",
                "underlying_symbol_col_name": "underlying_symbol_ctx" # For context in options_df
            }
        }
        def get_setting(self, key_path: Union[str, List[str]], default: Any = None, quiet: bool = False) -> Any:
            keys = key_path.split('.') if isinstance(key_path, str) else key_path; val = self._cfg
            try:
                for k in keys: val = val[k]
                return val if val is not None else default
            except KeyError: return default
    
    test_proc_cm = MockTestConfigManagerForProc()

    class MockMetricsCalculatorForProcTest:
        def __init__(self, config_mgr, hist_mgr=None): self.logger = logging.getLogger("MockMC_ProcTest"); self.cm = config_mgr
        def orchestrate_all_metric_calculations(self, options_df, underlying_data, current_processing_time_dt, symbol_context):
            self.logger.info(f"MockMC_ProcTest: Orchestrating for {symbol_context}. Options DF empty: {options_df.empty}")
            chain_out = options_df.copy(); 
            if not chain_out.empty: chain_out["test_metric_contract"] = 123
            
            strike_col = self.cm.get_setting("strategy_settings.strike_col_name", "strike")
            strike_out = pd.DataFrame()
            if not chain_out.empty and strike_col in chain_out.columns:
                strike_out = chain_out.groupby(strike_col).size().reset_index(name="contract_count_test")
            
            und_enriched = underlying_data.copy(); und_enriched["test_metric_und"] = 456
            return chain_out, strike_out, und_enriched
    
    mock_mc_proc_instance = MockMetricsCalculatorForProcTest(config_mgr=test_proc_cm)

    processor = InitialDataProcessorV2_4(
        config_manager_instance=test_proc_cm,
        metrics_calculator_instance=mock_mc_proc_instance
    )

    if processor.initialization_failed:
        main_test_logger.error("Processor test initialization failed.")
    else:
        sample_opts_df = pd.DataFrame({
            "strike": [100, 105, 100], "opt_kind": ["c", "p", "p"], 
            "expiration_days_from_epoch_calc": [19000, 19000, 19001], # Match config
            "oi": [10, 20, 5], "opt_price": [1.0, 1.5, 0.8], "iv": [0.2, 0.22, 0.21],
            "multiplier": [100.0, 100.0, 100.0], # From fetcher
            "fetch_timestamp": [datetime.now().isoformat()] * 3
        })
        sample_und_dict = {"symbol": "TEST", "und_price": 102.0, "fetch_timestamp_payload": datetime.now().isoformat()}
        now_time = datetime.now()

        main_test_logger.info("\n--- Processing Snapshot for 'TEST' (with options data) ---")
        bundle1 = processor.process_option_chain_snapshot_v2_4(sample_opts_df, sample_und_dict, now_time, "TEST")
        main_test_logger.info(f"Bundle1 Status: {bundle1.get('status')}")
        if bundle1.get('error_message'): main_test_logger.error(f"Bundle1 Error: {bundle1.get('error_message')}")
        main_test_logger.info(f"Bundle1 options_df_with_metrics_obj shape: {bundle1.get('options_df_with_metrics_obj', pd.DataFrame()).shape}")
        main_test_logger.info(f"Bundle1 df_strike_level_metrics_obj shape: {bundle1.get('df_strike_level_metrics_obj', pd.DataFrame()).shape}")
        main_test_logger.info(f"Bundle1 underlying_data_enriched_obj keys: {list(bundle1.get('underlying_data_enriched_obj', {}).keys())}")

        main_test_logger.info("\n--- Processing Snapshot for 'TESTNOOPTS' (empty options data) ---")
        bundle2 = processor.process_option_chain_snapshot_v2_4(pd.DataFrame(), sample_und_dict.copy(), now_time, "TESTNOOPTS") # Empty DF
        main_test_logger.info(f"Bundle2 Status: {bundle2.get('status')}")
        if bundle2.get('error_message'): main_test_logger.error(f"Bundle2 Error: {bundle2.get('error_message')}")
        main_test_logger.info(f"Bundle2 options_df_with_metrics_obj shape: {bundle2.get('options_df_with_metrics_obj', pd.DataFrame()).shape}")
        main_test_logger.info(f"Bundle2 df_strike_level_metrics_obj shape: {bundle2.get('df_strike_level_metrics_obj', pd.DataFrame()).shape}")

    main_test_logger.info("--- InitialDataProcessorV2_4 Standalone Test Finished ---")