# data_management/tradier_data_fetcher.py
# (Elite Options Trading System V2.4 - Tradier Data Fetcher - Enhanced)

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
# import pandas as pd # Optional: if you prefer to return DataFrames from some methods
import requests

# --- Module-Specific Logger ---
# The logger name can be configured or use a default.
# Actual configuration of level etc. should come from ConfigManager in __init__.
logger = logging.getLogger(__name__) # Will be child of data_management if imported as such

# --- Retry Decorator (Enhanced for Tradier) ---
def tradier_retry_api_call(
    retries_param: int, # Renamed to avoid conflict if used in a class that has self.retries
    base_delay_seconds_param: float,
    max_delay_seconds_param: float,
    jitter_param: bool = True,
    logger_instance_param: Optional[logging.Logger] = None,
    expected_response_type_param: type = dict,
    func_name_override_param: Optional[str] = None
):
    """
    Decorator to retry Tradier API calls with exponential backoff and jitter.
    Handles common HTTP errors and network issues.
    Parameters are explicitly passed to avoid conflicts with class attributes if used as a method decorator.
    """
    log = logger_instance_param if logger_instance_param else logging.getLogger(f"{__name__}.tradier_retry_api_call")

    def decorator(func: Callable):
        actual_func_name = func_name_override_param if func_name_override_param else func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = base_delay_seconds_param
            last_exception: Optional[BaseException] = None
            response_content_for_error: Optional[str] = None

            while attempts <= retries_param:
                try:
                    # The decorated function (_make_tradier_request) is expected to return a requests.Response object
                    response_obj: requests.Response = func(*args, **kwargs)

                    if not isinstance(response_obj, requests.Response):
                        log.error(f"Tradier API call {actual_func_name} (wrapper target) did not return a requests.Response object. Got: {type(response_obj)}. This is an internal logic error. Aborting.")
                        if expected_response_type_param == dict: return {"error": f"Internal error: {actual_func_name} did not return Response object."}
                        elif expected_response_type_param == list: return []
                        return None

                    response_content_for_error = str(response_obj.text)[:500] # For logging in case of JSON error
                    response_obj.raise_for_status() # Check for 4xx/5xx HTTP errors

                    parsed_response = response_obj.json()

                    # Tradier specific: Check for 'fault' or 'errors' object in the response
                    if isinstance(parsed_response, dict):
                        if "fault" in parsed_response:
                            fault_detail = parsed_response.get("fault", {}).get("detail", "Unknown API fault")
                            fault_string = parsed_response.get("fault", {}).get("faultstring", "N/A")
                            log.warning(f"Tradier API reported a 'fault' in {actual_func_name} on attempt {attempts + 1}: {fault_string} - {fault_detail}")
                            last_exception = RuntimeError(f"Tradier API Fault: {fault_string} - {fault_detail}")
                            raise last_exception # Trigger retry
                        if "errors" in parsed_response and parsed_response["errors"] and "error" in parsed_response["errors"]:
                            error_details = parsed_response["errors"]["error"]
                            log.warning(f"Tradier API reported 'errors' in {actual_func_name} on attempt {attempts + 1}: {error_details}")
                            last_exception = RuntimeError(f"Tradier API Error(s): {error_details}")
                            raise last_exception # Trigger retry
                    
                    if not isinstance(parsed_response, expected_response_type_param):
                        log.warning(f"Tradier API call {actual_func_name} returned unexpected JSON data type on attempt {attempts + 1}. "
                                    f"Expected {expected_response_type_param}, got {type(parsed_response)}. Response: {str(parsed_response)[:200]}")
                        if attempts == retries_param:
                            log.error(f"Tradier API call {actual_func_name} failed due to unexpected JSON data type after max retries.")
                            if expected_response_type_param == dict: return {"error": f"API returned unexpected JSON data type for {actual_func_name}"}
                            elif expected_response_type_param == list: return []
                            else: return None
                        # Allow retry for unexpected type, it might be a transient issue or malformed error
                        last_exception = TypeError(f"Unexpected JSON type: {type(parsed_response)}")
                        raise last_exception


                    log.debug(f"Tradier API call {actual_func_name} successful on attempt {attempts + 1}.")
                    return parsed_response

                except requests.exceptions.HTTPError as e_http:
                    status_code = e_http.response.status_code
                    log.warning(f"Tradier API HTTP Error on attempt {attempts + 1} for {actual_func_name}: {status_code} - {response_content_for_error}")
                    last_exception = e_http
                    if status_code in [401, 403]: # Unauthorized or Forbidden
                        log.error(f"Fatal Tradier API authentication/authorization error ({status_code}) for {actual_func_name}. Aborting retries.")
                        if expected_response_type_param == dict: return {"error": f"Tradier API Auth Error ({status_code}) for {actual_func_name}"}
                        elif expected_response_type_param == list: return []
                        else: raise last_exception 
                    
                    sleep_duration_http = current_delay
                    if status_code == 429: # Rate Limit Exceeded
                        log.warning(f"Tradier API Rate Limit Exceeded (429) for {actual_func_name}. Applying specific delay logic.")
                        retry_after_header = e_http.response.headers.get('X-Ratelimit-Retry-After') # Tradier uses X-Ratelimit-*, check exact header
                        if retry_after_header and retry_after_header.isdigit():
                            sleep_duration_http = int(retry_after_header)
                            log.info(f"Respecting Tradier's X-Ratelimit-Retry-After header: sleeping for {sleep_duration_http} seconds.")
                        else: # Fallback if header not present or not parsable
                            current_delay = min(current_delay * 2.5, max_delay_seconds_param * 1.5) # More aggressive backoff for 429
                            sleep_duration_http = current_delay + (random.uniform(0, current_delay * 0.2) if jitter_param else 0)
                    # For other HTTP errors, use standard backoff (current_delay will be updated later)
                
                except requests.exceptions.RequestException as e_req: # Connection error, timeout, etc.
                    log.warning(f"Tradier API Network/Request Error on attempt {attempts + 1} for {actual_func_name}: {type(e_req).__name__} - {str(e_req)[:150]}")
                    last_exception = e_req
                    sleep_duration_http = current_delay # Prepare for standard backoff
                
                except json.JSONDecodeError as e_json:
                    log.warning(f"Tradier API JSONDecodeError on attempt {attempts + 1} for {actual_func_name}: {e_json}. Response text: {response_content_for_error}")
                    last_exception = e_json
                    sleep_duration_http = current_delay # Prepare for standard backoff
                
                except RuntimeError as e_runtime_api_error: # Catch API errors re-raised from above
                    log.warning(f"Tradier API reported error (RuntimeError) on attempt {attempts + 1} for {actual_func_name}: {e_runtime_api_error}")
                    last_exception = e_runtime_api_error
                    sleep_duration_http = current_delay # Prepare for standard backoff

                except Exception as e_gen:
                    log.error(f"Unexpected Error during Tradier API call attempt {attempts + 1} for {actual_func_name}: {type(e_gen).__name__} - {e_gen}", exc_info=log.getEffectiveLevel() <= logging.DEBUG)
                    last_exception = e_gen
                    sleep_duration_http = current_delay # Prepare for standard backoff

                attempts += 1
                if attempts <= retries_param:
                    # Use sleep_duration_http if it was set (e.g., for 429 or specific handling)
                    # otherwise, use the standard jittered current_delay
                    actual_sleep_duration = sleep_duration_http if 'sleep_duration_http' in locals() and sleep_duration_http > current_delay else \
                                           (current_delay + (random.uniform(0, current_delay * 0.1) if jitter_param else 0))
                    
                    log.info(f"Retrying Tradier API call {actual_func_name} in {actual_sleep_duration:.2f} seconds... (Attempt {attempts}/{retries_param+1})")
                    time.sleep(actual_sleep_duration)
                    current_delay = min(current_delay * 1.8, max_delay_seconds_param) # Standard exponential backoff for next potential retry
                else:
                    log.error(f"Tradier API call {actual_func_name} failed after {retries_param} retries.")
                    error_message_final = f"Tradier API call {actual_func_name} failed after max retries."
                    if last_exception:
                        error_message_final += f" Last error: {type(last_exception).__name__} - {str(last_exception)[:100]}"
                    
                    if expected_response_type_param == dict: return {"error": error_message_final}
                    elif expected_response_type_param == list: return []
                    
                    if last_exception and not isinstance(last_exception, (requests.exceptions.HTTPError, requests.exceptions.RequestException, json.JSONDecodeError, RuntimeError)):
                        # If it's an unexpected exception type, re-raise it to signal a more severe issue
                        raise last_exception
                    return None # For handled exception types after retries exhausted
            
            log.critical(f"Fell through Tradier retry loop for {actual_func_name} - indicates a logic error.")
            if expected_response_type_param == dict: return {"error": "Retry loop logic error."}
            elif expected_response_type_param == list: return []
            return None
        return wrapper
    return decorator


class TradierDataFetcher:
    """
    Handles data fetching from the Tradier API for EOTS V2.4.
    """
    def __init__(self, config_manager_instance: Any):
        self.logger = logger.getChild(self.__class__.__name__) # Logger for the class instance
        self.initialization_failed = False

        if not hasattr(config_manager_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager instance. Tradier functionality will be severely impaired.")
            self.initialization_failed = True
            # Set safe defaults for critical attributes
            self.base_url: str = "https://api.tradier.com/v1/" 
            self.access_token: str = "INVALID_TOKEN_CONFIG_MANAGER_MISSING"
            self.max_retries: int = 1
            self.base_retry_delay: float = 1.0
            self.max_retry_delay: float = 3.0
            self.retry_jitter: bool = True
        else:
            self.config_manager = config_manager_instance
            self._load_config_settings() 
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }

        if self.initialization_failed or self.access_token == "YOUR_TRADIER_ACCESS_TOKEN" or not self.access_token or "INVALID_TOKEN" in self.access_token:
            self.logger.error("TradierDataFetcher: CRITICAL - Access token is missing, placeholder, or invalid due to config issues. API calls will likely fail.")
            self.initialization_failed = True # Ensure it's marked if token is bad
        
        self.logger.info(f"TradierDataFetcher initialized. Target API: {self.base_url}. Token Loaded: {'Yes (actual token)' if self.access_token and self.access_token not in ['YOUR_TRADIER_ACCESS_TOKEN', 'INVALID_TOKEN_CONFIG_MANAGER_MISSING'] else 'NO / Placeholder / Invalid'}")

    def _load_config_settings(self):
        """Loads settings from the ConfigManager instance."""
        self.logger.debug("Loading TradierDataFetcher configurations via ConfigManager...")
        
        self.base_url = self.config_manager.get_setting(
            ["tradier_api_settings", "base_url"],
            default_value_to_return="https://api.tradier.com/v1/"
        )
        access_token_env_var_name = str(self.config_manager.get_setting( # Ensure it's a string for os.getenv
            ["tradier_api_settings", "access_token_env_var"],
            default_value_to_return="J0bVBR60xoYQZw8tIEREcqVfcmfd" # Default from original code
        ))
        
        self.logger.info(f"Attempting to retrieve Tradier API access token from environment variable: '{access_token_env_var_name}'")
        self.access_token = os.getenv(access_token_env_var_name, "YOUR_TRADIER_ACCESS_TOKEN") # Default if env var not found

        if self.access_token == "YOUR_TRADIER_ACCESS_TOKEN" or not self.access_token:
            self.logger.info(f"Tradier API access token NOT FOUND using environment variable '{access_token_env_var_name}'. Will rely on post-load check.")
            # The actual critical error logging and setting initialization_failed is handled in __init__ after this.
        else:
            self.logger.info(f"Tradier API access token FOUND using environment variable '{access_token_env_var_name}'.")

        retry_cfg_path = ["tradier_api_settings", "retry_config"]
        self.max_retries = int(self.config_manager.get_setting(retry_cfg_path + ["max_retries"], default_value_to_return=3))
        self.base_retry_delay = float(self.config_manager.get_setting(retry_cfg_path + ["base_delay_seconds"], default_value_to_return=1.0))
        self.max_retry_delay = float(self.config_manager.get_setting(retry_cfg_path + ["max_delay_seconds"], default_value_to_return=10.0))
        self.retry_jitter = bool(self.config_manager.get_setting(retry_cfg_path + ["jitter"], default_value_to_return=True))
        
        log_level_str = self.config_manager.get_setting(["logging_settings", "tradier_fetcher_log_level"], default_value_to_return="INFO")
        try:
            self.logger.setLevel(getattr(logging, str(log_level_str).upper()))
        except (AttributeError, ValueError):
            self.logger.setLevel(logging.INFO) # Fallback
            self.logger.warning(f"Invalid log level '{log_level_str}' in config for TradierDataFetcher. Defaulting logger to INFO.")

        self.logger.debug(f"Tradier Config Loaded: API URL='{self.base_url}', Retries={self.max_retries}, BaseDelay={self.base_retry_delay}s, TokenEnvVarUsed='{access_token_env_var_name}'")

    def _make_tradier_request(self, endpoint_path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """
        Internal helper to make a GET request to a Tradier endpoint.
        This function is intended to be wrapped by the retry decorator.
        It returns the raw requests.Response object.
        """
        if self.initialization_failed:
            self.logger.error(f"Tradier API call to '{endpoint_path}' aborted: Fetcher initialization failed (e.g., missing token or config).")
            # Simulate a requests.Response object indicating an internal error
            error_response = requests.Response()
            error_response.status_code = 503 
            error_response.reason = "Fetcher Not Ready"
            error_response.encoding = 'utf-8'
            error_response._content = b'{"error": "TradierDataFetcher not properly initialized or token missing."}'
            return error_response

        full_url = f"{self.base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"
        self.logger.debug(f"Tradier Request: GET {full_url}, Params: {params}")
        
        # Default timeout for requests
        request_timeout_seconds = self.config_manager.get_setting(
            ["tradier_api_settings", "request_timeout_seconds"], 
            default_value_to_return=20.0 # Default to 20 seconds
        )

        return requests.get(full_url, headers=self.headers, params=params or {}, timeout=float(request_timeout_seconds))

    def get_underlying_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetches the current quote for an underlying symbol."""
        self.logger.info(f"Fetching Tradier quote for symbol: {symbol}")
        
        api_call_func = tradier_retry_api_call(
            retries_param=self.max_retries, base_delay_seconds_param=self.base_retry_delay,
            max_delay_seconds_param=self.max_retry_delay, jitter_param=self.retry_jitter,
            logger_instance_param=self.logger, expected_response_type_param=dict,
            func_name_override_param=f"get_underlying_quote_{symbol}"
        )(self._make_tradier_request)
        
        response_data = api_call_func(endpoint_path="markets/quotes", params={"symbols": symbol, "greeks": "false"})

        if isinstance(response_data, dict) and not response_data.get("error"):
            if 'quotes' in response_data and isinstance(response_data['quotes'], dict) and 'quote' in response_data['quotes']:
                quote_data_list_or_dict = response_data['quotes']['quote']
                final_quote = quote_data_list_or_dict[0] if isinstance(quote_data_list_or_dict, list) and quote_data_list_or_dict else quote_data_list_or_dict
                if isinstance(final_quote, dict): 
                    self.logger.debug(f"Successfully fetched quote for {symbol}.")
                    return final_quote
            # Handle cases where 'quotes' itself is the quote object (for single symbol requests on some API versions)
            elif 'symbol' in response_data.get('quotes', {}):
                 self.logger.debug(f"Successfully fetched quote (alt structure) for {symbol}.")
                 return response_data['quotes']
            self.logger.warning(f"Unexpected quote structure from Tradier for {symbol}: {str(response_data)[:300]}")
        elif isinstance(response_data, dict) and response_data.get("error"):
            self.logger.error(f"Failed to fetch Tradier quote for {symbol}: {response_data.get('error')}")
        return None

    def get_ohlcv_data(self, symbol: str, interval: str = "daily",
                       start_date_str: Optional[str] = None,
                       end_date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches historical OHLCV data. Returns a list of daily bar dictionaries."""
        self.logger.info(f"Fetching Tradier OHLCV for {symbol}, Interval: {interval}, Start: {start_date_str}, End: {end_date_str}")
        
        # Default date range handling
        if start_date_str is None and end_date_str is None:
            days_back = int(self.config_manager.get_setting(["tradier_api_settings", "ohlcv_default_days_back"], default_value_to_return=35))
            end_date_dt = datetime.now()
            start_date_dt = end_date_dt - timedelta(days=days_back) 
            end_date_str = end_date_dt.strftime('%Y-%m-%d')
            start_date_str = start_date_dt.strftime('%Y-%m-%d')
            self.logger.debug(f"Defaulting OHLCV date range for {symbol} to {start_date_str} - {end_date_str}")
        elif end_date_str is None:
            end_date_str = datetime.now().strftime('%Y-%m-%d')

        params = {"symbol": symbol, "interval": interval, "start": start_date_str, "end": end_date_str}
        
        api_call_func = tradier_retry_api_call(
            retries_param=self.max_retries, base_delay_seconds_param=self.base_retry_delay,
            max_delay_seconds_param=self.max_retry_delay, jitter_param=self.retry_jitter,
            logger_instance_param=self.logger, expected_response_type_param=dict,
            func_name_override_param=f"get_ohlcv_data_{symbol}"
        )(self._make_tradier_request)
        
        response_data = api_call_func(endpoint_path="markets/history", params=params)

        if isinstance(response_data, dict) and not response_data.get("error"):
            if response_data.get('history') and response_data['history'] != 'null' and isinstance(response_data['history'], dict) and 'day' in response_data['history']:
                days_data = response_data['history']['day']
                if isinstance(days_data, dict): # Single day returned
                    self.logger.debug(f"Successfully fetched 1 OHLCV bar for {symbol}.")
                    return [days_data]
                elif isinstance(days_data, list): # Multiple days returned
                    self.logger.debug(f"Successfully fetched {len(days_data)} OHLCV bars for {symbol}.")
                    return days_data
                else: # Unexpected type for 'day'
                    self.logger.warning(f"OHLCV 'day' data for {symbol} is not a dict or list: {type(days_data)}. Response: {str(response_data)[:300]}")
                    return []
            elif response_data.get('history') == 'null' or response_data.get('history', {}).get('day') is None: # Tradier returns "null" for no data
                 self.logger.info(f"No historical OHLCV data returned by Tradier for {symbol} (range: {start_date_str}-{end_date_str}). API indicated 'null' or empty history.")
                 return [] # Return empty list for no data
            self.logger.warning(f"Unexpected OHLCV data structure from Tradier for {symbol}: {str(response_data)[:300]}")
        elif isinstance(response_data, dict) and response_data.get("error"):
            self.logger.error(f"Failed to fetch Tradier OHLCV for {symbol}: {response_data.get('error')}")
        return []

    def get_option_expirations(self, symbol: str) -> List[str]:
        """Fetches option expiration dates."""
        self.logger.info(f"Fetching Tradier option expirations for {symbol}")
        api_call_func = tradier_retry_api_call(
            retries_param=self.max_retries, base_delay_seconds_param=self.base_retry_delay,
            max_delay_seconds_param=self.max_retry_delay, jitter_param=self.retry_jitter,
            logger_instance_param=self.logger, expected_response_type_param=dict,
            func_name_override_param=f"get_option_expirations_{symbol}"
        )(self._make_tradier_request)
        
        response_data = api_call_func(endpoint_path="markets/options/expirations", params={"symbol": symbol, "includeAllRoots": "true", "strikes": "false"})

        if isinstance(response_data, dict) and not response_data.get("error"):
            if 'expirations' in response_data and response_data['expirations'] != 'null' and isinstance(response_data['expirations'], dict) and 'date' in response_data['expirations']:
                dates = response_data['expirations']['date']
                if isinstance(dates, str): return [dates] # Single date
                elif isinstance(dates, list): return dates # List of dates
                else: self.logger.warning(f"Expirations 'date' field for {symbol} is not str or list: {type(dates)}"); return []
            elif response_data.get('expirations') == 'null':
                self.logger.info(f"No option expirations found for {symbol} from Tradier. API returned 'null' expirations.")
                return []
            self.logger.warning(f"Unexpected expirations data structure from Tradier for {symbol}: {str(response_data)[:300]}")
        elif isinstance(response_data, dict) and response_data.get("error"):
            self.logger.error(f"Failed to fetch Tradier expirations for {symbol}: {response_data.get('error')}")
        return []

    def get_option_chain(self, symbol: str, expiration_date: str) -> List[Dict[str, Any]]:
        """Fetches the option chain for a given symbol and expiration date, including Greeks."""
        self.logger.info(f"Fetching Tradier option chain for {symbol}, Expiration: {expiration_date}")
        params = {"symbol": symbol, "expiration": expiration_date, "greeks": "true"}
        api_call_func = tradier_retry_api_call(
            retries_param=self.max_retries, base_delay_seconds_param=self.base_retry_delay,
            max_delay_seconds_param=self.max_retry_delay, jitter_param=self.retry_jitter,
            logger_instance_param=self.logger, expected_response_type_param=dict,
            func_name_override_param=f"get_option_chain_{symbol}_{expiration_date}"
        )(self._make_tradier_request)
        
        response_data = api_call_func(endpoint_path="markets/options/chains", params=params)

        if isinstance(response_data, dict) and not response_data.get("error"):
            if 'options' in response_data and response_data['options'] != 'null' and isinstance(response_data['options'], dict) and 'option' in response_data['options']:
                options_data = response_data['options']['option']
                if isinstance(options_data, list): return options_data
                elif isinstance(options_data, dict): return [options_data] # Single contract in chain
                else: self.logger.warning(f"Option chain 'option' field for {symbol} is not list or dict: {type(options_data)}"); return []
            elif response_data.get('options') == 'null':
                self.logger.info(f"No option chain data found for {symbol} on {expiration_date} from Tradier. API returned 'null' options.")
                return []
            self.logger.warning(f"Unexpected option chain structure from Tradier for {symbol} (exp: {expiration_date}): {str(response_data)[:300]}")
        elif isinstance(response_data, dict) and response_data.get("error"):
            self.logger.error(f"Failed to fetch Tradier option chain for {symbol}, {expiration_date}: {response_data.get('error')}")
        return []

    def get_iv_approximation(self, symbol: str, target_dte: int = 5) -> Optional[Dict[str, Any]]:
        """
        Approximates implied volatility for a target DTE (e.g., IV5 for 5-day)
        by finding the option expiration closest to target_dte and returning ATM SMV_VOL.
        """
        self.logger.info(f"Approximating IV{target_dte} for {symbol} using Tradier.")
        
        quote_data = self.get_underlying_quote(symbol)
        if not quote_data or quote_data.get('last') is None:
            self.logger.error(f"Cannot get underlying price for {symbol} to approximate IV{target_dte}.")
            return {"error": f"Failed to get underlying price for {symbol} for IV{target_dte} approximation."}
        
        current_price = float(quote_data['last'])
        self.logger.info(f"Current {symbol} price for IV{target_dte} approximation: {current_price}")

        expirations = self.get_option_expirations(symbol)
        if not expirations:
            self.logger.warning(f"No expirations found for {symbol} for IV{target_dte} approximation.")
            return {"error": f"No option expirations found for {symbol}."}

        today = date.today()
        closest_expiration_str: Optional[str] = None
        min_dte_diff = float('inf')
        actual_dte_of_closest_exp = -1

        for exp_str in expirations:
            try:
                exp_date_obj = datetime.strptime(exp_str, '%Y-%m-%d').date()
                if exp_date_obj < today: continue
                
                dte = (exp_date_obj - today).days
                dte_diff = abs(dte - target_dte)

                if dte_diff < min_dte_diff:
                    min_dte_diff = dte_diff
                    closest_expiration_str = exp_str
                    actual_dte_of_closest_exp = dte
                elif dte_diff == min_dte_diff and (closest_expiration_str is None or dte < actual_dte_of_closest_exp):
                    closest_expiration_str = exp_str
                    actual_dte_of_closest_exp = dte
            except ValueError:
                self.logger.warning(f"Could not parse expiration date '{exp_str}' during IV{target_dte} approx.")
        
        if closest_expiration_str is None:
            self.logger.warning(f"No suitable future expiration found for {symbol} for IV{target_dte} approx.")
            return {"error": f"No suitable future expiration found for {symbol}."}
        
        self.logger.info(f"Selected expiration for IV{target_dte} approx: {closest_expiration_str} (Actual DTE: {actual_dte_of_closest_exp})")
        option_chain = self.get_option_chain(symbol, closest_expiration_str)
        if not option_chain: # Empty list indicates failure or no data
            self.logger.warning(f"Could not get option chain for {closest_expiration_str} for IV{target_dte} approx.")
            return {"error": f"Failed to get option chain for {symbol} on {closest_expiration_str}."}

        # Find ATM call and put SMV vol
        atm_call = min([opt for opt in option_chain if opt and opt.get('option_type') == 'call' and opt.get('strike') is not None and isinstance(opt.get('strike'), (int, float)) and opt.get('strike') >= current_price], 
                       key=lambda x: x['strike'], default=None)
        if not atm_call and option_chain: # Fallback to closest OTM if no ITM/ATM
             atm_call = max([opt for opt in option_chain if opt and opt.get('option_type') == 'call' and opt.get('strike') is not None and isinstance(opt.get('strike'), (int, float))], 
                       key=lambda x: x['strike'], default=None)

        atm_put = max([opt for opt in option_chain if opt and opt.get('option_type') == 'put' and opt.get('strike') is not None and isinstance(opt.get('strike'), (int, float)) and opt.get('strike') <= current_price], 
                      key=lambda x: x['strike'], default=None)
        if not atm_put and option_chain: # Fallback
            atm_put = min([opt for opt in option_chain if opt and opt.get('option_type') == 'put' and opt.get('strike') is not None and isinstance(opt.get('strike'), (int, float))], 
                      key=lambda x: x['strike'], default=None)

        call_smv = atm_call.get('greeks', {}).get('smv_vol') if atm_call and isinstance(atm_call.get('greeks'), dict) else None
        put_smv = atm_put.get('greeks', {}).get('smv_vol') if atm_put and isinstance(atm_put.get('greeks'), dict) else None
        
        avg_smv = None
        if call_smv is not None and put_smv is not None and isinstance(call_smv, (float, int)) and isinstance(put_smv, (float, int)):
            avg_smv = (call_smv + put_smv) / 2.0
        elif call_smv is not None and isinstance(call_smv, (float, int)):
            avg_smv = call_smv
        elif put_smv is not None and isinstance(put_smv, (float, int)):
            avg_smv = put_smv
            
        result = {
            "symbol": symbol,
            "target_dte_for_iv": target_dte,
            "selected_expiration": closest_expiration_str,
            "actual_dte": actual_dte_of_closest_exp,
            "underlying_price_at_calc": current_price,
            "atm_call_strike": atm_call.get('strike') if atm_call else None,
            "atm_call_smv_vol": call_smv,
            "atm_put_strike": atm_put.get('strike') if atm_put else None,
            "atm_put_smv_vol": put_smv,
            f"iv{target_dte}_approx_smv_avg": avg_smv,
            "error": None # Explicitly set error to None on success
        }
        self.logger.info(f"IV{target_dte} approximation for {symbol}: {result}")
        return result

    def shutdown(self):
        """Placeholder for any cleanup actions if needed."""
        self.logger.info("TradierDataFetcher shutdown initiated. (No specific actions implemented for this version)")


# --- Main Test Block (Example Usage) ---
if __name__ == '__main__': # pragma: no cover
    # This block is for direct testing of TradierDataFetcher.
    # Requires a .env file with TRADIER_ACCESS_TOKEN or direct assignment.
    # Also requires a simplified mock ConfigManager for this test.

    if not logging.getLogger().handlers: 
        test_format = '[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s'
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format=test_format, datefmt="%Y-%m-%d %H:%M:%S")
    
    module_test_logger_tradier = logging.getLogger(f"{__name__}_TradierTestMain")
    module_test_logger_tradier.setLevel(logging.DEBUG) 
    logger.setLevel(logging.DEBUG) # Ensure main module logger is also verbose

    module_test_logger_tradier.info("--- Starting TradierDataFetcher Standalone Test (Enhanced Version) ---")

    class MockTradierConfigManager:
        def __init__(self):
            self.config_data = {
                "tradier_api_settings": {
                    "base_url": "https://api.tradier.com/v1/", 
                    "access_token_env_var": "TRADIER_ACCESS_TOKEN", 
                    "retry_config": {
                        "max_retries": 2, 
                        "base_delay_seconds": 0.3, # Faster for testing
                        "max_delay_seconds": 1.5,  # Faster for testing
                        "jitter": True
                    },
                    "request_timeout_seconds": 15.0
                },
                "logging_settings": { 
                    "tradier_fetcher_log_level": "DEBUG"
                }
            }
            module_test_logger_tradier.info("MockTradierConfigManager initialized with test settings.")

        def get_setting(self, key_path: List[str], default_value_to_return: Any = None) -> Any:
            val = self.config_data; path_str = '.'.join(key_path)
            try:
                for k_segment in key_path: val = val[k_segment]
                # module_test_logger_tradier.debug(f"MockCM: Key '{path_str}' resolved to: {val}")
                return val if val is not None else default_value_to_return
            except KeyError:
                module_test_logger_tradier.debug(f"MockCM: Key '{path_str}' not found, returning default: {default_value_to_return}")
                return default_value_to_return
            except TypeError: 
                module_test_logger_tradier.debug(f"MockCM: Path segment invalid for '{path_str}', returning default: {default_value_to_return}")
                return default_value_to_return
    
    mock_cm_instance_tradier = MockTradierConfigManager()
    
    # For testing, you MUST set the TRADIER_ACCESS_TOKEN environment variable.
    # Example: export TRADIER_ACCESS_TOKEN="your_actual_token_here" (Linux/macOS)
    #          set TRADIER_ACCESS_TOKEN="your_actual_token_here" (Windows CMD)
    #          $env:TRADIER_ACCESS_TOKEN="your_actual_token_here" (Windows PowerShell)
    # Or, for a quick test, temporarily hardcode it in the TradierDataFetcher class's
    # _load_config_settings method (NOT RECOMMENDED FOR PRODUCTION CODE).
    
    tradier_fetcher = TradierDataFetcher(config_manager_instance=mock_cm_instance_tradier)

    if tradier_fetcher.initialization_failed:
        module_test_logger_tradier.critical("TradierDataFetcher failed to initialize properly in test. Aborting further tests.")
    else:
        test_sym = "SPY" # Changed to SPY for more likely data availability
        
        module_test_logger_tradier.info(f"\n--- Testing get_underlying_quote for {test_sym} ---")
        quote_result = tradier_fetcher.get_underlying_quote(test_sym)
        if quote_result and not quote_result.get("error"):
            module_test_logger_tradier.info(f"Quote for {test_sym}: Last Price = {quote_result.get('last')}, Volume = {quote_result.get('volume')}")
        else: module_test_logger_tradier.error(f"Failed to get quote for {test_sym} or error in response: {quote_result}")

        module_test_logger_tradier.info(f"\n--- Testing get_ohlcv_data for {test_sym} (daily, last ~30 days) ---")
        start_ohlcv_test = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
        end_ohlcv_test = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d') # Ensure we are not asking for current day if market closed
        ohlcv_result = tradier_fetcher.get_ohlcv_data(test_sym, interval="daily", start_date_str=start_ohlcv_test, end_date_str=end_ohlcv_test)
        if isinstance(ohlcv_result, list) and ohlcv_result:
            module_test_logger_tradier.info(f"OHLCV for {test_sym}: Retrieved {len(ohlcv_result)} days. First day: {ohlcv_result[0] if ohlcv_result else 'N/A'}, Last day: {ohlcv_result[-1] if ohlcv_result else 'N/A'}")
        elif isinstance(ohlcv_result, list) and not ohlcv_result:
             module_test_logger_tradier.info(f"OHLCV for {test_sym}: No data returned (empty list). This might be normal if market was closed for the entire period or no data available.")
        else: module_test_logger_tradier.error(f"Failed to get OHLCV data for {test_sym} or error in response: {ohlcv_result}")

        module_test_logger_tradier.info(f"\n--- Testing get_option_expirations for {test_sym} ---")
        expirations_result = tradier_fetcher.get_option_expirations(test_sym)
        if expirations_result:
            module_test_logger_tradier.info(f"Expirations for {test_sym} (first 5): {expirations_result[:5]}")
            
            # Find a valid future expiration for chain test
            test_expiry_for_chain = None
            today_for_exp_check = date.today()
            for exp_candidate_str in expirations_result:
                try:
                    exp_candidate_date = datetime.strptime(exp_candidate_str, '%Y-%m-%d').date()
                    if exp_candidate_date >= today_for_exp_check:
                        test_expiry_for_chain = exp_candidate_str
                        break
                except ValueError: continue
            
            if test_expiry_for_chain:
                module_test_logger_tradier.info(f"\n--- Testing get_option_chain for {test_sym}, Expiry: {test_expiry_for_chain} ---")
                chain_result = tradier_fetcher.get_option_chain(test_sym, test_expiry_for_chain)
                if isinstance(chain_result, list) and chain_result:
                    module_test_logger_tradier.info(f"Option chain for {test_sym} ({test_expiry_for_chain}): Found {len(chain_result)} contracts. First contract: {str(chain_result[0])[:250] if chain_result else 'N/A'}...")
                elif isinstance(chain_result, list) and not chain_result:
                    module_test_logger_tradier.info(f"Option chain for {test_sym} ({test_expiry_for_chain}): No contracts returned (empty list).")
                else: module_test_logger_tradier.error(f"Failed to get option chain for {test_sym} ({test_expiry_for_chain}) or error in response: {chain_result}")
            else:
                module_test_logger_tradier.warning(f"No suitable future expiration found for {test_sym} to test option chain.")
        else: module_test_logger_tradier.error(f"Failed to get expirations for {test_sym} or error in response: {expirations_result}")

        module_test_logger_tradier.info(f"\n--- Testing get_iv_approximation for {test_sym} (target_dte=7) ---")
        iv_approx_result = tradier_fetcher.get_iv_approximation(test_sym, target_dte=7) # Test with a slightly different DTE
        if iv_approx_result and not iv_approx_result.get("error"):
            module_test_logger_tradier.info(f"IV7 Approx for {test_sym}: {json.dumps(iv_approx_result, indent=2)}")
        else: module_test_logger_tradier.error(f"Failed to get IV7 approximation for {test_sym}: {iv_approx_result}")
        
        tradier_fetcher.shutdown()

    module_test_logger_tradier.info("--- TradierDataFetcher Standalone Test Finished ---")
