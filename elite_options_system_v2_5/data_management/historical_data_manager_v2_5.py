# data_management/historical_data_manager_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

import logging
import os
import pandas as pd # type: ignore
import numpy as np # For handling np.nan, np.isfinite
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Union
import re
import sys
import math

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class HistoricalDataManagerV2_5:
    """
    Manages historical OHLCV (for underlyings) and aggregated metric data for EOTS V2.5.
    - Stores and retrieves daily underlying OHLCV data.
    - Stores and retrieves historical daily values of specified EOTS V2.5 aggregated metrics
      for dynamic thresholding and ATIF learning context.
    """

    def __init__(self, config_manager_v2_5_instance: Any): # Expecting a ConfigManagerV2_5 instance
        self.logger = logger.getChild(self.__class__.__name__)

        if not hasattr(config_manager_v2_5_instance, 'get_setting') or not hasattr(config_manager_v2_5_instance, 'get_resolved_path_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5 instance. Functionality will be severely impaired.")
            # Fallback dummy config manager
            class DummyConfigManager:
                _project_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Heuristic
                def get_setting(self, *args, default_value_to_return: Any = None, **kwargs): return default_value_to_return
                def get_resolved_path_setting(self, *args, default_value_to_return: Optional[str] = None, **kwargs) -> Optional[str]:
                    path_key = args[-1] if args and isinstance(args[-1], str) else "default_path" # Simplified
                    relative_path = default_value_to_return if default_value_to_return else f"data_cache/fallback_hdm_v2_5/{path_key}"
                    return os.path.join(self._project_root_path, relative_path)

            self.config_manager = DummyConfigManager() # type: ignore
        else:
            self.config_manager = config_manager_v2_5_instance

        self.logger.info(f"Initializing HistoricalDataManagerV2_5...")

        self.base_historical_store_path: str = self.config_manager.get_resolved_path_setting(
            "paths", "historical_data_store_dir",
            default_value_to_return=os.path.join("data_cache", "historical_data_store")
        )
        if self.base_historical_store_path is None:
             self.logger.error("CRITICAL: base_historical_store_path is None after config lookup. Defaulting to emergency path.")
             self.base_historical_store_path = os.path.join(os.getcwd(), "data_cache_emergency", "historical_data_store")


        self.ohlc_store_path: str = os.path.join(self.base_historical_store_path, "ohlcv")
        self.metric_store_path: str = os.path.join(self.base_historical_store_path, "metrics")

        self.metrics_to_track_for_dynamic_thresholds: List[str] = self.config_manager.get_setting(
            "system_settings", "metrics_for_dynamic_threshold_distribution_tracking",
            default_value_to_return=[]
        )
        self.min_days_for_dynamic_threshold_activation: int = int(self.config_manager.get_setting(
            "system_settings", "min_days_for_dynamic_threshold_activation",
            default_value_to_return=20
        ))

        self.hdm_activation_cfg: Dict[str, bool] = self.config_manager.get_setting(
            "system_settings", "historical_data_manager_activation",
            default_value_to_return={
                "enable_ohlcv_storage": True, "enable_ohlcv_retrieval": True,
                "enable_metric_storage": True, "enable_metric_retrieval": True,
                "enable_average_iv_retrieval": True
            }
        )
        self.logger.info(f"HDM V2.5 Activation Config: {self.hdm_activation_cfg}")
        self._ensure_storage_directories_exist()
        self.logger.info(f"HistoricalDataManagerV2_5 initialized. Base Store Path: '{self.base_historical_store_path}', OHLCV SubPath: '{self.ohlc_store_path}', Metric SubPath: '{self.metric_store_path}'")
        self.logger.debug(f"Metrics configured for dynamic threshold tracking (v2.5): {self.metrics_to_track_for_dynamic_thresholds}")

    def _ensure_storage_directories_exist(self):
        try:
            if not self.ohlc_store_path or not self.metric_store_path:
                self.logger.error("Critical error: OHLC or Metric store path is None/empty. Cannot create directories.")
                return
            os.makedirs(self.ohlc_store_path, exist_ok=True)
            os.makedirs(self.metric_store_path, exist_ok=True)
            self.logger.debug(f"Ensured OHLCV directory exists: {self.ohlc_store_path}")
            self.logger.debug(f"Ensured Metric base directory exists: {self.metric_store_path}")
        except Exception as e:
            self.logger.error(f"Error creating historical storage directories (v2.5): {e}", exc_info=True)

    def _sanitize_filename(self, name_part: str) -> str:
        if not isinstance(name_part, str):
            self.logger.warning(f"Attempted to sanitize non-string filename part: {name_part} (type: {type(name_part)}). Returning as 'INVALID_NAMEPART'.")
            return "INVALID_NAMEPART"
        return re.sub(r'[^\w\-.]', '_', name_part)

    def store_daily_ohlcv(self, symbol: str, data_date: date, ohlcv_data: Dict[str, Any]) -> bool:
        if not self.hdm_activation_cfg.get("enable_ohlcv_storage", True):
            return False

        store_logger = self.logger.getChild(f"StoreOHLCV_v2.5.{symbol}")
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
                validated_ohlcv[key] = int(float(val)) if key == 'volume' else float(val)
                if not np.isfinite(validated_ohlcv[key]):
                    store_logger.warning(f"Non-finite value for '{key}' ({val}) for {symbol} on {data_date}. Skipping.")
                    return False
            except (ValueError, TypeError) as e_type:
                store_logger.error(f"Type conversion error for '{key}' ({val}) for {symbol} on {data_date}: {e_type}. Skipping.")
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
                    else: combined_df = new_data_df
                except Exception as e_read_parquet:
                    store_logger.error(f"Error reading existing OHLCV Parquet {file_path} for {symbol}. Will overwrite. Error: {e_read_parquet}")
                    combined_df = new_data_df
            else: combined_df = new_data_df

            if not combined_df.empty:
                combined_df['date'] = pd.to_datetime(combined_df['date']).dt.normalize()
                combined_df = combined_df.sort_values(by="date").drop_duplicates(subset=['date'], keep='last')
                combined_df.to_parquet(file_path, index=False, engine='pyarrow')
                store_logger.info(f"Stored/Updated OHLCV for {symbol} on {data_date}. Data: {validated_ohlcv}")
                return True
            return False
        except Exception as e_store:
            store_logger.error(f"Error storing OHLCV data for {symbol} to {file_path}: {e_store}", exc_info=True)
            return False

    def get_ohlc_history_for_atr(self, symbol: str, num_days_for_atr: int, current_trading_date: date) -> Optional[pd.DataFrame]:
        if not self.hdm_activation_cfg.get("enable_ohlcv_retrieval", True):
            return None

        retrieve_logger = self.logger.getChild(f"GetOHLC_ATR_v2.5.{symbol}")
        if not isinstance(current_trading_date, date):
            retrieve_logger.error(f"Invalid current_trading_date type: {type(current_trading_date)}.")
            return None

        sanitized_symbol = self._sanitize_filename(symbol)
        ohlcv_file_name = f"{sanitized_symbol}_ohlcv.parquet"
        file_path = os.path.join(self.ohlc_store_path, ohlcv_file_name)

        if not os.path.exists(file_path):
            retrieve_logger.warning(f"OHLCV data file not found for {symbol} at {file_path} for ATR.")
            return None
        try:
            df = pd.read_parquet(file_path)
            if df.empty or 'date' not in df.columns:
                retrieve_logger.warning(f"OHLCV data for {symbol} from {file_path} is empty or missing 'date' column.")
                return None

            df['date'] = pd.to_datetime(df['date']).dt.normalize()
            df = df.dropna(subset=['date']).set_index('date').sort_index(ascending=True)

            required_cols = ['open', 'high', 'low', 'close']
            if not all(col in df.columns for col in required_cols):
                retrieve_logger.error(f"OHLCV data for {symbol} missing required ATR columns. Have: {df.columns.tolist()}")
                return None

            for col in required_cols + ['volume']:
                if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=required_cols)

            end_date_for_history = pd.to_datetime(current_trading_date - timedelta(days=1)).normalize()
            df_filtered = df[df.index <= end_date_for_history]

            required_records_for_calc = num_days_for_atr
            if len(df_filtered) < required_records_for_calc:
                retrieve_logger.warning(f"Not enough historical OHLCV for {symbol} up to {end_date_for_history} ({len(df_filtered)} found, {required_records_for_calc} needed for ATR {num_days_for_atr}).")
                return None

            final_df_for_atr = df_filtered.tail(required_records_for_calc + 20).reset_index()
            retrieve_logger.debug(f"Retrieved {len(final_df_for_atr)} OHLCV points for {symbol} for ATR({num_days_for_atr}).")
            return final_df_for_atr
        except Exception as e_load:
            retrieve_logger.error(f"Error loading/processing OHLCV for {symbol} from {file_path} for ATR: {e_load}", exc_info=True)
            return None

    def store_daily_metric_value(self, symbol: Optional[str], data_date: date, metric_key: str, value: Any) -> bool:
        if not self.hdm_activation_cfg.get("enable_metric_storage", True):
            return False

        store_metric_logger = self.logger.getChild(f"StoreMetric_v2.5.{metric_key}")
        if not isinstance(data_date, date):
            store_metric_logger.error(f"Invalid data_date type for metric '{metric_key}', symbol '{symbol or 'GENERAL'}': {type(data_date)}. Skipping.")
            return False

        metric_value_float: Optional[float] = None
        metric_value_str: Optional[str] = None # type: ignore
        value_to_store: Any

        if pd.isna(value) or value is None:
            store_metric_logger.debug(f"Skipping storage of None/NaN for metric '{metric_key}', symbol '{symbol or 'GENERAL'}', date '{data_date}'.")
            return False

        try:
            metric_value_float = float(value)
            if not np.isfinite(metric_value_float):
                store_metric_logger.warning(f"Non-finite float value for '{metric_key}' ({value}), symbol '{symbol or 'GENERAL'}'. Skipping.")
                return False
            value_to_store = metric_value_float
        except (ValueError, TypeError):
            if isinstance(value, str) and ("REGIME_" in value.upper() or "_FLAG" in value.upper() or value.upper() in ["HIGH", "MEDIUM", "LOW", "OPENING_RUSH", "LUNCH_LULL", "POWER_HOUR"]):
                 metric_value_str = value
                 value_to_store = metric_value_str
            else:
                store_metric_logger.warning(f"Metric value for '{metric_key}' (symbol '{symbol or 'GENERAL'}', date '{data_date}') is not float convertible and not a recognized string type. Value: {value}. Skipping.")
                return False

        target_symbol_for_file = self._sanitize_filename(symbol if symbol is not None else "GENERAL_MARKET_CONTEXT")
        sanitized_metric_key = self._sanitize_filename(metric_key)

        metric_specific_dir = os.path.join(self.metric_store_path, sanitized_metric_key)
        try: os.makedirs(metric_specific_dir, exist_ok=True)
        except Exception as e_dir:
            store_metric_logger.error(f"Error creating metric-specific directory {metric_specific_dir}: {e_dir}"); return False

        metric_file_name = f"{target_symbol_for_file}.parquet"
        file_path = os.path.join(metric_specific_dir, metric_file_name)

        new_data_dict = {"date": [pd.to_datetime(data_date)], "value": [value_to_store]}
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
                    store_metric_logger.error(f"Error reading existing metric Parquet {file_path}. Will overwrite. Error: {e_read_metric_parquet}")
                    combined_df = new_data_df
            else: combined_df = new_data_df

            if not combined_df.empty:
                combined_df['date'] = pd.to_datetime(combined_df['date']).dt.normalize()
                combined_df = combined_df.sort_values(by="date").drop_duplicates(subset=['date'], keep='last')
                combined_df.to_parquet(file_path, index=False, engine='pyarrow')
                log_value_display = f"{metric_value_float:.4f}" if metric_value_float is not None else str(metric_value_str)
                store_metric_logger.debug(f"Stored metric '{sanitized_metric_key}' for '{target_symbol_for_file}' on {data_date} with value '{log_value_display}' to {file_path}")
                return True
            return False
        except Exception as e_store_metric_val:
            store_metric_logger.error(f"Error storing metric '{sanitized_metric_key}' for '{target_symbol_for_file}' to {file_path}: {e_store_metric_val}", exc_info=True)
            return False

    def get_metric_distribution_for_threshold(self, symbol: Optional[str], metric_key: str, days_history: int, current_trading_date: date) -> pd.Series:
        if not self.hdm_activation_cfg.get("enable_metric_retrieval", True):
            return pd.Series(dtype=float)

        retrieve_metric_logger = self.logger.getChild(f"GetMetricDist_v2.5.{metric_key}")
        if not isinstance(current_trading_date, date):
            retrieve_metric_logger.error(f"Invalid current_trading_date type: {type(current_trading_date)}.")
            return pd.Series(dtype=float)

        target_symbol_for_file = self._sanitize_filename(symbol if symbol is not None else "GENERAL_MARKET_CONTEXT")
        sanitized_metric_key = self._sanitize_filename(metric_key)

        metric_specific_dir = os.path.join(self.metric_store_path, sanitized_metric_key)
        metric_file_name = f"{target_symbol_for_file}.parquet"
        file_path = os.path.join(metric_specific_dir, metric_file_name)

        if not os.path.exists(file_path):
            retrieve_metric_logger.debug(f"Metric history file not found for '{sanitized_metric_key}', symbol '{target_symbol_for_file}' at {file_path}.")
            return pd.Series(dtype=float)
        try:
            df = pd.read_parquet(file_path)
            if df.empty or 'date' not in df.columns or 'value' not in df.columns:
                retrieve_metric_logger.warning(f"Metric history for '{sanitized_metric_key}', '{target_symbol_for_file}' from {file_path} is empty or missing required columns.")
                return pd.Series(dtype=float)

            df['date'] = pd.to_datetime(df['date']).dt.normalize()
            df = df.sort_values(by="date", ascending=True)

            end_date_for_history = pd.to_datetime(current_trading_date - timedelta(days=1)).normalize()
            df_filtered_by_date = df[df['date'] <= end_date_for_history]
            df_final_history = df_filtered_by_date.tail(days_history)

            if df_final_history.empty:
                retrieve_metric_logger.debug(f"No historical data for '{sanitized_metric_key}', '{target_symbol_for_file}' up to {end_date_for_history} or in last {days_history} days.")
                return pd.Series(dtype=float)

            if metric_key in self.metrics_to_track_for_dynamic_thresholds:
                metric_series = pd.to_numeric(df_final_history['value'], errors='coerce').dropna()
                if metric_series.empty and not df_final_history['value'].dropna().empty: # Check if conversion failed but there was data
                     retrieve_metric_logger.warning(f"Could not convert values to numeric for dynamic threshold metric '{sanitized_metric_key}', symbol '{target_symbol_for_file}'.")
                     return pd.Series(dtype=float) # Return empty numeric series
                retrieve_metric_logger.debug(f"Retrieved {len(metric_series)} numeric historical values for DYNAMIC THRESHOLD metric '{sanitized_metric_key}'.")
                return metric_series
            else:
                # For metrics not explicitly for numeric dynamic thresholds, return the series as is (could be object/string type)
                retrieve_metric_logger.debug(f"Retrieved {len(df_final_history['value'])} historical values (any type) for metric '{sanitized_metric_key}'.")
                return df_final_history['value'].reset_index(drop=True) # Return as Series of original dtype

        except Exception as e_load_metric:
            retrieve_metric_logger.error(f"Error loading metric history for '{sanitized_metric_key}', '{target_symbol_for_file}' from {file_path}: {e_load_metric}", exc_info=True)
            return pd.Series(dtype=float)

    def get_average_iv(self, symbol: str, period_days: int, current_date: date) -> Optional[float]:
        if not self.hdm_activation_cfg.get("enable_average_iv_retrieval", True):
            return None

        avg_iv_logger = self.logger.getChild(f"GetAvgIV_v2.5.{symbol}")
        # Path to this config needs to be confirmed for v2.5, e.g., ["metrics_io_params", "historical_iv_storage_key"]
        iv_metric_key_for_hist = self.config_manager.get_setting(
            "metrics_io_params", "historical_iv_metric_key", # This key needs to be defined in config_v2_5.json
            default_value_to_return="underlying_iv_daily" # A sensible default key name
        )

        historical_iv_series = self.get_metric_distribution_for_threshold(
            symbol=symbol,
            metric_key=iv_metric_key_for_hist,
            days_history=period_days + 5, # Fetch a bit more for robustness
            current_trading_date=current_date
        )
        # Ensure series is numeric before attempting mean
        if not historical_iv_series.empty and pd.api.types.is_numeric_dtype(historical_iv_series):
            if len(historical_iv_series) >= period_days:
                avg_iv = historical_iv_series.tail(period_days).mean()
                if pd.notna(avg_iv) and np.isfinite(avg_iv):
                    avg_iv_logger.info(f"Calculated average IV for {symbol} over {period_days} days using '{iv_metric_key_for_hist}': {avg_iv:.4f}")
                    return float(avg_iv)
                else: avg_iv_logger.warning(f"Average IV calculation for {symbol} from '{iv_metric_key_for_hist}' resulted in NaN/Inf.")
            else: avg_iv_logger.warning(f"Not enough historical IV data points for '{iv_metric_key_for_hist}' for {symbol} ({len(historical_iv_series)} found) for {period_days}-day average.")
        else: avg_iv_logger.warning(f"Historical IV data for '{iv_metric_key_for_hist}' for {symbol} is empty or not numeric, cannot calculate average.")
        return None

    def shutdown(self):
        self.logger.info(f"HistoricalDataManagerV2_5 ({self.__class__.__name__}) shutdown called.")
