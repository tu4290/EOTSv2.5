# data_management/performance_tracker_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

import logging
import os
import pandas as pd # type: ignore
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Union
import re

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class PerformanceTrackerV2_5:
    # Docstring uses single quotes for simplicity in heredoc
    '''
    Manages the persistent storage and retrieval of performance data
    related to EOTS V2.5 signals and recommendations.
    This data is crucial for the ATIF learning loop.
    '''

    def __init__(self, config_manager_v2_5_instance: Any):
        self.logger = logger.getChild(self.__class__.__name__)

        if not hasattr(config_manager_v2_5_instance, 'get_setting') or not hasattr(config_manager_v2_5_instance, 'get_resolved_path_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5 instance. Functionality will be impaired.")
            # Fallback dummy config manager
            class DummyConfigManager:
                _project_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                def get_setting(self, *args, symbol_context=None, default_value_to_return: Any = None, **kwargs):
                    return default_value_to_return
                def get_resolved_path_setting(self, *args, symbol_context=None, default_value_to_return: Optional[str] = None, **kwargs) -> Optional[str]:
                    path_key = args[-1] if args and isinstance(args[-1], str) else "default_path"
                    relative_path = default_value_to_return if default_value_to_return else f"data_cache/fallback_perf_tracker_v2_5/{path_key}"
                    return os.path.join(self._project_root_path, relative_path)
            self.config_manager = DummyConfigManager() # type: ignore
        else:
            self.config_manager = config_manager_v2_5_instance

        self.logger.info(f"Initializing PerformanceTrackerV2_5...")

        self.performance_store_path: str = self.config_manager.get_resolved_path_setting(
            "paths", "performance_data_store_dir",
            default_value_to_return=os.path.join("data_cache", "performance_data_store")
        )
        if self.performance_store_path is None:
            self.logger.error("CRITICAL: performance_store_path is None. Defaulting to emergency path.")
            self.performance_store_path = os.path.join(os.getcwd(), "data_cache_emergency", "performance_data_store")

        self.activation_cfg: Dict[str, bool] = self.config_manager.get_setting(
            "system_settings", "performance_tracker_activation",
            default_value_to_return={"enable_tracking": True, "enable_retrieval": True}
        )

        self._ensure_storage_directory_exists()
        self.logger.info(f"PerformanceTrackerV2_5 initialized. Performance Store Path: '{self.performance_store_path}'")

    def _ensure_storage_directory_exists(self):
        try:
            if not self.performance_store_path:
                self.logger.error("Critical error: Performance store path is None/empty. Cannot create directory.")
                return
            os.makedirs(self.performance_store_path, exist_ok=True)
            self.logger.debug(f"Ensured performance data storage directory exists: {self.performance_store_path}")
        except Exception as e:
            self.logger.error(f"Error creating performance data storage directory (v2.5): {e}", exc_info=True)

    def _sanitize_filename(self, name_part: str) -> str:
        if not isinstance(name_part, str):
            self.logger.warning(f"Attempted to sanitize non-string filename part: {name_part} (type: {type(name_part)}). Returning 'INVALID_NAMEPART'.")
            return "INVALID_NAMEPART"
        return re.sub(r'[^\w\-.]', '_', name_part)

    def record_recommendation_outcome(self, recommendation_data: Dict[str, Any]) -> bool:
        # Docstring uses single quotes
        '''
        Records the outcome of a closed/exited trade recommendation.
        The recommendation_data dictionary should contain all relevant information as
        outlined in Section XIV of the EOTS v2.5 guide (ID, symbol, params, context, outcome).
        Stores data in a Parquet file per symbol.
        '''
        if not self.activation_cfg.get("enable_tracking", True):
            self.logger.debug("Performance tracking is disabled by configuration. Skipping outcome recording.")
            return False

        symbol = recommendation_data.get("symbol")
        reco_id = recommendation_data.get("recommendation_id", "UNKNOWN_ID_" + datetime.now().strftime("%Y%m%d%H%M%S%f"))

        if not symbol or not isinstance(symbol, str):
            self.logger.error(f"Cannot record outcome: 'symbol' is missing or invalid in recommendation_data. ID: {reco_id}")
            return False

        store_logger = self.logger.getChild(f"RecordOutcome_v2.5.{symbol}.{reco_id}")
        store_logger.info(f"Recording outcome for recommendation ID: {reco_id}, Symbol: {symbol}")

        sanitized_symbol = self._sanitize_filename(symbol)
        performance_file_name = f"{sanitized_symbol}_performance_log.parquet"
        file_path = os.path.join(self.performance_store_path, performance_file_name)

        serializable_data = {}
        for key, value in recommendation_data.items():
            if isinstance(value, (datetime, date)):
                serializable_data[key] = value.isoformat()
            elif isinstance(value, (list, dict)):
                 try:
                    pd.Series([value]) # Check if pandas can handle it
                    serializable_data[key] = value
                 except:
                    serializable_data[key] = str(value) # Fallback to string
            else:
                serializable_data[key] = value

        new_data_df = pd.DataFrame([serializable_data])

        try:
            if os.path.exists(file_path):
                try:
                    existing_df = pd.read_parquet(file_path)
                    combined_df = pd.concat([existing_df, new_data_df], ignore_index=True)
                except Exception as e_read_perf_parquet:
                    store_logger.error(f"Error reading existing performance Parquet {file_path} for {symbol}. Will overwrite. Error: {e_read_perf_parquet}")
                    combined_df = new_data_df
            else:
                combined_df = new_data_df

            if not combined_df.empty:
                combined_df.to_parquet(file_path, index=False, engine='pyarrow')
                store_logger.info(f"Successfully recorded outcome for {reco_id} to {file_path}")
                return True
            else:
                store_logger.warning(f"Combined performance DataFrame for {symbol} was empty. Nothing written.")
                return False
        except Exception as e_store_perf:
            store_logger.error(f"Error storing performance data for {reco_id} to {file_path}: {e_store_perf}", exc_info=True)
            return False

    def query_performance_data(self, symbol: str,
                               date_range: Optional[Tuple[date, date]] = None,
                               market_regime_filter: Optional[str] = None,
                               strategy_type_filter: Optional[str] = None,
                               min_conviction_filter: Optional[float] = None
                               ) -> pd.DataFrame:
        # Docstring uses single quotes
        '''
        Queries historical performance data for a given symbol, with optional filters.
        This is a placeholder for more sophisticated querying logic ATIF might need.
        '''
        if not self.activation_cfg.get("enable_retrieval", True):
            self.logger.debug("Performance data retrieval is disabled by configuration.")
            return pd.DataFrame()

        query_logger = self.logger.getChild(f"QueryPerformance_v2.5.{symbol}")
        sanitized_symbol = self._sanitize_filename(symbol)
        performance_file_name = f"{sanitized_symbol}_performance_log.parquet"
        file_path = os.path.join(self.performance_store_path, performance_file_name)

        if not os.path.exists(file_path):
            query_logger.info(f"Performance data file not found for symbol '{symbol}' at {file_path}.")
            return pd.DataFrame()

        try:
            df = pd.read_parquet(file_path)
            if df.empty:
                query_logger.info(f"Performance data file for '{symbol}' is empty.")
                return pd.DataFrame()

            query_logger.debug(f"Initial performance data for {symbol} shape: {df.shape}")

            if date_range:
                # Assuming a column like 'entry_timestamp_iso' or 'timestamp_issued_iso' exists for date filtering
                # This needs to be consistent with what's saved in record_recommendation_outcome
                timestamp_col_to_use = None
                if 'entry_timestamp_iso' in df.columns: timestamp_col_to_use = 'entry_timestamp_iso'
                elif 'timestamp_issued_iso' in df.columns: timestamp_col_to_use = 'timestamp_issued_iso'

                if timestamp_col_to_use:
                    df['temp_date_col_for_filter'] = pd.to_datetime(df[timestamp_col_to_use], errors='coerce').dt.date
                    start_date_filter, end_date_filter = date_range
                    df = df[(df['temp_date_col_for_filter'] >= start_date_filter) & (df['temp_date_col_for_filter'] <= end_date_filter)]
                    df = df.drop(columns=['temp_date_col_for_filter'])
                else:
                    query_logger.warning("No suitable timestamp column found for date_range filtering in performance data.")


            if market_regime_filter and 'regime_at_entry' in df.columns:
                df = df[df['regime_at_entry'] == market_regime_filter]

            if strategy_type_filter and 'strategy_type' in df.columns:
                df = df[df['strategy_type'] == strategy_type_filter]

            if min_conviction_filter and 'atif_conviction_score_at_entry' in df.columns:
                 df['temp_conv_score_col'] = pd.to_numeric(df['atif_conviction_score_at_entry'], errors='coerce')
                 df = df[df['temp_conv_score_col'].notna() & (df['temp_conv_score_col'] >= min_conviction_filter)]
                 df = df.drop(columns=['temp_conv_score_col'])


            query_logger.info(f"Returning {df.shape[0]} performance records for {symbol} after filtering.")
            return df
        except Exception as e_query_perf:
            query_logger.error(f"Error querying performance data for {symbol} from {file_path}: {e_query_perf}", exc_info=True)
            return pd.DataFrame()

    def get_signal_pattern_performance(self, signal_pattern_key: str, symbol: str, market_regime: Optional[str] = None) -> Dict[str, Any]:
        # Docstring uses single quotes
        '''
        Placeholder: Retrieves performance statistics for a specific signal pattern.
        This would involve more complex aggregation on the queried data.
        '''
        self.logger.info(f"Placeholder: Calculating performance for signal pattern '{signal_pattern_key}' for {symbol} in regime '{market_regime}'.")
        return {"win_rate": 0.0, "avg_pnl": 0.0, "trades_count": 0, "message": "Not fully implemented"}

    def shutdown(self):
        self.logger.info(f"PerformanceTrackerV2_5 ({self.__class__.__name__}) shutdown called.")
