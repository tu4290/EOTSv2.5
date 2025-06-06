# data_management/historical_data_manager.py
# (Elite Version 2.4 - Co-Pilot - Phase 3: Refined Historical Data Management - Enhanced for Tradier Integration)

import logging
import os
import pandas as pd # type: ignore
import numpy as np # For handling np.nan, np.isfinite
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Union
import re # <<<<<<<<<<<< ADDED IMPORT FOR REGULAR EXPRESSIONS <<<<<<<<<<<<
import sys # For test block logging
import math # For test block math.isclose

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class HistoricalDataManagerV2_4:
    """
    Manages historical OHLCV (for underlyings) and aggregated metric data for EOTS V2.4.
    - Stores and retrieves daily underlying OHLCV data, primarily for ATR calculations.
      This data can be sourced from various fetchers (e.g., TradierDataFetcher).
    - Stores and retrieves historical daily values of specified aggregated metrics,
      primarily for dynamic thresholding in signals and regime engine.
    This class acts as a data store; it does not fetch external historical data itself.
    The orchestrator is responsible for fetching data and passing it to this manager
    in the expected format.
    """

    def __init__(self, config_manager_instance: Any): # Expecting a ConfigManager instance
        self.logger = logger.getChild(self.__class__.__name__)
        
        if not hasattr(config_manager_instance, 'get_setting') or not hasattr(config_manager_instance, 'get_resolved_path'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager instance. Functionality will be severely impaired.")
            class DummyConfigManager: # Fallback
                _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
                def get_setting(self, key_path: Union[str, List[str]], default_value_to_return: Any = None, quiet: bool = False) -> Any: return default_value_to_return
                def get_resolved_path(self, key_path: Union[str, List[str]], default_relative_path: Optional[str] = None, quiet: bool = False) -> Optional[str]:
                    if default_relative_path: return os.path.join(self._project_root, default_relative_path)
                    return None
            self.config_manager = DummyConfigManager() # type: ignore
        else:
            self.config_manager = config_manager_instance
        
        self.logger.info(f"Initializing HistoricalDataManagerV2_4 (Enhanced for Tradier Integration)...")

        self.base_project_dir = self.config_manager.get_setting("_project_root_path") 
        if not self.base_project_dir: 
            self.base_project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.logger.warning(f"HistoricalDataManager base_project_dir not found in ConfigManager, fell back to local resolution: {self.base_project_dir}")
        
        self.ohlc_store_path: str = self.config_manager.get_resolved_path(
            ["runner_settings", "paths", "historical_ohlc_store"], 
            default_relative_path=os.path.join("data_output", "historical_ohlc_data")
        ) or os.path.join(self.base_project_dir, "data_output", "historical_ohlc_data_fallback_hdm")

        self.metric_store_path: str = self.config_manager.get_resolved_path(
            ["runner_settings", "paths", "historical_metric_store"],
            default_relative_path=os.path.join("data_output", "historical_metric_data")
        ) or os.path.join(self.base_project_dir, "data_output", "historical_metric_data_fallback_hdm")

        self.metrics_to_track_for_dynamic_thresholds: List[str] = self.config_manager.get_setting(
            ["system_settings", "metrics_for_dynamic_threshold_distribution_tracking"],
            default_value_to_return=[]
        )
        self.min_days_for_dynamic_threshold_activation: int = int(self.config_manager.get_setting(
            ["system_settings", "min_days_for_dynamic_threshold_activation"],
            default_value_to_return=20
        ))
        self.hdm_activation_cfg: Dict[str, bool] = self.config_manager.get_setting(
                    ["system_settings", "historical_data_manager_activation"], # New config section
                    default_value_to_return={
                        "enable_ohlcv_storage": True,
                        "enable_ohlcv_retrieval": True,
                        "enable_metric_storage": True,
                        "enable_metric_retrieval": True,
                        "enable_average_iv_retrieval": True
                    }
                )
        self.logger.info(f"HDM Activation Config: {self.hdm_activation_cfg}")
        self._ensure_storage_directories_exist()
        self.logger.info(f"HistoricalDataManagerV2_4 initialized. OHLCV Path: '{self.ohlc_store_path}', Metric Path: '{self.metric_store_path}'")
        self.logger.debug(f"Metrics configured for dynamic threshold tracking: {self.metrics_to_track_for_dynamic_thresholds}")

    def _ensure_storage_directories_exist(self):
        """Ensures that the base storage directories for OHLCV and metrics exist."""
        try:
            if not self.ohlc_store_path or not self.metric_store_path:
                self.logger.error("Critical error: OHLC or Metric store path is None. Cannot create directories.")
                return
            os.makedirs(self.ohlc_store_path, exist_ok=True)
            os.makedirs(self.metric_store_path, exist_ok=True)
            self.logger.debug(f"Ensured OHLCV directory exists: {self.ohlc_store_path}")
            self.logger.debug(f"Ensured Metric base directory exists: {self.metric_store_path}")
        except Exception as e:
            self.logger.error(f"Error creating historical storage directories: {e}", exc_info=True)

    def _sanitize_filename(self, name_part: str) -> str:
        """Sanitizes symbol or metric key for use in filenames."""
        if not isinstance(name_part, str): # Handle non-string inputs gracefully
            self.logger.warning(f"Attempted to sanitize non-string filename part: {name_part} (type: {type(name_part)}). Returning as 'INVALID_NAMEPART'.")
            return "INVALID_NAMEPART"
        return re.sub(r'[^\w\-.]', '_', name_part) # Keep word chars, hyphens, dots; replace others with underscore

    def store_daily_ohlcv(self, symbol: str, data_date: date, ohlcv_data: Dict[str, Any]) -> bool:
        if not self.hdm_activation_cfg.get("enable_ohlcv_storage", True):
            # self.logger.debug(f"OHLCV storage for {symbol} on {data_date} SKIPPED by HDM config.")
            return False # Indicate operation was "skipped" rather than failed
        """
        Stores daily OHLCV data for a symbol. Appends or overwrites existing data for that date.
        The orchestrator is responsible for converting date strings from fetchers (like Tradier)
        into datetime.date objects before calling this method.

        Args:
            symbol (str): The stock symbol.
            data_date (date): The specific date for which the OHLCV data is.
            ohlcv_data (Dict[str, Any]): A dictionary containing OHLCV values.
                Expected keys: 'open', 'high', 'low', 'close', 'volume'.
                Example: {'open': 150.0, 'high': 152.0, 'low': 149.5, 'close': 151.0, 'volume': 1000000}
        
        Returns:
            bool: True if storage was successful, False otherwise.
        """
        store_logger = self.logger.getChild(f"StoreOHLCV.{symbol}")
        if not isinstance(data_date, date):
            store_logger.error(f"Invalid data_date type for {symbol}: {type(data_date)}. Must be datetime.date. Skipping storage.")
            return False
        
        sanitized_symbol = self._sanitize_filename(symbol)
        ohlcv_file_name = f"{sanitized_symbol}_ohlcv.parquet"
        file_path = os.path.join(self.ohlc_store_path, ohlcv_file_name)

        required_keys = ['open', 'high', 'low', 'close', 'volume']
        validated_ohlcv: Dict[str, Any] = {}

        for key in required_keys:
            val = ohlcv_data.get(key)
            if val is None or pd.isna(val): 
                store_logger.warning(f"Missing or NaN value for '{key}' for {symbol} on {data_date}. Skipping OHLCV storage.")
                return False
            try:
                if key == 'volume':
                    validated_ohlcv[key] = int(float(val)) 
                else:
                    validated_ohlcv[key] = float(val)
                if not np.isfinite(validated_ohlcv[key]): 
                    store_logger.warning(f"Non-finite value for '{key}' ({val}) for {symbol} on {data_date}. Skipping storage.")
                    return False
            except (ValueError, TypeError) as e_type:
                store_logger.error(f"Type conversion error for '{key}' ({val}) for {symbol} on {data_date}: {e_type}. Skipping storage.")
                return False
        
        new_data_entry = {"date": pd.to_datetime(data_date)} 
        new_data_entry.update(validated_ohlcv)
        new_data_df = pd.DataFrame([new_data_entry])

        try:
            if os.path.exists(file_path):
                try:
                    existing_df = pd.read_parquet(file_path)
                    if not existing_df.empty and 'date' in existing_df.columns:
                        existing_df['date'] = pd.to_datetime(existing_df['date']).dt.normalize()
                        existing_df = existing_df[existing_df['date'] != pd.to_datetime(data_date).normalize()]
                        combined_df = pd.concat([existing_df, new_data_df], ignore_index=True)
                    else: 
                        combined_df = new_data_df 
                except Exception as e_read_parquet:
                    store_logger.error(f"Error reading existing Parquet file {file_path} for {symbol}. Will attempt to overwrite if possible. Error: {e_read_parquet}")
                    combined_df = new_data_df 
            else: 
                combined_df = new_data_df
            
            if not combined_df.empty:
                combined_df['date'] = pd.to_datetime(combined_df['date']).dt.normalize()
                combined_df = combined_df.sort_values(by="date").drop_duplicates(subset=['date'], keep='last')
                combined_df.to_parquet(file_path, index=False, engine='pyarrow') 
                store_logger.info(f"Stored/Updated OHLCV for {symbol} on {data_date} to {file_path}. Data: {validated_ohlcv}")
                return True
            else:
                store_logger.warning(f"Combined OHLCV DataFrame for {symbol} was empty. Nothing written to {file_path}.")
                return False
        except Exception as e_store:
            store_logger.error(f"Error storing OHLCV data for {symbol} to {file_path}: {e_store}", exc_info=True)
            return False

    def get_ohlc_history_for_atr(self, symbol: str, num_days_for_atr: int, current_trading_date: date) -> Optional[pd.DataFrame]:
        if not self.hdm_activation_cfg.get("enable_ohlcv_retrieval", True):
            # self.logger.debug(f"OHLCV history retrieval for {symbol} SKIPPED by HDM config for ATR.")
            return None # Or pd.DataFrame() if callers expect a DF
        """
        Retrieves historical OHLCV data for ATR calculation, ensuring data up to `current_trading_date - 1 day`.
        """
        retrieve_logger = self.logger.getChild(f"GetOHLC_ATR.{symbol}")
        if not isinstance(current_trading_date, date):
            retrieve_logger.error(f"Invalid current_trading_date type: {type(current_trading_date)}. Must be datetime.date.")
            return None

        sanitized_symbol = self._sanitize_filename(symbol)
        ohlcv_file_name = f"{sanitized_symbol}_ohlcv.parquet"
        file_path = os.path.join(self.ohlc_store_path, ohlcv_file_name)

        if not os.path.exists(file_path):
            retrieve_logger.warning(f"OHLCV data file not found for {symbol} at {file_path} for ATR calculation.")
            return None
        try:
            df = pd.read_parquet(file_path)
            if df.empty:
                retrieve_logger.warning(f"OHLCV data file for {symbol} at {file_path} is empty.")
                return None
            if 'date' not in df.columns: 
                retrieve_logger.error(f"OHLCV data for {symbol} from {file_path} does not have a 'date' column.")
                return None
            
            df['date'] = pd.to_datetime(df['date']).dt.normalize()
            df = df.dropna(subset=['date']).set_index('date').sort_index(ascending=True) 
            
            required_cols = ['open', 'high', 'low', 'close'] 
            if not all(col in df.columns for col in required_cols):
                retrieve_logger.error(f"OHLCV data for {symbol} from {file_path} is missing required ATR columns: {required_cols}. Available: {df.columns.tolist()}")
                return None
            
            for col in required_cols + ['volume']: 
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=required_cols) 

            end_date_for_history = pd.to_datetime(current_trading_date - timedelta(days=1)).normalize()
            df_filtered = df[df.index <= end_date_for_history]

            required_records_for_calc = num_days_for_atr 
            if len(df_filtered) < required_records_for_calc: 
                retrieve_logger.warning(f"Not enough historical OHLCV data for {symbol} up to {end_date_for_history} "
                                    f"({len(df_filtered)} found, {required_records_for_calc} needed for ATR {num_days_for_atr}).")
                return None
            
            final_df_for_atr = df_filtered.tail(required_records_for_calc + 20).reset_index()
            retrieve_logger.debug(f"Retrieved {len(final_df_for_atr)} OHLCV data points for {symbol} for ATR({num_days_for_atr}).")
            return final_df_for_atr
        except Exception as e_load:
            retrieve_logger.error(f"Error loading/processing OHLCV data for {symbol} from {file_path} for ATR: {e_load}", exc_info=True)
            return None

    def store_daily_metric_value(self, symbol: Optional[str], data_date: date, metric_key: str, value: Any) -> bool:
        if not self.hdm_activation_cfg.get("enable_metric_storage", True):
            # self.logger.debug(f"Metric storage for {metric_key}, {symbol or 'GENERAL'} on {data_date} SKIPPED by HDM config.")
            return False
        """ Stores a single daily aggregated metric value for a symbol or general market context. """
        store_metric_logger = self.logger.getChild(f"StoreMetric.{metric_key}")
        if not isinstance(data_date, date):
            store_metric_logger.error(f"Invalid data_date type for metric '{metric_key}', symbol '{symbol or 'GENERAL'}': {type(data_date)}. Skipping.")
            return False

        if pd.isna(value) or value is None:
            store_metric_logger.debug(f"Skipping storage of None/NaN value for metric '{metric_key}', symbol '{symbol or 'GENERAL'}', date '{data_date}'.")
            return False
        
        try: 
            metric_value_float = float(value)
            if not np.isfinite(metric_value_float): 
                store_metric_logger.warning(f"Non-finite float value for '{metric_key}' ({value}), symbol '{symbol or 'GENERAL'}'. Skipping.")
                return False
        except (ValueError, TypeError):
            store_metric_logger.warning(f"Could not convert metric value to float for '{metric_key}', symbol '{symbol or 'GENERAL'}', date '{data_date}'. Value: {value}. Skipping storage.")
            return False

        target_symbol_for_file = self._sanitize_filename(symbol if symbol is not None else "GENERAL_MARKET_CONTEXT")
        sanitized_metric_key = self._sanitize_filename(metric_key)
        
        metric_specific_dir = os.path.join(self.metric_store_path, sanitized_metric_key) 
        try: os.makedirs(metric_specific_dir, exist_ok=True)
        except Exception as e_dir: 
            store_metric_logger.error(f"Error creating metric-specific directory {metric_specific_dir}: {e_dir}"); return False

        metric_file_name = f"{target_symbol_for_file}.parquet"
        file_path = os.path.join(metric_specific_dir, metric_file_name)

        new_data_dict = {"date": [pd.to_datetime(data_date)], "value": [metric_value_float]}
        new_data_df = pd.DataFrame(new_data_dict)
        
        try:
            if os.path.exists(file_path):
                try:
                    existing_df = pd.read_parquet(file_path)
                    if not existing_df.empty and 'date' in existing_df.columns:
                        existing_df['date'] = pd.to_datetime(existing_df['date']).dt.normalize()
                        existing_df = existing_df[existing_df['date'] != pd.to_datetime(data_date).normalize()]
                        combined_df = pd.concat([existing_df, new_data_df], ignore_index=True)
                    else: combined_df = new_data_df
                except Exception as e_read_metric_parquet:
                    store_metric_logger.error(f"Error reading existing metric Parquet file {file_path}. Will attempt to overwrite. Error: {e_read_metric_parquet}")
                    combined_df = new_data_df
            else: combined_df = new_data_df
            
            if not combined_df.empty:
                combined_df['date'] = pd.to_datetime(combined_df['date']).dt.normalize()
                combined_df = combined_df.sort_values(by="date").drop_duplicates(subset=['date'], keep='last')
                combined_df.to_parquet(file_path, index=False, engine='pyarrow')
                store_metric_logger.debug(f"Stored metric '{sanitized_metric_key}' for '{target_symbol_for_file}' on {data_date} with value {metric_value_float:.4f} to {file_path}")
                return True
            else:
                store_metric_logger.warning(f"Combined metric DataFrame for '{sanitized_metric_key}', '{target_symbol_for_file}' was empty. Nothing written.")
                return False
        except Exception as e_store_metric_val:
            store_metric_logger.error(f"Error storing metric '{sanitized_metric_key}' for '{target_symbol_for_file}' to {file_path}: {e_store_metric_val}", exc_info=True)
            return False

    def get_metric_distribution_for_threshold(self, symbol: Optional[str], metric_key: str, days_history: int, current_trading_date: date) -> pd.Series:
        if not self.hdm_activation_cfg.get("enable_metric_retrieval", True):
            # self.logger.debug(f"Metric distribution retrieval for {metric_key}, {symbol or 'GENERAL'} SKIPPED by HDM config.")
            return pd.Series(dtype=float)
        """
        Retrieves historical values for a specific metric, for a symbol or general context,
        up to the day *before* current_trading_date, for dynamic threshold calculation.
        """
        retrieve_metric_logger = self.logger.getChild(f"GetMetricDist.{metric_key}")
        if not isinstance(current_trading_date, date):
            retrieve_metric_logger.error(f"Invalid current_trading_date type: {type(current_trading_date)}. Must be datetime.date.")
            return pd.Series(dtype=float)

        target_symbol_for_file = self._sanitize_filename(symbol if symbol is not None else "GENERAL_MARKET_CONTEXT")
        sanitized_metric_key = self._sanitize_filename(metric_key)
        
        metric_specific_dir = os.path.join(self.metric_store_path, sanitized_metric_key)
        metric_file_name = f"{target_symbol_for_file}.parquet"
        file_path = os.path.join(metric_specific_dir, metric_file_name)

        if not os.path.exists(file_path):
            retrieve_metric_logger.warning(f"Metric history file not found for '{sanitized_metric_key}', symbol '{target_symbol_for_file}' at {file_path}.")
            return pd.Series(dtype=float)
        try:
            df = pd.read_parquet(file_path)
            if df.empty:
                retrieve_metric_logger.warning(f"Metric history file for '{sanitized_metric_key}', symbol '{target_symbol_for_file}' at {file_path} is empty.")
                return pd.Series(dtype=float)
            if 'date' not in df.columns or 'value' not in df.columns:
                retrieve_metric_logger.error(f"Metric history for '{sanitized_metric_key}', '{target_symbol_for_file}' is missing 'date' or 'value' column from {file_path}.")
                return pd.Series(dtype=float)

            df['date'] = pd.to_datetime(df['date']).dt.normalize()
            df = df.sort_values(by="date", ascending=True)
            
            end_date_for_history = pd.to_datetime(current_trading_date - timedelta(days=1)).normalize()
            df_filtered_by_date = df[df['date'] <= end_date_for_history]
            
            df_final_history = df_filtered_by_date.tail(days_history)

            if df_final_history.empty:
                retrieve_metric_logger.debug(f"No historical data for '{sanitized_metric_key}', '{target_symbol_for_file}' up to {end_date_for_history} "
                                    f"or within the last {days_history} available days.")
                return pd.Series(dtype=float)
                
            metric_series = pd.to_numeric(df_final_history['value'], errors='coerce').dropna()
            retrieve_metric_logger.debug(f"Retrieved {len(metric_series)} historical values for '{sanitized_metric_key}', '{target_symbol_for_file}' "
                              f"(requested {days_history} days up to {end_date_for_history}).")
            return metric_series
        except Exception as e_load_metric:
            retrieve_metric_logger.error(f"Error loading metric history for '{sanitized_metric_key}', '{target_symbol_for_file}' from {file_path}: {e_load_metric}", exc_info=True)
            return pd.Series(dtype=float)
    
    def get_average_iv(self, symbol: str, period_days: int, current_date: date) -> Optional[float]:
        if not self.hdm_activation_cfg.get("enable_average_iv_retrieval", True): # Could also be tied to "enable_metric_retrieval"
            # self.logger.debug(f"Average IV retrieval for {symbol} SKIPPED by HDM config.")
            return None
        """
        Placeholder: Retrieves average historical IV for a symbol over a period.
        This would typically involve fetching a specific 'underlying_volatility' metric
        that has been stored daily via store_daily_metric_value.
        """
        avg_iv_logger = self.logger.getChild(f"GetAvgIV.{symbol}")
        
        # Conceptual metric key for stored daily underlying IV (e.g., from ConvexValue or calculated)
        # This key should match what's used in store_daily_metric_value for daily IV.
        # For example, if orchestrator stores 'u_volatility' from ConvexValue as 'und_iv_daily':
        iv_metric_key_for_hist = "und_iv_daily" # This needs to be a metric you are storing daily

        historical_iv_series = self.get_metric_distribution_for_threshold(
            symbol=symbol, 
            metric_key=iv_metric_key_for_hist, 
            days_history=period_days + 5, # Fetch a bit more for averaging
            current_trading_date=current_date
        )
        if not historical_iv_series.empty and len(historical_iv_series) >= period_days:
            avg_iv = historical_iv_series.tail(period_days).mean()
            if pd.notna(avg_iv) and np.isfinite(avg_iv):
                avg_iv_logger.info(f"Calculated average IV for {symbol} over {period_days} days: {avg_iv:.4f}")
                return float(avg_iv)
            else:
                avg_iv_logger.warning(f"Average IV calculation for {symbol} resulted in NaN/Inf.")
        else:
            avg_iv_logger.warning(f"Not enough historical IV data for '{iv_metric_key_for_hist}' for {symbol} to calculate {period_days}-day average.")
        return None # Fallback if not enough data or error

    def shutdown(self):
        """Placeholder for any cleanup activities if needed in the future."""
        self.logger.info(f"HistoricalDataManager_V2_4 ({self.__class__.__name__}) shutdown called. No specific actions implemented.")

# --- Main Test Block (Conceptual for this module) ---
if __name__ == '__main__': # pragma: no cover
    if not logging.getLogger("EOTS_SystemRunnerV2.4").handlers and not logging.getLogger(__name__).handlers : 
        test_handler = logging.StreamHandler(sys.stdout) 
        test_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - L%(lineno)d - %(message)s')
        test_handler.setFormatter(test_formatter)
        logging.getLogger().addHandler(test_handler)
        logging.getLogger().setLevel(logging.DEBUG)

    main_test_logger_hdm = logging.getLogger(f"{__name__}_HDMTestMain")
    main_test_logger_hdm.info("Running HistoricalDataManager_V2_4 in standalone test mode (Enhanced)...")

    class TestConfigManagerForHDMEnhanced:
        _config_data: Dict[str, Any]
        _project_root_path: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def __init__(self, ohlc_path_rel="data_output/test_hdm_ohlc_enhanced", metric_path_rel="data_output/test_hdm_metrics_enhanced", metrics_to_track=None):
            self._config_data = {
                "_project_root_path": self._project_root_path,
                "runner_settings": {
                    "paths": {
                        "historical_ohlc_store": ohlc_path_rel,
                        "historical_metric_store": metric_path_rel
                    }
                },
                "system_settings": {
                     "metrics_for_dynamic_threshold_distribution_tracking": metrics_to_track if metrics_to_track else ["ssi_agg_und_avg_test_hdm", "GIB_OI_based_Und_test_hdm"],
                     "min_days_for_dynamic_threshold_activation": 3 
                }
            }
            main_test_logger_hdm.info(f"TestConfigManagerForHDMEnhanced initialized. Project root: {self._project_root_path}")
            main_test_logger_hdm.info(f"  OHLC store relative path: {ohlc_path_rel}")
            main_test_logger_hdm.info(f"  Metric store relative path: {metric_path_rel}")

        def get_setting(self, key_path: Union[str, List[str]], default_value_to_return: Any = None, quiet: bool = False) -> Any:
            keys = key_path.split('.') if isinstance(key_path, str) else key_path
            val = self._config_data
            try:
                for k in keys: val = val[k]
                return val if val is not None else default_value_to_return
            except KeyError: return default_value_to_return
            except TypeError: return default_value_to_return 
        
        def get_resolved_path(self, key_path: Union[str, List[str]], default_relative_path: Optional[str] = None, quiet: bool = False) -> Optional[str]:
            raw_path = self.get_setting(key_path, default_value_to_return=default_relative_path, quiet=quiet)
            if isinstance(raw_path, str):
                if os.path.isabs(raw_path): return os.path.normpath(raw_path)
                return os.path.normpath(os.path.join(self._project_root_path, raw_path))
            return None

    test_cm_hdm = TestConfigManagerForHDMEnhanced()
    hdm_instance_test = HistoricalDataManagerV2_4(config_manager_instance=test_cm_hdm)
    
    main_test_logger_hdm.info(f"HDM Test Instance: OHLC Path: {hdm_instance_test.ohlc_store_path}")
    main_test_logger_hdm.info(f"HDM Test Instance: Metric Path: {hdm_instance_test.metric_store_path}")

    test_symbol_ohlc_hdm = "TEST_HDM_OHLC"
    today_hdm = date.today()
    for i in range(10, 0, -1): 
        d_ohlc = today_hdm - timedelta(days=i)
        ohlcv_hdm = {'open': 100.0+i, 'high': 102.5+i, 'low': 99.5+i, 'close': 101.0+i, 'volume': 10000+i*100}
        hdm_instance_test.store_daily_ohlcv(test_symbol_ohlc_hdm, d_ohlc, ohlcv_hdm)
    
    ohlc_for_atr_test = hdm_instance_test.get_ohlc_history_for_atr(test_symbol_ohlc_hdm, num_days_for_atr=7, current_trading_date=today_hdm)
    if ohlc_for_atr_test is not None:
        main_test_logger_hdm.info(f"Retrieved OHLCV for {test_symbol_ohlc_hdm} for ATR (7 days up to yesterday):\n{ohlc_for_atr_test.tail(10)}")
        assert len(ohlc_for_atr_test) >= 7, "Should have at least 7 days for ATR history"
        assert ohlc_for_atr_test['date'].max() <= pd.to_datetime(today_hdm - timedelta(days=1)).normalize(), "Max date should be yesterday or earlier"
    else:
        main_test_logger_hdm.error(f"Failed to retrieve OHLCV for {test_symbol_ohlc_hdm} for ATR.")

    test_symbol_metric_hdm = "TEST_HDM_MET"
    metric_key_1_hdm = "ssi_agg_und_avg_test_hdm" 
    for i in range(15): 
        d_metric = today_hdm - timedelta(days=i)
        val_metric = 0.5 + (i % 10) * 0.01 
        hdm_instance_test.store_daily_metric_value(test_symbol_metric_hdm, d_metric, metric_key_1_hdm, val_metric)
    
    metric_dist_test = hdm_instance_test.get_metric_distribution_for_threshold(test_symbol_metric_hdm, metric_key_1_hdm, days_history=10, current_trading_date=today_hdm)
    if not metric_dist_test.empty:
        main_test_logger_hdm.info(f"Retrieved metric series for '{metric_key_1_hdm}', '{test_symbol_metric_hdm}' (10 days up to yesterday), length: {len(metric_dist_test)}")
        main_test_logger_hdm.info(f"Values: {metric_dist_test.values}")
        assert len(metric_dist_test) <= 10, "Should have at most 10 days for metric history"
    else:
        main_test_logger_hdm.error(f"Failed to retrieve metric series for '{metric_key_1_hdm}', '{test_symbol_metric_hdm}'.")

    hdm_instance_test.shutdown()
    main_test_logger_hdm.info("HistoricalDataManager_V2_4 standalone test (Enhanced) finished.")

