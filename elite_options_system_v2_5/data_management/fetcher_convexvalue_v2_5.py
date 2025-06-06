# data_management/fetcher_convexvalue_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

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
# This section remains largely the same as v2.4, assuming convexlib is still the way to interact
try:
    from convexlib.api import ConvexApi
    CONVEXLIB_AVAILABLE = True
    _api_import_error_fetcher_cv = None # Renamed to avoid global collision if other fetchers are in same scope
    logger.info("Convexlib API imported successfully by fetcher_convexvalue_v2_5.")
except ImportError as import_error_fetcher_cv_imp:
    logger.critical(f"Fetcher_ConvexValue_v2_5: Could not import ConvexApi: {import_error_fetcher_cv_imp}. Ensure 'convexlib' is installed.", exc_info=False)
    CONVEXLIB_AVAILABLE = False
    _api_import_error_fetcher_cv = import_error_fetcher_cv_imp
    class ConvexApi: # type: ignore # pragma: no cover
        def __init__(self, *args, **kwargs): raise ImportError(f"Dummy ConvexApi (CV Fetcher): convexlib not found. Original error: {_api_import_error_fetcher_cv}")
        def get_und(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi (CV Fetcher) used for get_und.")
        def get_chain_as_rows(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi (CV Fetcher) used for get_chain_as_rows.")
except Exception as general_import_err_fetcher_cv: # pragma: no cover
    logger.critical(f"Fetcher_ConvexValue_v2_5: Unexpected error during ConvexApi import: {general_import_err_fetcher_cv}", exc_info=True)
    CONVEXLIB_AVAILABLE = False
    _api_import_error_fetcher_cv = general_import_err_fetcher_cv
    class ConvexApi: # type: ignore
        def __init__(self, *args, **kwargs): raise ImportError(f"Dummy ConvexApi (CV Fetcher): convexlib not found due to general error. Original error: {_api_import_error_fetcher_cv}")
        def get_und(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi (CV Fetcher) used for get_und due to general error.")
        def get_chain_as_rows(self, *args, **kwargs): raise NotImplementedError("Dummy ConvexApi (CV Fetcher) used for get_chain_as_rows due to general error.")

if not CONVEXLIB_AVAILABLE:
    logger.error("FETCHER_CONVEXVALUE_V2_5 CRITICAL: Convexlib library is not available. ConvexValueDataFetcherV2_5 will operate in a severely limited or non-functional state.")

# --- Retry Decorator (Copied from v2.4 fetcher.py, consider moving to a common utils if widely used) ---
def retry_api_call_cv(retries: int, base_delay: float, max_delay: float, jitter: bool = True,
                   logger_instance: Optional[logging.Logger] = None,
                   expected_response_type: type = dict,
                   func_name_override: Optional[str] = None): # Renamed decorator to avoid collision
    log = logger_instance if logger_instance else logging.getLogger(f"{__name__}.retry_api_call_cv")

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
                        log.warning(f"CV API call {actual_func_name} returned unexpected data type on attempt {attempts + 1}. "
                                    f"Expected {expected_response_type}, got {type(response)}. Response: {str(response)[:200]}")
                        if attempts == retries:
                            log.error(f"CV API call {actual_func_name} failed due to unexpected data type after max retries.")
                            if expected_response_type == dict: return {"error": f"CV API returned unexpected data type for {actual_func_name}"}
                            elif expected_response_type == list: return []
                            else: return None

                    if isinstance(response, dict) and response.get("error"):
                        log.warning(f"CV API call {actual_func_name} returned an error in response dict on attempt {attempts + 1}: {response.get('error')}")
                        if attempts == retries:
                             log.error(f"CV API call {actual_func_name} failed with API-reported error after max retries: {response.get('error')}")
                             return response
                    elif isinstance(response, dict) and response.get("data") is None and "data" in response: # ConvexValue specific
                        log.warning(f"CV API call {actual_func_name} returned dict with 'data' key as None on attempt {attempts+1}.")

                    log.debug(f"CV API call {actual_func_name} successful on attempt {attempts + 1}.")
                    return response

                except (requests.exceptions.HTTPError) as e_http: # type: ignore
                    status_code = e_http.response.status_code if hasattr(e_http, 'response') and e_http.response is not None else 'N/A'
                    response_text = str(e_http.response.text)[:100] if hasattr(e_http, 'response') and e_http.response is not None else 'No response text'
                    log.warning(f"CV API HTTP Error on attempt {attempts + 1} for {actual_func_name}: {status_code} - {response_text}")
                    last_exception = e_http
                    if status_code in [401, 403]: # type: ignore
                        log.error(f"Fatal CV API authentication/authorization error ({status_code}) for {actual_func_name}. Aborting retries.")
                        # For critical auth errors, we might not want to return a simple error dict but raise
                        if expected_response_type == dict: return {"error": f"CV API Auth Error ({status_code}) for {actual_func_name}. Aborting."}
                        elif expected_response_type == list: return []
                        raise last_exception # Re-raise to stop execution if preferred
                    if status_code == 429: # type: ignore
                        log.warning(f"CV API Rate Limit Exceeded (429) for {actual_func_name}. Significantly increasing delay.")
                        current_delay = min(current_delay * 2.5, max_delay * 2.5) # More aggressive backoff
                except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as e_req:
                    log.warning(f"CV API Network/Request Error on attempt {attempts + 1} for {actual_func_name}: {type(e_req).__name__} - {str(e_req)[:150]}")
                    last_exception = e_req
                except Exception as e_gen:
                    log.error(f"Unexpected Error during CV API call attempt {attempts + 1} for {actual_func_name}: {type(e_gen).__name__} - {e_gen}", exc_info=False)
                    if log.getEffectiveLevel() <= logging.DEBUG: log.debug(f"Full traceback for {actual_func_name}:", exc_info=True)
                    last_exception = e_gen

                attempts += 1
                if attempts <= retries:
                    sleep_duration = current_delay + (random.uniform(0, current_delay * 0.2) if jitter else 0)
                    log.info(f"Retrying CV API call {actual_func_name} in {sleep_duration:.2f} seconds... (Attempt {attempts}/{retries})")
                    time.sleep(sleep_duration)
                    current_delay = min(current_delay * 1.8, max_delay) # Standard backoff for next retry
                else:
                    log.error(f"CV API call {actual_func_name} failed after {retries} retries.")
                    final_error_msg = f"CV API call {actual_func_name} failed after max retries."
                    if last_exception:
                        final_error_msg += f" Last error: {type(last_exception).__name__} - {str(last_exception)[:100]}"

                    if expected_response_type == dict: return {"error": final_error_msg}
                    elif expected_response_type == list: return []

                    # If it's an unexpected exception type that wasn't handled above (like auth), re-raise
                    if last_exception and not isinstance(last_exception, (requests.exceptions.HTTPError, requests.exceptions.RequestException)):
                        raise last_exception
                    return None # For handled exception types after retries exhausted

            # This part should ideally not be reached if logic is correct
            log.critical(f"Fell through CV retry loop for {actual_func_name} - this indicates a logic error in retry handling.")
            if expected_response_type == dict: return {"error": "CV Retry loop logic error."}
            elif expected_response_type == list: return []
            return None
        return wrapper
    return decorator


class ConvexValueDataFetcherV2_5:
    def __init__(self, config_manager_v2_5_instance: Any):
        self.logger = logger.getChild(self.__class__.__name__)
        if not hasattr(config_manager_v2_5_instance, 'get_setting') or not hasattr(config_manager_v2_5_instance, 'get_resolved_path_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5 instance. Functionality will be severely impaired.")
            class DummyConfigManager: # Fallback
                def get_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    return default_value_to_return
                def get_resolved_path_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    # Simplified: still return None for path if it's a dummy
                    return None
            self.config_manager = DummyConfigManager() # type: ignore
        else:
            self.config_manager = config_manager_v2_5_instance

        self.logger.info(f"Initializing ConvexValueDataFetcherV2_5 (ConfigManagerV2_5 Integrated)...")

        if not CONVEXLIB_AVAILABLE:
            self.logger.critical("Convexlib not loaded. ConvexValueDataFetcherV2_5 cannot function for live data.")
            self.api: Optional[ConvexApi] = None
            self._load_config_settings_for_cv_fetcher(minimal=True)
            return

        self._load_config_settings_for_cv_fetcher()
        self._load_credentials_from_env()

        self.api: Optional[ConvexApi] = None
        if self.email and self.password:
            try:
                @retry_api_call_cv(retries=max(1, self.max_retries_cfg // 2),
                                base_delay=self.base_retry_delay_cfg,
                                max_delay=self.max_retry_delay_cfg,
                                logger_instance=self.logger,
                                expected_response_type=type(None),
                                func_name_override="_connect_to_cv_api_internal_retried")
                def connect_with_retry_cv():
                    self._connect_to_cv_api_internal()

                connect_with_retry_cv()
                if self.api:
                     self.logger.info(f"ConvexValueDataFetcherV2_5 Initialized. API connection for env '{self.api_env}' successful.")
                else:
                     self.logger.error(f"ConvexValueDataFetcherV2_5 Initialized, but API connection for env '{self.api_env}' FAILED after retries.")
            except Exception as e_conn_final:
                self.logger.error(f"Initial CV API connection attempt FAILED critically: {type(e_conn_final).__name__} - {e_conn_final}")
                self.api = None
        else:
            self.logger.error("CV API credentials (email or password) missing. Cannot attempt to connect to API.")

        if not self.api:
            self.logger.warning("ConvexValueDataFetcherV2_5 API client is not connected. Operations requiring API will fail or return empty/error data.")

    def _load_config_settings_for_cv_fetcher(self, minimal: bool = False):
        self.logger.debug(f"Loading ConvexValue fetcher configurations (minimal={minimal})...")

        # These config paths are examples and MUST be aligned with the actual config_v2_5.json structure
        # For example, 'data_fetcher_settings.convexvalue.api_credentials'
        # and 'data_fetcher_settings.convexvalue.fetch_config'

        # Using more specific paths as per v2.5 guide's implication of modularity
        cv_base_path = ["data_fetcher_settings", "convexvalue"] # Base path for CV specific settings

        cred_path = cv_base_path + ["api_credentials"]
        self.api_email_env_var: str = self.config_manager.get_setting(*cred_path, "email_env_var", default_value_to_return="CONVEX_EMAIL")
        self.api_password_env_var: str = self.config_manager.get_setting(*cred_path, "password_env_var", default_value_to_return="CONVEX_PASSWORD")
        self.api_env: str = self.config_manager.get_setting(*cred_path, "environment", default_value_to_return="pro")

        fetch_cfg_path = cv_base_path + ["fetch_config"]
        self.max_retries_cfg: int = int(self.config_manager.get_setting(*fetch_cfg_path, "max_retries", default_value_to_return=3 if not minimal else 1))
        self.base_retry_delay_cfg: float = float(self.config_manager.get_setting(*fetch_cfg_path, "base_retry_delay_seconds", default_value_to_return=1.0 if not minimal else 0.2))
        self.max_retry_delay_cfg: float = float(self.config_manager.get_setting(*fetch_cfg_path, "max_retry_delay_seconds", default_value_to_return=10.0 if not minimal else 0.5))
        self.inter_call_delay: float = float(self.config_manager.get_setting(*fetch_cfg_path, "inter_call_delay_seconds", default_value_to_return=0.25 if not minimal else 0.05))
        self.default_dte_range_cfg: List[int] = self.config_manager.get_setting(*fetch_cfg_path, "default_dte_range", default_value_to_return=[0, 1, 7, 14, 30, 60, 90])
        self.default_price_range_pct_cfg: float = float(self.config_manager.get_setting(*fetch_cfg_path, "default_price_range_pct", default_value_to_return=0.075))


        # API parameter lists should come from a section detailing data requirements, e.g., 'metrics_io_params.convexvalue_fields'
        # For now, using placeholder paths that need to be confirmed with final config_v2_5.json
        api_fields_path = ["metrics_io_params", "convexvalue_fields"] # Example path
        self.underlying_api_params_to_request: List[str] = list(OrderedDict.fromkeys(
            self.config_manager.get_setting(*api_fields_path, "get_und_params", default_value_to_return=[])
        ))
        if not self.underlying_api_params_to_request and not minimal:
            self.logger.critical(f"CV FETCHER CONFIG ERROR (v2.5): '{'.'.join(api_fields_path + ['get_und_params'])}' is empty or path invalid. `get_und` calls may fail.")

        self.options_contract_api_params_to_request: List[str] = sorted(list(set(
             self.config_manager.get_setting(*api_fields_path, "get_chain_additional_params", default_value_to_return=[])
        )))
        if not self.options_contract_api_params_to_request and not minimal:
            self.logger.warning(f"CV Fetcher Config (v2.5): '{'.'.join(api_fields_path + ['get_chain_additional_params'])}' is empty or path invalid.")

        self.raw_chain_row_prefix_names: List[str] = self.config_manager.get_setting(
            *api_fields_path, "get_chain_prefix_params",
            default_value_to_return=["api_temp_contract_symbol", "api_temp_expiration", "api_temp_strike", "api_temp_opt_kind"]
        )

        # Column name mappings for internal use, from config_v2_5.json
        col_map_base = ["column_name_mappings", "convexvalue_internal"] # Example path
        self.cfg_exp_col_name: str = self.config_manager.get_setting(*col_map_base, "expiration_col_name", default_value_to_return="expiration_days_from_epoch_calc")
        self.cfg_strike_col_name: str = self.config_manager.get_setting(*col_map_base, "strike_col_name", default_value_to_return="strike")
        self.cfg_opt_kind_col_name: str = self.config_manager.get_setting(*col_map_base, "option_kind_col_name", default_value_to_return="opt_kind")
        self.cfg_und_sym_col_name: str = self.config_manager.get_setting(*col_map_base, "underlying_symbol_col_name", default_value_to_return="underlying_symbol")
        self.cfg_und_price_col_name: str = self.config_manager.get_setting(*col_map_base, "underlying_price_col_name", default_value_to_return="price")


        self.logger.info(f"CV Fetcher v2.5 loaded {len(self.underlying_api_params_to_request)} underlying params and "
                         f"{len(self.options_contract_api_params_to_request)} options contract (additional) params from config.")

    def _load_credentials_from_env(self):
        self.logger.debug(f"Loading CV API credentials from ENV vars: '{self.api_email_env_var}', '{self.api_password_env_var}'")
        self.email = os.getenv(self.api_email_env_var)
        self.password = os.getenv(self.api_password_env_var)
        if not (self.email and self.password):
            self.logger.error(f"CV API Credentials NOT FOUND in environment variables ('{self.api_email_env_var}', '{self.api_password_env_var}').")
        elif self.email and self.password:
            self.logger.info(f"CV API credentials found in environment variables ('{self.api_email_env_var}', password present).")

    def _connect_to_cv_api_internal(self) -> None:
        if not CONVEXLIB_AVAILABLE: raise ConnectionError("Convexlib library not available for CV Fetcher.")
        if not (self.email and self.password): raise ConnectionError("CV API credentials missing for CV Fetcher.")
        self.logger.info(f"Attempting ConvexAPI connection for env: '{self.api_env}' with user: {str(self.email)[:3]}***...")
        try:
            self.api = ConvexApi(self.email, self.password)
            self.logger.info(f"ConvexApi object instantiated for CV Fetcher. Connection assumed successful.")
        except Exception as e_api_init:
            self.logger.error(f"Failed to instantiate ConvexApi client for CV Fetcher: {type(e_api_init).__name__} - {e_api_init}", exc_info=True)
            self.api = None
            raise ConnectionError(f"ConvexApi instantiation failed for CV Fetcher: {e_api_init}") from e_api_init

    def _parse_underlying_data(self, raw_response_data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        parsed_data: Dict[str, Any] = {"symbol": symbol.upper(), "fetch_timestamp_parser_cv": datetime.now().isoformat()}
        self.logger.debug(f"Parsing CV underlying data for {symbol} (v2.5). Response head: {str(raw_response_data)[:250]}")

        api_data_list = raw_response_data.get("data")
        if isinstance(api_data_list, list) and len(api_data_list) == 1 and \
            isinstance(api_data_list[0], list) and len(api_data_list[0]) == 1 and \
            isinstance(api_data_list[0][0], list) and \
            len(api_data_list[0][0]) > 0 and isinstance(api_data_list[0][0][0], str):
            self.logger.debug(f"CV Fetcher V2.5: Unwrapping extra list nesting in get_und response for {symbol}.")
            api_data_list = api_data_list[0]

        if not isinstance(api_data_list, list) or not api_data_list or \
            not isinstance(api_data_list[0], list) or not api_data_list[0] or \
            not isinstance(api_data_list[0][0], str):
            parsed_data["error_parsing_cv"] = f"CV Underlying 'data' malformed/empty for {symbol}. Resp: {str(raw_response_data)[:200]}"
            self.logger.warning(parsed_data["error_parsing_cv"])
            return parsed_data

        symbol_data_values_list = api_data_list[0]
        api_symbol = symbol_data_values_list[0]
        actual_values = symbol_data_values_list[1:]

        if api_symbol.upper() != symbol.upper():
            self.logger.warning(f"CV Symbol mismatch: Expected '{symbol.upper()}', API returned '{api_symbol.upper()}'.")
        parsed_data["api_response_symbol_und_cv"] = api_symbol

        params_requested_count = len(self.underlying_api_params_to_request)
        num_actual_values = len(actual_values)

        if num_actual_values != params_requested_count:
            warn_msg = (f"CV Positional Mapping CRITICAL WARNING for {symbol} (get_und): "
                        f"Requested {params_requested_count} params, API returned {num_actual_values}. MISALIGNMENT LIKELY! "
                        f"Requested: {self.underlying_api_params_to_request}, Got (first 5): {actual_values[:5]}...")
            self.logger.error(warn_msg)
            parsed_data["warning_param_mismatch_critical_cv"] = warn_msg

        max_len_to_parse = min(num_actual_values, params_requested_count)
        for i in range(max_len_to_parse):
            key_name = self.underlying_api_params_to_request[i]
            value = actual_values[i]
            try: parsed_data[key_name] = float(value) if pd.notna(value) and value is not None else None # Ensure None for various "empty"
            except (ValueError, TypeError): parsed_data[key_name] = str(value) if value is not None else None

        if self.cfg_und_price_col_name in parsed_data and parsed_data[self.cfg_und_price_col_name] is not None:
             try: parsed_data[self.cfg_und_price_col_name] = float(parsed_data[self.cfg_und_price_col_name])
             except (ValueError, TypeError): self.logger.warning(f"Could not convert CV underlying price field '{self.cfg_und_price_col_name}' to float for {symbol}.")
        return parsed_data

    def _parse_options_chain_data(self, raw_chain_rows: List[List[Any]], symbol: str) -> pd.DataFrame:
        self.logger.debug(f"Parsing CV options chain data for {symbol} (v2.5). Num rows: {len(raw_chain_rows)}")
        if not raw_chain_rows: return pd.DataFrame()

        df_columns_expected = self.raw_chain_row_prefix_names + self.options_contract_api_params_to_request
        num_expected_cols = len(df_columns_expected)

        valid_rows = [row for row in raw_chain_rows if isinstance(row, list) and len(row) == num_expected_cols]
        if len(valid_rows) != len(raw_chain_rows):
            self.logger.warning(f"CV Chain for {symbol}: Dropped {len(raw_chain_rows) - len(valid_rows)} malformed rows.")
        if not valid_rows: return pd.DataFrame()

        try:
            options_df = pd.DataFrame(valid_rows, columns=df_columns_expected)
            rename_map = {
                self.raw_chain_row_prefix_names[0]: "option_symbol_api_raw_cv", # Distinguish if needed
                self.raw_chain_row_prefix_names[1]: self.cfg_exp_col_name,
                self.raw_chain_row_prefix_names[2]: self.cfg_strike_col_name,
                self.raw_chain_row_prefix_names[3]: self.cfg_opt_kind_col_name
            }
            options_df.rename(columns=rename_map, inplace=True, errors='ignore')

            if self.cfg_exp_col_name in options_df.columns:
                 options_df[self.cfg_exp_col_name] = pd.to_numeric(options_df[self.cfg_exp_col_name], errors='coerce')
            if self.cfg_strike_col_name in options_df.columns:
                 options_df[self.cfg_strike_col_name] = pd.to_numeric(options_df[self.cfg_strike_col_name], errors='coerce')
            if self.cfg_opt_kind_col_name in options_df.columns:
                options_df[self.cfg_opt_kind_col_name] = options_df[self.cfg_opt_kind_col_name].astype(str).str.lower().str.strip()

            for col_name in self.options_contract_api_params_to_request: # Convert known numeric types
                if col_name in options_df.columns and options_df[col_name].dtype == 'object':
                    # Basic check for numeric potential, can be expanded
                    if any(kw in col_name.lower() for kw in ['price', 'value', 'oi', 'vol', 'delta', 'gamma', 'theta', 'vega', 'iv']):
                        options_df[col_name] = pd.to_numeric(options_df[col_name], errors='coerce')
            return options_df
        except Exception as e:
            self.logger.error(f"Error parsing CV chain data to DataFrame for {symbol} in v2.5: {e}", exc_info=True)
            return pd.DataFrame()

    def fetch_options_chain_and_underlying(
        self, symbol: str,
        dte_list_override: Optional[List[int]] = None,
        price_range_pct_override: Optional[float] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        symbol_upper = symbol.strip().upper()
        self.logger.info(f"Fetching CV data for {symbol_upper} (v2.5 Fetcher) - DTEs: {dte_list_override or 'config_default'}, RangePct: {price_range_pct_override or 'config_default'})")
        overall_fetch_start_time_dt = datetime.now()
        overall_fetch_start_time_iso = overall_fetch_start_time_dt.isoformat()

        if not self.api:
            err_msg = f"CV API client not connected. Cannot fetch data for {symbol_upper}."
            self.logger.error(err_msg)
            return pd.DataFrame(), {"error_cv": err_msg, "symbol": symbol_upper, "fetch_timestamp_payload_cv": overall_fetch_start_time_iso}

        und_data_dict: Dict[str, Any] = {"symbol": symbol_upper, "fetch_timestamp_payload_cv": overall_fetch_start_time_iso}

        if not self.underlying_api_params_to_request:
            und_data_dict["error_cv"] = "CRITICAL_CONFIG_CV_V2.5: 'get_und_params' list empty. `get_und` call aborted."
            self.logger.error(und_data_dict["error_cv"])
        else:
            try:
                @retry_api_call_cv(retries=self.max_retries_cfg, base_delay=self.base_retry_delay_cfg,
                                max_delay=self.max_retry_delay_cfg, logger_instance=self.logger,
                                expected_response_type=dict, func_name_override=f"{symbol_upper}_get_und_cv_v2.5")
                def _get_und_retried_cv(sym: str, params_list: List[str]):
                    if self.api: return self.api.get_und(symbols=[sym], params=params_list)
                    return {"error": "CV API client not available in _get_und_retried_cv"}

                raw_und_response = _get_und_retried_cv(symbol_upper, self.underlying_api_params_to_request)
                if isinstance(raw_und_response, dict) and not raw_und_response.get("error"):
                    parsed_und_data = self._parse_underlying_data(raw_und_response, symbol_upper)
                    und_data_dict.update(parsed_und_data)
                    if parsed_und_data.get("error_parsing_cv") or parsed_und_data.get("warning_param_mismatch_critical_cv"):
                        und_data_dict["error_cv"] = parsed_und_data.get("warning_param_mismatch_critical_cv") or parsed_und_data.get("error_parsing_cv")
                else:
                    error_msg = raw_und_response.get("error", "Unknown error from CV get_und") if isinstance(raw_und_response, dict) else f"Unexpected CV get_und type: {type(raw_und_response)}"
                    self.logger.error(f"CV Underlying data fetch FAILED for {symbol_upper}: {error_msg}")
                    und_data_dict["error_cv"] = error_msg
            except Exception as e_und:
                self.logger.error(f"Exception in CV underlying fetch for {symbol_upper}: {e_und}", exc_info=True)
                und_data_dict["error_cv"] = f"CV Underlying fetch exception: {str(e_und)[:150]}"

        if self.inter_call_delay > 0 and not und_data_dict.get("error_cv"): time.sleep(self.inter_call_delay)

        options_df = pd.DataFrame()
        eff_dte_list = dte_list_override if dte_list_override is not None else self.default_dte_range_cfg
        eff_price_range_decimal = (price_range_pct_override / 100.0) if price_range_pct_override is not None else self.default_price_range_pct_cfg

        try:
            @retry_api_call_cv(retries=self.max_retries_cfg, base_delay=self.base_retry_delay_cfg,
                            max_delay=self.max_retry_delay_cfg, logger_instance=self.logger,
                            expected_response_type=list, func_name_override=f"{symbol_upper}_get_chain_cv_v2.5")
            def _get_chain_retried_cv(sym: str, params_list: List[str], exps_list: List[int], rng_dec: float):
                if self.api: return self.api.get_chain_as_rows(root=sym, params=params_list, exps=exps_list, rng=rng_dec)
                return []

            raw_chain_rows = _get_chain_retried_cv(symbol_upper, self.options_contract_api_params_to_request, eff_dte_list, eff_price_range_decimal)
            if isinstance(raw_chain_rows, list):
                options_df = self._parse_options_chain_data(raw_chain_rows, symbol_upper)
                if not options_df.empty:
                    options_df[self.cfg_und_sym_col_name] = symbol_upper
                    current_und_price_val = und_data_dict.get(self.cfg_und_price_col_name) # Uses v2.5 config for name
                    options_df["underlying_price_at_fetch_cv"] = float(current_und_price_val) if isinstance(current_und_price_val, (int,float)) and pd.notna(current_und_price_val) else np.nan
                    options_df["fetch_timestamp_cv"] = overall_fetch_start_time_iso
                    options_df["processing_time_dt_obj_cv"] = overall_fetch_start_time_dt # For DTE calc
        except Exception as e_chain:
            self.logger.error(f"Exception during CV chain fetch for {symbol_upper}: {e_chain}", exc_info=True)
            current_error_str = und_data_dict.get("error_cv", "")
            und_data_dict["error_cv"] = f"{current_error_str}{' | ' if current_error_str else ''}CV Chain fetch exception: {str(e_chain)[:100]}"

        self.logger.info(f"CV Data fetch cycle for {symbol_upper} (v2.5) complete. Options DF shape: {options_df.shape}. "
                         f"Und data keys: {len(und_data_dict)}. Error: {und_data_dict.get('error_cv')}")
        return options_df, und_data_dict

    def shutdown(self) -> None:
        self.logger.info("ConvexValueDataFetcherV2_5 shutting down...")
        self.api = None
        self.logger.info("ConvexValueDataFetcherV2_5 shutdown complete.")
