# data_management/fetcher_tradier_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

# Standard Library Imports
import os
import time
import logging
import json
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union, Callable
from functools import wraps

# Third-Party Imports
import requests

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

# --- Retry Decorator (Copied from v2.4 tradier_data_fetcher.py, consider moving to common utils) ---
def tradier_retry_api_call_v2_5(
    retries_param: int,
    base_delay_seconds_param: float,
    max_delay_seconds_param: float,
    jitter_param: bool = True,
    logger_instance_param: Optional[logging.Logger] = None,
    expected_response_type_param: type = dict,
    func_name_override_param: Optional[str] = None
):
    log = logger_instance_param if logger_instance_param else logging.getLogger(f"{__name__}.tradier_retry_api_call_v2_5")

    def decorator(func: Callable):
        actual_func_name = func_name_override_param if func_name_override_param else func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = base_delay_seconds_param
            last_exception: Optional[BaseException] = None
            response_content_for_error: Optional[str] = None # Store response text for better error logging

            while attempts <= retries_param:
                try:
                    response_obj: requests.Response = func(*args, **kwargs)

                    if not isinstance(response_obj, requests.Response):
                        log.error(f"Tradier API call {actual_func_name} (wrapper target) did not return requests.Response. Got: {type(response_obj)}. Internal error.")
                        if expected_response_type_param == dict: return {"error": f"Internal error: {actual_func_name} did not return Response."}
                        elif expected_response_type_param == list: return []
                        return None # Or raise

                    response_content_for_error = str(response_obj.text)[:500] # Capture for potential JSON error
                    response_obj.raise_for_status() # Check for 4xx/5xx HTTP errors first

                    parsed_response = response_obj.json() # Attempt to parse JSON

                    # Tradier specific: Check for 'fault' or 'errors' object
                    if isinstance(parsed_response, dict):
                        if "fault" in parsed_response:
                            fault_detail = parsed_response.get("fault", {}).get("detail", "Unknown API fault")
                            fault_string = parsed_response.get("fault", {}).get("faultstring", "N/A")
                            log.warning(f"Tradier API 'fault' in {actual_func_name} (Attempt {attempts + 1}): {fault_string} - {fault_detail}")
                            last_exception = RuntimeError(f"Tradier API Fault: {fault_string} - {fault_detail}")
                            raise last_exception # Trigger retry for API-level fault
                        if "errors" in parsed_response and parsed_response["errors"] and "error" in parsed_response["errors"]:
                            error_details = parsed_response["errors"]["error"]
                            log.warning(f"Tradier API 'errors' in {actual_func_name} (Attempt {attempts + 1}): {error_details}")
                            last_exception = RuntimeError(f"Tradier API Error(s): {error_details}")
                            raise last_exception # Trigger retry for API-level error

                    if not isinstance(parsed_response, expected_response_type_param):
                        log.warning(f"Tradier API call {actual_func_name} returned unexpected JSON data type (Attempt {attempts + 1}). "
                                    f"Expected {expected_response_type_param}, got {type(parsed_response)}. Response: {str(parsed_response)[:200]}")
                        if attempts == retries_param: # Max retries reached
                            log.error(f"Tradier API call {actual_func_name} failed: unexpected JSON data type after max retries.")
                            if expected_response_type_param == dict: return {"error": f"API returned unexpected JSON type for {actual_func_name}."}
                            elif expected_response_type_param == list: return []
                            return None
                        last_exception = TypeError(f"Unexpected JSON type: {type(parsed_response)}")
                        raise last_exception # Allow retry for potentially transient malformed response


                    log.debug(f"Tradier API call {actual_func_name} successful on attempt {attempts + 1}.")
                    return parsed_response

                except requests.exceptions.HTTPError as e_http:
                    status_code = e_http.response.status_code
                    log.warning(f"Tradier API HTTP Error (Attempt {attempts + 1}) for {actual_func_name}: {status_code} - {response_content_for_error}")
                    last_exception = e_http
                    sleep_duration_http = current_delay # Default for most HTTP errors
                    if status_code in [401, 403]:
                        log.error(f"Fatal Tradier API authentication/authorization error ({status_code}) for {actual_func_name}. Aborting retries.")
                        if expected_response_type_param == dict: return {"error": f"Tradier API Auth Error ({status_code}) for {actual_func_name}."}
                        elif expected_response_type_param == list: return []
                        raise last_exception # Re-raise critical auth error

                    if status_code == 429:
                        log.warning(f"Tradier API Rate Limit Exceeded (429) for {actual_func_name}. Applying specific delay.")
                        retry_after_header = e_http.response.headers.get('X-Ratelimit-Retry-After') # Check Tradier docs for exact header
                        if retry_after_header and retry_after_header.isdigit():
                            sleep_duration_http = int(retry_after_header)
                            log.info(f"Respecting Tradier's X-Ratelimit-Retry-After: sleeping {sleep_duration_http}s.")
                        else:
                            current_delay = min(current_delay * 2.5, max_delay_seconds_param * 1.5) # Aggressive backoff for 429
                            sleep_duration_http = current_delay + (random.uniform(0, current_delay * 0.2) if jitter_param else 0)

                except requests.exceptions.RequestException as e_req:
                    log.warning(f"Tradier API Network/Request Error (Attempt {attempts + 1}) for {actual_func_name}: {type(e_req).__name__} - {str(e_req)[:150]}")
                    last_exception = e_req
                    sleep_duration_http = current_delay # Prepare for standard backoff

                except json.JSONDecodeError as e_json:
                    log.warning(f"Tradier API JSONDecodeError (Attempt {attempts + 1}) for {actual_func_name}: {e_json}. Response: {response_content_for_error}")
                    last_exception = e_json
                    sleep_duration_http = current_delay

                except RuntimeError as e_runtime_api_error: # Catch API 'fault' or 'errors' re-raised
                    log.warning(f"Tradier API reported error (RuntimeError, Attempt {attempts + 1}) for {actual_func_name}: {e_runtime_api_error}")
                    last_exception = e_runtime_api_error
                    sleep_duration_http = current_delay

                except Exception as e_gen: # Catch-all for other unexpected errors
                    log.error(f"Unexpected Error during Tradier API call (Attempt {attempts + 1}) for {actual_func_name}: {type(e_gen).__name__} - {e_gen}", exc_info=log.getEffectiveLevel() <= logging.DEBUG)
                    last_exception = e_gen
                    sleep_duration_http = current_delay

                attempts += 1
                if attempts <= retries_param:
                    # Use sleep_duration_http if it was specifically set (e.g., for 429), else standard jittered current_delay
                    actual_sleep_duration = sleep_duration_http if 'sleep_duration_http' in locals() and sleep_duration_http > current_delay else \
                                            (current_delay + (random.uniform(0, current_delay * 0.1) if jitter_param else 0))

                    log.info(f"Retrying Tradier API call {actual_func_name} in {actual_sleep_duration:.2f} seconds... (Attempt {attempts}/{retries_param+1})")
                    time.sleep(actual_sleep_duration)
                    current_delay = min(current_delay * 1.8, max_delay_seconds_param) # Standard exponential backoff for next potential retry
                else: # Max retries exceeded
                    log.error(f"Tradier API call {actual_func_name} failed after {retries_param} retries.")
                    error_message_final = f"Tradier API call {actual_func_name} failed after max retries."
                    if last_exception:
                        error_message_final += f" Last error: {type(last_exception).__name__} - {str(last_exception)[:100]}"

                    if expected_response_type_param == dict: return {"error": error_message_final}
                    elif expected_response_type_param == list: return []

                    # If it's an unexpected exception type that wasn't handled above, re-raise
                    if last_exception and not isinstance(last_exception, (requests.exceptions.HTTPError, requests.exceptions.RequestException, json.JSONDecodeError, RuntimeError)):
                        raise last_exception
                    return None # For handled exception types after retries exhausted

            # This part should ideally not be reached
            log.critical(f"Fell through Tradier retry loop for {actual_func_name} - indicates a logic error in retry handling.")
            if expected_response_type_param == dict: return {"error": "Tradier Retry loop logic error."}
            elif expected_response_type_param == list: return []
            return None
        return wrapper
    return decorator


class TradierDataFetcherV2_5:
    def __init__(self, config_manager_v2_5_instance: Any):
        self.logger = logger.getChild(self.__class__.__name__)
        self.initialization_failed = False

        if not hasattr(config_manager_v2_5_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5 instance. Tradier functionality will be severely impaired.")
            self.initialization_failed = True
            # Set safe defaults
            self.base_url: str = "https://sandbox.tradier.com/v1/" # Default to sandbox for safety
            self.access_token: str = "INVALID_TOKEN_CONFIG_MANAGER_V2_5_MISSING"
            self.max_retries: int = 1
            self.base_retry_delay: float = 1.0
            self.max_retry_delay: float = 3.0
            self.retry_jitter: bool = True
            self.request_timeout: float = 10.0
        else:
            self.config_manager = config_manager_v2_5_instance
            self._load_config_settings_for_tradier_fetcher()

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }

        if self.initialization_failed or self.access_token == "YOUR_TRADIER_ACCESS_TOKEN" or not self.access_token or "INVALID_TOKEN" in self.access_token:
            self.logger.error("TradierDataFetcherV2_5: CRITICAL - Access token is missing, placeholder, or invalid. API calls will likely fail.")
            self.initialization_failed = True # Ensure marked if token is bad from env or default

        self.logger.info(f"TradierDataFetcherV2_5 initialized. Target API: {self.base_url}. Token Loaded: {'Yes' if self.access_token and 'YOUR_TRADIER_ACCESS_TOKEN' not in self.access_token and 'INVALID_TOKEN' not in self.access_token else 'NO / Placeholder / Invalid'}")

    def _load_config_settings_for_tradier_fetcher(self):
        self.logger.debug("Loading TradierDataFetcherV2_5 configurations via ConfigManagerV2_5...")

        # Config paths should align with config_v2_5.json structure
        # Example: ["data_fetcher_settings", "tradier", "api_config"]
        #          ["data_fetcher_settings", "tradier", "retry_config"]
        #          ["data_fetcher_settings", "tradier", "feature_config"]

        td_base = ["data_fetcher_settings", "tradier"] # Base path for Tradier settings
        api_cfg_path = td_base + ["api_config"]
        retry_cfg_path = td_base + ["retry_config"]
        feature_cfg_path = td_base + ["feature_config"] # For things like default DTEs for IV approx etc.

        self.base_url = self.config_manager.get_setting(*api_cfg_path, "base_url", default_value_to_return="https://sandbox.tradier.com/v1/")
        access_token_env_var = str(self.config_manager.get_setting(*api_cfg_path, "access_token_env_var", default_value_to_return="TRADIER_SANDBOX_ACCESS_TOKEN"))

        self.logger.info(f"Attempting to retrieve Tradier API access token from env var: '{access_token_env_var}'")
        self.access_token = os.getenv(access_token_env_var, "YOUR_TRADIER_ACCESS_TOKEN") # Default if env var not found

        self.max_retries = int(self.config_manager.get_setting(*retry_cfg_path, "max_retries", default_value_to_return=3))
        self.base_retry_delay = float(self.config_manager.get_setting(*retry_cfg_path, "base_delay_seconds", default_value_to_return=1.0))
        self.max_retry_delay = float(self.config_manager.get_setting(*retry_cfg_path, "max_delay_seconds", default_value_to_return=10.0))
        self.retry_jitter = bool(self.config_manager.get_setting(*retry_cfg_path, "jitter", default_value_to_return=True))
        self.request_timeout = float(self.config_manager.get_setting(*api_cfg_path, "request_timeout_seconds", default_value_to_return=20.0))

        # Example for a feature-specific config like default days back for OHLCV
        self.ohlcv_default_days_back_cfg = int(self.config_manager.get_setting(*feature_cfg_path, "ohlcv_default_days_back", default_value_to_return=35))

        # Example: system_settings.log_levels.tradier_fetcher
        log_level_str = self.config_manager.get_setting("system_settings", "log_levels", "tradier_fetcher", default_value_to_return="INFO")
        try: self.logger.setLevel(getattr(logging, str(log_level_str).upper()))
        except (AttributeError, ValueError):
            self.logger.setLevel(logging.INFO)
            self.logger.warning(f"Invalid log level '{log_level_str}' in config for TradierDataFetcherV2_5. Defaulting to INFO.")
        self.logger.debug(f"Tradier Config V2.5 Loaded: API URL='{self.base_url}', Retries={self.max_retries}, Timeout={self.request_timeout}s, TokenEnvVar='{access_token_env_var}'")

    def _make_tradier_request(self, endpoint_path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        if self.initialization_failed:
            self.logger.error(f"Tradier API call to '{endpoint_path}' aborted (v2.5): Fetcher initialization failed.")
            error_response = requests.Response()
            error_response.status_code = 503; error_response.reason = "Fetcher Not Ready V2.5"
            error_response._content = b'{"error": "TradierDataFetcherV2_5 not properly initialized."}'
            return error_response

        full_url = f"{self.base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"
        self.logger.debug(f"Tradier Request V2.5: GET {full_url}, Params: {params}")
        return requests.get(full_url, headers=self.headers, params=params or {}, timeout=self.request_timeout)

    # --- Public API Methods (Adapted for V2.5) ---
    def get_underlying_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        self.logger.info(f"Fetching Tradier quote for symbol (v2.5): {symbol}")

        @tradier_retry_api_call_v2_5(
            retries_param=self.max_retries, base_delay_seconds_param=self.base_retry_delay,
            max_delay_seconds_param=self.max_retry_delay, jitter_param=self.retry_jitter,
            logger_instance_param=self.logger, expected_response_type_param=dict,
            func_name_override_param=f"get_underlying_quote_tradier_v2.5_{symbol}"
        )
        def _fetch_quote_v2_5(endpoint: str, query_params: dict):
            return self._make_tradier_request(endpoint_path=endpoint, params=query_params)

        response_data = _fetch_quote_v2_5(endpoint="markets/quotes", query_params={"symbols": symbol, "greeks": "false"})

        if isinstance(response_data, dict) and not response_data.get("error"):
            if 'quotes' in response_data and isinstance(response_data['quotes'], dict) and 'quote' in response_data['quotes']:
                quote_data = response_data['quotes']['quote']
                final_quote = quote_data[0] if isinstance(quote_data, list) and quote_data else quote_data
                if isinstance(final_quote, dict): self.logger.debug(f"Quote for {symbol} (v2.5): {final_quote.get('last')}"); return final_quote
            elif 'symbol' in response_data.get('quotes', {}): # Alternative structure for single quote
                 self.logger.debug(f"Quote (alt structure) for {symbol} (v2.5): {response_data['quotes'].get('last')}"); return response_data['quotes']
            self.logger.warning(f"Unexpected quote structure from Tradier for {symbol} (v2.5): {str(response_data)[:300]}")
        elif isinstance(response_data, dict) and response_data.get("error"):
            self.logger.error(f"Failed to fetch Tradier quote for {symbol} (v2.5): {response_data.get('error')}")
        return None

    def get_ohlcv_data(self, symbol: str, interval: str = "daily",
                       start_date_str: Optional[str] = None,
                       end_date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        self.logger.info(f"Fetching Tradier OHLCV for {symbol} (v2.5), Interval: {interval}, Start: {start_date_str}, End: {end_date_str}")
        if start_date_str is None and end_date_str is None:
            end_date_dt = datetime.now()
            start_date_dt = end_date_dt - timedelta(days=self.ohlcv_default_days_back_cfg) # Use configured default
            end_date_str = end_date_dt.strftime('%Y-%m-%d')
            start_date_str = start_date_dt.strftime('%Y-%m-%d')
        elif end_date_str is None: end_date_str = datetime.now().strftime('%Y-%m-%d')

        params = {"symbol": symbol, "interval": interval, "start": start_date_str, "end": end_date_str}

        @tradier_retry_api_call_v2_5(
            retries_param=self.max_retries, base_delay_seconds_param=self.base_retry_delay,
            max_delay_seconds_param=self.max_retry_delay, jitter_param=self.retry_jitter,
            logger_instance_param=self.logger, expected_response_type_param=dict,
            func_name_override_param=f"get_ohlcv_data_tradier_v2.5_{symbol}"
        )
        def _fetch_ohlcv_v2_5(endpoint: str, query_params: dict):
            return self._make_tradier_request(endpoint_path=endpoint, params=query_params)

        response_data = _fetch_ohlcv_v2_5(endpoint="markets/history", query_params=params)

        if isinstance(response_data, dict) and not response_data.get("error"):
            if response_data.get('history') and response_data['history'] != 'null' and isinstance(response_data['history'], dict) and 'day' in response_data['history']:
                days_data = response_data['history']['day']
                if isinstance(days_data, dict): return [days_data] # Single day
                elif isinstance(days_data, list): return days_data # Multiple days
            elif response_data.get('history') == 'null' or response_data.get('history', {}).get('day') is None:
                 self.logger.info(f"No OHLCV data from Tradier for {symbol} (v2.5) for range {start_date_str}-{end_date_str}.")
                 return []
            self.logger.warning(f"Unexpected OHLCV data structure for {symbol} (v2.5): {str(response_data)[:300]}")
        elif isinstance(response_data, dict) and response_data.get("error"):
            self.logger.error(f"Failed to fetch Tradier OHLCV for {symbol} (v2.5): {response_data.get('error')}")
        return []

    # get_option_expirations, get_option_chain, get_iv_approximation would be similarly adapted.
    # For brevity, they are sketched here.

    def get_option_expirations(self, symbol: str) -> List[str]:
        self.logger.info(f"Fetching Tradier option expirations for {symbol} (v2.5)")
        # ... use @tradier_retry_api_call_v2_5 ...
        # ... parse response similar to v2.4 ...
        return [] # Placeholder

    def get_option_chain(self, symbol: str, expiration_date: str) -> List[Dict[str, Any]]:
        self.logger.info(f"Fetching Tradier option chain for {symbol} (v2.5), Expiry: {expiration_date}")
        # ... use @tradier_retry_api_call_v2_5 ...
        # ... parse response similar to v2.4 ...
        return [] # Placeholder

    def get_iv_approximation(self, symbol: str, target_dte: int = 5) -> Optional[Dict[str, Any]]:
        self.logger.info(f"Approximating IV{target_dte} for {symbol} using Tradier (v2.5).")
        # This method calls get_underlying_quote, get_option_expirations, get_option_chain.
        # Ensure those calls use the v2.5 adapted methods.
        # The logic for finding closest expiry and ATM options remains the same.
        # ... (Full adaptation omitted for brevity but follows the pattern) ...
        return {"error_tradier_v2.5": "IV Approx not fully sketched in v2.5 Tradier Fetcher"} # Placeholder

    def shutdown(self):
        self.logger.info("TradierDataFetcherV2_5 shutdown initiated.")
