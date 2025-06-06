# data_management/fetcher.py
# (Elite Version 2.4 - Co-Pilot - Canonical Fetcher - Phase 2: API Aligned & Cleaned OHLCV Sourcing)

# Standard Library Imports
import os
import traceback
import time
import logging
import json
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union, Callable
from functools import wraps
import sys
from collections import OrderedDict

# Third-Party Imports
import pandas as pd # type: ignore
import numpy as np # type: ignore
import requests # For specific exception types

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

# --- Convexlib API Wrapper Import ---
try:
    from convexlib.api import ConvexApi
    CONVEXLIB_AVAILABLE = True
    _api_import_error_fetcher = None
    logger.info("Convexlib API imported successfully by fetcher.")
except ImportError as import_error_fetcher_imp:
    logger.critical(f"Fetcher: Could not import ConvexApi: {import_error_fetcher_imp}. Ensure 'convexlib' is installed.", exc_info=False)
    CONVEXLIB_AVAILABLE = False
    _api_import_error_fetcher = import_error_fetcher_imp
    class ConvexApi: # type: ignore # pragma: no cover
        def __init__(self, *args, **kwargs): raise ImportError(f"Dummy ConvexApi: convexlib not found. Original error: {_api_import_error_fetcher}")
        def get_und(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi used for get_und.")
        def get_chain_as_rows(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi used for get_chain_as_rows.")
except Exception as general_import_err_fetcher: # pragma: no cover
    logger.critical(f"Fetcher: Unexpected error during ConvexApi import: {general_import_err_fetcher}", exc_info=True)
    CONVEXLIB_AVAILABLE = False
    _api_import_error_fetcher = general_import_err_fetcher
    class ConvexApi: # type: ignore
        def __init__(self, *args, **kwargs): raise ImportError(f"Dummy ConvexApi: convexlib not found due to general error. Original error: {_api_import_error_fetcher}")
        def get_und(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi used for get_und due to general error.")
        def get_chain_as_rows(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi used for get_chain_as_rows due to general error.")

if not CONVEXLIB_AVAILABLE:
    logger.error("FETCHER CRITICAL: Convexlib library is not available. DataFetcherV2_4 will operate in a severely limited or non-functional state regarding live data.")

# --- Retry Decorator ---
def retry_api_call(retries: int, base_delay: float, max_delay: float, jitter: bool = True,
                   logger_instance: Optional[logging.Logger] = None,
                   expected_response_type: type = dict,
                   func_name_override: Optional[str] = None):
    log = logger_instance if logger_instance else logging.getLogger(f"{__name__}.retry_api_call")

    def decorator(func: Callable):
        actual_func_name = func_name_override if func_name_override else func.__name__
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = base_delay
            last_exception: Optional[BaseException] = None

            while attempts <= retries:
                try:
                    response = func(*args, **kwargs)
                    if not isinstance(response, expected_response_type):
                        log.warning(f"API call {actual_func_name} returned unexpected data type on attempt {attempts + 1}. "
                                    f"Expected {expected_response_type}, got {type(response)}. Response: {str(response)[:200]}")
                        if attempts == retries:
                            log.error(f"API call {actual_func_name} failed due to unexpected data type after max retries.")
                            if expected_response_type == dict: return {"error": f"API returned unexpected data type for {actual_func_name}"}
                            elif expected_response_type == list: return []
                            else: return None
                    
                    if isinstance(response, dict) and response.get("error"):
                        log.warning(f"API call {actual_func_name} returned an error in response dict on attempt {attempts + 1}: {response.get('error')}")
                        if attempts == retries:
                             log.error(f"API call {actual_func_name} failed with API-reported error after max retries: {response.get('error')}")
                             return response
                    elif isinstance(response, dict) and response.get("data") is None and "data" in response:
                        log.warning(f"API call {actual_func_name} returned dict with 'data' key as None on attempt {attempts+1}.")
                    
                    log.debug(f"API call {actual_func_name} successful on attempt {attempts + 1}.")
                    return response

                except (requests.exceptions.HTTPError) as e_http: # type: ignore
                    status_code = e_http.response.status_code if hasattr(e_http, 'response') and e_http.response is not None else 'N/A'
                    response_text = str(e_http.response.text)[:100] if hasattr(e_http, 'response') and e_http.response is not None else 'No response text'
                    log.warning(f"API HTTP Error on attempt {attempts + 1} for {actual_func_name}: {status_code} - {response_text}")
                    last_exception = e_http
                    if status_code in [401, 403]: # type: ignore
                        log.error(f"Fatal API authentication/authorization error ({status_code}) for {actual_func_name}. Aborting retries.")
                        raise last_exception 
                    if status_code == 429: # type: ignore
                        log.warning(f"API Rate Limit Exceeded (429) for {actual_func_name}. Significantly increasing delay.")
                        current_delay = min(current_delay * 2.5, max_delay * 2.5) 
                except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as e_req: 
                    log.warning(f"API Network/Request Error on attempt {attempts + 1} for {actual_func_name}: {type(e_req).__name__} - {str(e_req)[:150]}")
                    last_exception = e_req
                except Exception as e_gen:
                    log.error(f"Unexpected Error during API call attempt {attempts + 1} for {actual_func_name}: {type(e_gen).__name__} - {e_gen}", exc_info=False)
                    if log.getEffectiveLevel() <= logging.DEBUG: log.debug(f"Full traceback for {actual_func_name}:", exc_info=True)
                    last_exception = e_gen

                attempts += 1
                if attempts <= retries:
                    sleep_duration = current_delay + (random.uniform(0, current_delay * 0.2) if jitter else 0)
                    log.info(f"Retrying {actual_func_name} in {sleep_duration:.2f} seconds... (Attempt {attempts}/{retries})")
                    time.sleep(sleep_duration)
                    current_delay = min(current_delay * 1.8, max_delay)
                else: 
                    log.error(f"API call {actual_func_name} failed after {retries} retries.")
                    if last_exception:
                        log.error(f"Last error for {actual_func_name}: {type(last_exception).__name__} - {last_exception}")
                        if expected_response_type == dict: return {"error": f"API call {actual_func_name} failed after max retries. Last error: {str(last_exception)[:100]}"}
                        elif expected_response_type == list: return []
                        else: raise last_exception 
                    else:
                        log.error(f"API call {actual_func_name} failed after max retries with no specific exception caught in the final attempt's try-except block.")
                        if expected_response_type == dict: return {"error": f"API call {actual_func_name} failed after max retries (unknown final state)."}
                        elif expected_response_type == list: return []
                        else: return None
            log.critical(f"Fell through retry loop for {actual_func_name} - this indicates a logic error.")
            if expected_response_type == dict: return {"error": "Retry loop logic error."}
            elif expected_response_type == list: return []
            return None
        return wrapper
    return decorator

class DataFetcherV2_4:
    def __init__(self, config_manager_instance: Any): 
        self.logger = logger.getChild(self.__class__.__name__)
        if not hasattr(config_manager_instance, 'get_setting'): # Basic check for a ConfigManager-like object
            self.logger.critical("DataFetcherV2_4 initialized with an invalid ConfigManager instance. Functionality will be severely impaired.")
            class DummyConfigManager: # Fallback to prevent AttributeError, but system won't work
                def get_setting(self, *args, **kwargs): return kwargs.get('default')
                def get_resolved_path(self, *args, **kwargs): return None
            self.config_manager = DummyConfigManager() # type: ignore
        else:
            self.config_manager = config_manager_instance
        
        self.logger.info(f"Initializing DataFetcherV2_4 (ConfigManager Integrated, V2.4 API Aligned - Phase 2)...")

        if not CONVEXLIB_AVAILABLE:
            self.logger.critical("Convexlib not loaded. DataFetcherV2_4 cannot function for live data.")
            self.api: Optional[ConvexApi] = None
            self._load_config_settings_for_fetcher(minimal=True)
            return

        self._load_config_settings_for_fetcher()
        self._load_credentials_from_env()

        self.api: Optional[ConvexApi] = None
        if self.email and self.password:
            try:
                @retry_api_call(retries=max(1, self.max_retries_cfg // 2), 
                                base_delay=self.base_retry_delay_cfg, 
                                max_delay=self.max_retry_delay_cfg, 
                                logger_instance=self.logger, 
                                expected_response_type=type(None),
                                func_name_override="_connect_to_api_internal_retried")
                def connect_with_retry():
                    self._connect_to_api_internal()
                
                connect_with_retry()
                if self.api:
                     self.logger.info(f"DataFetcherV2_4 Initialized. API connection for env '{self.api_env}' successful.")
                else:
                     self.logger.error(f"DataFetcherV2_4 Initialized, but API connection for env '{self.api_env}' FAILED after retries.")
            except Exception as e_conn_final:
                self.logger.error(f"Initial API connection attempt FAILED critically: {type(e_conn_final).__name__} - {e_conn_final}")
                self.api = None
        else:
            self.logger.error("API credentials (email or password) missing. Cannot attempt to connect to API.")

        if not self.api:
            self.logger.warning("DataFetcherV2_4 API client is not connected. Operations requiring API will fail or return empty/error data.")

    def _load_config_settings_for_fetcher(self, minimal: bool = False):
        self.logger.debug(f"Loading fetcher configurations (minimal={minimal})...")

        self.api_email_env_var: str = self.config_manager.get_setting("api_credentials.email_env_var", "CONVEX_EMAIL")
        self.api_password_env_var: str = self.config_manager.get_setting("api_credentials.password_env_var", "CONVEX_PASSWORD")
        self.api_env: str = self.config_manager.get_setting("api_credentials.environment", "pro")

        fetch_cfg_path = "data_fetcher_settings"
        self.max_retries_cfg: int = int(self.config_manager.get_setting(f"{fetch_cfg_path}.max_retries", 3 if not minimal else 1))
        self.base_retry_delay_cfg: float = float(self.config_manager.get_setting(f"{fetch_cfg_path}.base_retry_delay_seconds", 1.0 if not minimal else 0.2))
        self.max_retry_delay_cfg: float = float(self.config_manager.get_setting(f"{fetch_cfg_path}.max_retry_delay_seconds", 10.0 if not minimal else 0.5))
        self.inter_call_delay: float = float(self.config_manager.get_setting(f"{fetch_cfg_path}.inter_call_delay_seconds", 0.25 if not minimal else 0.05))
        self.default_dte_range_cfg: List[int] = self.config_manager.get_setting(f"{fetch_cfg_path}.default_dte_range", [0, 1, 7, 14, 30, 60, 90])
        self.default_price_range_pct_cfg: float = float(self.config_manager.get_setting(f"{fetch_cfg_path}.default_price_range_pct", 0.075))

        strat_cfg_path = "strategy_settings"
        self.cfg_exp_col_name: str = self.config_manager.get_setting(f"{strat_cfg_path}.expiration_col_name", "expiration_days_from_epoch_calc") # Match config
        self.cfg_strike_col_name: str = self.config_manager.get_setting(f"{strat_cfg_path}.strike_col_name", "strike")
        self.cfg_opt_kind_col_name: str = self.config_manager.get_setting(f"{strat_cfg_path}.option_kind_col_name", "opt_kind")
        self.cfg_und_sym_col_name: str = self.config_manager.get_setting(f"{strat_cfg_path}.underlying_symbol_col_name", "underlying_symbol") # Used to add context to options_df
        
        # CRITICAL: Load API parameter lists strictly from config
        self.underlying_api_params_to_request: List[str] = list(OrderedDict.fromkeys( # Preserve order from config
            self.config_manager.get_setting(f"{strat_cfg_path}.api_params_get_und", []) 
        ))
        if not self.underlying_api_params_to_request and not minimal:
            self.logger.critical("FETCHER CONFIG ERROR: 'strategy_settings.api_params_get_und' is NOT DEFINED or EMPTY in config. `get_und` calls will fail or return minimal data (likely just symbol if API supports that). THIS IS REQUIRED.")
        
        self.options_contract_api_params_to_request: List[str] = sorted(list(set( # Order not strictly critical for these additional named params, but sorting aids consistency
             self.config_manager.get_setting(f"{strat_cfg_path}.api_params_get_chain_additional", [])
        )))
        if not self.options_contract_api_params_to_request and not minimal:
            self.logger.warning("Fetcher Config: 'strategy_settings.api_params_get_chain_additional' is missing or empty. `get_chain_as_rows` will only fetch prefix columns, if API supports that mode.")

        self.raw_chain_row_prefix_names: List[str] = self.config_manager.get_setting(
            f"{strat_cfg_path}.api_get_chain_prefix_cols", 
            ["api_temp_contract_symbol", "api_temp_expiration", "api_temp_strike", "api_temp_opt_kind"] # Default if missing
        )
        
        self.logger.info(f"Fetcher loaded {len(self.underlying_api_params_to_request)} underlying params and "
                         f"{len(self.options_contract_api_params_to_request)} options contract (additional) params from config.")
        self.logger.debug(f"Underlying Params to Request for get_und (ORDERED FROM CONFIG): {self.underlying_api_params_to_request}")
        self.logger.debug(f"Options Contract (Additional) Params for get_chain_as_rows: {self.options_contract_api_params_to_request}")
        self.logger.debug(f"Chain Row Prefix Columns Expected from Config: {self.raw_chain_row_prefix_names}")

    def _load_credentials_from_env(self):
        self.logger.debug(f"Loading API credentials from ENV vars: '{self.api_email_env_var}', '{self.api_password_env_var}'")
        self.email = os.getenv(self.api_email_env_var)
        self.password = os.getenv(self.api_password_env_var)
        if not (self.email and self.password):
            self.logger.error(f"API Credentials NOT FOUND in environment variables ('{self.api_email_env_var}', '{self.api_password_env_var}').")
        elif self.email and self.password:
            self.logger.info(f"API credentials found in environment variables ('{self.api_email_env_var}', password for '{self.api_password_env_var}' redacted).")

    def _connect_to_api_internal(self) -> None:
        if not CONVEXLIB_AVAILABLE: raise ConnectionError("Convexlib library not available.")
        if not (self.email and self.password): raise ConnectionError("API credentials missing.")
        self.logger.info(f"Attempting ConvexAPI connection for env: '{self.api_env}' with user: {str(self.email)[:3]}***...")
        try:
            self.api = ConvexApi(self.email, self.password) # Corrected: removed 'env'
            self.logger.info(f"ConvexApi object instantiated. Connection assumed successful if no immediate error.")
        except Exception as e_api_init:
            self.logger.error(f"Failed to instantiate ConvexApi client: {type(e_api_init).__name__} - {e_api_init}", exc_info=True)
            self.api = None
            raise ConnectionError(f"ConvexApi instantiation failed: {e_api_init}") from e_api_init

    def _parse_underlying_data(self, raw_response_data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        parsed_data: Dict[str, Any] = {"symbol": symbol.upper(), "fetch_timestamp_parser": datetime.now().isoformat()}
        
        if not isinstance(raw_response_data, dict):
            parsed_data["error_parsing"] = f"Underlying raw_response_data is not a dict. Type: {type(raw_response_data)}"
            self.logger.error(f"{parsed_data['error_parsing']} for {symbol}")
            return parsed_data

        api_data_list = raw_response_data.get("data")

        # --- START OF ADDED FIX ---
        # Handle potential triple nesting for single symbol get_und responses
        # Expected structure if correctly unwrapped for single symbol: [ ['SYM', v1, v2, ...] ]
        # Problematic structure observed: [ [ ['SYM', v1, v2, ...] ] ]
        if isinstance(api_data_list, list) and len(api_data_list) == 1 and \
           isinstance(api_data_list[0], list) and len(api_data_list[0]) == 1 and \
           isinstance(api_data_list[0][0], list) and \
           len(api_data_list[0][0]) > 0 and isinstance(api_data_list[0][0][0], str):
            self.logger.debug(f"Detected and unwrapping one level of extra list nesting in get_und response for {symbol}.")
            api_data_list = api_data_list[0] # Unwraps from [ [ [...] ] ] to [ [...] ]
        # --- END OF ADDED FIX ---
        
        if not isinstance(api_data_list, list) or not api_data_list or \
           not isinstance(api_data_list[0], list) or not api_data_list[0]:
            parsed_data["error_parsing"] = f"Underlying 'data' from API is malformed or empty after potential unwrap. Resp: {str(raw_response_data)[:200]}"
            self.logger.warning(f"{parsed_data['error_parsing']} for {symbol}")
            return parsed_data
        
        symbol_data_values_list = api_data_list[0] # Now should correctly be e.g., ['SPY', val1, val2, ...]
        
        if not isinstance(symbol_data_values_list[0], str):
             parsed_data["error_parsing"] = f"First item in get_und data row is not symbol string. Got: {symbol_data_values_list[0]}"
             self.logger.warning(f"{parsed_data['error_parsing']} for {symbol}")
             return parsed_data

        api_symbol = symbol_data_values_list[0]
        actual_values = symbol_data_values_list[1:]
        num_actual_values = len(actual_values)

        if api_symbol.upper() != symbol.upper():
            self.logger.warning(f"Symbol mismatch in get_und: Expected '{symbol.upper()}', API returned '{api_symbol.upper()}'.")
        parsed_data["api_response_symbol_und"] = api_symbol
        
        params_requested_count = len(self.underlying_api_params_to_request)
        if num_actual_values != params_requested_count:
            warn_msg = (f"Positional Mapping CRITICAL WARNING for {symbol} (get_und): "
                        f"Requested {params_requested_count} params (from config 'api_params_get_und'), "
                        f"but API returned {num_actual_values} values. Data WILL BE MISALIGNED or incomplete! "
                        f"Requested: {self.underlying_api_params_to_request}, Got values: {actual_values[:5]}...")
            self.logger.error(warn_msg)
            parsed_data["warning_param_mismatch_critical"] = warn_msg
        
        max_len_to_parse = min(num_actual_values, params_requested_count)
        for i in range(max_len_to_parse):
            key_name_expected_by_its = self.underlying_api_params_to_request[i]
            value_to_process = actual_values[i]
            try:
                num_val = pd.to_numeric(value_to_process, errors='raise')
                parsed_data[key_name_expected_by_its] = None if pd.isna(num_val) else float(num_val)
            except (ValueError, TypeError):
                parsed_data[key_name_expected_by_its] = str(value_to_process)
        
        if params_requested_count > num_actual_values:
            for i in range(num_actual_values, params_requested_count):
                key_name_missed = self.underlying_api_params_to_request[i]
                parsed_data[key_name_missed] = None
                self.logger.warning(f"Positional mapping for {symbol} (get_und): No value from API for requested param '{key_name_missed}' (expected at index {i}). Setting to None.")

        price_col = self.config_manager.get_setting("strategy_settings.underlying_price_col_name", "price")
        if price_col in parsed_data and parsed_data[price_col] is not None:
            try: parsed_data[price_col] = float(parsed_data[price_col])
            except (ValueError, TypeError): self.logger.warning(f"Could not convert final underlying price field '{price_col}' to float for {symbol}. Value: {parsed_data[price_col]}")
        
        return parsed_data

    def _parse_options_chain_data(self, raw_chain_rows: List[List[Any]], symbol: str) -> pd.DataFrame:
        options_df = pd.DataFrame()
        if not raw_chain_rows:
            self.logger.warning(f"Options chain for {symbol}: No rows provided to parser.")
            return options_df

        df_columns_expected = self.raw_chain_row_prefix_names + self.options_contract_api_params_to_request
        num_expected_cols = len(df_columns_expected)
        
        processed_rows = []
        for i, row_data in enumerate(raw_chain_rows):
            if not isinstance(row_data, list):
                self.logger.warning(f"Chain row {i} for {symbol} not a list. Skipping. Type: {type(row_data)}, Data: {str(row_data)[:100]}")
                continue
            if len(row_data) != num_expected_cols:
                self.logger.warning(f"Chain row {i} for {symbol}: Expected {num_expected_cols} cols (prefix:{len(self.raw_chain_row_prefix_names)} + addtl:{len(self.options_contract_api_params_to_request)}), "
                                    f"got {len(row_data)}. Skipping. Expected cols: {df_columns_expected}. Row data (first 5): {str(row_data[:5])}...")
                continue
            processed_rows.append(row_data)
        
        if not processed_rows:
            self.logger.warning(f"Options chain for {symbol}: No valid rows after structural check.")
            return options_df

        try:
            options_df = pd.DataFrame(processed_rows, columns=df_columns_expected)
            self.logger.debug(f"ChainFetch ({symbol}): DataFrame from rows, shape: {options_df.shape}.")
        except Exception as e_df_create:
            self.logger.error(f"ChainFetch ({symbol}): Error creating DataFrame from rows: {e_df_create}", exc_info=True)
            return pd.DataFrame()

        rename_map = {
            self.raw_chain_row_prefix_names[0]: "option_symbol_api_raw",
            self.raw_chain_row_prefix_names[1]: self.cfg_exp_col_name,
            self.raw_chain_row_prefix_names[2]: self.cfg_strike_col_name,
            self.raw_chain_row_prefix_names[3]: self.cfg_opt_kind_col_name
        }
        options_df.rename(columns=rename_map, inplace=True, errors='ignore')

        if self.cfg_exp_col_name in options_df.columns:
            try:
                exp_data = pd.to_numeric(options_df[self.cfg_exp_col_name], errors='coerce')
                options_df[self.cfg_exp_col_name] = exp_data 
                def convert_exp_to_date_str(exp_val):
                    if pd.isna(exp_val): return None
                    try: return (date(1970, 1, 1) + timedelta(days=int(exp_val))).strftime('%Y-%m-%d')
                    except: 
                        try: return datetime.strptime(str(int(exp_val)), '%Y%m%d').strftime('%Y-%m-%d')
                        except: return str(exp_val)
                options_df["expiration_date_str_calc"] = exp_data.apply(convert_exp_to_date_str)
            except Exception as e_exp: self.logger.error(f"Error processing expiration '{self.cfg_exp_col_name}' for {symbol}: {e_exp}")

        if self.cfg_opt_kind_col_name in options_df.columns:
            options_df[self.cfg_opt_kind_col_name] = options_df[self.cfg_opt_kind_col_name].astype(str).str.lower().str.strip()
        if self.cfg_strike_col_name in options_df.columns:
            options_df[self.cfg_strike_col_name] = pd.to_numeric(options_df[self.cfg_strike_col_name], errors='coerce')
        
        for col_name in self.options_contract_api_params_to_request:
            if col_name in options_df.columns and options_df[col_name].dtype == 'object':
                is_numeric_candidate = False
                numeric_keywords = ["price", "value", "oi", "volm", "volatility", "delta", "gamma", "theta", "vega", "vanna", "vomma", "charm", "multiplier"]
                numeric_suffixes = ["xoi", "xvolm", "_bs", "_5m", "_15m", "_30m", "_60m", "_buy", "_sell"]
                if col_name.lower() in numeric_keywords: is_numeric_candidate = True
                if not is_numeric_candidate:
                    for suffix in numeric_suffixes:
                        if col_name.lower().endswith(suffix): is_numeric_candidate = True; break
                if is_numeric_candidate:
                    try: options_df[col_name] = pd.to_numeric(options_df[col_name], errors='coerce')
                    except: pass
        
        if 'multiplier' in options_df.columns: # Ensure multiplier is numeric
            options_df['multiplier'] = pd.to_numeric(options_df['multiplier'], errors='coerce')
            # Check if all multipliers are the same for this underlying, or if any are NaN
            if not options_df.empty and options_df['multiplier'].notna().all():
                if options_df['multiplier'].nunique() > 1:
                    self.logger.warning(f"ChainFetch ({symbol}): Multiple different 'multiplier' values found in chain data. This is unusual. Values: {options_df['multiplier'].unique()}")
            elif not options_df.empty: # Some NaNs exist
                self.logger.warning(f"ChainFetch ({symbol}): Some 'multiplier' values are NaN. Defaulting NaNs if a common multiplier exists.")
                common_multiplier = options_df['multiplier'].mode()
                if not common_multiplier.empty:
                    options_df['multiplier'].fillna(common_multiplier[0], inplace=True)
                else: # All are NaN or no clear mode
                     default_mult_cfg = self.config_manager.get_setting("strategy_settings.contract_multiplier_default_value", 100.0)
                     options_df['multiplier'].fillna(default_mult_cfg, inplace=True)
                     self.logger.warning(f"Filled NaN multipliers for {symbol} with default from config: {default_mult_cfg}")


        # **REMOVED EXTRACTION OF UNDERLYING OHLCV FROM CHAIN**
        # The fields like 'day_open_price' if present in chain's additional params,
        # refer to the OPTION's OHLCV, not the underlying's.
        # Underlying OHLCV for ATR/HP_EOD must come from a different source or specific get_und params if confirmed.
        return options_df

    def fetch_options_chain_and_underlying(
        self, symbol: str,
        dte_list_override: Optional[List[int]] = None,
        price_range_pct_override: Optional[float] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        symbol_upper = symbol.strip().upper()
        self.logger.info(f"Fetching data for {symbol_upper} (DTEs: {dte_list_override or 'config_default'}, RangePct: {price_range_pct_override or 'config_default'})")
        overall_fetch_start_time_dt = datetime.now()
        overall_fetch_start_time_iso = overall_fetch_start_time_dt.isoformat()

        if not self.api: 
            err_msg = f"API client not connected. Cannot fetch data for {symbol_upper}."
            self.logger.error(err_msg)
            return pd.DataFrame(), {"error": err_msg, "symbol": symbol_upper, "fetch_timestamp_payload": overall_fetch_start_time_iso}

        und_data_dict: Dict[str, Any] = {"symbol": symbol_upper, "fetch_timestamp_payload": overall_fetch_start_time_iso}
        if not self.underlying_api_params_to_request: # Critical check from config
            und_data_dict["error"] = "CRITICAL_CONFIG: 'strategy_settings.api_params_get_und' is empty in config. `get_und` call cannot proceed meaningfully."
            self.logger.error(und_data_dict["error"])
        else:
            try:
                @retry_api_call(retries=self.max_retries_cfg, base_delay=self.base_retry_delay_cfg,
                                max_delay=self.max_retry_delay_cfg, logger_instance=self.logger, 
                                expected_response_type=dict, func_name_override=f"{symbol_upper}_get_und")
                def _get_und_retried(sym: str, params_list: List[str]):
                    if self.api: return self.api.get_und(symbols=[sym], params=params_list)
                    return {"error": "API client not available in _get_und_retried"}
                
                raw_und_response = _get_und_retried(symbol_upper, self.underlying_api_params_to_request)

                if isinstance(raw_und_response, dict) and not raw_und_response.get("error"):
                    parsed_und_data = self._parse_underlying_data(raw_und_response, symbol_upper)
                    und_data_dict.update(parsed_und_data)
                    if parsed_und_data.get("error_parsing") or parsed_und_data.get("warning_param_mismatch_critical"):
                        # Prioritize critical mismatch warning
                        und_data_dict["error"] = parsed_und_data.get("warning_param_mismatch_critical") or parsed_und_data.get("error_parsing")
                else:
                    error_msg = raw_und_response.get("error", "Unknown error/empty response from get_und") if isinstance(raw_und_response, dict) else f"Unexpected get_und type: {type(raw_und_response)}"
                    self.logger.error(f"Underlying data fetch FAILED for {symbol_upper}: {error_msg}")
                    und_data_dict["error"] = error_msg
            except Exception as e_und:
                self.logger.error(f"Exception in underlying fetch for {symbol_upper}: {e_und}", exc_info=True)
                und_data_dict["error"] = f"Underlying fetch exception: {str(e_und)[:150]}"
        
        if self.inter_call_delay > 0 and not und_data_dict.get("error"): # Only delay if first call was okay
             time.sleep(self.inter_call_delay)

        options_df = pd.DataFrame()
        eff_dte_list = dte_list_override if dte_list_override is not None else self.default_dte_range_cfg
        eff_price_range_decimal = (price_range_pct_override / 100.0) if price_range_pct_override is not None else self.default_price_range_pct_cfg
        
        if not self.options_contract_api_params_to_request and not und_data_dict.get("error"): # Only warn if get_und didn't already fail
             self.logger.warning(f"No options contract (additional) parameters configured for {symbol_upper} in 'api_params_get_chain_additional'. Fetching get_chain with only prefix columns if API supports that.")
        
        try:
            @retry_api_call(retries=self.max_retries_cfg, base_delay=self.base_retry_delay_cfg,
                            max_delay=self.max_retry_delay_cfg, logger_instance=self.logger, 
                            expected_response_type=list, func_name_override=f"{symbol_upper}_get_chain")
            def _get_chain_retried(sym: str, params_list: List[str], exps_list: List[int], rng_dec: float):
                if self.api: return self.api.get_chain_as_rows(root=sym, params=params_list, exps=exps_list, rng=rng_dec)
                return [] 

            raw_chain_rows = _get_chain_retried(symbol_upper, self.options_contract_api_params_to_request, eff_dte_list, eff_price_range_decimal)
            
            if isinstance(raw_chain_rows, list): 
                options_df = self._parse_options_chain_data(raw_chain_rows, symbol_upper)
                if not options_df.empty:
                    options_df[self.cfg_und_sym_col_name] = symbol_upper
                    price_col_key_und = self.config_manager.get_setting("strategy_settings.underlying_price_col_name", "price")
                    current_und_price_val = und_data_dict.get(price_col_key_und) # From get_und
                    valid_price_for_df = float(current_und_price_val) if isinstance(current_und_price_val, (int, float)) and pd.notna(current_und_price_val) else np.nan
                    options_df["underlying_price_at_fetch"] = valid_price_for_df
                    options_df["fetch_timestamp"] = overall_fetch_start_time_iso
                    options_df["processing_time_dt_obj"] = overall_fetch_start_time_dt # For DTE calc by MetricsCalculator
        except Exception as e_chain:
            self.logger.error(f"Exception during chain fetch for {symbol_upper}: {e_chain}", exc_info=True)
            error_key_chain = "error_chain_fetch_exception"
            current_error = und_data_dict.get("error", "") 
            separator = " | " if current_error else ""
            und_data_dict["error"] = f"{current_error}{separator}{error_key_chain}: {str(e_chain)[:150]}"

        self.logger.info(f"Data fetch cycle for {symbol_upper} complete. Options DF shape: {options_df.shape}. "
                         f"Und data keys: {len(und_data_dict)}. Error: {und_data_dict.get('error')}")
        return options_df, und_data_dict

    def fetch_market_data_bundle(self, symbols: List[str],
                                 dte_list_override: Optional[List[int]] = None,
                                 price_range_pct_override: Optional[float] = None
                                 ) -> Dict[str, Dict[str, Any]]:
        self.logger.info(f"\n--- DataFetcherV2_4: Starting Market Data Bundle Fetch for Symbols: {symbols} ---")
        bundle_fetch_start_time = datetime.now()
        market_data_bundle_output: Dict[str, Dict[str, Any]] = {}

        for i, symbol_iter in enumerate(symbols):
            symbol_iter_upper = symbol_iter.strip().upper()
            if not symbol_iter_upper:
                self.logger.warning(f"Skipping empty symbol at index {i} in bundle request.")
                continue
            
            self.logger.info(f"MarketBundleFetch ({i+1}/{len(symbols)}): Processing '{symbol_iter_upper}'...")
            df_opts, dict_und = self.fetch_options_chain_and_underlying(
                symbol_iter_upper, dte_list_override=dte_list_override, price_range_pct_override=price_range_pct_override
            )
            market_data_bundle_output[symbol_iter_upper] = {
                "options_chain_df_raw": df_opts, 
                "underlying_data_raw": dict_und,
                "fetch_timestamp_bundle_item": bundle_fetch_start_time.isoformat(),
                "fetch_timestamp_underlying_payload": dict_und.get("fetch_timestamp_payload"),
                "symbol": symbol_iter_upper, 
                "error_details": dict_und.get("error") 
            }
            status = "Failed" if market_data_bundle_output[symbol_iter_upper]["error_details"] else \
                     ("Success" if not df_opts.empty else "Success (Options Chain Empty or Not Fetched)")
            self.logger.info(f"MarketBundleFetch ({i+1}/{len(symbols)}): Finished '{symbol_iter_upper}'. Status: {status}.")
            if i < len(symbols) - 1 and self.inter_call_delay > 0:
                self.logger.debug(f"Inter-symbol delay: sleeping for {self.inter_call_delay:.2f}s.")
                time.sleep(self.inter_call_delay)
                
        total_duration = (datetime.now() - bundle_fetch_start_time).total_seconds()
        self.logger.info(f"--- DataFetcherV2_4: Market Data Bundle Fetch COMPLETE for {len(symbols)} symbols in {total_duration:.2f}s ---")
        return market_data_bundle_output

    def shutdown(self) -> None:
        self.logger.info("DataFetcherV2_4 shutting down...")
        self.api = None 
        self.logger.info("DataFetcherV2_4 shutdown complete.")

# --- Main Test Block (Example Usage) ---
if __name__ == '__main__': # pragma: no cover
    # This block is for direct testing of fetcher.py.
    # Requires a .env file and a config_v2_4.json in the project root.
    if not logging.getLogger("EOTS_SystemRunnerV2.4").handlers: 
        test_format = '[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s'
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format=test_format, datefmt="%Y-%m-%d %H:%M:%S")
    
    module_test_logger = logging.getLogger(f"{__name__}_TestMain") # Use a distinct logger for test output
    module_test_logger.setLevel(logging.DEBUG) # Ensure test logger is verbose
    module_test_logger.info("--- Starting DataFetcherV2_4 Standalone Test (Phase 2 API Aligned) ---")
    
    # --- Standalone ConfigManager Setup for Test ---
    class StandaloneTestConfigManager: # Simplified ConfigManager for testing fetcher
        _config = {}
        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Assumes fetcher.py is in data_management/
        
        def __init__(self, config_file_name="config_v2_4.json", schema_file_name=None): # Schema optional for this test
            self.logger = logging.getLogger(f"{__name__}.StandaloneTestConfigManager")
            config_path = os.path.join(self._project_root, config_file_name)
            self.logger.info(f"TestConfigManager: Attempting to load config from {config_path}")
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f: self._config = json.load(f)
                    self.logger.info(f"TestConfigManager: Config loaded from {config_path}.")
                    # Basic validation if schema provided - production runner does full validation
                    if schema_file_name:
                        schema_path = os.path.join(self._project_root, schema_file_name)
                        if os.path.exists(schema_path):
                            from jsonschema import validate, ValidationError # type: ignore
                            with open(schema_path, 'r') as sf: schema_data = json.load(sf)
                            try: validate(instance=self._config, schema=schema_data); self.logger.info("TestConfigManager: Basic schema validation passed.")
                            except ValidationError as ve_test: self.logger.error(f"TestConfigManager: Schema validation FAILED: {ve_test.message}")
                        else: self.logger.warning(f"TestConfigManager: Schema file {schema_path} not found for validation.")
                except Exception as e_cfg_load:
                     self.logger.error(f"TestConfigManager: Error loading config {config_path}: {e_cfg_load}")
                     self._config = {} # Ensure empty on error
            else: 
                self.logger.error(f"TestConfigManager: Test config file {config_path} NOT FOUND!")
                self._config = {}

        def get_setting(self, key_path: Union[str, List[str]], default: Any = None, quiet: bool = False) -> Any:
            keys = key_path.split('.') if isinstance(key_path, str) else key_path; val = self._config
            try:
                for k in keys: val = val[k]
                return val if val is not None else default
            except KeyError: 
                if not quiet: self.logger.debug(f"TestConfigManager: Key '{key_path}' not found, returning default {default}.")
                return default
            except TypeError: # val became non-dict before end of path
                if not quiet: self.logger.debug(f"TestConfigManager: Path segment invalid for '{key_path}', returning default {default}.")
                return default

        def get_resolved_path(self, key_path: Union[str, List[str]], default_relative_path: Optional[str] = None, quiet: bool = False) -> Optional[str]:
            raw_path = self.get_setting(key_path, default_relative_path, quiet=quiet)
            if isinstance(raw_path, str):
                if os.path.isabs(raw_path): return os.path.normpath(raw_path)
                return os.path.normpath(os.path.join(self._project_root, raw_path))
            return None

    test_cm_instance = StandaloneTestConfigManager(config_file_name="config_v2_4.json") # Use your actual config
    if not test_cm_instance._config:
        module_test_logger.critical("Failed to load config for standalone fetcher test. Aborting.")
        sys.exit(1)
    # --- End Standalone ConfigManager Setup ---

    # Load .env for credentials for the test
    try:
        from dotenv import load_dotenv
        project_r_env = StandaloneTestConfigManager._project_root # Use class variable if instance one not set yet for paths
        env_p = os.path.join(project_r_env if project_r_env else os.getcwd(), ".env")
        if os.path.exists(env_p): load_dotenv(dotenv_path=env_p, verbose=True, override=True); module_test_logger.info(f"Test .env loaded: {env_p}")
        else: module_test_logger.warning(f"Test .env not found: {env_p}")
    except ImportError: module_test_logger.warning("'python-dotenv' not installed for test .env loading.")


    if not (os.getenv(test_cm_instance.get_setting("api_credentials.email_env_var", "CONVEX_EMAIL")) and \
            os.getenv(test_cm_instance.get_setting("api_credentials.password_env_var", "CONVEX_PASSWORD"))):
        module_test_logger.critical("Fetcher Test: CONVEX_EMAIL and CONVEX_PASSWORD (as defined in config) required in environment. Skipping API tests.")
    elif not CONVEXLIB_AVAILABLE :
        module_test_logger.critical("Fetcher Test: Convexlib is not available. Skipping API tests.")
    else:
        try:
            fetcher_instance = DataFetcherV2_4(config_manager_instance=test_cm_instance)
            
            if fetcher_instance.api:
                module_test_logger.info(f"Test Fetcher: Underlying Params Loaded from Config: {len(fetcher_instance.underlying_api_params_to_request)}")
                module_test_logger.info(f"Test Fetcher: Chain (Additional) Params Loaded from Config: {len(fetcher_instance.options_contract_api_params_to_request)}")
                
                test_sym_main = "SPY" 
                module_test_logger.info(f"\n--- Testing single fetch for {test_sym_main} (using config-defined DTEs/Range) ---")
                df_main_opts, und_main_data = fetcher_instance.fetch_options_chain_and_underlying(test_sym_main) # Use config defaults
                
                module_test_logger.info(f"{test_sym_main} Underlying Data Keys Count: {len(und_main_data.keys())}")
                if und_main_data.get("error"): module_test_logger.error(f"  {test_sym_main} Underlying/Chain Error: {und_main_data['error']}")
                else: module_test_logger.info(f"  {test_sym_main} Price (from get_und): {und_main_data.get(test_cm_instance.get_setting('strategy_settings.underlying_price_col_name', 'price'))}")
                
                module_test_logger.info(f"{test_sym_main} Options DF Shape: {df_main_opts.shape}")
                if not df_main_opts.empty:
                     module_test_logger.info(f"  {test_sym_main} Options Columns ({len(df_main_opts.columns)}): {df_main_opts.columns.tolist()}")
                     # Check for multiplier in options_df
                     if 'multiplier' in df_main_opts.columns:
                         module_test_logger.info(f"  {test_sym_main} Options 'multiplier' unique values: {df_main_opts['multiplier'].unique()}")
                     else:
                         module_test_logger.warning(f"  {test_sym_main} 'multiplier' column NOT FOUND in options_df.")
                else:
                     module_test_logger.warning(f"  {test_sym_main} Options DataFrame is empty.")
                
                fetcher_instance.shutdown()
            else: module_test_logger.error("Fetcher API client failed to initialize within the test instance for live calls.")
        except Exception as e_fetch_test: 
            module_test_logger.critical(f"Exception during FetcherV2_4 test execution: {e_fetch_test}", exc_info=True)

    module_test_logger.info("--- DataFetcherV2_4 Standalone Test Finished ---")