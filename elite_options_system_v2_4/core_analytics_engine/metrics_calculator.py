# core_analytics_engine/metrics_calculator.py
# (Elite Version 2.4 - Co-Pilot - Canonical Metrics Calculator - Phase 5 Revamp)

# Standard Library Imports
import logging
import os
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from collections import deque 
import math
from datetime import time, date, datetime, timedelta

# Third-Party Imports
import pandas as pd # type: ignore
import numpy as np # type: ignore

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

# --- Helper Constants ---
MIN_NORMALIZATION_DENOMINATOR: float = 1e-9
DEFAULT_ATR_FALLBACK_MIN_VALUE: float = 0.01 # Default if ATR calc fails or price is very low
DEFAULT_ATR_FALLBACK_PERCENTAGE: float = 0.01 # Default ATR as % of price if other fallbacks fail
EPSILON: float = 1e-9 # Small number to prevent division by zero

class MetricsCalculatorV2_4:
    """
    Calculates all granular and aggregate metrics for EOTS V2.4.
    Relies on configuration for parameters and API column name mappings.
    Interacts with HistoricalDataManager for ATR, historical IV, and metric distributions.
    Receives underlying data that may be pre-enriched with metrics from other sources (e.g., Tradier IVs).
    """

    def __init__(self,
                 config_manager_instance: Any,
                 historical_data_manager_instance: Optional[Any] = None
                 ):
        self.logger = logger.getChild(self.__class__.__name__)
        self.initialization_failed = False

        if not hasattr(config_manager_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager. Critical failure.")
            class DummyCM:
                def get_setting(self, *args, **kwargs): return kwargs.get('default_value_to_return')
            self.config_manager: Any = DummyCM()
            self.initialization_failed = True
        else:
            self.config_manager: Any = config_manager_instance

        self.historical_data_manager: Optional[Any] = historical_data_manager_instance
        if self.historical_data_manager is None:
            self.logger.warning("HistoricalDataManager instance not provided to MetricsCalculator. ATR, historical IV trends, and dynamic metric thresholds will use fallbacks or may not function fully.")
        elif not hasattr(self.historical_data_manager, 'get_ohlc_history_for_atr') or \
             not hasattr(self.historical_data_manager, 'get_average_iv') or \
             not hasattr(self.historical_data_manager, 'get_metric_distribution_for_threshold'):
            self.logger.warning("Provided HistoricalDataManager instance is missing one or more required methods (get_ohlc_history_for_atr, get_average_iv, get_metric_distribution_for_threshold). Functionality will be impaired.")
            # Consider setting self.historical_data_manager to None to force fallbacks if methods are missing.

        self.logger.info("MetricsCalculatorV2_4 (Tradier Integration Ready, Phased Toggles) initialized.")
        
        if not self.initialization_failed:
            self._initialize_column_names_from_config()
            self._initialize_common_parameters_from_config()
            # Load metric calculation phase toggles
            self.metric_phases_activation_cfg: Dict[str, bool] = self._get_config_setting(
                ["system_settings", "metric_calculation_phases_activation"], {}
            )
            self.logger.info(f"Metric calculation phase activations: {self.metric_phases_activation_cfg}")
        else:
            self.logger.error("MetricsCalculatorV2_4 initialization encountered critical errors. Critical attributes will use fallbacks.")
            self._use_fallback_initializations()
            self.metric_phases_activation_cfg: Dict[str, bool] = {} # Empty if init failed

        # Per-cycle state
        self.current_processing_symbol: Optional[str] = None
        self.current_processing_time_dt: Optional[datetime] = None
        self.current_und_data_api: Optional[Dict[str,Any]] = None
        self.current_und_price: Optional[float] = None
        self.current_und_multiplier: Optional[float] = None
        self.mre_settings_cfg: Dict[str, Any] = self._get_config_setting("market_regime_engine_settings", {})

    def _use_fallback_initializations(self):
        """Sets fallback values for critical attributes if main initialization fails."""
        self.logger.warning("Using fallback initializations for MetricsCalculator attributes.")
        # Column Names (ensure all attributes from _initialize_column_names_from_config have a default)
        self.col_strike: str = "strike"; self.col_opt_kind: str = "opt_kind"
        self.col_expiration: str = "expiration_days_from_epoch_calc"; self.col_oi: str = "oi"
        self.col_opt_volatility: str = "volatility"; self.col_opt_price: str = "price"
        self.col_delta: str = "delta"; self.col_gamma: str = "gamma"; self.col_theta: str = "theta"
        self.col_vega: str = "vega"; self.col_vanna: str = "vanna"; self.col_vomma: str = "vomma"; self.col_charm: str = "charm"
        self.col_gxoi: str = "gxoi"; self.col_dxoi: str = "dxoi"; self.col_txoi: str = "txoi"; self.col_vxoi: str = "vxoi"
        self.col_charmxoi: str = "charmxoi"; self.col_vannaxoi: str = "vannaxoi"; self.col_vommaxoi: str = "vommaxoi"
        self.col_dxvolm: str = "dxvolm"; self.col_gxvolm: str = "gxvolm"; self.col_txvolm: str = "txvolm"; self.col_vxvolm: str = "vxvolm"
        self.col_charmxvolm: str = "charmxvolm"; self.col_vannaxvolm: str = "vannaxvolm"; self.col_vommaxvolm: str = "vommaxvolm"
        self.col_c_value_bs: str = "value_bs"; self.col_c_volm_bs: str = "volm_bs"
        self.col_c_deltas_buy: str = "deltas_buy"; self.col_c_deltas_sell: str = "deltas_sell"
        self.col_c_gammas_buy: str = "gammas_buy"; self.col_c_gammas_sell: str = "gammas_sell"
        self.col_c_vegas_buy: str = "vegas_buy"; self.col_c_vegas_sell: str = "vegas_sell"
        self.col_c_thetas_buy: str = "thetas_buy"; self.col_c_thetas_sell: str = "thetas_sell"
        self.col_c_valuebs_base: str = "valuebs_"; self.col_c_volmbs_base: str = "volmbs_"
        self.rolling_intervals_cfg: List[str] = ["5m", "15m", "30m", "60m"]
        self.col_und_price: str = "price"; self.col_und_multiplier: str = "multiplier"
        # Mappings for underlying greeks from get_und
        self.col_u_call_gxoi: str = "call_gxoi"; self.col_u_put_gxoi: str = "put_gxoi"
        self.col_u_call_vxoi: str = "call_vxoi"; self.col_u_put_vxoi: str = "put_vxoi"
        self.col_u_deltas_buy: str = "deltas_buy"; self.col_u_deltas_sell: str = "deltas_sell"
        self.col_u_gammas_buy: str = "gammas_buy"; self.col_u_gammas_sell: str = "gammas_sell"
        self.col_u_gammas_call_buy: str = "gammas_call_buy"; self.col_u_gammas_call_sell: str = "gammas_call_sell"
        self.col_u_gammas_put_buy: str = "gammas_put_buy"; self.col_u_gammas_put_sell: str = "gammas_put_sell"
        self.col_u_vegas_buy: str = "vegas_buy"; self.col_u_vegas_sell: str = "vegas_sell"
        self.col_u_thetas_buy: str = "thetas_buy"; self.col_u_thetas_sell: str = "thetas_sell"
        self.col_u_vflowratio: str = "vflowratio"; self.col_u_volm_call_buy: str = "volm_call_buy"
        self.col_u_volm_put_sell: str = "volm_put_sell"; self.col_u_volm_put_buy: str = "volm_put_buy"
        self.col_u_volm_call_sell: str = "volm_call_sell"; self.col_u_value_call_buy: str = "value_call_buy"
        self.col_u_value_put_sell: str = "value_put_sell"; self.col_u_value_put_buy: str = "value_put_buy"
        self.col_u_value_call_sell: str = "value_call_sell"; self.col_u_day_open_price: str = "day_open_price"
        self.col_u_volatility: str = "volatility"
        self.use_skew_adjusted_sdag: bool = False; self.col_sgxoi_calculated: str = "sgxoi_calc"

        # Common Parameters
        self.dag_alpha_aligned: float = 1.3; self.dag_alpha_opposed: float = 0.7; self.dag_alpha_neutral: float = 1.0
        self.tdpi_beta_aligned: float = 1.3; self.tdpi_beta_opposed: float = 0.7; self.tdpi_beta_neutral: float = 1.0
        self.tdpi_gaussian_width: float = -0.45; self.tdpi_atr_fallback_cfg: Dict[str, Any] = {"type": "percentage_of_price", "percentage": 0.005, "min_value": 0.01, "atr_period": 10}
        self.vri_gamma_aligned: float = 1.3; self.vri_gamma_opposed: float = 0.7; self.vri_gamma_neutral: float = 1.0
        self.vri_vol_trend_fb_factor: float = 0.95
        self.vri_0dte_vanna_align_reinforce: float = 1.5; self.vri_0dte_vanna_align_contradict: float = 0.5
        self.vri_0dte_vol_trend_fb_no_hist: float = 1.0
        self.vol_trend_avg_days_vri0dte: int = 5; self.vol_trend_avg_days_vri_sens: int = 20
        self.generic_atr_period: int = 14
        self.enabled_sdag_methodologies: List[str] = []; self.sdag_methodology_params: Dict[str, Dict[str, Any]] = {}
        self.mre_time_defs_cfg: Dict[str, str] = {}; self.market_open_hour: float = 9.5; self.market_close_hour: float = 16.0
        self.iv_rank_col_from_und: Optional[str] = None; self.clip_percentile: float = 99.0
        self.gamma_col_for_sdag_calc: str = self.col_gxoi
    def _get_config_setting(self, key_path: Union[str, List[str]], default: Any = None, quiet: bool = False) -> Any:
        """Convenience wrapper for ConfigManager get_setting."""
        if self.initialization_failed or not hasattr(self.config_manager, 'get_setting'):
            return default
        return self.config_manager.get_setting(key_path, default_value_to_return=default, quiet=quiet)

    def _initialize_column_names_from_config(self) -> None:
        self.logger.debug("Initializing column names for MetricsCalculatorV2_4 from config...")
        s_cfg = "strategy_settings" # Base path

        # Per-Contract `get_chain` based field names (as they appear in DataFrames from InitialProcessor)
        self.col_strike: str = self._get_config_setting(f"{s_cfg}.strike_col_name", "strike")
        self.col_opt_kind: str = self._get_config_setting(f"{s_cfg}.option_kind_col_name", "opt_kind")
        self.col_expiration: str = self._get_config_setting(f"{s_cfg}.expiration_col_name", "expiration_days_from_epoch_calc") # After InitialProcessor's DTE calc
        self.col_oi: str = self._get_config_setting(f"{s_cfg}.oi_col_name", "oi")
        self.col_opt_volatility: str = self._get_config_setting(f"{s_cfg}.option_volatility_col_name", "volatility")
        self.col_opt_price: str = self._get_config_setting(f"{s_cfg}.option_price_col_name", "price") # Option's price
        
        # Base Greeks (per contract)
        self.col_delta: str = "delta" # Assuming base Greeks are standard names after fetcher/processor
        self.col_gamma: str = "gamma"
        self.col_theta: str = "theta"
        self.col_vega: str = "vega"
        self.col_vanna: str = "vanna"
        self.col_vomma: str = "vomma"
        self.col_charm: str = "charm"

        # OI-Multiplied Greeks (per contract)
        self.col_gxoi: str = self._get_config_setting(f"{s_cfg}.gamma_exposure_source_col", "gxoi")
        self.col_dxoi: str = self._get_config_setting(f"{s_cfg}.delta_exposure_source_col", "dxoi")
        self.col_txoi: str = self._get_config_setting(f"{s_cfg}.theta_exposure_source_col", "txoi")
        self.col_vxoi: str = self._get_config_setting(f"{s_cfg}.vega_exposure_source_col", "vxoi")
        self.col_charmxoi: str = self._get_config_setting(f"{s_cfg}.charm_exposure_source_col", "charmxoi")
        self.col_vannaxoi: str = self._get_config_setting(f"{s_cfg}.vanna_exposure_source_col", "vannaxoi")
        self.col_vommaxoi: str = self._get_config_setting(f"{s_cfg}.vomma_exposure_source_col", "vommaxoi")

        # Greek-Weighted Volume (Flow Proxies per contract)
        self.col_dxvolm: str = self._get_config_setting(f"{s_cfg}.delta_flow_proxy_col", "dxvolm")
        self.col_gxvolm: str = self._get_config_setting(f"{s_cfg}.gamma_flow_proxy_col", "gxvolm")
        self.col_txvolm: str = self._get_config_setting(f"{s_cfg}.theta_flow_proxy_col", "txvolm")
        self.col_vxvolm: str = self._get_config_setting(f"{s_cfg}.vega_flow_proxy_col", "vxvolm")
        self.col_charmxvolm: str = self._get_config_setting(f"{s_cfg}.charm_flow_proxy_col", "charmxvolm")
        self.col_vannaxvolm: str = self._get_config_setting(f"{s_cfg}.vanna_flow_proxy_col", "vannaxvolm")
        self.col_vommaxvolm: str = self._get_config_setting(f"{s_cfg}.vomma_flow_proxy_col", "vommaxvolm")

        # Per-contract Netted Signed Value/Volume & Greek Flows (from `get_chain` via `net_flow_cols_chain` mapping)
        net_flow_chain_map = self._get_config_setting(f"{s_cfg}.net_flow_cols_chain", {})
        self.col_c_value_bs: str = net_flow_chain_map.get("value_bs_contract", "value_bs") # Maps conceptual to actual column name
        self.col_c_volm_bs: str = net_flow_chain_map.get("volm_bs_contract", "volm_bs")
        self.col_c_deltas_buy: str = net_flow_chain_map.get("deltas_buy_contract", "deltas_buy") 
        self.col_c_deltas_sell: str = net_flow_chain_map.get("deltas_sell_contract", "deltas_sell")
        self.col_c_gammas_buy: str = net_flow_chain_map.get("gammas_buy_contract", "gammas_buy")
        self.col_c_gammas_sell: str = net_flow_chain_map.get("gammas_sell_contract", "gammas_sell")
        self.col_c_vegas_buy: str = net_flow_chain_map.get("vegas_buy_contract", "vegas_buy")
        self.col_c_vegas_sell: str = net_flow_chain_map.get("vegas_sell_contract", "vegas_sell")
        self.col_c_thetas_buy: str = net_flow_chain_map.get("thetas_buy_contract", "thetas_buy")
        self.col_c_thetas_sell: str = net_flow_chain_map.get("thetas_sell_contract", "thetas_sell")
        
        # Rolling window flow base names (actual column names will be like valuebs_5m_contract)
        self.col_c_valuebs_base: str = net_flow_chain_map.get("valuebs_Xm_base", "valuebs_") # Base for valuebs_5m etc.
        self.col_c_volmbs_base: str = net_flow_chain_map.get("volmbs_Xm_base", "volmbs_")   # Base for volmbs_5m etc.
        self.rolling_intervals_cfg: List[str] = self._get_config_setting("visualization_settings.mspi_visualizer.rolling_intervals", ["5m", "15m", "30m", "60m"])


        # Underlying `get_und` based field names (as they appear in `und_data_api_raw` from InitialProcessor)
        self.col_und_price: str = self._get_config_setting(f"{s_cfg}.underlying_price_col_name", "price") # Key for current_und_price
        self.col_und_multiplier: str = self._get_config_setting(f"{s_cfg}.contract_multiplier_col_name", "multiplier") # Key for current_und_multiplier

        greeks_und_map = self._get_config_setting(f"{s_cfg}.greeks_from_und", {})
        self.col_u_call_gxoi: str = greeks_und_map.get("call_gxoi_und", "call_gxoi")
        self.col_u_put_gxoi: str = greeks_und_map.get("put_gxoi_und", "put_gxoi")
        self.col_u_call_vxoi: str = greeks_und_map.get("call_vxoi_und", "call_vxoi")
        self.col_u_put_vxoi: str = greeks_und_map.get("put_vxoi_und", "put_vxoi")
        self.col_u_deltas_buy: str = greeks_und_map.get("deltas_buy_und", "deltas_buy")
        self.col_u_deltas_sell: str = greeks_und_map.get("deltas_sell_und", "deltas_sell")
        self.col_u_gammas_buy: str = greeks_und_map.get("gammas_buy_und", "gammas_buy")
        self.col_u_gammas_sell: str = greeks_und_map.get("gammas_sell_und", "gammas_sell")
        self.col_u_vegas_buy: str = greeks_und_map.get("vegas_buy_und", "vegas_buy")
        self.col_u_vegas_sell: str = greeks_und_map.get("vegas_sell_und", "vegas_sell")
        self.col_u_thetas_buy: str = greeks_und_map.get("thetas_buy_und", "thetas_buy")
        self.col_u_thetas_sell: str = greeks_und_map.get("thetas_sell_und", "thetas_sell")
        self.col_u_gammas_call_buy: str = greeks_und_map.get("gammas_call_buy_und", "gammas_call_buy")
        self.col_u_gammas_call_sell: str = greeks_und_map.get("gammas_call_sell_und", "gammas_call_sell")
        self.col_u_gammas_put_buy: str = greeks_und_map.get("gammas_put_buy_und", "gammas_put_buy")
        self.col_u_gammas_put_sell: str = greeks_und_map.get("gammas_put_sell_und", "gammas_put_sell")
        self.col_u_vflowratio: str = greeks_und_map.get("vflowratio_und", "vflowratio") # Use the direct API field name
        self.col_u_volm_call_buy: str = greeks_und_map.get("volm_call_buy_und", "volm_call_buy")
        self.col_u_volm_put_sell: str = greeks_und_map.get("volm_put_sell_und", "volm_put_sell")
        self.col_u_volm_put_buy: str = greeks_und_map.get("volm_put_buy_und", "volm_put_buy")
        self.col_u_volm_call_sell: str = greeks_und_map.get("volm_call_sell_und", "volm_call_sell")
        self.col_u_value_call_buy: str = greeks_und_map.get("value_call_buy_und", "value_call_buy")
        self.col_u_value_put_sell: str = greeks_und_map.get("value_put_sell_und", "value_put_sell")
        self.col_u_value_put_buy: str = greeks_und_map.get("value_put_buy_und", "value_put_buy")
        self.col_u_value_call_sell: str = greeks_und_map.get("value_call_sell_und", "value_call_sell")
        self.col_u_day_open_price: str = greeks_und_map.get("day_open_price_und", "day_open_price") # For HP_EOD ref
        self.col_u_volatility: str = greeks_und_map.get("volatility_und", "volatility") # Aggregate IV for underlying

        self.use_skew_adjusted_sdag: bool = self._get_config_setting(f"{s_cfg}.use_skew_adjusted_for_sdag", False)
        self.col_sgxoi_calculated: str = self._get_config_setting(f"{s_cfg}.skew_adjusted_gamma_source_col", "sgxoi_calc") # Name for calculated SGEXOI column
        
        self.logger.debug("MetricsCalculatorV2_4 column names initialized from config.")

    def _initialize_common_parameters_from_config(self) -> None:
        """Initializes common calculation parameters from the configuration."""
        dp_cfg = "data_processor_settings"
        s_cfg = "strategy_settings"
        self.logger.debug("Initializing common calculation parameters for MetricsCalculatorV2_4...")

        self.dag_alpha_aligned: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.dag_alpha.aligned", 1.35))
        self.dag_alpha_opposed: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.dag_alpha.opposed", 0.65))
        self.dag_alpha_neutral: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.dag_alpha.neutral", 1.0))

        self.tdpi_beta_aligned: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.tdpi_beta.aligned", 1.3))
        self.tdpi_beta_opposed: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.tdpi_beta.opposed", 0.7))
        self.tdpi_beta_neutral: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.tdpi_beta.neutral", 1.0))
        self.tdpi_gaussian_width: float = float(self._get_config_setting(f"{dp_cfg}.factors.tdpi_gaussian_width", -0.45))
        self.tdpi_atr_fallback_cfg: Dict[str, Any] = self._get_config_setting(f"{dp_cfg}.approximations.tdpi_atr_fallback", {})

        self.vri_gamma_aligned: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.vri_gamma.aligned", 1.3))
        self.vri_gamma_opposed: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.vri_gamma.opposed", 0.7))
        self.vri_gamma_neutral: float = float(self._get_config_setting(f"{dp_cfg}.coefficients.vri_gamma.neutral", 1.0))
        self.vri_vol_trend_fb_factor: float = float(self._get_config_setting(f"{dp_cfg}.factors.vri_vol_trend_fallback_factor", 0.95))
        
        self.vri_0dte_vanna_align_reinforce: float = float(self._get_config_setting(f"{dp_cfg}.factors.vri_0dte_gamma_align_reinforcing", 1.5))
        self.vri_0dte_vanna_align_contradict: float = float(self._get_config_setting(f"{dp_cfg}.factors.vri_0dte_gamma_align_contradicting", 0.5))
        self.vri_0dte_vol_trend_fb_no_hist: float = float(self._get_config_setting(f"{dp_cfg}.factors.vri_0dte_vol_trend_fallback_factor_no_history", 1.0))

        self.vol_trend_avg_days_vri0dte: int = int(self._get_config_setting(f"{dp_cfg}.iv_context_parameters.vol_trend_avg_days_vri0dte", 5))
        self.vol_trend_avg_days_vri_sens: int = int(self._get_config_setting(f"{dp_cfg}.iv_context_parameters.vol_trend_avg_days_vri_sens", 20))
        self.generic_atr_period: int = int(self._get_config_setting(f"{dp_cfg}.approximations.generic_atr_period", 14))

        self.enabled_sdag_methodologies: List[str] = self._get_config_setting(f"{s_cfg}.dag_methodologies.enabled", [])
        self.sdag_methodology_params: Dict[str, Dict[str, Any]] = self._get_config_setting(f"{s_cfg}.dag_methodologies", {})
        
        mre_cfg_path = "market_regime_engine_settings" # Corrected: This should be at top level or strategy_settings
        # Assuming MRE settings are directly under top-level for now, adjust if nested under strategy_settings
        self.mre_time_defs_cfg: Dict[str, str] = self._get_config_setting(f"{mre_cfg_path}.time_of_day_definitions", {})
        
        self.market_open_hour: float = self._time_str_to_float(self.mre_time_defs_cfg.get("morning_start_time", "09:30:00"))
        self.market_close_hour: float = self._time_str_to_float(self.mre_time_defs_cfg.get("market_close_time", "16:00:00"))

        self.iv_rank_col_from_und: Optional[str] = self._get_config_setting(f"{dp_cfg}.iv_context_parameters.iv_rank_col_from_und") # Can be None
        self.clip_percentile: float = float(self._get_config_setting(f"{dp_cfg}.normalization_clip_percentile", 99.0))

        self.gamma_col_for_sdag_calc: str = self.col_sgxoi_calculated if self.use_skew_adjusted_sdag else self.col_gxoi
        self.logger.debug(f"SDAGs will use gamma source column: '{self.gamma_col_for_sdag_calc}' (use_skew_adjusted_sdag: {self.use_skew_adjusted_sdag})")
        self.logger.info("MetricsCalculatorV2_4 common calculation parameters initialized.")

    # --- Utility Methods (Normalization, ATR, DTE, Ensure Columns) ---
    # (These methods: _time_str_to_float, _normalize_series, _ensure_columns_internal, 
    #  _get_atr_internal, _calculate_dte are identical to your provided good versions,
    #  so they are included here verbatim for completeness of the canonical file)

    def _time_str_to_float(self, time_str: str) -> float:
        """
        Converts a time string in HH:MM:SS or HH:MM format to a float representing
        the hour of the day (e.g., "09:30:00" becomes 9.5).

        This utility is primarily used for time-based logic within metric calculations,
        such as determining time weighting factors or checking against configured
        market session times (e.g., from `self.mre_time_defs_cfg`).

        Args:
            time_str (str): The time string to convert. Expected formats are
                            "HH:MM:SS" or "HH:MM".

        Returns:
            float: The time as a float (hours + fraction of an hour), or 0.0 if
                   the input is invalid or parsing fails.
        """
        # This is a core utility; no separate toggle is typically applied here.
        # Its callers (e.g., calculate_tdpi_v2_4) would be toggled.

        if not isinstance(time_str, str):
            self.logger.warning(f"Invalid input type for time string: '{type(time_str)}'. Using 0.0.")
            return 0.0
        try:
            parts = time_str.split(':')
            if len(parts) >= 2:
                h = int(parts[0])
                m = int(parts[1])
                # s = int(parts[2]) if len(parts) > 2 else 0 # Seconds not typically used for float hour
                return h + m / 60.0
            else:
                self.logger.warning(f"Invalid time string format '{time_str}'. Expected HH:MM:SS or HH:MM. Using 0.0.")
                return 0.0
        except (ValueError, IndexError, TypeError) as e: # Added TypeError
            self.logger.warning(f"Error parsing time string '{time_str}': {e}. Using 0.0.")
            return 0.0
            
    def _normalize_series(self, series: pd.Series, series_name_debug: str, method: str = "max_abs", clip_percentile: Optional[float] = None) -> pd.Series:
        """
        Normalizes a pandas Series of numeric data to a common scale, typically for
        comparative analysis or as input to weighted composite indicators like MSPI.

        Supported normalization methods:
        - "max_abs": Scales values to the range [-1, 1] (or [0, 1] if all values are
          non-negative) by dividing by the maximum absolute value in the series.
        - "z_score": Standardizes values by subtracting the mean and dividing by the
          standard deviation (mean = 0, stddev = 1).

        Optionally, the series can be clipped at specified lower and upper percentiles
        (defined by `clip_percentile` or `self.clip_percentile` from config)
        before normalization to mitigate the impact of extreme outliers.

        If the series is empty, non-numeric after coercion, or if the chosen normalization
        denominator (e.g., max_abs_val or std_dev) is too close to zero, a Series of zeros
        is returned.

        Args:
            series (pd.Series): The input pandas Series to normalize.
            series_name_debug (str): A descriptive name for the series, used for logging.
            method (str, optional): The normalization method ("max_abs" or "z_score").
                                    Defaults to "max_abs".
            clip_percentile (Optional[float], optional): The percentile to use for symmetrical
                                                         clipping (e.g., 99.0 means clip at 0.5th
                                                         and 99.5th percentiles). If None,
                                                         `self.clip_percentile` (from config) is used.

        Returns:
            pd.Series: The normalized pandas Series, or a Series of zeros if normalization
                       is not possible.
        """
        # This is a core utility; no separate toggle is typically applied here.
        # Its callers (e.g., calculate_mspi_sai_ssi_v2_4) would be toggled.

        norm_logger = self.logger.getChild(f"NormalizeSeries.{series_name_debug}")
        if not isinstance(series, pd.Series) or series.empty:
            # norm_logger.debug(f"Input series '{series_name_debug}' is empty or not a Series. Returning empty Series.")
            return pd.Series(dtype=float, name=series_name_debug) # Return an empty series with the same name

        series_numeric = pd.to_numeric(series, errors='coerce').fillna(0.0) # Coerce and fill NaNs
        if series_numeric.empty: # Can happen if all values were non-numeric and coerced to NaN
            # norm_logger.debug(f"Series '{series_name_debug}' became empty after numeric coercion and NaN fill. Returning empty Series.")
            return series_numeric.rename(series_name_debug)

        # Clipping logic
        clip_val_to_use = clip_percentile if clip_percentile is not None else self.clip_percentile
        if 0.0 < clip_val_to_use < 100.0 : # Valid percentile for clipping
            q_low = (100.0 - clip_val_to_use) / 2.0
            q_high = 100.0 - q_low
            # Ensure q_low and q_high are valid before trying to get percentiles
            if q_low > 0 and q_high < 100 and q_low < q_high and not series_numeric.dropna().empty: # Also check if series is all NaN after dropna
                try:
                    lower_bound, upper_bound = np.percentile(series_numeric.dropna(), [q_low, q_high])
                    if pd.notna(lower_bound) and pd.notna(upper_bound): # Check if bounds are valid numbers
                        series_numeric = series_numeric.clip(lower_bound, upper_bound)
                    # else: norm_logger.debug(f"Percentile bounds were NaN for '{series_name_debug}', no clipping performed.")
                except IndexError: # Can happen if series_numeric.dropna() is empty
                     pass # norm_logger.debug(f"IndexError during percentile calculation for '{series_name_debug}' (likely all NaNs). No clipping.")
                except Exception as e_clip:
                     norm_logger.warning(f"Error during clipping for '{series_name_debug}': {e_clip}. Proceeding without clipping.")


        if method == "max_abs":
            max_abs_val = series_numeric.abs().max()
            if max_abs_val >= MIN_NORMALIZATION_DENOMINATOR: # Avoid division by zero or tiny numbers
                return (series_numeric / max_abs_val).fillna(0.0)
            else:
                # norm_logger.debug(f"Max absolute value for '{series_name_debug}' is too small ({max_abs_val}). Returning zeros.")
                return pd.Series(0.0, index=series.index, name=series_name_debug)
        elif method == "z_score":
            mean_val = series_numeric.mean() # Calculate mean before std to avoid issues with all-zero series for std
            std_val = series_numeric.std()
            if std_val >= MIN_NORMALIZATION_DENOMINATOR: # Avoid division by zero or tiny numbers
                return ((series_numeric - mean_val) / std_val).fillna(0.0)
            else:
                # norm_logger.debug(f"Standard deviation for '{series_name_debug}' is too small ({std_val}). Returning zeros.")
                return pd.Series(0.0, index=series.index, name=series_name_debug)
        
        norm_logger.warning(f"Unknown normalization method '{method}' for '{series_name_debug}'. Defaulting to max_abs.")
        return self._normalize_series(series, series_name_debug, method="max_abs", clip_percentile=clip_percentile) # Recursive call with default

    def _ensure_columns_internal(self, df: pd.DataFrame, required_cols: List[str], calculation_name: str, fill_numeric_with: Any = 0.0, fill_object_with: str = "UNKNOWN_ENSURE") -> Tuple[pd.DataFrame, bool]:
        """
        Ensures that a list of specified columns exist in the input DataFrame.
        If a required column is missing, it's added and filled with a default value based
        on a heuristic guess of its likely data type (numeric or object).

        It also attempts to convert columns that are expected to be numeric (based on keywords
        in their names) to a numeric data type if they aren't already. If this conversion
        introduces new NaNs (e.g., from unparseable strings), these are logged and filled.
        Existing NaNs in numeric or object columns are also filled with the specified defaults.

        This utility is crucial for robustly preparing DataFrames before they are used in
        metric calculations, preventing `KeyError` exceptions for missing columns and
        `TypeError` exceptions for incorrect data types.

        Args:
            df (pd.DataFrame): The input pandas DataFrame to check and modify.
            required_cols (List[str]): A list of column names that must exist in the DataFrame.
            calculation_name (str): A descriptive name of the calling calculation/process,
                                    used for logging purposes.
            fill_numeric_with (Any, optional): Value to use for filling NaNs in numeric
                                               columns or for newly added numeric columns.
                                               Defaults to 0.0.
            fill_object_with (str, optional): Value to use for filling NaNs in object
                                              columns or for newly added object columns.
                                              Defaults to "UNKNOWN_ENSURE".

        Returns:
            Tuple[pd.DataFrame, bool]:
                - The modified DataFrame (a copy of the input).
                - A boolean indicating if all columns were initially present and valid
                  (True if no columns were added and no type conversions introduced new NaNs,
                  False otherwise).
        """
        # This is a core utility; no separate toggle is typically applied here.
        # Its callers would be toggled.

        ensure_logger = self.logger.getChild(f"EnsureCols.{calculation_name}") # Copied
        df_copy = df.copy() # Work on a copy # Copied
        all_present_and_valid = True # Copied
        missing_cols_added_log: List[str] = [] # Copied
        type_conversion_issues_log: List[str] = [] # Copied

        for col in required_cols: # Copied
            if col not in df_copy.columns: # Copied
                missing_cols_added_log.append(col); all_present_and_valid = False # Copied
                is_likely_numeric = any(s in col.lower() for s in ['oi', 'volm', 'price', 'value', 'strike', 'delta', 'gamma', 'vega', 'theta', 'vanna', 'vomma', 'charm', '_bs', 'ratio', 'exposure', 'flow', 'calc', 'sens', 'multiplier', 'expiration']) or col.endswith(('_api', '_und', '_norm', 'xoi', 'xvolm', '_buy', '_sell')) or col.startswith(('valuebs_', 'volmbs_')) # Copied
                df_copy[col] = fill_numeric_with if is_likely_numeric else fill_object_with # Copied
                # ensure_logger.debug(f"Added missing column '{col}' with {'numeric' if is_likely_numeric else 'object'} default for {calculation_name}.") # Copied
            else: # Column exists # Copied
                is_expected_numeric = any(s in col.lower() for s in ['oi', 'volm', 'price', 'value', 'strike', 'delta', 'gamma', 'vega', 'theta', 'vanna', 'vomma', 'charm', '_bs', 'ratio', 'exposure', 'flow', 'calc', 'sens', 'multiplier', 'expiration']) or col.endswith(('_api', '_und', '_norm', 'xoi', 'xvolm', '_buy', '_sell')) or col.startswith(('valuebs_', 'volmbs_')) # Copied
                if is_expected_numeric and not pd.api.types.is_numeric_dtype(df_copy[col]): # Copied
                    original_non_numeric_sum = (~pd.to_numeric(df_copy[col], errors='coerce').notna()).sum() if df_copy[col].dtype == 'object' else 0 # Copied
                    df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce') # Copied
                    if df_copy[col].isnull().sum() > original_non_numeric_sum : all_present_and_valid = False; type_conversion_issues_log.append(col) # Copied
                if pd.api.types.is_numeric_dtype(df_copy[col]): # Copied
                    if df_copy[col].isnull().any(): df_copy[col] = df_copy[col].fillna(fill_numeric_with) # Copied
        if missing_cols_added_log: ensure_logger.warning(f"For '{calculation_name}', added missing columns: {missing_cols_added_log}.") # Copied
        if type_conversion_issues_log: ensure_logger.warning(f"For '{calculation_name}', type conversion introduced NaNs (then filled) in columns: {type_conversion_issues_log}.") # Copied
        return df_copy, all_present_and_valid # Copied

    def _get_atr_internal(self, symbol: str, current_price: float, period: Optional[int] = None, current_trading_date: Optional[date] = None) -> float:
        """
        Calculates the Average True Range (ATR) for a given symbol, typically for a specified period.
        This method is a core utility used by other metric calculations (e.g., TDPI for strike
        proximity weighting, or by the TradeParameterOptimizer for setting stops/targets).

        It attempts to retrieve historical Open-High-Low-Close (OHLCV) data via the
        HistoricalDataManager. The historical data is expected to be available up to
        the day *before* the 'current_trading_date'.

        If sufficient historical data is not available or if the HistoricalDataManager
        is not properly initialized, or if OHLCV retrieval is disabled via config,
        this method employs fallback mechanisms.

        The ATR period defaults to 'data_processor_settings.approximations.generic_atr_period'
        if not explicitly provided.

        This calculation can be toggled off via the 'utility_calculate_atr' configuration setting.
        If disabled, it returns a basic percentage-of-price fallback or a minimum default.
        """
        atr_logger = self.logger.getChild(f"GetATRInternal.{symbol}")

        # Outer toggle for the entire ATR utility
        if not self.metric_phases_activation_cfg.get("utility_calculate_atr", True):
            atr_logger.info(f"ATR calculation for {symbol} SKIPPED by global config toggle 'utility_calculate_atr'.")
            if not isinstance(current_price, (int, float)) or pd.isna(current_price) or current_price <= 0:
                atr_logger.warning(f"ATR SKIPPED & FALLBACK: Invalid current_price ({current_price}) for {symbol}. Returning DEFAULT_ATR_FALLBACK_MIN_VALUE.")
                return DEFAULT_ATR_FALLBACK_MIN_VALUE
            return max(DEFAULT_ATR_FALLBACK_MIN_VALUE, current_price * DEFAULT_ATR_FALLBACK_PERCENTAGE)

        atr_period_to_use = period if period is not None and period > 0 else self.generic_atr_period # type: ignore

        date_for_hist_lookup = current_trading_date
        if date_for_hist_lookup is None:
            if self.current_processing_time_dt:
                date_for_hist_lookup = self.current_processing_time_dt.date()
            else:
                date_for_hist_lookup = date.today()
                atr_logger.warning(f"ATR: current_trading_date and self.current_processing_time_dt are None. Using today ({date_for_hist_lookup}).")

        if not isinstance(symbol, str) or not symbol:
            atr_logger.error("ATR: Symbol is invalid. Using ultimate fallback ATR value.")
            return DEFAULT_ATR_FALLBACK_MIN_VALUE
        if not isinstance(current_price, (int, float)) or pd.isna(current_price) or current_price <= 0:
            atr_logger.warning(f"ATR for {symbol}: Current price invalid ({current_price}). Using ultimate fallback ATR value.")
            return DEFAULT_ATR_FALLBACK_MIN_VALUE
        if not isinstance(atr_period_to_use, int) or atr_period_to_use <= 0:
            atr_logger.warning(f"ATR for {symbol}: Period invalid ({atr_period_to_use}). Defaulting to {self.generic_atr_period}.") # type: ignore
            atr_period_to_use = self.generic_atr_period # type: ignore

        # Check if HDM OHLCV retrieval is enabled
        hdm_ohlcv_retrieval_active = self.config_manager.get_setting(
            ["system_settings", "historical_data_manager_activation", "enable_ohlcv_retrieval"],
            default_value_to_return=True
        )

        if self.historical_data_manager and hasattr(self.historical_data_manager, 'get_ohlc_history_for_atr') and hdm_ohlcv_retrieval_active:
            num_days_to_fetch_hdm = atr_period_to_use + 20
            atr_logger.debug(f"Requesting {num_days_to_fetch_hdm} days of OHLCV history for {symbol} up to {date_for_hist_lookup - timedelta(days=1)} from HDM for ATR({atr_period_to_use}).")
            ohlc_hist_df = self.historical_data_manager.get_ohlc_history_for_atr(symbol, num_days_to_fetch_hdm, date_for_hist_lookup)

            if ohlc_hist_df is not None and isinstance(ohlc_hist_df, pd.DataFrame) and not ohlc_hist_df.empty:
                atr_logger.debug(f"Received {len(ohlc_hist_df)} OHLCV bars from HDM for {symbol} for ATR calculation.")
                required_ohlc_cols = ['high', 'low', 'close', 'date']
                df_atr, ohlc_cols_ok = self._ensure_columns_internal(ohlc_hist_df.copy(), required_ohlc_cols, f"ATR_OHLC_{symbol}", fill_numeric_with=np.nan)

                if ohlc_cols_ok and len(df_atr) >= 2:
                    try:
                        for col_atr in ['high', 'low', 'close']:
                            df_atr[col_atr] = pd.to_numeric(df_atr[col_atr], errors='coerce')
                        df_atr['date'] = pd.to_datetime(df_atr['date'], errors='coerce')
                        df_atr = df_atr.dropna(subset=['high', 'low', 'close', 'date']).sort_values(by='date').reset_index(drop=True)

                        min_rows_needed_for_calc = max(2, atr_period_to_use // 2 if atr_period_to_use > 2 else 2)
                        if len(df_atr) < min_rows_needed_for_calc:
                            atr_logger.warning(f"Not enough valid OHLC rows for {symbol} ({len(df_atr)}) after cleaning for ATR({atr_period_to_use}). Min needed: {min_rows_needed_for_calc}. Using fallback ATR.")
                        else:
                            df_atr['h_minus_l'] = df_atr['high'] - df_atr['low']
                            df_atr['h_minus_pc'] = np.abs(df_atr['high'] - df_atr['close'].shift(1))
                            df_atr['l_minus_pc'] = np.abs(df_atr['low'] - df_atr['close'].shift(1))

                            tr_col_components = [df_atr['h_minus_l']]
                            if 'h_minus_pc' in df_atr.columns: tr_col_components.append(df_atr['h_minus_pc'])
                            if 'l_minus_pc' in df_atr.columns: tr_col_components.append(df_atr['l_minus_pc'])

                            tr_col = pd.concat(tr_col_components, axis=1).max(axis=1, skipna=False)
                            if not df_atr.empty and 'h_minus_l' in df_atr.columns and pd.notna(df_atr['h_minus_l'].iloc[0]):
                                tr_col.iloc[0] = df_atr['h_minus_l'].iloc[0]

                            df_atr['tr_calc'] = tr_col
                            tr_series_for_atr = df_atr['tr_calc'].dropna()

                            if len(tr_series_for_atr) >= atr_period_to_use:
                                atr_series = tr_series_for_atr.ewm(span=atr_period_to_use, adjust=False, min_periods=atr_period_to_use).mean()
                                if not atr_series.empty and pd.notna(atr_series.iloc[-1]) and np.isfinite(atr_series.iloc[-1]):
                                    atr_val = atr_series.iloc[-1]
                                    if atr_val > EPSILON:
                                        min_atr_val_from_cfg = float(self._get_config_setting(["data_processor_settings", "approximations", "tdpi_atr_fallback", "min_value"], DEFAULT_ATR_FALLBACK_MIN_VALUE))
                                        atr_logger.info(f"ATR for {symbol} (period {atr_period_to_use}) calculated from HDM data: {atr_val:.4f}")
                                        return max(atr_val, min_atr_val_from_cfg)
                                    else:
                                        atr_logger.warning(f"Calculated ATR for {symbol} from HDM data is not positive ({atr_val:.4f}). Using fallback.")
                            else:
                                atr_logger.warning(f"Not enough TR values ({len(tr_series_for_atr)}) for {symbol} to calculate ATR({atr_period_to_use}) after NaN drop. Using fallback.")
                    except Exception as e_atr_calc:
                        atr_logger.error(f"ATR {symbol}: Error during ATR calculation from historical data: {e_atr_calc}", exc_info=True)
            else:
                atr_logger.info(f"No or insufficient historical OHLCV data received from HDM for {symbol} for ATR({atr_period_to_use}). Using fallback ATR.")
        elif not hdm_ohlcv_retrieval_active:
            atr_logger.info(f"HDM OHLCV retrieval for ATR for {symbol} is disabled by global config. Using direct fallback ATR.")
        else: # HistoricalDataManager not available or method missing
            atr_logger.warning(f"HistoricalDataManager not available/valid or OHLCV retrieval disabled for ATR for {symbol}. Using fallback ATR.")

        # Fallback ATR logic (consolidated)
        atr_fallback_cfg_local = self._get_config_setting(["data_processor_settings", "approximations", "tdpi_atr_fallback"], {})
        min_fallback_val_attr = float(atr_fallback_cfg_local.get("min_value", DEFAULT_ATR_FALLBACK_MIN_VALUE))
        
        calculated_fallback_atr_value: float
        if atr_fallback_cfg_local.get("type") == "percentage_of_price" and isinstance(current_price, (int, float)) and current_price > 0:
            percentage_attr = float(atr_fallback_cfg_local.get("percentage", DEFAULT_ATR_FALLBACK_PERCENTAGE))
            calculated_fallback_atr_value = max(current_price * percentage_attr, min_fallback_val_attr)
            atr_logger.info(f"ATR for {symbol} (Fallback): Using percentage-of-price ({calculated_fallback_atr_value:.4f}) from {percentage_attr*100:.2f}% of Price {current_price:.2f}.")
        else:
            calculated_fallback_atr_value = min_fallback_val_attr
            atr_logger.warning(f"ATR for {symbol} (Fallback): Using ultimate minimum value ({calculated_fallback_atr_value:.4f}).")
        return calculated_fallback_atr_value
    
    def _calculate_dte(self, df_contracts: pd.DataFrame, current_processing_date: date) -> pd.Series:
        """
        Calculates the Days To Expiration (DTE) for each option contract in the input DataFrame.
        Uses the 'expiration_days_from_epoch_calc' column (expected from InitialProcessor 
        after converting raw expiration dates) and the provided 'current_processing_date'.
        
        The output DTE is clipped at a minimum of 0 (representing 0DTE).
        This method can be toggled off via the 'utility_calculate_dte' configuration setting;
        if disabled, it returns a Series of -1s or an empty Series.

        Args:
            df_contracts (pd.DataFrame): DataFrame containing option contracts with an
                                         expiration column (e.g., 'expiration_days_from_epoch_calc').
            current_processing_date (date): The current date against which to calculate DTE.

        Returns:
            pd.Series: A pandas Series containing the calculated DTE for each contract,
                       named 'dte_calc'. Returns -1 for unparseable or invalid DTEs if
                       calculation is attempted but fails, or if toggled off and input is not empty.
                       Returns an empty Series if input df_contracts is empty.
        """
        # Toggle Key in config: "utility_calculate_dte"
        if not self.metric_phases_activation_cfg.get("utility_calculate_dte", True): # Default to True (essential utility)
            self.logger.info(f"DTE calculation for {self.current_processing_symbol} SKIPPED by config toggle 'utility_calculate_dte'.")
            if isinstance(df_contracts, pd.DataFrame) and not df_contracts.empty:
                return pd.Series(-1, index=df_contracts.index, name='dte_calc')
            return pd.Series(dtype=int, name='dte_calc') # Empty series if input is empty

        # --- Original _calculate_dte logic continues here ---
        dte_logger = self.logger.getChild("DTESeriesCalc")
        if not isinstance(df_contracts, pd.DataFrame) or df_contracts.empty:
            return pd.Series(dtype=int, name='dte_calc')
        if self.col_expiration not in df_contracts.columns:
            dte_logger.error(f"Expiration col '{self.col_expiration}' missing. Cannot calc DTE.")
            return pd.Series(-1, index=df_contracts.index, name='dte_calc')
        if not isinstance(current_processing_date, date):
            dte_logger.error(f"Invalid 'current_processing_date' for DTE. Type: {type(current_processing_date)}.")
            return pd.Series(-1, index=df_contracts.index, name='dte_calc')

        try:
            epoch_date = date(1970, 1, 1)
            current_days_since_epoch = (current_processing_date - epoch_date).days
        except Exception as e_epoch: # Catch potential errors with date arithmetic
            dte_logger.error(f"Error calculating current_days_since_epoch for DTE: {e_epoch}")
            return pd.Series(-1, index=df_contracts.index, name='dte_calc')
        
        exp_days_since_epoch = pd.to_numeric(df_contracts[self.col_expiration], errors='coerce')
        
        # Calculate DTE
        dte_values = (exp_days_since_epoch - current_days_since_epoch)
        
        # Fill NaNs (from coercion errors or if exp_days_since_epoch was NaN) with -1 before astype(int)
        # Then clip to ensure DTE is non-negative.
        # Values that were NaN will become -1, then clipped to 0.
        # Valid DTEs will be calculated, then clipped to 0 if they were negative (past expiration).
        dte_values = dte_values.fillna(-1).astype(int).clip(lower=0)
        
        return dte_values.rename('dte_calc')

    # --------------------------------------- Main Orchestration Method -------------------------------------------

    # --- Main Orchestration Method ---
    def orchestrate_all_metric_calculations(
        self,
        options_df_raw: pd.DataFrame,
        und_data_api_raw: Dict[str, Any],
        current_time_dt: datetime,
        symbol: str
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """
        Main orchestration method for the entire metric calculation pipeline for a given symbol and time.
        This function serves as the central hub within MetricsCalculatorV2_4, coordinating the
        sequential execution of various specialized metric calculation methods.

        Key Responsibilities:
        1.  Initializes per-cycle instance variables like current symbol, time, underlying data,
            price, and multiplier. Validates critical inputs like underlying price.
        2.  Adds common context columns (e.g., DTE, current price, symbol) to the raw options DataFrame.
        3.  Conditionally executes blocks of metric calculations based on phase activation toggles
            defined in `system_settings.metric_calculation_phases_activation` from the configuration.
            These phases include:
            - Core structural metrics (DAG, TDPI, VRI-Sensitivity)
            - SDAG methodologies (including SGXOI if enabled)
            - 0DTE suite (vri_0dte, vvr_0dte, vfi_0dte, vci_0dte contract prep)
            - Strike-level flow metrics (NVP, ARFI)
            - MSPI suite (MSPI, SAI, SSI, including component normalization)
        4.  Aggregates per-contract metrics to the strike level after relevant chain-level
            calculations are complete.
        5.  Calls `calculate_underlying_aggregate_metrics_v2_4` to compute summary metrics
            for the underlying security, enriching the input `und_data_api_raw`. This sub-orchestrator
            also respects its own internal phase toggles for groups like rolling flows,
            net customer greek flows, dealer positioning metrics (GIB, td_gib, HP_EOD), etc.
        6.  Ensures that any pre-existing keys in `und_data_api_raw` (such as IV metrics potentially
            sourced from Tradier by the ITSOrchestrator) are preserved and carried through
            in the final enriched underlying data dictionary.
        7.  If the master toggle "run_metric_orchestration" is disabled in the config, this entire
            orchestration process is skipped, returning basic data structures.

        Args:
            options_df_raw (pd.DataFrame): The raw options chain data, typically from
                                           InitialDataProcessor after basic fetcher parsing.
            und_data_api_raw (Dict[str, Any]): The raw and potentially pre-enriched underlying
                                               data dictionary.
            current_time_dt (datetime): The current processing timestamp for this cycle.
            symbol (str): The symbol for which metrics are being calculated.

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
                - df_chain (pd.DataFrame): Options chain DataFrame enriched with all calculated
                                           per-contract and relevant strike-level metrics.
                - df_strike_level_metrics (pd.DataFrame): DataFrame containing metrics aggregated
                                                          or calculated purely at the strike level.
                - und_data_enriched (Dict[str, Any]): The underlying data dictionary, enriched
                                                      with all calculated aggregate metrics.
        """
        # Toggle Key in config: "run_metric_orchestration" (master toggle for this entire function)
        if not self.metric_phases_activation_cfg.get("run_metric_orchestration", True):
            self.logger.info(f"Metric Orchestration for {symbol} SKIPPED entirely by config toggle 'run_metric_orchestration'.")
            empty_df = pd.DataFrame()
            und_data_to_return = und_data_api_raw.copy() if isinstance(und_data_api_raw, dict) else {}
            if 'symbol' not in und_data_to_return and symbol:
                und_data_to_return['symbol'] = symbol
            und_data_to_return['error_metrics_calc'] = "Metric orchestration disabled by config."
            # Return structure consistent with a successful but data-empty run for downstream safety
            return empty_df, empty_df, und_data_to_return
        
        orchestrate_logger = self.logger.getChild(f"OrchestrateMetrics.{symbol}")
        orchestrate_logger.info(f"Starting all metric calculations for '{symbol}' at {current_time_dt.isoformat()}")
        orchestrate_logger.debug(f"Active metric phases: {self.metric_phases_activation_cfg}")

        # --- Set Per-Cycle Instance Variables ---
        self.current_processing_symbol = symbol
        self.current_processing_time_dt = current_time_dt
        self.current_und_data_api = und_data_api_raw.copy() if isinstance(und_data_api_raw, dict) else {}
        
        # ... (Existing price/multiplier setup and validation) ...
        raw_price_from_und_data = self.current_und_data_api.get(self.col_und_price) 
        raw_multiplier_from_und_data = self.current_und_data_api.get(self.col_und_multiplier)
        try:
            self.current_und_price = float(raw_price_from_und_data) if raw_price_from_und_data is not None and pd.notna(raw_price_from_und_data) else 0.0
        except (ValueError, TypeError):
            orchestrate_logger.error(f"Underlying price '{raw_price_from_und_data}' for {symbol} is invalid. Defaulting to 0.0.")
            self.current_und_price = 0.0
        try:
            default_mult_from_cfg = self._get_config_setting("strategy_settings.contract_multiplier_default_value", 100.0)
            self.current_und_multiplier = float(raw_multiplier_from_und_data) if raw_multiplier_from_und_data is not None and pd.notna(raw_multiplier_from_und_data) else default_mult_from_cfg
        except (ValueError, TypeError):
            orchestrate_logger.error(f"Underlying multiplier '{raw_multiplier_from_und_data}' for {symbol} is invalid. Defaulting to configured default.")
            self.current_und_multiplier = self._get_config_setting("strategy_settings.contract_multiplier_default_value", 100.0)

        if self.current_und_price <= 0:
            orchestrate_logger.critical(f"Underlying Price for {symbol} is invalid or zero ({self.current_und_price}). Most metric calculations will be skipped or inaccurate.")
            empty_df = pd.DataFrame()
            und_data_enriched_on_error = self.current_und_data_api.copy()
            if 'symbol' not in und_data_enriched_on_error: und_data_enriched_on_error['symbol'] = symbol
            und_data_enriched_on_error['error_metrics_calc'] = "Invalid underlying price for metric calculations."
            return empty_df, empty_df, und_data_enriched_on_error


        df_chain = options_df_raw.copy() if isinstance(options_df_raw, pd.DataFrame) else pd.DataFrame()
        df_strike_level_metrics = pd.DataFrame() # Initialize empty

        # --- A. Add Common Context Columns to df_chain ---
        orchestrate_logger.info(f"[{symbol}] Step A: Adding context columns to df_chain (Initial Shape: {df_chain.shape}).")
        if not df_chain.empty:
            df_chain[self.col_und_price] = self.current_und_price
            df_chain[self.col_und_multiplier] = self.current_und_multiplier
            if 'current_time_dt' not in df_chain.columns: df_chain['current_time_dt'] = current_time_dt
            if 'symbol' not in df_chain.columns: df_chain['symbol'] = symbol
            if 'underlying_symbol_calc' not in df_chain.columns: df_chain['underlying_symbol_calc'] = symbol
            df_chain['dte_calc'] = self._calculate_dte(df_chain, current_time_dt.date())
        else: # If df_chain is empty, df_strike_level_metrics will also be empty.
            orchestrate_logger.warning(f"[{symbol}] Input options_df_raw is empty. Chain-dependent metrics and strike aggregations will be skipped.")
            # No need to initialize df_strike_level_metrics again, it's already empty.
            # Underlying aggregates will still be calculated.

        # --- B. Per-Contract & Initial Strike-Aggregated Metrics (DAG, SDAGs, TDPI, VRI-Sens) ---
        if self.metric_phases_activation_cfg.get("core_structural_metrics", True):
            orchestrate_logger.info(f"[{symbol}] Step B: Calculating core structural metrics (DAG, TDPI, VRI-Sens)...")
            if not df_chain.empty:
                df_chain = self.calculate_dag_custom_v2_4(df_chain)
                df_chain = self.calculate_tdpi_v2_4(df_chain)
                df_chain = self.calculate_vri_sensitivity_v2_4(df_chain)
            orchestrate_logger.debug(f"[{symbol}] Step B.1 (Core Structural) complete.")
        else:
            orchestrate_logger.info(f"[{symbol}] Step B.1: Core Structural Metrics (DAG, TDPI, VRI-Sens) SKIPPED by config.")
            # Ensure columns exist for later steps if they are used regardless
            for col in ['dag_custom', 'tdpi', 'ctr_strike', 'tdfi_strike', 'vri_sensitivity', 'vvr_sens_strike', 'vfi_sens_strike']:
                if col not in df_chain.columns and not df_chain.empty: df_chain[col] = 0.0

        if self.metric_phases_activation_cfg.get("sdag_methodologies", True):
            orchestrate_logger.info(f"[{symbol}] Step B.2: Calculating SDAG methodologies...")
            if not df_chain.empty:
                if self.use_skew_adjusted_sdag:
                    und_atm_iv_for_sgxoi = float(self.current_und_data_api.get(self.col_u_volatility, 0.20))
                    df_chain = self.calculate_sgxoi_v2_4(df_chain, und_atm_iv_for_sgxoi)
                df_chain = self.calculate_all_sdags_v2_4(df_chain)
            orchestrate_logger.debug(f"[{symbol}] Step B.2 (SDAGs) complete.")
        else:
            orchestrate_logger.info(f"[{symbol}] Step B.2: SDAG Methodologies SKIPPED by config.")
            for method_name in self.enabled_sdag_methodologies:
                if f"sdag_{method_name}" not in df_chain.columns and not df_chain.empty : df_chain[f"sdag_{method_name}"] = 0.0

        # --- C. Processes 0DTE Suite specific metrics ---
        if self.metric_phases_activation_cfg.get("0dte_suite", True):
            orchestrate_logger.info(f"[{symbol}] Step C: Processing 0DTE specific metrics...")
            # ... (existing 0DTE logic, but ensure it handles empty df_chain gracefully if prior steps were skipped) ...
            if not df_chain.empty and 'dte_calc' in df_chain.columns:
                df_0dte_subset = df_chain[df_chain['dte_calc'] == 0].copy()
                # ... (rest of 0DTE logic)
                # Merge back as before
                cols_0dte_to_merge_back = ['vri_0dte', 'vvr_0dte', 'vfi_0dte', 'abs_vannaxoi_contract'] # define this list explicitly
                if not df_0dte_subset.empty and cols_0dte_to_merge_back:
                    merge_keys_0dte = [self.col_strike, self.col_opt_kind, self.col_expiration] 
                    if all(key in df_0dte_subset.columns for key in merge_keys_0dte) and all(key in df_chain.columns for key in merge_keys_0dte):
                        # ... merge logic ...
                        pass # Placeholder for brevity
            else:
                 orchestrate_logger.debug(f"[{symbol}] Step C: Skipping 0DTE subset processing as df_chain is empty or missing 'dte_calc'.")
        else:
            orchestrate_logger.info(f"[{symbol}] Step C: 0DTE Suite SKIPPED by config.")
        # Default 0DTE columns if not created
        for col_0dte in ['vri_0dte', 'vvr_0dte', 'vfi_0dte', 'abs_vannaxoi_contract']:
            if col_0dte not in df_chain.columns and not df_chain.empty: df_chain[col_0dte] = 0.0
            elif not df_chain.empty: df_chain[col_0dte] = df_chain[col_0dte].fillna(0.0)


        # --- D. Aggregates Per-Contract to Strike Level ---
        orchestrate_logger.info(f"[{symbol}] Step D: Aggregating per-contract metrics to strike level...")
        # This aggregation should happen regardless of toggles, but will only aggregate columns that *were* calculated
        # ... (existing aggregation logic from your file for final_strike_agg_spec) ...
        strike_agg_specification: Dict[str, Union[str, Callable]] = {}
        cols_to_sum_to_strike = [
            self.col_dxoi, self.col_gxoi, self.col_vxoi, self.col_txoi, self.col_vannaxoi, self.col_vommaxoi, self.col_charmxoi, self.col_oi,
            self.col_dxvolm, self.col_gxvolm, self.col_vxvolm, self.col_txvolm, self.col_vannaxvolm, self.col_vommaxvolm, self.col_charmxvolm,
            self.col_c_deltas_buy, self.col_c_deltas_sell, self.col_c_gammas_buy, self.col_c_gammas_sell,
            self.col_c_vegas_buy, self.col_c_vegas_sell, self.col_c_thetas_buy, self.col_c_thetas_sell
        ]
        for col in cols_to_sum_to_strike:
            if col in df_chain.columns: strike_agg_specification[col] = 'sum'
        
        metrics_to_take_first_or_sum_at_strike = [
            'dag_custom', 'tdpi', 'ctr_strike', 'tdfi_strike', 'vri_sensitivity', 'vvr_sens_strike', 'vfi_sens_strike',
            'vri_0dte', 'vvr_0dte', 'vfi_0dte' 
        ] + [f"sdag_{m}" for m in self.enabled_sdag_methodologies]
        for col in metrics_to_take_first_or_sum_at_strike:
            if col in df_chain.columns:
                if col in ['vri_0dte', 'vvr_0dte', 'vfi_0dte']: 
                    strike_agg_specification[col] = 'sum'
                else: 
                    strike_agg_specification[col] = 'first' 
        
        context_cols_for_strike = [self.col_und_price, self.col_und_multiplier, 'current_time_dt', 'symbol', 'underlying_symbol_calc']
        for col in context_cols_for_strike:
            if col in df_chain.columns: strike_agg_specification[col] = 'first' 
        if 'dte_calc' in df_chain.columns: strike_agg_specification['dte_calc'] = 'min'

        final_strike_agg_spec = {k: v for k, v in strike_agg_specification.items() if k in df_chain.columns}

        if not df_chain.empty and self.col_strike in df_chain.columns and final_strike_agg_spec:
            df_strike_level_metrics = df_chain.groupby(self.col_strike, as_index=False).agg(final_strike_agg_spec).fillna(0.0)
        elif not df_chain.empty and self.col_strike in df_chain.columns: # Only strikes and context
             df_strike_level_metrics = df_chain[[self.col_strike] + [c for c in context_cols_for_strike + ['dte_calc'] if c in df_chain.columns]].drop_duplicates(subset=[self.col_strike]).reset_index(drop=True)
        else: # df_chain was empty or had no strike column
            df_strike_level_metrics = pd.DataFrame() # Ensure it's an empty DF

        orchestrate_logger.debug(f"[{symbol}] Step D complete. df_strike_level_metrics shape: {df_strike_level_metrics.shape}")


        # --- E. Calculates further Strike-Level Metrics (NVP, ARFI) ---
        if self.metric_phases_activation_cfg.get("flow_metrics_nvp_arfi", True):
            orchestrate_logger.info(f"[{symbol}] Step E: Calculating NVP, ARFI at strike level...")
            if not df_strike_level_metrics.empty or not df_chain.empty: # NVP needs df_chain for flows
                df_strike_level_metrics = self.calculate_nvp_nvp_vol_per_strike_v2_4(df_strike_level_metrics, df_chain)
            if not df_strike_level_metrics.empty: # ARFI needs df_strike_level_metrics with OI and flow proxies
                df_strike_level_metrics = self.calculate_arfi_strike_level_v2_4(df_strike_level_metrics)
            orchestrate_logger.debug(f"[{symbol}] Step E complete.")
        else:
            orchestrate_logger.info(f"[{symbol}] Step E: NVP & ARFI SKIPPED by config.")
            for col in ['nvp_strike', 'nvp_vol_strike', 'arfi_strike']:
                if col not in df_strike_level_metrics.columns and not df_strike_level_metrics.empty: df_strike_level_metrics[col] = 0.0


        # --- F. & G. MSPI Suite (Normalization and Calculation) ---
        # This could be its own phase "mspi_suite_calculation"
        if self.metric_phases_activation_cfg.get("mspi_suite_calculation", True):
            orchestrate_logger.info(f"[{symbol}] Step F & G: Normalizing MSPI components and Calculating MSPI, SAI, SSI...")
            if not df_strike_level_metrics.empty:
                # Normalization (Step F)
                mspi_comp_src_cols = {
                    'dag_custom': 'dag_custom_norm', 'tdpi': 'tdpi_norm', 'vri_sensitivity': 'vri_sensitivity_norm',
                    'arfi_strike': 'arfi_strike_norm', 'vri_0dte': 'vri_0dte_norm', 'vfi_0dte': 'vfi_0dte_norm'
                }
                for sdag_m in self.enabled_sdag_methodologies: mspi_comp_src_cols[f"sdag_{sdag_m}"] = f"sdag_{sdag_m}_norm"
                df_strike_level_metrics, _ = self._ensure_columns_internal(df_strike_level_metrics, list(mspi_comp_src_cols.keys()), "MSPI_NormSrcCheck")
                for raw_col, norm_col in mspi_comp_src_cols.items():
                    if raw_col in df_strike_level_metrics.columns:
                        df_strike_level_metrics[norm_col] = self._normalize_series(df_strike_level_metrics[raw_col], norm_col, clip_percentile=self.clip_percentile)
                    else: df_strike_level_metrics[norm_col] = 0.0
                # Calculation (Step G)
                current_regime_for_weights = self.current_und_data_api.get("current_market_regime_snapshot", self._get_config_setting("market_regime_engine_settings.default_regime", "REGIME_UNCLEAR_LOW_CONVICTION"))
                mspi_weights = self._get_mspi_weights_v2_4_metrics_calc(current_time_dt.time(), self.current_und_data_api, current_regime_for_weights)
                df_strike_level_metrics = self.calculate_mspi_sai_ssi_v2_4(df_strike_level_metrics, mspi_weights)
            orchestrate_logger.debug(f"[{symbol}] Step F & G (MSPI Suite) complete.")
        else:
            orchestrate_logger.info(f"[{symbol}] Step F & G: MSPI Suite Calculation SKIPPED by config.")
            for col in ['mspi_raw', 'mspi', 'sai', 'ssi_agg']: # Ensure MSPI output columns exist
                if col not in df_strike_level_metrics.columns and not df_strike_level_metrics.empty: df_strike_level_metrics[col] = 0.0


        # --- H. Calculates Underlying-Level Aggregate Metrics ---
        # We'll make calculate_underlying_aggregate_metrics_v2_4 internally respect the toggles too.
        orchestrate_logger.info(f"[{symbol}] Step H: Calculating final underlying-level aggregate metrics...")
        und_data_enriched = self.calculate_underlying_aggregate_metrics_v2_4(
            self.current_und_data_api, df_chain, df_strike_level_metrics, current_time_dt.time()
        )
        if 'symbol' not in und_data_enriched or und_data_enriched.get('symbol') != symbol:
            und_data_enriched['symbol'] = symbol
        if 'underlying_metrics_calculation_timestamp' not in und_data_enriched:
            und_data_enriched['underlying_metrics_calculation_timestamp'] = datetime.now().isoformat()

        orchestrate_logger.info(f"[{symbol}] All metric calculations complete. Final df_chain: {df_chain.shape}, df_strike: {df_strike_level_metrics.shape}, und_data keys: {len(und_data_enriched)}.")
        return df_chain, df_strike_level_metrics, und_data_enriched

    # ----------------------------------- Placeholder for Individual Metric Calculations --------------------------------
    # --- Individual Metric Calculation Methods (Per-Contract / Per-Strike Focus) ---

    def calculate_dag_custom_v2_4(self, df_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the Delta Adjusted Gamma Exposure (DAG_Custom) per strike.
        This metric integrates Gamma Exposure (GXOI) and Delta Exposure (DXOI) from open interest
        with recent net delta and gamma flows to provide a flow-confirmed view of potential
        market maker hedging pressure.

        The calculation involves:
        1. Aggregating GXOI, DXOI, and relevant flow proxies (or direct signed flows if available)
           to the strike level.
        2. Determining an Alpha coefficient based on the alignment of structural delta exposure (DXOI)
           and recent net delta flow.
        3. Computing a ratio of net delta flow magnitude to delta OI magnitude.
        4. Normalizing the net gamma flow component.
        5. Combining these factors with base gamma exposure and delta exposure sign.

        This metric is a key input to the MSPI (Market Structure Position Indicator).
        The calculation can be toggled off via the "calculate_dag_custom" config setting,
        or if its parent phase "core_structural_metrics" is disabled. If skipped,
        the 'dag_custom' column will be added to the DataFrame with default (0.0) values.

        Args:
            df_chain (pd.DataFrame): The input options chain DataFrame, expected to contain
                                     GXOI, DXOI, and flow-related columns per contract.

        Returns:
            pd.DataFrame: The input DataFrame with an added 'dag_custom' column,
                          representing the calculated DAG value broadcasted to each contract
                          at its respective strike.
        """
        # Toggle Key in config: "calculate_dag_custom"
        # Also implicitly part of phase: "core_structural_metrics"
        # Check the specific toggle first, then the phase toggle.
        if not self.metric_phases_activation_cfg.get("calculate_dag_custom", True) or \
           not self.metric_phases_activation_cfg.get("core_structural_metrics", True):
            self.logger.info(f"DAG Custom calculation for {self.current_processing_symbol} SKIPPED by config.")
            # Ensure 'dag_custom' column exists with a default if skipped
            if isinstance(df_chain, pd.DataFrame) and 'dag_custom' not in df_chain.columns and not df_chain.empty:
                df_chain['dag_custom'] = 0.0
            elif isinstance(df_chain, pd.DataFrame) and df_chain.empty and 'dag_custom' not in df_chain.columns:
                # If input df is empty, add the column so schema is consistent if it's expected
                df_chain['dag_custom'] = pd.Series(dtype=float)
            return df_chain

        # --- Original calculate_dag_custom_v2_4 logic continues here ---
        df = df_chain.copy()
        calc_name = "DAG_Custom_V2.4_MC"
        dag_logger = self.logger.getChild(calc_name)

        required_cols_chain = [self.col_strike, self.col_gxoi, self.col_dxoi]
        signed_flow_cols = [self.col_c_deltas_buy, self.col_c_deltas_sell, self.col_c_gammas_buy, self.col_c_gammas_sell]
        proxy_flow_cols = [self.col_dxvolm, self.col_gxvolm]

        df_check_signed, signed_cols_ok_initially = self._ensure_columns_internal(df.copy(), signed_flow_cols, calc_name + "_SignedCheck", fill_numeric_with=np.nan)
        use_signed_flows = signed_cols_ok_initially and not df_check_signed[signed_flow_cols].isnull().values.all()

        if use_signed_flows:
            dag_logger.debug(f"{calc_name} ({self.current_processing_symbol}): Using direct signed Greek flows for DAG.")
            required_cols_chain.extend(signed_flow_cols)
        else:
            dag_logger.info(f"{calc_name} ({self.current_processing_symbol}): Direct signed flows for DAG not fully available/valid. Using dxvolm/gxvolm proxies.")
            required_cols_chain.extend(proxy_flow_cols)
            # Ensure proxy columns exist if we fall back to them
            df, _ = self._ensure_columns_internal(df, proxy_flow_cols, calc_name + "_ProxyEnsure", fill_numeric_with=0.0)


        df, cols_ok_final = self._ensure_columns_internal(df, required_cols_chain, calc_name, fill_numeric_with=0.0)

        if not cols_ok_final or df.empty:
            dag_logger.warning(f"{calc_name} ({self.current_processing_symbol}): Missing core inputs (GXOI, DXOI, or flows) or empty DF after ensure. 'dag_custom' will be 0.")
            if 'dag_custom' not in df.columns and not df.empty: df['dag_custom'] = 0.0
            elif df.empty and 'dag_custom' not in df.columns: df['dag_custom'] = pd.Series(dtype=float)
            return df

        agg_rules_dag = {self.col_gxoi: 'sum', self.col_dxoi: 'sum'}
        flow_cols_to_agg = signed_flow_cols if use_signed_flows else proxy_flow_cols
        for col in flow_cols_to_agg:
            if col in df.columns: # Only add to agg_rules if column exists after ensure
                 agg_rules_dag[col] = 'sum'

        valid_agg_keys = {k: v for k, v in agg_rules_dag.items() if k in df.columns}

        if not valid_agg_keys or self.col_strike not in df.columns or not any(fc in valid_agg_keys for fc in flow_cols_to_agg):
            dag_logger.error(f"{calc_name} ({self.current_processing_symbol}): Essential columns for strike aggregation or flow data missing. 'dag_custom' set to 0.")
            if 'dag_custom' not in df.columns and not df.empty: df['dag_custom'] = 0.0
            elif df.empty and 'dag_custom' not in df.columns: df['dag_custom'] = pd.Series(dtype=float)
            return df

        df_strike = df.groupby(self.col_strike, as_index=False).agg(valid_agg_keys).fillna(0.0)

        if df_strike.empty:
            dag_logger.warning(f"{calc_name} ({self.current_processing_symbol}): df_strike empty post-aggregation. 'dag_custom' set to 0.")
            if 'dag_custom' not in df.columns and not df.empty: df['dag_custom'] = 0.0
            elif df.empty and 'dag_custom' not in df.columns: df['dag_custom'] = pd.Series(dtype=float)
            return df

        base_gamma_exposure_strike = df_strike[self.col_gxoi]
        delta_exposure_oi_strike_sign = np.sign(df_strike[self.col_dxoi])
        delta_exposure_oi_strike_sign.loc[delta_exposure_oi_strike_sign == 0] = 1.0

        if use_signed_flows:
            net_delta_flow_dealer_absorbed_strike = df_strike.get(self.col_c_deltas_sell, 0.0) - df_strike.get(self.col_c_deltas_buy, 0.0)
            net_gamma_flow_dealer_absorbed_strike = df_strike.get(self.col_c_gammas_sell, 0.0) - df_strike.get(self.col_c_gammas_buy, 0.0)
        else:
            net_delta_flow_dealer_absorbed_strike = df_strike.get(self.col_dxvolm, 0.0)
            net_gamma_flow_dealer_absorbed_strike = df_strike.get(self.col_gxvolm, 0.0)

        alpha_coeff_vals = np.select(
            [np.sign(net_delta_flow_dealer_absorbed_strike) == delta_exposure_oi_strike_sign,
             np.sign(net_delta_flow_dealer_absorbed_strike) == -delta_exposure_oi_strike_sign],
            [self.dag_alpha_aligned, self.dag_alpha_opposed], default=self.dag_alpha_neutral
        )
        alpha_coeff = pd.Series(alpha_coeff_vals, index=df_strike.index)
        alpha_coeff.loc[net_delta_flow_dealer_absorbed_strike.abs() < EPSILON] = self.dag_alpha_neutral

        abs_dxoi_strike = df_strike[self.col_dxoi].abs()
        net_delta_flow_magnitude_ratio_strike = net_delta_flow_dealer_absorbed_strike.abs() / (abs_dxoi_strike + EPSILON)
        
        normalized_net_gamma_flow_strike = self._normalize_series(net_gamma_flow_dealer_absorbed_strike, "norm_net_gamma_flow_dag", clip_percentile=100.0)

        dag_strike_values = (base_gamma_exposure_strike * delta_exposure_oi_strike_sign *
                             (1 + alpha_coeff * net_delta_flow_magnitude_ratio_strike) *
                             normalized_net_gamma_flow_strike)
        
        df_strike['dag_custom'] = dag_strike_values.fillna(0.0)
        
        # Merge 'dag_custom' back to the original df_chain structure
        if self.col_strike in df.columns and 'dag_custom' in df_strike.columns:
            if 'dag_custom' in df.columns: # Drop if it somehow exists from a previous partial run
                df = df.drop(columns=['dag_custom'], errors='ignore')
            df = df.merge(df_strike[[self.col_strike, 'dag_custom']], on=self.col_strike, how='left')
            df['dag_custom'] = df['dag_custom'].fillna(0.0) # Fill NaNs for strikes not in df_strike (shouldn't happen if df_strike built from df)
        elif 'dag_custom' not in df.columns and not df.empty: # Should only happen if df_strike was empty or merge failed
             dag_logger.error(f"{calc_name} ({self.current_processing_symbol}): Failed to merge 'dag_custom' or it was not calculated. Setting to 0.")
             df['dag_custom'] = 0.0
        elif df.empty and 'dag_custom' not in df.columns: # If input was empty, ensure col exists
             df['dag_custom'] = pd.Series(dtype=float)

        return df

    def calculate_sgxoi_v2_4(self, df_contracts: pd.DataFrame, und_atm_iv: Optional[float]) -> pd.DataFrame:
        """
        Calculates Skew-Adjusted Gamma Exposure (SGXOI) per option contract.
        This metric adjusts the standard Gamma Exposure (GXOI) by a factor derived from
        the individual option's implied volatility (IV) relative to the underlying's
        at-the-money (ATM) IV. This aims to provide a more realistic measure of gamma
        exposure by accounting for the volatility skew.

        The `col_sgxoi_calculated` (defined in config, e.g., "sgxoi_calc") is added to
        the DataFrame. This column is typically used as the gamma source for SDAG calculations
        if `strategy_settings.use_skew_adjusted_for_sdag` is true.

        This calculation can be toggled off via the "calculate_sgxoi" config setting.
        It might also be implicitly skipped if the "sdag_methodologies" phase is disabled
        and `use_skew_adjusted_for_sdag` is true, or if its primary consumer (SDAGs) is off.
        If skipped, the output column will be populated with raw GXOI values or zeros.

        Args:
            df_contracts (pd.DataFrame): DataFrame of option contracts, requiring columns for
                                         GXOI (e.g., 'gxoi') and option IV (e.g., 'volatility').
            und_atm_iv (Optional[float]): The underlying's current at-the-money implied volatility.
                                          If None or invalid, SGXOI will default to GXOI.

        Returns:
            pd.DataFrame: The input DataFrame with an added column for calculated SGXOI
                          (e.g., 'sgxoi_calc').
        """
        # Toggle Key in config: "calculate_sgxoi"
        # This might also be influenced by "sdag_methodologies" phase if use_skew_adjusted_sdag is True.
        # For direct control, we use a specific toggle.
        output_col = self.col_sgxoi_calculated # Name of the output column from config

        if not self.metric_phases_activation_cfg.get("calculate_sgxoi", True):
            self.logger.info(f"SGXOI calculation for {self.current_processing_symbol} SKIPPED by config.")
            # If SGXOI is skipped, default it to raw GXOI if available, otherwise to 0.0
            # This is important if subsequent SDAG calculations expect this column name.
            df_out = df_contracts.copy()
            if isinstance(df_out, pd.DataFrame) and not df_out.empty:
                if output_col not in df_out.columns:
                    if self.col_gxoi in df_out.columns:
                        df_out[output_col] = pd.to_numeric(df_out[self.col_gxoi], errors='coerce').fillna(0.0)
                    else:
                        df_out[output_col] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty and output_col not in df_out.columns:
                df_out[output_col] = pd.Series(dtype=float)
            return df_out

        # --- Original calculate_sgxoi_v2_4 logic continues here ---
        df = df_contracts.copy()
        calc_name = "SGXOI_V2.4_MC" # Updated name to reflect output
        sgxoi_logger = self.logger.getChild(calc_name)

        required_cols = [self.col_gxoi, self.col_opt_volatility]
        df, cols_ok = self._ensure_columns_internal(df, required_cols, calc_name, fill_numeric_with=0.0)

        if df.empty or not cols_ok:
            sgxoi_logger.warning(f"{calc_name} ({self.current_processing_symbol}): Input empty or missing required columns (GXOI, Option IV). "
                                 f"'{output_col}' will default to GXOI values or 0.")
            if isinstance(df, pd.DataFrame) and not df.empty: # Check df is DataFrame and not empty
                if output_col not in df.columns:
                    df[output_col] = df[self.col_gxoi] if self.col_gxoi in df.columns and cols_ok else 0.0
            elif isinstance(df, pd.DataFrame) and df.empty and output_col not in df.columns:
                 df[output_col] = pd.Series(dtype=float)
            return df

        gxoi_series = pd.to_numeric(df[self.col_gxoi], errors='coerce').fillna(0.0)

        if und_atm_iv is None or not isinstance(und_atm_iv, (float, int)) or und_atm_iv <= EPSILON:
            sgxoi_logger.info(f"{calc_name} ({self.current_processing_symbol}): Underlying ATM IV invalid ({und_atm_iv}). "
                              f"'{output_col}' will be equal to '{self.col_gxoi}'.")
            df[output_col] = gxoi_series
            return df

        opt_vol_series = pd.to_numeric(df[self.col_opt_volatility], errors='coerce').fillna(und_atm_iv) # Fill missing option IV with ATM IV
        
        # Calculate skew adjustment ratio, ensuring it's within reasonable bounds
        skew_adjustment_ratios = (opt_vol_series / und_atm_iv).clip(lower=0.1, upper=10.0)
        
        df[output_col] = gxoi_series * skew_adjustment_ratios
        df[output_col] = df[output_col].fillna(0.0) # Ensure no NaNs from multiplication

        # sgxoi_logger.debug(f"{calc_name} calculated for {self.current_processing_symbol}. Added '{output_col}'.")
        return df

    def calculate_all_sdags_v2_4(self, df_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates all enabled Skew and Delta Adjusted Gamma (SDAG) methodologies.
        SDAG metrics provide different perspectives on structural market pressure by combining
        Gamma Exposure (GEX or skew-adjusted SGXOI) with Delta Exposure (DEX) at each strike.

        The specific SDAG methodologies to calculate are determined by the
        `strategy_settings.dag_methodologies.enabled` list in the configuration.
        Supported methodologies include: "multiplicative", "directional", "weighted",
        and "volatility_focused". Each has its own configurable parameters.

        The gamma source for SDAGs (raw GXOI or calculated SGXOI) is determined by
        `self.gamma_col_for_sdag_calc` (which itself is set based on
        `strategy_settings.use_skew_adjusted_for_sdag` and
        `strategy_settings.skew_adjusted_gamma_source_col`).

        This function aggregates per-contract GXOI/SGXOI and DXOI to the strike level
        before applying the SDAG formulas. The resulting SDAG values for each enabled
        methodology are then added as new columns to the input DataFrame (e.g., 'sdag_multiplicative',
        'sdag_directional'), broadcasted to each contract at its respective strike.

        This entire block of SDAG calculations can be toggled off via the "calculate_all_sdags"
        (or the broader "sdag_methodologies") config setting. If skipped, the output SDAG columns
        will be added to the DataFrame with default (0.0) values.

        Args:
            df_chain (pd.DataFrame): The input options chain DataFrame, expected to contain
                                     the configured gamma source (GXOI or SGXOI) and DXOI
                                     columns per contract.

        Returns:
            pd.DataFrame: The input DataFrame enriched with columns for each calculated
                          SDAG methodology.
        """
        # Toggle Key in config: "calculate_all_sdags" or "sdag_methodologies"
        if not self.metric_phases_activation_cfg.get("calculate_all_sdags", True) and \
           not self.metric_phases_activation_cfg.get("sdag_methodologies", True): # Check both for flexibility
            self.logger.info(f"All SDAG calculations for {self.current_processing_symbol} SKIPPED by config.")
            df_out = df_chain.copy()
            if isinstance(df_out, pd.DataFrame) and not df_out.empty:
                for method_name in self.enabled_sdag_methodologies: # type: ignore
                    sdag_col_name = f"sdag_{method_name}"
                    if sdag_col_name not in df_out.columns:
                        df_out[sdag_col_name] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty:
                 for method_name in self.enabled_sdag_methodologies: # type: ignore
                    df_out[f"sdag_{method_name}"] = pd.Series(dtype=float)
            return df_out
        
        df = df_chain.copy()
        calc_name = "SDAGs_V2.4_MC"
        sdag_logger = self.logger.getChild(calc_name)
        
        gamma_source_col_for_sdag = self.gamma_col_for_sdag_calc # Determined in init
        required_cols_chain_sdag = [gamma_source_col_for_sdag, self.col_dxoi, self.col_strike]
        
        df, cols_ok = self._ensure_columns_internal(df, required_cols_chain_sdag, calc_name, fill_numeric_with=0.0)
        if not cols_ok or (gamma_source_col_for_sdag not in df.columns):
             sdag_logger.error(f"{calc_name}: Gamma source '{gamma_source_col_for_sdag}' or other critical inputs missing. SDAGs set to 0.")
             for method_name in self.enabled_sdag_methodologies: df[f"sdag_{method_name}"] = 0.0
             return df
        if df.empty:
            sdag_logger.warning(f"{calc_name}: Input df_chain is empty. Returning with empty SDAG columns.")
            for method_name in self.enabled_sdag_methodologies: df[f"sdag_{method_name}"] = 0.0
            return df
        
        agg_rules_sdag = {gamma_source_col_for_sdag: 'sum', self.col_dxoi: 'sum'}
        valid_agg_keys = {k:v for k,v in agg_rules_sdag.items() if k in df.columns}

        if not valid_agg_keys or self.col_strike not in df.columns:
            sdag_logger.error(f"{calc_name}: Essential cols for SDAG strike aggregation missing. SDAGs set to 0.")
            for method_name in self.enabled_sdag_methodologies: df[f"sdag_{method_name}"] = 0.0
            return df

        df_strike = df.groupby(self.col_strike, as_index=False).agg(valid_agg_keys).fillna(0.0)
        if df_strike.empty:
            sdag_logger.warning(f"{calc_name}: df_strike empty post-aggregation. SDAGs set to 0.")
            for method_name in self.enabled_sdag_methodologies: df[f"sdag_{method_name}"] = 0.0
            return df

        raw_dex_strike_series = pd.to_numeric(df_strike[self.col_dxoi], errors='coerce').fillna(0.0)
        dex_norm_for_sdag = self._normalize_series(raw_dex_strike_series, "dex_norm_for_sdag", clip_percentile=self.clip_percentile)
        df_strike['dex_norm_for_sdag'] = dex_norm_for_sdag.reindex(df_strike.index).fillna(0.0) # Reindex to align

        gex_strike_source_series = pd.to_numeric(df_strike[gamma_source_col_for_sdag], errors='coerce').fillna(0.0)

        for method_name in self.enabled_sdag_methodologies:
            method_config = self.sdag_methodology_params.get(method_name, {})
            factor = float(method_config.get("delta_weight_factor", 0.5))
            sdag_col_name = f"sdag_{method_name}"
            
            current_dex_component_series = df_strike['dex_norm_for_sdag'] if method_name != "weighted" else raw_dex_strike_series
            calculated_sdag_values = pd.Series(0.0, index=df_strike.index, dtype=float)

            if method_name == "multiplicative":
                calculated_sdag_values = gex_strike_source_series * (1 + current_dex_component_series * factor)
            elif method_name == "directional":
                gex_dex_prod = gex_strike_source_series * current_dex_component_series
                sign_gex_dex_prod = np.sign(gex_dex_prod)
                sign_gex_dex_prod.loc[gex_dex_prod.abs() < EPSILON] = 1.0 
                calculated_sdag_values = gex_strike_source_series * sign_gex_dex_prod * (1 + current_dex_component_series.abs() * factor)
            elif method_name == "weighted":
                w1_gamma = float(method_config.get("w1_gamma", 0.6))
                w2_delta = float(method_config.get("w2_delta", 0.4))
                denominator = w1_gamma + w2_delta
                if abs(denominator) < EPSILON: calculated_sdag_values = pd.Series(0.0, index=df_strike.index, dtype=float)
                else: calculated_sdag_values = (w1_gamma * gex_strike_source_series + w2_delta * current_dex_component_series) / denominator
            elif method_name == "volatility_focused":
                sign_gex = np.sign(gex_strike_source_series)
                sign_gex.loc[gex_strike_source_series.abs() < EPSILON] = 1.0
                calculated_sdag_values = gex_strike_source_series * (1 + current_dex_component_series * sign_gex * factor)
            
            df_strike[sdag_col_name] = calculated_sdag_values.fillna(0.0)

        sdag_cols_to_merge = [f"sdag_{m}" for m in self.enabled_sdag_methodologies if f"sdag_{m}" in df_strike.columns]
        if sdag_cols_to_merge and self.col_strike in df.columns and self.col_strike in df_strike.columns:
            for col in sdag_cols_to_merge:
                 if col in df.columns: df = df.drop(columns=[col], errors='ignore')
            df = df.merge(df_strike[[self.col_strike] + sdag_cols_to_merge], on=self.col_strike, how='left')
            for col in sdag_cols_to_merge: df[col] = df[col].fillna(0.0)
        elif sdag_cols_to_merge : # sdag_cols_to_merge is not empty but merge conditions failed
             sdag_logger.error(f"{calc_name}: SDAG merge conditions failed. SDAGs set to 0 in main df.")
             for col in sdag_cols_to_merge: df[col] = 0.0
        return df
        
    def calculate_tdpi_v2_4(self, df_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the Time Decay Pressure Indicator (TDPI) suite per strike, which includes
        TDPI itself, Charm Decay Rate (CTR_strike), and Time Decay Flow Imbalance (TDFI_strike).
        These metrics assess the market impact of accelerating option time decay (Theta and Charm),
        especially near expiration, weighted by flow alignment, time of day, and strike proximity.

        TDPI aims to identify strikes with high time decay pressure, potentially leading to
        price "pinning". CTR and TDFI are used to identify "Charm Cascade" risk, where
        rapid delta decay due to charm can force accelerated hedging and price moves.

        The V2.4 calculation benefits from potentially more precise net signed flow inputs for
        its charm and theta flow components if available from the API.

        This calculation suite can be toggled off via the "calculate_tdpi_suite" config setting,
        or if its parent phase "core_structural_metrics" is disabled. If skipped,
        the output columns ('tdpi', 'ctr_strike', 'tdfi_strike') will be added to the
        DataFrame with default (0.0) values.

        Args:
            df_chain (pd.DataFrame): The input options chain DataFrame, expected to contain
                                     CharmxOI, TxOI, and flow-related columns (charm/theta)
                                     per contract, along with context like underlying price
                                     and current time.

        Returns:
            pd.DataFrame: The input DataFrame enriched with 'tdpi', 'ctr_strike', and
                          'tdfi_strike' columns, broadcasted to each contract at its
                          respective strike.
        """
        # Toggle Key in config: "calculate_tdpi_suite"
        # Part of phase: "core_structural_metrics"
        if not self.metric_phases_activation_cfg.get("calculate_tdpi_suite", True) and \
           not self.metric_phases_activation_cfg.get("core_structural_metrics", True): # Check specific and phase
            self.logger.info(f"TDPI suite (TDPI, CTR, TDFI) for {self.current_processing_symbol} SKIPPED by config.")
            output_cols = ['tdpi', 'ctr_strike', 'tdfi_strike']
            df_out = df_chain.copy()
            if isinstance(df_out, pd.DataFrame) and not df_out.empty:
                for col in output_cols:
                    if col not in df_out.columns:
                        df_out[col] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty:
                for col in output_cols:
                    df_out[col] = pd.Series(dtype=float)
            return df_out
        
        df = df_chain.copy()
        calc_name = "TDPI_CTR_TDFI_V2.4_MC"
        tdpi_logger = self.logger.getChild(calc_name)
        
        required_cols = [ self.col_strike, self.col_charmxoi, self.col_txoi, self.col_charmxvolm, # Proxies
                          self.col_c_thetas_buy, self.col_c_thetas_sell, # Signed Theta Flows
                          self.col_und_price, 'current_time_dt' # Context from df_chain after prep
                        ]
        df, cols_ok = self._ensure_columns_internal(df, required_cols, calc_name, fill_numeric_with=0.0)
        default_cols_tdpi = ['tdpi', 'ctr_strike', 'tdfi_strike']
        if not cols_ok or df.empty:
            tdpi_logger.warning(f"{calc_name}: Missing inputs or empty DF. Metrics will be zero.")
            for col_add in default_cols_tdpi: df[col_add] = 0.0
            return df

        current_und_price_val = self.current_und_price # From instance variable
        current_time_dt_val = self.current_processing_time_dt # From instance variable
            
        if current_und_price_val is None or current_time_dt_val is None or current_und_price_val <=0:
            tdpi_logger.error(f"{calc_name}: Invalid context data. Und Px: {current_und_price_val}, Time: {current_time_dt_val}.")
            for col_add in default_cols_tdpi: df[col_add] = 0.0
            return df
        current_market_time_obj = current_time_dt_val.time()

        agg_rules = { self.col_charmxoi: 'sum', self.col_txoi: 'sum', self.col_charmxvolm: 'sum', 
                      self.col_c_thetas_buy: 'sum', self.col_c_thetas_sell: 'sum'}
        valid_agg_keys = {k:v for k,v in agg_rules.items() if k in df.columns}
        if not valid_agg_keys or self.col_strike not in df.columns:
            tdpi_logger.error(f"{calc_name}: Missing cols for strike aggregation. Metrics set to 0.")
            for col_add in default_cols_tdpi: df[col_add] = 0.0
            return df

        df_strike = df.groupby(self.col_strike, as_index=False).agg(valid_agg_keys).fillna(0.0)
        if df_strike.empty:
            tdpi_logger.warning(f"{calc_name}: df_strike empty post-aggregation. Metrics set to 0.")
            for col_add in default_cols_tdpi: df[col_add] = 0.0
            return df
                
        net_charm_exposure_oi_s = df_strike[self.col_charmxoi]
        sign_net_theta_exposure_oi_s = np.sign(df_strike[self.col_txoi])
        sign_net_theta_exposure_oi_s.loc[sign_net_theta_exposure_oi_s == 0] = 1.0

        charm_flow_proxy_s = df_strike[self.col_charmxvolm]
        beta_vals = np.select(
            [np.sign(charm_flow_proxy_s) == np.sign(net_charm_exposure_oi_s),
             np.sign(charm_flow_proxy_s) == -np.sign(net_charm_exposure_oi_s)],
            [self.tdpi_beta_aligned, self.tdpi_beta_opposed], default=self.tdpi_beta_neutral
        )
        beta_coeff_s = pd.Series(beta_vals, index=df_strike.index)
        beta_coeff_s.loc[(charm_flow_proxy_s.abs() < EPSILON) | (net_charm_exposure_oi_s.abs() < EPSILON)] = self.tdpi_beta_neutral

        net_charm_flow_to_oi_ratio_s = charm_flow_proxy_s.abs() / (net_charm_exposure_oi_s.abs() + EPSILON)
        
        net_theta_flow_cust_sell_s = df_strike[self.col_c_thetas_sell] - df_strike[self.col_c_thetas_buy]
        norm_net_theta_flow_s = self._normalize_series(net_theta_flow_cust_sell_s, "norm_theta_flow_tdpi", clip_percentile=100.0)

        current_hour_float = current_market_time_obj.hour + current_market_time_obj.minute / 60.0
        time_progress = np.clip((current_hour_float - self.market_open_hour) / (self.market_close_hour - self.market_open_hour + EPSILON), 0, 1)
        time_weight_factor = 1 + time_progress**2

        atr_val = self._get_atr_internal(self.current_processing_symbol, current_und_price_val, period=self.tdpi_atr_fallback_cfg.get("atr_period",14), current_trading_date=current_time_dt_val.date())
        
        strike_series_num = pd.to_numeric(df_strike[self.col_strike], errors='coerce').fillna(current_und_price_val)
        strike_diff_norm_sq = ((strike_series_num - current_und_price_val) / (atr_val + EPSILON))**2 # Added EPSILON for ATR
        strike_proximity_factor = np.exp(self.tdpi_gaussian_width * strike_diff_norm_sq)

        tdpi_s_values = (net_charm_exposure_oi_s * sign_net_theta_exposure_oi_s *
                         (1 + beta_coeff_s * net_charm_flow_to_oi_ratio_s) *
                         norm_net_theta_flow_s * time_weight_factor * strike_proximity_factor)
        df_strike['tdpi'] = tdpi_s_values.fillna(0.0)

        df_strike['ctr_strike'] = charm_flow_proxy_s.abs() / (net_theta_flow_cust_sell_s.abs() + EPSILON)
        df_strike.loc[net_theta_flow_cust_sell_s.abs() < EPSILON, 'ctr_strike'] = np.where(
            charm_flow_proxy_s[net_theta_flow_cust_sell_s.abs() < EPSILON].abs() > EPSILON, 1000.0, 0.0)
        
        abs_txoi_s = df_strike[self.col_txoi].abs()
        norm_abs_txoi_s = self._normalize_series(abs_txoi_s, "norm_abs_txoi_tdfi", clip_percentile=self.clip_percentile)
        norm_abs_refined_theta_flow_s = self._normalize_series(net_theta_flow_cust_sell_s.abs(), "norm_abs_theta_flow_tdfi", clip_percentile=self.clip_percentile)
        df_strike['tdfi_strike'] = norm_abs_refined_theta_flow_s / (norm_abs_txoi_s + EPSILON)
        df_strike.fillna({'tdpi':0.0, 'ctr_strike':0.0, 'tdfi_strike':0.0}, inplace=True)

        cols_to_merge = [self.col_strike] + default_cols_tdpi
        if self.col_strike in df.columns and all(c in df_strike.columns for c in default_cols_tdpi):
            for col in default_cols_tdpi: 
                if col in df.columns: df = df.drop(columns=[col], errors='ignore')
            df = df.merge(df_strike[cols_to_merge], on=self.col_strike, how='left')
            for col in default_cols_tdpi: df[col] = df[col].fillna(0.0)
        else:
            tdpi_logger.error(f"{calc_name}: Merge issue. Metrics not added correctly.")
            for col_add in default_cols_tdpi: df[col_add] = 0.0
        return df

    def calculate_vri_sensitivity_v2_4(self, df_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the Volatility Risk Indicator (VRI Sensitivity) per strike, along with
        related strike-level metrics: VVR_sens_strike (Vanna-Vomma Ratio from sensitivity
        flow proxies) and VFI_sens_strike (Volatility Flow Imbalance from sensitivity
        flow proxies).

        VRI Sensitivity (a refinement of the V2.3 VRI) quantifies a market's potential
        sensitivity to general implied volatility (IV) shifts at specific strikes. It's a
        composite metric integrating Vega, Vanna, and Vomma exposures (from Open Interest),
        recent volatility-related order flow proxies (e.g., total vannaxvolm, vommaxvolm),
        and global context from underlying IV skew and IV trend. A high magnitude suggests
        that IV changes could have a disproportionate impact on option prices and subsequent
        dealer delta hedging activities around that strike.

        V2.4 aims to use total Greek-weighted volumes (vannaxvolm, vommaxvolm) as proxies
        for vanna/vomma flow components due to common API limitations on per-contract signed
        flows for these higher-order Greeks.

        This calculation suite can be toggled off via the "calculate_vri_sensitivity_suite"
        config setting, or if its parent phase "core_structural_metrics" is disabled.
        If skipped, the output columns ('vri_sensitivity', 'vvr_sens_strike',
        'vfi_sens_strike') will be added to the DataFrame with default (0.0) values.

        Args:
            df_chain (pd.DataFrame): The input options chain DataFrame, expected to contain
                                     VannaXOI, VegaXOI, VommaXOI, and flow proxy columns
                                     (vannaxvolm, vommaxvolm, vxvolm) per contract.
                                     It also relies on underlying aggregate data (skew, IV trend)
                                     being available via `self.current_und_data_api`.

        Returns:
            pd.DataFrame: The input DataFrame enriched with 'vri_sensitivity',
                          'vvr_sens_strike', and 'vfi_sens_strike' columns,
                          broadcasted to each contract at its respective strike.
        """
        # Toggle Key: "calculate_vri_sensitivity_suite"
        # Part of phase: "core_structural_metrics"
        if not self.metric_phases_activation_cfg.get("calculate_vri_sensitivity_suite", True) and \
           not self.metric_phases_activation_cfg.get("core_structural_metrics", True): # Check specific and phase
            self.logger.info(f"VRI Sensitivity suite for {self.current_processing_symbol} SKIPPED by config.")
            output_cols = ['vri_sensitivity', 'vvr_sens_strike', 'vfi_sens_strike']
            df_out = df_chain.copy() # Work on a copy
            if isinstance(df_out, pd.DataFrame) and not df_out.empty:
                for col in output_cols:
                    if col not in df_out.columns:
                        df_out[col] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty:
                for col in output_cols: # Ensure columns exist even if df is empty
                    df_out[col] = pd.Series(dtype=float)
            return df_out
        
        df = df_chain.copy()
        calc_name = "VRI_Sensitivity_V2.4_MC"
        vri_sens_logger = self.logger.getChild(calc_name)
        # vri_sens_logger.debug(f"Calculating {calc_name} for {self.current_processing_symbol}...")

        # Output columns for this method
        output_cols = ['vri_sensitivity', 'vvr_sens_strike', 'vfi_sens_strike']

        # Context from instance variables (set by orchestrator)
        current_und_data = self.current_und_data_api # This is the enriched underlying data dict
        if current_und_data is None:
            vri_sens_logger.error(f"{calc_name}: Missing current underlying data (self.current_und_data_api). Cannot calculate global factors. Metrics set to 0.")
            for col_add in output_cols: df[col_add] = 0.0
            return df

        # Required per-contract columns from df_chain for aggregation
        required_cols_chain = [
            self.col_strike,
            self.col_vannaxoi, # Vanna * OI
            self.col_vxoi,     # Vega * OI (for sign and VFI component)
            self.col_vommaxoi, # Vomma * OI (not directly in VRI formula but good for context/VVR)
            self.col_vannaxvolm, # Vanna * Volume (proxy for Vanna Flow)
            self.col_vommaxvolm, # Vomma * Volume (proxy for Vomma Flow)
            self.col_vxvolm      # Vega * Volume (proxy for Vega Flow for VFI_sens)
        ]
        
        df, cols_ok = self._ensure_columns_internal(df, required_cols_chain, calc_name + "_ChainInputCheck", fill_numeric_with=0.0)
        if not cols_ok or df.empty:
            vri_sens_logger.warning(f"{calc_name}: Missing critical inputs or empty DF after ensure_columns. Metrics set to 0.")
            for col_add in output_cols: df[col_add] = 0.0
            return df

        # 1. Aggregate necessary inputs to strike level
        agg_rules_vri_sens = {
            self.col_vannaxoi: 'sum',
            self.col_vxoi: 'sum',
            # self.col_vommaxoi: 'sum', # Not directly in VRI formula but can be aggregated for VVR
            self.col_vannaxvolm: 'sum',
            self.col_vommaxvolm: 'sum',
            self.col_vxvolm: 'sum'
        }
        valid_agg_keys = {k:v for k,v in agg_rules_vri_sens.items() if k in df.columns}
        if not valid_agg_keys or self.col_strike not in df.columns:
            vri_sens_logger.error(f"{calc_name}: Essential columns for strike aggregation missing. Metrics set to 0.")
            for col_add in output_cols: df[col_add] = 0.0
            return df
            
        df_strike = df.groupby(self.col_strike, as_index=False).agg(valid_agg_keys).fillna(0.0)
        if df_strike.empty:
            vri_sens_logger.warning(f"{calc_name}: df_strike empty post-aggregation. Metrics set to 0.")
            for col_add in output_cols: df[col_add] = 0.0
            return df

        # 2. Calculate VRI Sensitivity components at strike level
        net_vanna_exposure_oi_strike = pd.to_numeric(df_strike[self.col_vannaxoi], errors='coerce').fillna(0.0)
        
        vxoi_strike_series = pd.to_numeric(df_strike[self.col_vxoi], errors='coerce').fillna(0.0)
        sign_net_vega_exposure_oi_strike = np.sign(vxoi_strike_series)
        sign_net_vega_exposure_oi_strike.loc[sign_net_vega_exposure_oi_strike == 0] = 1.0 # Treat zero vega OI as neutral sign

        # Flow Proxies (using total Greek-weighted volumes)
        vanna_flow_proxy_strike = pd.to_numeric(df_strike[self.col_vannaxvolm], errors='coerce').fillna(0.0)
        vomma_flow_proxy_strike = pd.to_numeric(df_strike[self.col_vommaxvolm], errors='coerce').fillna(0.0)
        vega_flow_proxy_strike = pd.to_numeric(df_strike[self.col_vxvolm], errors='coerce').fillna(0.0)

        # Gamma Coefficient (Alignment Factor for Vanna Flow)
        # Compares sign of vanna flow proxy with sign of vanna OI
        gamma_coeff_vri_vals = np.select(
            [np.sign(vanna_flow_proxy_strike) == np.sign(net_vanna_exposure_oi_strike),
             np.sign(vanna_flow_proxy_strike) == -np.sign(net_vanna_exposure_oi_strike)],
            [self.vri_gamma_aligned, self.vri_gamma_opposed], # From config
            default=self.vri_gamma_neutral # From config
        )
        gamma_coeff_vri = pd.Series(gamma_coeff_vri_vals, index=df_strike.index)
        # If either flow or OI is near zero, treat alignment as neutral
        gamma_coeff_vri.loc[(vanna_flow_proxy_strike.abs() < EPSILON) | (net_vanna_exposure_oi_strike.abs() < EPSILON)] = self.vri_gamma_neutral

        net_vanna_flow_to_oi_ratio_strike = vanna_flow_proxy_strike.abs() / (net_vanna_exposure_oi_strike.abs() + EPSILON)
        
        normalized_net_vomma_flow_strike = self._normalize_series(
            vomma_flow_proxy_strike, 
            "norm_vomma_flow_for_vri_sens", 
            clip_percentile=100.0 # No clipping for internal factors typically
        )

        # Global Skew Factor (from underlying aggregate data)
        # self.col_u_call_vxoi and self.col_u_put_vxoi are actual API field names from get_und
        call_vxoi_und = float(current_und_data.get(self.col_u_call_vxoi, 0.0))
        put_vxoi_und = float(current_und_data.get(self.col_u_put_vxoi, 0.0))
        total_vega_oi_und = call_vxoi_und + put_vxoi_und
        skew_factor_global = (1.0 + ((put_vxoi_und - call_vxoi_und) / (total_vega_oi_und + EPSILON))) \
                             if abs(total_vega_oi_und) > EPSILON else 1.0
        
        # Global Volatility Trend Factor (from underlying aggregate data and historical IV)
        # self.col_u_volatility is the API field name for underlying IV from get_und
        current_iv_und = float(current_und_data.get(self.col_u_volatility, 0.0)) 
        avg_iv_hist_for_sens = None
        if self.historical_data_manager and hasattr(self.historical_data_manager, 'get_average_iv') and self.current_processing_symbol and self.current_processing_time_dt:
            # Assuming get_average_iv takes symbol, lookback_days, and current_date
             avg_iv_hist_for_sens = self.historical_data_manager.get_average_iv(
                 symbol=self.current_processing_symbol, 
                 period_days=self.vol_trend_avg_days_vri_sens, # Configured lookback
                 current_date=self.current_processing_time_dt.date() # Pass current date
             )
        
        vol_trend_factor_global = 1.0
        if avg_iv_hist_for_sens is not None and avg_iv_hist_for_sens > EPSILON and current_iv_und > EPSILON:
            vol_trend_factor_global = 1.0 + (current_iv_und - avg_iv_hist_for_sens) / avg_iv_hist_for_sens
        elif current_iv_und > EPSILON: # If no history, use fallback factor from config
            vol_trend_factor_global = self.vri_vol_trend_fb_factor # From config
        vol_trend_factor_global = np.clip(vol_trend_factor_global, 0.5, 1.5) # Cap the factor

        # Calculate VRI Sensitivity
        vri_sensitivity_values = (net_vanna_exposure_oi_strike *
                                  sign_net_vega_exposure_oi_strike *
                                  (1 + gamma_coeff_vri * net_vanna_flow_to_oi_ratio_strike) *
                                  normalized_net_vomma_flow_strike *
                                  skew_factor_global *
                                  vol_trend_factor_global)
        df_strike['vri_sensitivity'] = vri_sensitivity_values.fillna(0.0)

        # Calculate VVR_sens_strike (Vanna-Vomma Ratio using flow proxies)
        df_strike['vvr_sens_strike'] = vanna_flow_proxy_strike.abs() / (vomma_flow_proxy_strike.abs() + EPSILON)
        # Handle division by zero if vomma flow is zero
        df_strike.loc[vomma_flow_proxy_strike.abs() < EPSILON, 'vvr_sens_strike'] = np.where(
            vanna_flow_proxy_strike[vomma_flow_proxy_strike.abs() < EPSILON].abs() > EPSILON, 
            1000.0,  # High value if vanna flow but no vomma flow
            0.0      # Both zero
        )
        
        # Calculate VFI_sens_strike (Volatility Flow Imbalance using flow proxies)
        # Ratio of normalized absolute vega flow proxy to normalized absolute vega OI
        norm_abs_vxoi_strike = self._normalize_series(vxoi_strike_series.abs(), "norm_abs_vxoi_for_vfi_sens", clip_percentile=self.clip_percentile)
        norm_abs_vega_flow_proxy_strike = self._normalize_series(vega_flow_proxy_strike.abs(), "norm_abs_vega_flow_for_vfi_sens", clip_percentile=self.clip_percentile)
        df_strike['vfi_sens_strike'] = norm_abs_vega_flow_proxy_strike / (norm_abs_vxoi_strike + EPSILON)
        
        df_strike.fillna({'vri_sensitivity':0.0, 'vvr_sens_strike':0.0, 'vfi_sens_strike':0.0}, inplace=True)

        # 3. Merge results back to the main df_chain (per-contract level)
        # VRI_sensitivity and its components are typically analyzed at the strike level,
        # but are merged back to df_chain for consistency if MSPI components are per-contract.
        cols_to_merge_from_strike = [self.col_strike] + output_cols
        
        if self.col_strike in df.columns and all(c in df_strike.columns for c in output_cols):
            for col_to_drop in output_cols: # Drop if they exist from a bad prior state
                if col_to_drop in df.columns: 
                    df = df.drop(columns=[col_to_drop], errors='ignore')
            
            df = df.merge(df_strike[cols_to_merge_from_strike], on=self.col_strike, how='left')
            for col_fill in output_cols: 
                df[col_fill] = df[col_fill].fillna(0.0)
        else:
            vri_sens_logger.error(f"{calc_name}: Merge conditions failed. Required columns not in df_strike or df. Metrics not added properly.")
            for col_add in output_cols: 
                if col_add not in df.columns: df[col_add] = 0.0
        
        vri_sens_logger.info(f"{calc_name} calculated and merged. Added/updated: {output_cols}.")
        return df
    
    def calculate_vri_0dte_v2_4(self, df_0dte_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the 0DTE-Style Volatility Regime Indicator (vri_0dte) per 0DTE contract.
        This metric is specialized for options expiring on the current trading day and aims to
        quantify imminent pressure for a volatility regime change, considering flow dynamics.

        It analyzes 0DTE Vanna exposure from Open Interest (VannaXOI), current Vanna and Vomma
        related hedging flow proxies (e.g., total vannaxvolm, vommaxvolm), and contextualizes
        this with market-wide skew (from underlying aggregate Vega OI) and recent IV trends.
        A high positive or negative vri_0dte suggests building pressure for volatility
        expansion, potentially with a directional price bias due to vanna/vomma hedging.

        This calculation can be toggled off via the "calculate_vri_0dte" config setting,
        or if its parent phase "0dte_suite" is disabled. If skipped, the 'vri_0dte'
        column will be added to the DataFrame with default (0.0) values.

        Args:
            df_0dte_chain (pd.DataFrame): DataFrame of option contracts, filtered to include
                                          only those expiring on the current day (0 DTE).
                                          Requires VannaXOI, VegaXOI, and flow proxy columns.

        Returns:
            pd.DataFrame: The input 0DTE DataFrame with an added 'vri_0dte' column for
                          each contract.
        """
        # Toggle Key in config: "calculate_vri_0dte"
        # Part of phase: "0dte_suite"
        output_col = 'vri_0dte'
        if not self.metric_phases_activation_cfg.get("calculate_vri_0dte", True) and \
           not self.metric_phases_activation_cfg.get("0dte_suite", True): # Check specific and phase
            self.logger.info(f"VRI 0DTE calculation for {self.current_processing_symbol} SKIPPED by config.")
            df_out = df_0dte_chain.copy()
            if isinstance(df_out, pd.DataFrame) and output_col not in df_out.columns and not df_out.empty:
                df_out[output_col] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty and output_col not in df_out.columns:
                df_out[output_col] = pd.Series(dtype=float)
            return df_out

        df = df_0dte_chain.copy() # df is already filtered for 0DTE by the caller
        calc_name = "VRI_0DTE_V2.4_MC"
        vri0_logger = self.logger.getChild(calc_name)
        
        output_col_vri0 = 'vri_0dte' # Output column name

        if df.empty:
            vri0_logger.debug(f"{calc_name}: No 0DTE contracts to process for {self.current_processing_symbol}.")
            if output_col_vri0 not in df.columns: df[output_col_vri0] = 0.0
            return df

        # Underlying data context is crucial for global factors
        current_und_data = self.current_und_data_api
        if current_und_data is None:
            vri0_logger.error(f"{calc_name}: Missing current underlying data. Cannot calculate global factors. '{output_col_vri0}' set to 0.")
            df[output_col_vri0] = 0.0
            return df

        # Required per-contract columns from the 0DTE DataFrame
        required_cols_0dte_chain = [
            self.col_vannaxoi,     # Vanna * OI
            self.col_vxoi,         # Vega * OI (for sign orientation)
            self.col_vannaxvolm,   # Vanna * Volume (proxy for Vanna Flow)
            self.col_vommaxvolm    # Vomma * Volume (proxy for Vomma Flow)
            # self.col_strike is not directly used in per-contract formula but good for ensuring data integrity
        ]
        
        df, cols_ok = self._ensure_columns_internal(df, required_cols_0dte_chain, calc_name + "_0DTE_InputCheck", fill_numeric_with=0.0)
        if not cols_ok or df.empty: # Check df.empty again after ensure_columns
            vri0_logger.warning(f"{calc_name}: Missing critical inputs or empty 0DTE DF after ensure_columns. '{output_col_vri0}' set to 0.")
            df[output_col_vri0] = 0.0
            return df

        # Per-contract calculations
        vannaxoi_contract = pd.to_numeric(df[self.col_vannaxoi], errors='coerce').fillna(0.0)
        
        vxoi_contract_series = pd.to_numeric(df[self.col_vxoi], errors='coerce').fillna(0.0)
        sign_vxoi_contract = np.sign(vxoi_contract_series)
        sign_vxoi_contract.loc[sign_vxoi_contract == 0] = 1.0 # Neutral sign if Vega OI is zero

        net_vanna_flow_contract_proxy = pd.to_numeric(df[self.col_vannaxvolm], errors='coerce').fillna(0.0)
        net_vomma_flow_contract_proxy = pd.to_numeric(df[self.col_vommaxvolm], errors='coerce').fillna(0.0)

        # Vanna Flow Alignment Coefficient (Gamma Align Coeff from V2.4 guide for vri_0dte)
        gamma_align_coeff_0dte_vals = np.select(
            [np.sign(net_vanna_flow_contract_proxy) == np.sign(vannaxoi_contract),      # Flow aligns with OI
             np.sign(net_vanna_flow_contract_proxy) == -np.sign(vannaxoi_contract)],   # Flow opposes OI
            [self.vri_0dte_vanna_align_reinforce, self.vri_0dte_vanna_align_contradict], # From config
            default=1.0 # Neutral if signs are zero or different for other reasons
        )
        gamma_align_coeff_0dte = pd.Series(gamma_align_coeff_0dte_vals, index=df.index)
        # If either flow or OI is near zero, treat alignment as neutral (coeff = 1.0)
        gamma_align_coeff_0dte.loc[(net_vanna_flow_contract_proxy.abs() < EPSILON) | (vannaxoi_contract.abs() < EPSILON)] = 1.0

        # Ratio of Vanna flow magnitude to Vanna OI magnitude
        abs_net_vanna_flow_div_vannaxoi_ratio = net_vanna_flow_contract_proxy.abs() / (vannaxoi_contract.abs() + EPSILON)
        
        # Normalized Vomma Flow Term (NetVommaFlow_contract / MaxMarketNetVommaFlow)
        # MaxMarketNetVommaFlow is the max absolute vomma flow proxy across THIS BATCH of 0DTE contracts
        max_batch_net_vomma_flow_abs = net_vomma_flow_contract_proxy.abs().max()
        normalized_vomma_flow_term = (net_vomma_flow_contract_proxy / max_batch_net_vomma_flow_abs) \
                                     if max_batch_net_vomma_flow_abs >= MIN_NORMALIZATION_DENOMINATOR \
                                     else pd.Series(0.0, index=df.index) # Avoid division by zero, default to 0 impact
        normalized_vomma_flow_term = normalized_vomma_flow_term.fillna(0.0)

        # Global Skew Factor (from underlying aggregate data - self.current_und_data_api)
        call_vxoi_und = float(current_und_data.get(self.col_u_call_vxoi, 0.0))
        put_vxoi_und = float(current_und_data.get(self.col_u_put_vxoi, 0.0))
        total_vega_oi_und = call_vxoi_und + put_vxoi_und
        # Formula from guide: 1 + (put_vxoi - call_vxoi) / (put_vxoi + call_vxoi)
        skew_factor_global = (1.0 + ((put_vxoi_und - call_vxoi_und) / (total_vega_oi_und + EPSILON))) \
                             if abs(total_vega_oi_und) > EPSILON else 1.0
        
        # Global Volatility Trend Factor (from underlying aggregate data and historical IV)
        current_iv_und = float(current_und_data.get(self.col_u_volatility, 0.0)) # Underlying aggregate IV
        avg_hist_iv_for_0dte = None
        if self.historical_data_manager and hasattr(self.historical_data_manager, 'get_average_iv') and self.current_processing_symbol and self.current_processing_time_dt:
             avg_hist_iv_for_0dte = self.historical_data_manager.get_average_iv(
                 symbol=self.current_processing_symbol, 
                 period_days=self.vol_trend_avg_days_vri0dte, # Configured lookback for 0DTE VRI
                 current_date=self.current_processing_time_dt.date()
             )
        
        vol_trend_factor_global = 1.0
        if avg_hist_iv_for_0dte is not None and avg_hist_iv_for_0dte > EPSILON and current_iv_und > EPSILON:
            vol_trend_factor_global = 1.0 + (current_iv_und - avg_hist_iv_for_0dte) / avg_hist_iv_for_0dte
        elif current_iv_und > EPSILON: # If no history, use fallback factor from config
            vol_trend_factor_global = self.vri_0dte_vol_trend_fb_no_hist # From config
        vol_trend_factor_global = np.clip(vol_trend_factor_global, 0.5, 2.0) # Cap the factor's influence

        # Calculate vri_0dte per contract
        # Formula: [vannaxoi * sign(vxoi) * (1 + γ_align_coeff_0dte * abs(NetVannaFlow / vannaxoi)) * (NetVommaFlow / MaxMarketNetVommaFlow)] * SkewFactor_Global * VolatilityTrendFactor_Global
        vri_0dte_values_contract = (vannaxoi_contract *
                                   sign_vxoi_contract *
                                   (1 + gamma_align_coeff_0dte * abs_net_vanna_flow_div_vannaxoi_ratio) *
                                   normalized_vomma_flow_term * 
                                   skew_factor_global *
                                   vol_trend_factor_global)
        
        df[output_col_vri0] = vri_0dte_values_contract.fillna(0.0)
        
        # vri0_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}. Added '{output_col_vri0}'.")
        return df
    
    def calculate_vvr_0dte_v2_4(self, df_0dte_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the Vanna-Vomma Ratio (VVR_0DTE) per 0DTE option contract.
        This metric new to V2.4 assesses the relative dominance of Vanna-related flow
        versus Vomma-related flow for options expiring on the current day.

        VVR_0DTE is calculated as the ratio of the absolute magnitude of net Vanna flow proxy
        (e.g., total vannaxvolm) to the absolute magnitude of net Vomma flow proxy
        (e.g., total vommaxvolm) for each contract.

        A high VVR (e.g., > 1.0 or 1.5) suggests that dealer hedging responses to IV changes
        are more likely to be direct delta adjustments (Vanna-driven), potentially leading to
        more directional price impact. A low VVR suggests Vega convexity effects (Vomma)
        might be more dominant, leading to more complex vol surface shifts.
        This metric is particularly relevant context for vri_0dte and is a key condition
        for the Vanna Cascade Alert regime/signal.

        This calculation can be toggled off via the "calculate_vvr_0dte" config setting,
        or if its parent phase "0dte_suite" is disabled. If skipped, the 'vvr_0dte'
        column will be added to the DataFrame with default (0.0) values.

        Args:
            df_0dte_chain (pd.DataFrame): DataFrame of 0DTE option contracts, requiring
                                          flow proxy columns for Vanna (e.g., 'vannaxvolm')
                                          and Vomma (e.g., 'vommaxvolm').

        Returns:
            pd.DataFrame: The input 0DTE DataFrame with an added 'vvr_0dte' column.
        """
        # Toggle Key in config: "calculate_vvr_0dte"
        # Part of phase: "0dte_suite"
        output_col = 'vvr_0dte'
        if not self.metric_phases_activation_cfg.get("calculate_vvr_0dte", True) and \
           not self.metric_phases_activation_cfg.get("0dte_suite", True):
            self.logger.info(f"VVR 0DTE calculation for {self.current_processing_symbol} SKIPPED by config.")
            df_out = df_0dte_chain.copy()
            if isinstance(df_out, pd.DataFrame) and output_col not in df_out.columns and not df_out.empty:
                df_out[output_col] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty and output_col not in df_out.columns:
                df_out[output_col] = pd.Series(dtype=float)
            return df_out
        
        df = df_0dte_chain.copy()
        calc_name = "VVR_0DTE_V2.4_MC"
        vvr0_logger = self.logger.getChild(calc_name)
        
        output_col_vvr0 = 'vvr_0dte'

        if df.empty:
            # vvr0_logger.debug(f"{calc_name}: No 0DTE contracts for {self.current_processing_symbol}.")
            if output_col_vvr0 not in df.columns: df[output_col_vvr0] = 0.0
            return df
        
        required_cols = [self.col_vannaxvolm, self.col_vommaxvolm] # Proxies for Vanna and Vomma flow
        df, cols_ok = self._ensure_columns_internal(df, required_cols, calc_name + "_0DTE_InputCheck", fill_numeric_with=0.0)
        
        if not cols_ok or df.empty:
            vvr0_logger.warning(f"{calc_name}: Missing inputs or empty 0DTE DF. '{output_col_vvr0}' set to 0.")
            df[output_col_vvr0] = 0.0
            return df

        net_vanna_flow_proxy_abs = pd.to_numeric(df[self.col_vannaxvolm], errors='coerce').abs().fillna(0.0)
        net_vomma_flow_proxy_abs = pd.to_numeric(df[self.col_vommaxvolm], errors='coerce').abs().fillna(0.0)

        vvr_0dte_values_contract = net_vanna_flow_proxy_abs / (net_vomma_flow_proxy_abs + EPSILON)
        
        # Handle cases where denominator is zero
        # If Vomma flow is zero but Vanna flow is significant, VVR should be very high
        vvr_0dte_values_contract.loc[(net_vomma_flow_proxy_abs < EPSILON) & (net_vanna_flow_proxy_abs > EPSILON)] = 1000.0 # Arbitrary high value
        # If both are zero, VVR is zero
        vvr_0dte_values_contract.loc[(net_vomma_flow_proxy_abs < EPSILON) & (net_vanna_flow_proxy_abs < EPSILON)] = 0.0
        
        df[output_col_vvr0] = vvr_0dte_values_contract.fillna(0.0)
        
        # vvr0_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}. Added '{output_col_vvr0}'.")
        return df
    

    def calculate_vfi_0dte_v2_4(self, df_0dte_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the Volatility Flow Indicator (VFI_0DTE) per 0DTE option contract.
        This new V2.4 metric measures the intensity of current Vega-related hedging flow
        relative to the existing Vega Open Interest (VegaOI) specifically for options
        expiring on the current day.

        VFI_0DTE is determined by the ratio of normalized absolute net Vega flow to
        normalized absolute Vega OI, considering only 0DTE contracts. Ideally, net Vega
        flow is derived from direct signed API data (e.g., 'vegas_buy' - 'vegas_sell'
        per contract); otherwise, a Vega-weighted volume proxy (e.g., 'vxvolm') might be used.
        High VFI_0DTE values suggest that current Vega trading (customer flow absorbed by
        dealers) is proportionally large compared to the standing Vega OI, signaling
        "accelerated volatility hedging" and potentially confirming conditions for
        a volatility regime shift.

        This calculation can be toggled off via the "calculate_vfi_0dte" config setting,
        or if its parent phase "0dte_suite" is disabled. If skipped, the 'vfi_0dte'
        column will be added to the DataFrame with default (0.0) values.

        Args:
            df_0dte_chain (pd.DataFrame): DataFrame of 0DTE option contracts, requiring
                                          VegaXOI (e.g., 'vxoi') and Vega flow columns
                                          (e.g., 'vegas_buy', 'vegas_sell', or 'vxvolm').

        Returns:
            pd.DataFrame: The input 0DTE DataFrame with an added 'vfi_0dte' column.
        """
        # Toggle Key in config: "calculate_vfi_0dte"
        # Part of phase: "0dte_suite"
        output_col = 'vfi_0dte'
        if not self.metric_phases_activation_cfg.get("calculate_vfi_0dte", True) and \
           not self.metric_phases_activation_cfg.get("0dte_suite", True):
            self.logger.info(f"VFI 0DTE calculation for {self.current_processing_symbol} SKIPPED by config.")
            df_out = df_0dte_chain.copy()
            if isinstance(df_out, pd.DataFrame) and output_col not in df_out.columns and not df_out.empty:
                df_out[output_col] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty and output_col not in df_out.columns:
                df_out[output_col] = pd.Series(dtype=float)
            return df_out
        
        df = df_0dte_chain.copy()
        calc_name = "VFI_0DTE_V2.4_MC"
        vfi0_logger = self.logger.getChild(calc_name)

        output_col_vfi0 = 'vfi_0dte'

        if df.empty:
            # vfi0_logger.debug(f"{calc_name}: No 0DTE contracts for {self.current_processing_symbol}.")
            if output_col_vfi0 not in df.columns: df[output_col_vfi0] = 0.0
            return df

        # Required per-contract columns from the 0DTE DataFrame
        # Using direct signed vega flows as per V2.4 "Ideal" for VFI_0DTE
        required_cols = [
            self.col_vxoi,          # Vega * OI (Vega Open Interest)
            self.col_c_vegas_buy,   # Signed Vega Flow (Customer Buys Vega)
            self.col_c_vegas_sell   # Signed Vega Flow (Customer Sells Vega)
        ]
        
        df, cols_ok = self._ensure_columns_internal(df, required_cols, calc_name + "_0DTE_InputCheck", fill_numeric_with=0.0)
        if not cols_ok or df.empty:
            vfi0_logger.warning(f"{calc_name}: Missing critical inputs or empty 0DTE DF. '{output_col_vfi0}' set to 0.")
            df[output_col_vfi0] = 0.0
            return df

        # Calculate Net Signed Vega Flow per contract (Customer Perspective: Buy - Sell)
        # Positive means customers net bought vega; Negative means customers net sold vega.
        net_vega_flow_customer_contract = pd.to_numeric(df[self.col_c_vegas_buy], errors='coerce').fillna(0.0) - \
                                          pd.to_numeric(df[self.col_c_vegas_sell], errors='coerce').fillna(0.0)
        
        # Absolute magnitude of this net vega flow per contract
        net_vega_flow_abs_contract = net_vega_flow_customer_contract.abs()
        
        # Absolute Vega Open Interest per contract
        vxoi_abs_contract = pd.to_numeric(df[self.col_vxoi], errors='coerce').abs().fillna(0.0)

        # Normalize the absolute net vega flow and absolute vega OI across THIS BATCH of 0DTE contracts
        # This makes the VFI a relative intensity measure within the current 0DTE context.
        norm_net_vega_flow_abs_batch = self._normalize_series(
            net_vega_flow_abs_contract, 
            "norm_net_vega_flow_0dte_batch", 
            method="max_abs", 
            clip_percentile=100.0 # Usually no clipping for internal factors unless extreme outliers
        )
        norm_vxoi_abs_batch = self._normalize_series(
            vxoi_abs_contract, 
            "norm_vxoi_0dte_batch", 
            method="max_abs", 
            clip_percentile=100.0
        )
        
        # Calculate VFI_0DTE per contract
        # Ratio of normalized absolute net vega flow to normalized absolute vega OI
        vfi_0dte_values_contract = norm_net_vega_flow_abs_batch / (norm_vxoi_abs_batch + EPSILON)
        
        df[output_col_vfi0] = vfi_0dte_values_contract.fillna(0.0)
        
        # vfi0_logger.info(f"{calc_name} calculated using signed vega flows for {self.current_processing_symbol}. Added '{output_col_vfi0}'.")
        return df
    
    def calculate_vci_0dte_contracts_v2_4(self, df_0dte_chain: pd.DataFrame) -> pd.DataFrame:
        """
        Prepares per-contract data necessary for the Vanna Concentration Index (VCI_0DTE)
        calculation by determining the absolute Vanna exposure from Open Interest (VannaXOI)
        for each 0DTE option contract.

        This method adds a column, typically named 'abs_vannaxoi_contract', to the input
        0DTE DataFrame. This column represents `abs(vannaxoi)` for each contract.
        The actual VCI_0DTE (an underlying-level aggregate, often an HHI-style sum of
        squared proportions of this 'abs_vannaxoi_contract' at different strikes)
        is calculated in a later aggregation step
        (e.g., within `calculate_underlying_aggregate_metrics_v2_4`).

        This preparation step can be toggled off via the "calculate_vci_0dte_contracts"
        config setting, or if its parent phase "0dte_suite" is disabled. If skipped,
        the 'abs_vannaxoi_contract' column will be added with default (0.0) values.

        Args:
            df_0dte_chain (pd.DataFrame): DataFrame of 0DTE option contracts, requiring
                                          the VannaXOI column (e.g., 'vannaxoi').

        Returns:
            pd.DataFrame: The input 0DTE DataFrame with an added 'abs_vannaxoi_contract'
                          column.
        """
        # Toggle Key in config: "calculate_vci_0dte_contracts"
        # Part of phase: "0dte_suite"
        output_col = 'abs_vannaxoi_contract'
        if not self.metric_phases_activation_cfg.get("calculate_vci_0dte_contracts", True) and \
           not self.metric_phases_activation_cfg.get("0dte_suite", True):
            self.logger.info(f"VCI 0DTE Contract Prep for {self.current_processing_symbol} SKIPPED by config.")
            df_out = df_0dte_chain.copy()
            if isinstance(df_out, pd.DataFrame) and output_col not in df_out.columns and not df_out.empty:
                df_out[output_col] = 0.0
            elif isinstance(df_out, pd.DataFrame) and df_out.empty and output_col not in df_out.columns:
                df_out[output_col] = pd.Series(dtype=float)
            return df_out
        
        df = df_0dte_chain.copy() # df is already filtered for 0DTE by the caller
        calc_name = "VCI_0DTE_Contract_Prep_V2.4_MC"
        vci_prep_logger = self.logger.getChild(calc_name)
        
        output_col_abs_vannaxoi = 'abs_vannaxoi_contract' # Output column name

        if df.empty:
            # vci_prep_logger.debug(f"{calc_name}: No 0DTE contracts to process for VCI prep for {self.current_processing_symbol}.")
            # Ensure column exists even if df is empty, for consistent schema if merged back
            if output_col_abs_vannaxoi not in df.columns: 
                df[output_col_abs_vannaxoi] = pd.Series(dtype=float) if not df.empty else 0.0 # Handle truly empty df
            return df

        # Required per-contract column from the 0DTE DataFrame
        # self.col_vannaxoi is the name of the 'Vanna * OI' column (e.g., "vannaxoi") from config
        required_cols = [self.col_vannaxoi] 
        
        df, cols_ok = self._ensure_columns_internal(df, required_cols, calc_name + "_0DTE_InputCheck", fill_numeric_with=0.0)
        
        if not cols_ok or df.empty: # Check df.empty again after ensure_columns
            vci_prep_logger.warning(f"{calc_name}: Missing critical input '{self.col_vannaxoi}' or empty 0DTE DF. '{output_col_abs_vannaxoi}' set to 0.")
            df[output_col_abs_vannaxoi] = 0.0
            return df

        # Calculate absolute Vanna OI per contract
        vannaxoi_contract_series = pd.to_numeric(df[self.col_vannaxoi], errors='coerce').fillna(0.0)
        df[output_col_abs_vannaxoi] = vannaxoi_contract_series.abs()
        
        vci_prep_logger.info(f"{calc_name}: Prepared '{output_col_abs_vannaxoi}' for {self.current_processing_symbol} on {len(df)} 0DTE contracts.")
        return df
    
    # ----- Strike-Level Metrics (Calculated on or added to df_strike_level_metrics) -----
    def calculate_nvp_nvp_vol_per_strike_v2_4(
        self,
        df_strike_level_metrics: pd.DataFrame,
        df_chain_with_contract_flows: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculates Net Value Pressure (NVP) and Net Volume Pressure (NVP_Vol) per strike.
        These V2.4 metrics provide a direct measure of the net buying or selling pressure
        at specific option strikes based on the current day's transactional activity.

        - NVP ('nvp_strike'): Sum of (per-contract net value bought - sold) at each strike,
          derived from the 'value_bs' API field per contract. Positive NVP indicates
          net customer buying value at that strike.
        - NVP_Vol ('nvp_vol_strike'): Sum of (per-contract net volume bought - sold) at each
          strike, derived from the 'volm_bs' API field per contract. Positive NVP_Vol
          indicates net customer contracts bought.

        These metrics are crucial for identifying transactional support/resistance levels,
        confirming structural levels (like MSPI), and are inputs to the Market Regime Engine
        and target/stop logic.

        This calculation can be toggled off via the "calculate_nvp_strike" config setting,
        or if its parent phase "flow_metrics_nvp_arfi" is disabled. If skipped,
        'nvp_strike' and 'nvp_vol_strike' columns will be added to the
        `df_strike_level_metrics` DataFrame with default (0.0) values.

        Args:
            df_strike_level_metrics (pd.DataFrame): The strike-level DataFrame to which
                                                    NVP and NVP_Vol will be added/updated.
            df_chain_with_contract_flows (pd.DataFrame): The options chain DataFrame containing
                                                         per-contract flow data (specifically
                                                         'value_bs' and 'volm_bs' columns, mapped via
                                                         `self.col_c_value_bs` and `self.col_c_volm_bs`).
        Returns:
            pd.DataFrame: The `df_strike_level_metrics` DataFrame enriched with 'nvp_strike'
                          and 'nvp_vol_strike' columns.
        """
        # Toggle Key in config: "calculate_nvp_strike"
        # Part of phase: "flow_metrics_nvp_arfi"
        output_col_nvp = 'nvp_strike'; output_col_nvp_vol = 'nvp_vol_strike'; default_cols_to_add = [output_col_nvp, output_col_nvp_vol] # Copied
        if not self.metric_phases_activation_cfg.get("calculate_nvp_strike", True) and \
           not self.metric_phases_activation_cfg.get("flow_metrics_nvp_arfi", True):
            self.logger.info(f"NVP & NVP_Vol per strike for {self.current_processing_symbol} SKIPPED by config.")
            df_strike_out_toggle = df_strike_level_metrics.copy()
            if isinstance(df_strike_out_toggle, pd.DataFrame):
                for col_add_toggle in default_cols_to_add:
                    if col_add_toggle not in df_strike_out_toggle.columns and not df_strike_out_toggle.empty:
                        df_strike_out_toggle[col_add_toggle] = 0.0
                    elif df_strike_out_toggle.empty and col_add_toggle not in df_strike_out_toggle.columns:
                        df_strike_out_toggle[col_add_toggle] = pd.Series(dtype=float)
            return df_strike_out_toggle
        
        df_strike_out = df_strike_level_metrics.copy() # Work on a copy of the strike-level DataFrame
        calc_name = "NVP_NVP_Vol_Strike_V2.4_MC"
        nvp_logger = self.logger.getChild(calc_name)
        
        # Output column names (these will be new columns in df_strike_out)
        output_col_nvp = 'nvp_strike'
        output_col_nvp_vol = 'nvp_vol_strike'
        default_cols_nvp = [output_col_nvp, output_col_nvp_vol]

        # Pre-initialize output columns in df_strike_out to ensure they exist even if chain is empty or processing fails
        for col_add in default_cols_nvp:
            if col_add not in df_strike_out.columns:
                df_strike_out[col_add] = 0.0
            else: # If it exists (e.g. from a re-run), ensure it's float and fill NaNs
                df_strike_out[col_add] = pd.to_numeric(df_strike_out[col_add], errors='coerce').fillna(0.0)


        if df_chain_with_contract_flows.empty:
            nvp_logger.warning(f"{calc_name}: Input 'df_chain_with_contract_flows' is empty for {self.current_processing_symbol}. NVP/NVP_Vol will be zero for all strikes.")
            # Columns already initialized to 0.0 in df_strike_out
            return df_strike_out
        
        # Required columns from df_chain_with_contract_flows:
        # self.col_strike (strike identifier)
        # self.col_c_value_bs (per-contract net signed value, e.g., "value_bs" from chain)
        # self.col_c_volm_bs (per-contract net signed volume, e.g., "volm_bs" from chain)
        required_cols_chain_for_nvp = [
            self.col_strike, 
            self.col_c_value_bs, 
            self.col_c_volm_bs
        ]
        
        df_chain_flows_prepared, cols_ok = self._ensure_columns_internal(
            df_chain_with_contract_flows, 
            required_cols_chain_for_nvp, 
            calc_name + "_ChainInputCheck", 
            fill_numeric_with=0.0 # Fill missing numeric flow data with 0
        )

        if not cols_ok: # If critical columns like strike, value_bs, or volm_bs were missing and defaulted
            nvp_logger.warning(f"{calc_name}: Missing required flow columns ('{self.col_c_value_bs}', '{self.col_c_volm_bs}') or strike "
                               f"from df_chain_with_contract_flows for {self.current_processing_symbol}. NVP/NVP_Vol will be based on zeros or be inaccurate.")
            # df_strike_out already has NVP columns initialized to 0.0, so just return it
            return df_strike_out
        
        # Ensure strike is numeric for groupby, handle potential errors
        if self.col_strike not in df_chain_flows_prepared.columns: # Should be caught by ensure_columns if fatal
            nvp_logger.error(f"{calc_name}: Strike column '{self.col_strike}' critically missing in prepared chain data. Cannot aggregate NVP/NVP_Vol.")
            return df_strike_out # df_strike_out has NVP cols as 0.0
            
        df_chain_flows_prepared[self.col_strike] = pd.to_numeric(df_chain_flows_prepared[self.col_strike], errors='coerce')
        # Drop rows where strike could not be converted to numeric, as they can't be grouped
        df_chain_flows_prepared = df_chain_flows_prepared.dropna(subset=[self.col_strike])
        
        if df_chain_flows_prepared.empty:
            nvp_logger.warning(f"{calc_name}: Chain data for NVP became empty after strike processing for {self.current_processing_symbol}. NVP/NVP_Vol will be zero.")
            return df_strike_out # df_strike_out has NVP cols as 0.0

        # Perform the aggregation: sum 'value_bs' and 'volm_bs' per strike
        try:
            nvp_aggregated_data = df_chain_flows_prepared.groupby(self.col_strike, as_index=False).agg(
                # Use the actual column names from self.col_c_... for aggregation
                temp_nvp_strike_sum=(self.col_c_value_bs, 'sum'),
                temp_nvp_vol_strike_sum=(self.col_c_volm_bs, 'sum')
            ).fillna(0.0) # Fill any NaN sums (e.g. if all inputs were NaN for a strike) with 0.0
            
            # Rename aggregated columns to the target output column names
            nvp_aggregated_data.rename(columns={
                'temp_nvp_strike_sum': output_col_nvp,
                'temp_nvp_vol_strike_sum': output_col_nvp_vol
            }, inplace=True)

        except Exception as e_agg:
            nvp_logger.error(f"{calc_name}: Error during groupby aggregation for NVP/NVP_Vol for {self.current_processing_symbol}: {e_agg}", exc_info=False)
            # df_strike_out already has NVP cols as 0.0
            return df_strike_out
            
        # Merge the aggregated NVP data into the main df_strike_level_metrics DataFrame
        if not df_strike_out.empty and self.col_strike in df_strike_out.columns and not nvp_aggregated_data.empty:
            # Drop existing NVP columns from df_strike_out to prevent duplication issues if re-run
            for col_to_drop_nvp in default_cols_nvp:
                if col_to_drop_nvp in df_strike_out.columns: 
                    df_strike_out = df_strike_out.drop(columns=[col_to_drop_nvp], errors='ignore')
            
            df_strike_out = df_strike_out.merge(nvp_aggregated_data[[self.col_strike, output_col_nvp, output_col_nvp_vol]], 
                                                on=self.col_strike, 
                                                how='left')
            # Fill NaNs that might result from strikes present in df_strike_out but not in nvp_aggregated_data (e.g., no flow data)
            df_strike_out[output_col_nvp] = df_strike_out[output_col_nvp].fillna(0.0)
            df_strike_out[output_col_nvp_vol] = df_strike_out[output_col_nvp_vol].fillna(0.0)
        elif nvp_aggregated_data.empty and not df_strike_out.empty :
             nvp_logger.debug(f"{calc_name}: No data aggregated for NVP for {self.current_processing_symbol}. Existing NVP columns in df_strike_out (if any) remain 0.0.")
             # NVP columns in df_strike_out are already 0.0 from initialization
        elif df_strike_out.empty and not nvp_aggregated_data.empty:
            nvp_logger.info(f"{calc_name}: df_strike_level_metrics was empty. NVP results will be the aggregated NVP data only for {self.current_processing_symbol}.")
            df_strike_out = nvp_aggregated_data # The aggregated data becomes the new strike df
        else: # Both empty or other merge issue
            nvp_logger.warning(f"{calc_name}: Could not merge NVP data for {self.current_processing_symbol}. Base 'df_strike_level_metrics' might be empty or missing '{self.col_strike}'. NVP columns remain 0.0.")
            # NVP columns in df_strike_out (if it exists) remain 0.0
                
        # nvp_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}. Added '{output_col_nvp}' and '{output_col_nvp_vol}'.")
        return df_strike_out
    
    def calculate_arfi_strike_level_v2_4(self, df_strike_level_metrics: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the Average Relative Flow Index (ARFI) at the strike level.
        ARFI aims to measure the significance of recent net options order flow across
        key Greek dimensions (Delta, Charm, Vanna) relative to the existing Open Interest (OI)
        structure in those same dimensions at each strike.

        It's computed as an average of individual flow-to-OI ratios for these Greeks.
        A high ARFI suggests recent transactional activity is proportionally large compared
        to existing OI, potentially indicating strong conviction or a capacity to shift dealer
        hedging. ARFI is primarily used to spot divergences with price action, which can
        signal trend exhaustion.

        V2.4 refines ARFI by aiming to use direct net signed customer Greek flows for its
        flow components (e.g., from per-contract 'deltas_buy'/'deltas_sell' summed at strike)
        rather than relying solely on total Greek-weighted volume proxies. For Charm and Vanna
        flows, summed 'charmxvolm' and 'vannaxvolm' often serve as proxies.

        This calculation can be toggled off via the "calculate_arfi_strike" config setting,
        or if its parent phase "flow_metrics_nvp_arfi" is disabled. If skipped,
        the 'arfi_strike' column will be added with a default (0.0) value.

        Args:
            df_strike_level_metrics (pd.DataFrame): DataFrame containing strike-level aggregated
                                                    metrics, including summed OI for Delta, Charm,
                                                    Vanna (e.g., 'dxoi', 'charmxoi', 'vannaxoi') and
                                                    summed flow components/proxies for these Greeks.
        Returns:
            pd.DataFrame: The input `df_strike_level_metrics` DataFrame enriched with an
                          'arfi_strike' column.
        """
        # Toggle Key in config: "calculate_arfi_strike"
        # Part of phase: "flow_metrics_nvp_arfi"
        output_col = 'arfi_strike'
        if not self.metric_phases_activation_cfg.get("calculate_arfi_strike", True) and \
           not self.metric_phases_activation_cfg.get("flow_metrics_nvp_arfi", True):
            self.logger.info(f"ARFI Strike calculation for {self.current_processing_symbol} SKIPPED by config.")
            df_strike_out = df_strike_level_metrics.copy()
            if isinstance(df_strike_out, pd.DataFrame) and output_col not in df_strike_out.columns and not df_strike_out.empty:
                df_strike_out[output_col] = 0.0
            elif isinstance(df_strike_out, pd.DataFrame) and df_strike_out.empty and output_col not in df_strike_out.columns:
                df_strike_out[output_col] = pd.Series(dtype=float)
            return df_strike_out
        
        df_strike = df_strike_level_metrics.copy() # Work on a copy
        calc_name = "ARFI_Strike_V2.4_MC_RefinedDelta"
        arfi_logger = self.logger.getChild(calc_name)

        output_col_arfi = 'arfi_strike'

        # Initialize output column
        if output_col_arfi not in df_strike.columns:
            df_strike[output_col_arfi] = 0.0
        else: # Ensure it's float and fill NaNs
            df_strike[output_col_arfi] = pd.to_numeric(df_strike[output_col_arfi], errors='coerce').fillna(0.0)


        if df_strike.empty:
            arfi_logger.warning(f"{calc_name}: Input df_strike_level_metrics is empty for {self.current_processing_symbol}. '{output_col_arfi}' remains 0.0.")
            return df_strike # Already has arfi_strike as 0.0

        # Required columns from df_strike_level_metrics (these are strike-level sums)
        # OI components:
        req_cols_oi = [self.col_dxoi, self.col_charmxoi, self.col_vannaxoi]
        
        # Flow components:
        # For Delta: Using summed signed flows (these columns should exist on df_strike if aggregated from df_chain)
        # Note: The aggregation in orchestrator must sum self.col_c_deltas_buy and self.col_c_deltas_sell to strike level.
        # Let's assume df_strike now has columns like 'sum_c_deltas_buy' and 'sum_c_deltas_sell'
        # For simplicity in this method, we assume these were renamed or are directly accessible with these names
        # if MetricsCalculator's orchestrator prepares them with these exact names at strike level.
        # However, `self.col_c_deltas_buy` and `self.col_c_deltas_sell` are per-contract names.
        # The aggregation step should have produced strike-level sums like:
        # df_strike['sum_deltas_buy_strike'] = df_chain.groupby('strike')[self.col_c_deltas_buy].sum()
        # For this function, we expect these summed values to be present.
        # Let's define expected strike-level sum names:
        strike_level_sum_deltas_buy = self.col_c_deltas_buy # Assuming agg used original name
        strike_level_sum_deltas_sell = self.col_c_deltas_sell # Assuming agg used original name

        req_cols_flow_signed_delta = [strike_level_sum_deltas_buy, strike_level_sum_deltas_sell]
        
        # Flow proxies for Charm and Vanna (these are already sums from total Greek-weighted volumes)
        req_cols_flow_proxies = [self.col_charmxvolm, self.col_vannaxvolm]
        
        # Fallback Delta Flow Proxy (if signed delta flows are not deemed reliable or available at strike level)
        # For now, we will prioritize signed delta flows. If they are problematic,
        # this logic would need a switch to use self.col_dxvolm (summed dxvolm at strike).
        # req_cols_flow_delta_proxy = [self.col_dxvolm] 

        all_required_cols = req_cols_oi + req_cols_flow_signed_delta + req_cols_flow_proxies
        
        df_strike_prepared, cols_ok = self._ensure_columns_internal(
            df_strike, 
            all_required_cols, 
            calc_name + "_InputCheck", 
            fill_numeric_with=0.0
        )

        if not cols_ok: 
            arfi_logger.warning(f"{calc_name}: Missing one or more critical input columns in df_strike_level_metrics for {self.current_processing_symbol}. '{output_col_arfi}' calculation will be based on zeros or be inaccurate.")
            # arfi_strike is already 0.0, so just return
            return df_strike
        
        # Helper function to calculate ratio: abs(Flow) / (abs(OI) + EPSILON)
        # Handles division by zero and cases where OI is zero but flow is not.
        def calculate_flow_oi_ratio(flow_series_abs: pd.Series, oi_series_abs: pd.Series) -> pd.Series:
            # Ensure inputs are numeric and fill NaNs from coercion with 0
            flow_s = pd.to_numeric(flow_series_abs, errors='coerce').fillna(0.0)
            oi_s = pd.to_numeric(oi_series_abs, errors='coerce').fillna(0.0)

            ratio = flow_s / (oi_s + EPSILON)
            # If OI is effectively zero but flow is present, assign a high ratio
            ratio.loc[(oi_s.abs() < EPSILON) & (flow_s.abs() > EPSILON)] = 1000.0 # Arbitrary high value
            # If both OI and flow are effectively zero, ratio is zero
            ratio.loc[(oi_s.abs() < EPSILON) & (flow_s.abs() < EPSILON)] = 0.0
            return ratio.fillna(0.0) # Final fillna for any other odd cases

        # 1. Delta Component Ratio (Using refined signed delta flows)
        # These columns in df_strike_prepared are strike-level sums of per-contract signed flows
        sum_deltas_buy_at_strike = pd.to_numeric(df_strike_prepared[strike_level_sum_deltas_buy], errors='coerce').fillna(0.0)
        sum_deltas_sell_at_strike = pd.to_numeric(df_strike_prepared[strike_level_sum_deltas_sell], errors='coerce').fillna(0.0)
        
        # Net delta flow from customer perspective (Buy - Sell) at strike level
        net_delta_flow_customer_strike_abs = (sum_deltas_buy_at_strike - sum_deltas_sell_at_strike).abs()
        dxoi_strike_abs = pd.to_numeric(df_strike_prepared[self.col_dxoi], errors='coerce').abs().fillna(0.0)
        abs_dx_ratio = calculate_flow_oi_ratio(net_delta_flow_customer_strike_abs, dxoi_strike_abs)
        arfi_logger.debug(f"{calc_name} ({self.current_processing_symbol}): Max abs_dx_ratio (signed delta flow based): {abs_dx_ratio.max():.4f}")

        # 2. Charm Component Ratio (td - Time/Delta related flow proxy)
        # Using summed charmxvolm (total charm-weighted volume at strike)
        charmxvolm_strike_abs = pd.to_numeric(df_strike_prepared[self.col_charmxvolm], errors='coerce').abs().fillna(0.0)
        charmxoi_strike_abs = pd.to_numeric(df_strike_prepared[self.col_charmxoi], errors='coerce').abs().fillna(0.0)
        abs_td_ratio = calculate_flow_oi_ratio(charmxvolm_strike_abs, charmxoi_strike_abs)
        arfi_logger.debug(f"{calc_name} ({self.current_processing_symbol}): Max abs_td_ratio (charmxvolm based): {abs_td_ratio.max():.4f}")

        # 3. Vanna Component Ratio (vx - Vol/Delta related flow proxy)
        # Using summed vannaxvolm (total vanna-weighted volume at strike)
        vannaxvolm_strike_abs = pd.to_numeric(df_strike_prepared[self.col_vannaxvolm], errors='coerce').abs().fillna(0.0)
        vannaxoi_strike_abs = pd.to_numeric(df_strike_prepared[self.col_vannaxoi], errors='coerce').abs().fillna(0.0)
        abs_vx_ratio = calculate_flow_oi_ratio(vannaxvolm_strike_abs, vannaxoi_strike_abs)
        arfi_logger.debug(f"{calc_name} ({self.current_processing_symbol}): Max abs_vx_ratio (vannaxvolm based): {abs_vx_ratio.max():.4f}")
        
        # Calculate ARFI as the average of the three ratios
        df_strike[output_col_arfi] = (abs_dx_ratio + abs_td_ratio + abs_vx_ratio) / 3.0
        df_strike[output_col_arfi] = df_strike[output_col_arfi].fillna(0.0) # Final safety fill

        arfi_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}. Added '{output_col_arfi}'. Max ARFI: {df_strike[output_col_arfi].max():.4f}")
        return df_strike
    
    # --- MSPI Suite (Operates on df_strike_level_metrics with normalized components) ---
    def _get_mspi_weights_v2_4_metrics_calc(
        self,
        current_market_time_obj: time,
        current_und_data_for_weights: Dict[str, Any],
        current_market_regime_str: str
    ) -> Dict[str, float]:
        """
        Determines the appropriate weights for Market Structure Position Indicator (MSPI) components.
        This method implements the logic for selecting MSPI weights based on the configured
        `data_processor_settings.weights.selection_logic`.

        Supported selection logics include:
        - "regime_then_time_based": Prioritizes regime-specific weights if available and enabled,
                                    then falls back to time-based weights, then to default.
        - "regime_only": Uses only regime-specific weights if found, otherwise defaults.
        - "time_based_only": Uses only time-of-day based weights, otherwise defaults.
        - "volatility_based_only": Uses only volatility context (e.g., IV rank) based weights,
                                   otherwise defaults. (Requires IV rank in `current_und_data_for_weights`).
        - "default_only": Always uses `default_fallback_weights`.

        The method ensures that a weight (even if 0.0) is returned for all recognized
        normalized MSPI components (e.g., "dag_custom_norm", "tdpi_norm", "sdag_multiplicative_norm", etc.).
        The sum of returned weights is checked against a tolerance for validation.

        This calculation can be toggled off via the "calculate_mspi_weights" config setting,
        or if its parent phase "mspi_suite_calculation" is disabled. If skipped, it returns
        a dictionary with all component weights set to 0.0, which will result in a zero MSPI.

        Args:
            current_market_time_obj (time): Current market time, used for time-based weight selection.
            current_und_data_for_weights (Dict[str, Any]): Underlying aggregate data, potentially
                                                           containing IV rank for volatility-based
                                                           weight selection and regime for regime-based.
            current_market_regime_str (str): The currently classified market regime string.

        Returns:
            Dict[str, float]: A dictionary mapping normalized MSPI component names to their
                              calculated weights for the current context.
        """
        # Toggle Key: "calculate_mspi_weights"
        # Part of phase: "mspi_suite_calculation"
        # Define all possible normalized MSPI component names first for default return
        all_possible_mspi_components_norm = [
            "dag_custom_norm", "tdpi_norm", "vri_sensitivity_norm",
            "vri_0dte_norm", "vfi_0dte_norm", "arfi_strike_norm"
        ]
        # Ensure self.enabled_sdag_methodologies is initialized (e.g., in __init__ or fallback)
        enabled_sdags = getattr(self, 'enabled_sdag_methodologies', [])
        for sdag_m_key in enabled_sdags:
            all_possible_mspi_components_norm.append(f"sdag_{sdag_m_key}_norm")

        if not self.metric_phases_activation_cfg.get("calculate_mspi_weights", True) and \
           not self.metric_phases_activation_cfg.get("mspi_suite_calculation", True):
            self.logger.info(f"MSPI Weights calculation for {self.current_processing_symbol} SKIPPED by config.")
            # Return a dictionary with all possible component weights set to 0
            return {comp: 0.0 for comp in all_possible_mspi_components_norm}
        
        weights_logger = self.logger.getChild("GetMSPIWeights")
        # weights_logger.debug(f"Determining MSPI weights. Logic: configured, Time: {current_market_time_obj.strftime('%H:%M:%S')}, Regime: {current_market_regime_str}")

        weights_config_section = self._get_config_setting("data_processor_settings.weights", {})
        selection_logic: str = weights_config_section.get("selection_logic", "time_based_only") # Default if not specified
        
        resolved_weights_dict_source: Optional[Dict[str, Any]] = None # Will hold the dict of {component_name: weight_value}
        resolved_weights_source_name: str = "NONE_RESOLVED"

        # Strategy 1: Regime-Based Weights (Highest Priority if enabled by selection_logic)
        if selection_logic in ["regime_then_time_based", "regime_only"]:
            if self._get_config_setting("data_processor_settings.weights.regime_specific_weights_enabled", False):
                regime_weights_map = self._get_config_setting("data_processor_settings.weights.regime_weights", {})
                if isinstance(regime_weights_map, dict) and current_market_regime_str in regime_weights_map:
                    resolved_weights_dict_source = regime_weights_map[current_market_regime_str]
                    resolved_weights_source_name = f"REGIME ('{current_market_regime_str}')"
                    # weights_logger.debug(f"MSPI Weights: Tentatively selected using {resolved_weights_source_name}.")
                # else:
                    # weights_logger.debug(f"MSPI Weights: Regime '{current_market_regime_str}' not found in 'regime_weights' config or map is not a dict.")
            # else:
                # weights_logger.debug("MSPI Weights: Regime-specific weights are disabled in config.")
        
        # Strategy 2: Time-Based Weights (Fallback or primary if regime not matched/used)
        if resolved_weights_dict_source is None and selection_logic in ["regime_then_time_based", "time_based_only"]:
            time_based_cfg = self._get_config_setting("data_processor_settings.weights.time_based", {})
            current_hour_float = current_market_time_obj.hour + current_market_time_obj.minute / 60.0
            
            # Get time period definitions from MRE settings (already initialized in self.mre_time_defs_cfg)
            morning_end_str = self.mre_time_defs_cfg.get("morning_end_time", "11:00:00")
            midday_end_str = self.mre_time_defs_cfg.get("midday_end_time", "14:00:00") # Using midday_end_time for final_hour logic
            # final_hour_start_str = self.mre_time_defs_cfg.get("final_hour_start_time", "15:00:00") # Alternative way

            morning_end_float = self._time_str_to_float(morning_end_str)
            midday_end_float = self._time_str_to_float(midday_end_str)
            # final_hour_start_float = self._time_str_to_float(final_hour_start_str)


            period_key = "final_hour" # Default to final_hour (covers afternoon too)
            if current_hour_float < morning_end_float:
                period_key = "morning"
            elif current_hour_float < midday_end_float: # If after morning_end but before midday_end
                period_key = "midday"
            # If current_hour_float >= midday_end_float, it defaults to "final_hour" which covers the rest of the day.
            # If you need a distinct "afternoon" before "final_hour", the logic would need another elif.
            
            if isinstance(time_based_cfg, dict) and period_key in time_based_cfg:
                resolved_weights_dict_source = time_based_cfg[period_key]
                resolved_weights_source_name = f"TIME_BASED ('{period_key}')"
                # weights_logger.debug(f"MSPI Weights: Tentatively selected using {resolved_weights_source_name}.")
            # else:
                # weights_logger.debug(f"MSPI Weights: Time period key '{period_key}' not found in 'time_based' config or config is not a dict.")

        # Strategy 3: Volatility-Based Weights (If specified by selection_logic and others didn't match)
        if resolved_weights_dict_source is None and selection_logic == "volatility_based_only":
            vol_based_cfg = self._get_config_setting("data_processor_settings.weights.volatility_based", {})
            iv_rank_col = self.iv_rank_col_from_und # From common_configs init
            
            iv_percentile_val = None
            if iv_rank_col and isinstance(current_und_data_for_weights, dict):
                iv_percentile_val = current_und_data_for_weights.get(iv_rank_col) # This IV rank should be in the enriched und_data

            iv_threshold_cfg = float(vol_based_cfg.get("iv_percentile_threshold", 50.0))
            
            if iv_percentile_val is not None and isinstance(iv_percentile_val, (float, int)):
                period_key = "low_iv" if iv_percentile_val < iv_threshold_cfg else "high_iv"
                if isinstance(vol_based_cfg, dict) and period_key in vol_based_cfg:
                    resolved_weights_dict_source = vol_based_cfg[period_key]
                    resolved_weights_source_name = f"VOL_BASED ('{period_key}', IV Rank: {iv_percentile_val:.2f})"
                    # weights_logger.debug(f"MSPI Weights: Tentatively selected using {resolved_weights_source_name}.")
                # else:
                    # weights_logger.debug(f"MSPI Weights: Volatility key '{period_key}' not found in 'volatility_based' config or config is not a dict.")
            # else:
                # weights_logger.debug(f"MSPI Weights: IV Rank from column '{iv_rank_col}' not available or invalid ({iv_percentile_val}) for 'volatility_based' logic.")

        # Strategy 4: Fallback to Default Weights
        if resolved_weights_dict_source is None or selection_logic == "default_only":
            resolved_weights_dict_source = self._get_config_setting("data_processor_settings.weights.default_fallback_weights", {})
            resolved_weights_source_name = "DEFAULT_FALLBACK_WEIGHTS"
            weights_logger.info(f"MSPI Weights: Using {resolved_weights_source_name} as no specific weights were resolved by logic '{selection_logic}' or default_only was chosen.")
        
        weights_logger.info(f"MSPI Weights final selection source: {resolved_weights_source_name}.")

        # Define all possible normalized MSPI component names based on config and enabled SDAGs
        # These are the keys the final weights dictionary MUST have.
        all_possible_mspi_components_norm = [
            "dag_custom_norm", "tdpi_norm", "vri_sensitivity_norm", 
            "vri_0dte_norm", "vfi_0dte_norm", "arfi_strike_norm"
            # "vci_0dte_agg_norm" # VCI is underlying aggregate, usually not direct MSPI component per strike
            # "HP_EOD_Und_norm_mspi" # This is an underlying metric; if used in MSPI, means MSPI is influenced by underlying trend
        ]
        # Add MSPI-normalized names for enabled SDAGs
        for sdag_m_key in self.enabled_sdag_methodologies: # e.g., "multiplicative", "weighted"
            sdag_norm_col_name = f"sdag_{sdag_m_key}_norm" # e.g., "sdag_multiplicative_norm"
            all_possible_mspi_components_norm.append(sdag_norm_col_name)
        
        # Add any other specifically named normalized MSPI components from config (e.g. NetValueFlow_15m_Und_norm_mspi)
        # This requires parsing the weight dictionaries to find unique keys if they are not predefined.
        # For simplicity, we rely on the `all_possible_mspi_components_norm` being comprehensive.
        # If a weight dict has a key not in this list, it might be logged as an unknown component.

        final_weights_output: Dict[str, float] = {comp: 0.0 for comp in all_possible_mspi_components_norm}
        
        if isinstance(resolved_weights_dict_source, dict):
            total_weight_sum = 0.0
            for comp_key_from_config, weight_val_from_config in resolved_weights_dict_source.items():
                # comp_key_from_config should match one of the keys in all_possible_mspi_components_norm
                if comp_key_from_config in final_weights_output:
                    try:
                        weight_float = float(weight_val_from_config)
                        final_weights_output[comp_key_from_config] = weight_float
                        total_weight_sum += weight_float
                    except (ValueError, TypeError):
                        weights_logger.warning(f"Invalid weight value '{weight_val_from_config}' for MSPI component '{comp_key_from_config}'. Defaulting to 0.0.")
                        # final_weights_output[comp_key_from_config] remains 0.0
                else:
                    weights_logger.warning(f"Weight provided in '{resolved_weights_source_name}' for an unrecognized MSPI component "
                                         f"'{comp_key_from_config}'. This component name needs to be added to the "
                                         f"system's known list or MSPI weight definition corrected.")
            
            # Optional: Check if weights sum to ~1.0 (or configured tolerance)
            weights_sum_tolerance = float(self._get_config_setting("validation.weights_sum_tolerance", 0.05))
            if not math.isclose(total_weight_sum, 1.0, abs_tol=weights_sum_tolerance) and total_weight_sum != 0.0:
                weights_logger.warning(f"MSPI component weights from source '{resolved_weights_source_name}' sum to {total_weight_sum:.3f}, "
                                       f"which is outside the tolerance of 1.0 +/- {weights_sum_tolerance}. Review config.")
        else:
            weights_logger.error(f"Resolved MSPI weights source ('{resolved_weights_source_name}') did not yield a dictionary: {resolved_weights_dict_source}. All MSPI component weights will be 0.0.")

        weights_logger.debug(f"Final MSPI weights to be used by {self.current_processing_symbol}: {final_weights_output}")
        return final_weights_output
    
    def calculate_mspi_sai_ssi_v2_4(
        self,
        df_strike_level_with_norm_components: pd.DataFrame,
        mspi_weights_dict: Dict[str, float]
    ) -> pd.DataFrame:
        """
        Calculates the core Market Structure Position Indicator (MSPI), Sentiment Alignment
        Indicator (SAI), and Structural Stability Index (SSI) at the strike level.

        - MSPI: A composite indicator derived from the weighted sum of several normalized
          structural and flow-based metrics (e.g., DAG_Custom_norm, TDPI_norm, VRI_norm, SDAG_norms).
          The weights are dynamically determined by `_get_mspi_weights_v2_4_metrics_calc`
          based on the current market context (regime, time, volatility).
          MSPI_raw is the direct weighted sum, and MSPI is its normalized version.
        - SAI: Measures the internal consistency (sign alignment) among the weighted,
          normalized MSPI components. A high positive SAI indicates component agreement.
        - SSI: Assesses market structure stability by measuring the variance among the
          weighted, normalized MSPI components. High SSI indicates a stable structure.

        These metrics are fundamental for identifying potential support/resistance, gauging
        market conviction, and assessing structural integrity.

        This calculation can be toggled off via the "calculate_mspi_sai_ssi" config setting,
        or if its parent phase "mspi_suite_calculation" is disabled. If skipped, the output
        columns ('mspi_raw', 'mspi', 'sai', 'ssi_agg') will be added with default (0.0 or 0.5 for SSI) values.

        Args:
            df_strike_level_with_norm_components (pd.DataFrame): DataFrame containing strike-level
                                                                metrics, including all
                                                                pre-normalized components that
                                                                will be weighted for MSPI.
            mspi_weights_dict (Dict[str, float]): A dictionary of (normalized component name: weight),
                                                  as determined by `_get_mspi_weights_v2_4_metrics_calc`.

        Returns:
            pd.DataFrame: The input DataFrame enriched with 'mspi_raw', 'mspi', 'sai',
                          and 'ssi_agg' columns.
        """
        # Toggle Key: "calculate_mspi_sai_ssi"
        # Part of phase: "mspi_suite_calculation"
        output_cols = ['mspi_raw', 'mspi', 'sai', 'ssi_agg']
        if not self.metric_phases_activation_cfg.get("calculate_mspi_sai_ssi", True) and \
           not self.metric_phases_activation_cfg.get("mspi_suite_calculation", True):
            self.logger.info(f"MSPI, SAI, SSI calculation for {self.current_processing_symbol} SKIPPED by config.")
            df_out = df_strike_level_with_norm_components.copy()
            if isinstance(df_out, pd.DataFrame) and not df_out.empty:
                for col in output_cols:
                    if col not in df_out.columns:
                        df_out[col] = 0.5 if col == 'ssi_agg' else 0.0 # SSI default might be neutral 0.5
            elif isinstance(df_out, pd.DataFrame) and df_out.empty:
                for col in output_cols:
                    df_out[col] = pd.Series(dtype=float)
            return df_out
        
        df = df_strike_level_with_norm_components.copy()
        calc_name = "MSPI_SAI_SSI_V2.4_MC"
        mspi_calc_logger = self.logger.getChild(calc_name)
        # mspi_calc_logger.debug(f"Calculating {calc_name} for {self.current_processing_symbol} using weights: {mspi_weights_dict}")

        # Output columns
        output_cols_mspi = ['mspi_raw', 'mspi', 'sai', 'ssi_agg']

        if df.empty:
            mspi_calc_logger.warning(f"{calc_name}: Input df_strike_level_metrics is empty for {self.current_processing_symbol}. Output columns set to 0.")
            for col_add in output_cols_mspi: df[col_add] = 0.0
            return df

        # Ensure all component columns that have non-zero weights exist in the DataFrame
        # The _get_mspi_weights method already ensures the mspi_weights_dict keys are known components.
        # Here, we ensure those columns are present in the df.
        weighted_component_cols_needed = [col_norm for col_norm, weight in mspi_weights_dict.items() if abs(weight) > EPSILON]
        
        df, components_ok = self._ensure_columns_internal(
            df, 
            weighted_component_cols_needed, 
            f"{calc_name}_NormCompsCheck", 
            fill_numeric_with=0.0
        )
        if not components_ok:
             mspi_calc_logger.warning(f"{calc_name}: Some weighted MSPI components were missing/invalid. Results may be affected.")


        # --- Calculate Raw MSPI ---
        raw_mspi_series = pd.Series(0.0, index=df.index, dtype=float)
        active_weighted_components_for_sai_ssi: List[pd.Series] = [] 
        active_component_names_for_log: List[str] = []

        for component_col_norm, weight_float in mspi_weights_dict.items():
            if component_col_norm in df.columns and pd.notna(weight_float) and abs(weight_float) > EPSILON:
                component_data_series = pd.to_numeric(df[component_col_norm], errors='coerce').fillna(0.0)
                weighted_component_value_series = component_data_series * weight_float
                raw_mspi_series += weighted_component_value_series
                
                # Store the actual weighted component series for SAI/SSI
                # Only include if the weight is significant, to avoid noise in SAI/SSI from tiny weights
                if abs(weight_float) > 0.01: # Configurable threshold for "significant weight"
                    active_weighted_components_for_sai_ssi.append(weighted_component_value_series.rename(component_col_norm + "_weighted_val"))
                    active_component_names_for_log.append(f"{component_col_norm}(w={weight_float:.2f})")
            # else: # Log if a configured weight applies to a missing column (should be caught by ensure_columns)
                # if component_col_norm not in df.columns and pd.notna(weight_float) and abs(weight_float) > EPSILON:
                #     mspi_calc_logger.debug(f"MSPI component '{component_col_norm}' (weight {weight_float:.2f}) not found in strike DF. Ignored.")
        
        df['mspi_raw'] = raw_mspi_series.fillna(0.0)
        df['mspi'] = self._normalize_series(df['mspi_raw'], "mspi_final_norm", clip_percentile=self.clip_percentile).fillna(0.0)
        # mspi_calc_logger.debug(f"Raw MSPI calculated using components: {active_component_names_for_log}")

        # --- Calculate SAI (Sentiment Alignment Indicator) ---
        if len(active_weighted_components_for_sai_ssi) >= 2:
            components_df_for_sai = pd.concat(active_weighted_components_for_sai_ssi, axis=1)
            sign_matrix = np.sign(components_df_for_sai) # +1 for positive, -1 for negative, 0 for zero
            
            sai_pairwise_scores_sum = pd.Series(0.0, index=df.index, dtype=float)
            num_pairs_sai = 0
            active_cols_sai = components_df_for_sai.columns # These are named like "component_norm_weighted_val"
            for i in range(len(active_cols_sai)):
                for j in range(i + 1, len(active_cols_sai)):
                    # Product of signs: +1 if same, -1 if different, 0 if one is zero
                    sai_pairwise_scores_sum += sign_matrix[active_cols_sai[i]] * sign_matrix[active_cols_sai[j]]
                    num_pairs_sai += 1
            
            df['sai'] = (sai_pairwise_scores_sum / num_pairs_sai).fillna(0.0) if num_pairs_sai > 0 else 0.0
        else:
            mspi_calc_logger.debug(f"Not enough active weighted components ({len(active_weighted_components_for_sai_ssi)}) for SAI. SAI set to 0.0.")
            df['sai'] = 0.0
        
        # --- Calculate SSI (Structural Stability Index) ---
        if len(active_weighted_components_for_sai_ssi) >= 2:
            # Use the same components_df_for_sai which holds the *weighted* component values
            std_dev_of_weighted_components = components_df_for_sai.std(axis=1, skipna=True).fillna(0.0)
            
            # Normalize std_dev across strikes to approx [0,1] then invert. 
            # Low std_dev (components are similar in their weighted contribution) = high stability (SSI near 1).
            # High std_dev (components disagree in weighted contribution) = low stability (SSI near 0).
            normalized_std_dev_for_ssi = self._normalize_series(
                std_dev_of_weighted_components, 
                "normalized_std_dev_for_ssi", 
                method="max_abs", # Ensures range [0,1] if std_dev is non-negative
                clip_percentile=100.0 # Usually no clipping for this type of factor
            )
            df['ssi_agg'] = (1.0 - normalized_std_dev_for_ssi).fillna(0.5).clip(0.0, 1.0) # Clip to ensure [0,1]
        else:
            mspi_calc_logger.debug(f"Not enough active weighted components ({len(active_weighted_components_for_sai_ssi)}) for SSI. SSI set to 0.5 (neutral).")
            df['ssi_agg'] = 0.5 
        
        # Ensure all output columns exist and fill NaNs
        for col_final in output_cols_mspi:
            if col_final not in df.columns: df[col_final] = 0.0
            else: df[col_final] = df[col_final].fillna(0.0)

        mspi_calc_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}. Added 'mspi', 'sai', 'ssi_agg'. Max MSPI: {df['mspi'].max():.3f}, Min MSPI: {df['mspi'].min():.3f}")
        return df
    
    # --- Underlying-Level Aggregate Metrics (Orchestrator and Sub-Calculators) ---
        # --- START: Updated _ensure_ohlcv_fallbacks method ---
    def _ensure_ohlcv_fallbacks(self, und_data_dict_to_modify: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensures that daily Open-High-Low-Close-Volume (OHLCV) fields are present and valid
        in the provided underlying data dictionary. This is typically called at the beginning
        of `calculate_underlying_aggregate_metrics_v2_4`.

        This method prioritizes OHLCV data that might have already been populated by the
        ITSOrchestrator (e.g., from Tradier's current day quote/bar). If these fields are
        missing, appear invalid (e.g., non-positive, NaN), or cannot be converted to the
        correct numeric type, this method applies fallbacks.

        Fallbacks are primarily based on `self.current_und_price` (the last trade price of
        the current snapshot). For example, if 'open' is missing, it might default to
        `self.current_und_price`. It also ensures logical consistency (e.g., low <= high,
        close is within high/low).

        The actual field names for OHLCV (e.g., 'day_open_price', 'day_high_price') are
        sourced from the configuration (`strategy_settings.greeks_from_und` mapping
        conceptual keys like 'day_open_price_und' to actual API field names).

        This utility can be toggled off via the "ensure_ohlcv_fallbacks" config setting.
        If disabled, the input dictionary is returned as is, which might lead to errors
        in downstream metrics (like HP_EOD) if OHLCV data is missing or invalid.

        Args:
            und_data_dict_to_modify (Dict[str, Any]): The underlying data dictionary
                                                       to validate and potentially modify.

        Returns:
            Dict[str, Any]: The (potentially) modified underlying data dictionary with
                            ensured OHLCV fields.
        """
        # Toggle Key in config: "ensure_ohlcv_fallbacks"
        # This is often critical, especially for HP_EOD.
        if not self.metric_phases_activation_cfg.get("ensure_ohlcv_fallbacks", True): # Default to True
            self.logger.info(f"OHLCV Fallbacks for {self.current_processing_symbol} SKIPPED by config toggle 'ensure_ohlcv_fallbacks'.")
            # Return the dict unmodified; downstream functions must handle potentially missing/invalid OHLCV.
            return und_data_dict_to_modify
        
        ohlcv_fallback_logger = self.logger.getChild(f"EnsureOHLCVFallbacks.{self.current_processing_symbol or 'UnknownSym'}")
        
        # self.current_und_price should be set by orchestrate_all_metric_calculations
        # It's the 'last' price of the current snapshot, used as the ultimate reference.
        current_snapshot_price = self.current_und_price 

        if current_snapshot_price is None or pd.isna(current_snapshot_price) or current_snapshot_price <= 0:
            ohlcv_fallback_logger.error(f"Current underlying snapshot price (self.current_und_price) is invalid ({current_snapshot_price}). Cannot apply meaningful OHLCV fallbacks. OHLCV fields might remain None or default to 0.")
            # Ensure essential OHLCV keys exist with default "bad" values if price itself is bad
            ohlc_conceptual_keys_on_error = {
                "day_open_price_und": None, "day_high_price_und": None,
                "day_low_price_und": None, "day_volume_und": 0
            }
            for conceptual_key, default_val_err in ohlc_conceptual_keys_on_error.items():
                actual_api_field_err = self._get_config_setting(["strategy_settings", "greeks_from_und", conceptual_key], default=conceptual_key)
                if actual_api_field_err not in und_data_dict_to_modify:
                    und_data_dict_to_modify[actual_api_field_err] = default_val_err
            return und_data_dict_to_modify

        # Define conceptual keys for OHLCV and their corresponding actual API field names from config
        ohlcv_fields_map = {
            "open": self._get_config_setting(["strategy_settings", "greeks_from_und", "day_open_price_und"], "day_open_price"),
            "high": self._get_config_setting(["strategy_settings", "greeks_from_und", "day_high_price_und"], "day_high_price"),
            "low": self._get_config_setting(["strategy_settings", "greeks_from_und", "day_low_price_und"], "day_low_price"),
            "close": self._get_config_setting(["strategy_settings", "greeks_from_und", "day_close_price_und"], "day_close_price"), # Current day's close is often the last trade price
            "volume": self._get_config_setting(["strategy_settings", "greeks_from_und", "day_volume_und"], "day_volume")
        }
        
        # --- Validate or Fallback for OPEN ---
        open_field = ohlcv_fields_map["open"]
        current_open_val = und_data_dict_to_modify.get(open_field)
        try:
            open_price = float(current_open_val)
            if not (pd.notna(open_price) and open_price > 0): raise ValueError("Open price not positive")
            und_data_dict_to_modify[open_field] = open_price
        except (ValueError, TypeError, AttributeError):
            und_data_dict_to_modify[open_field] = current_snapshot_price # Fallback: Open = Current Snapshot Price
            ohlcv_fallback_logger.warning(f"Missing/invalid '{open_field}' (value: {current_open_val}). Using current snapshot price ({current_snapshot_price:.2f}) as fallback for OPEN.")
        
        effective_open_price = und_data_dict_to_modify[open_field]

        # --- Validate or Fallback for HIGH ---
        high_field = ohlcv_fields_map["high"]
        current_high_val = und_data_dict_to_modify.get(high_field)
        try:
            high_price = float(current_high_val)
            if not (pd.notna(high_price) and high_price > 0): raise ValueError("High price not positive")
            # Ensure High is at least the open and at least the current snapshot price
            und_data_dict_to_modify[high_field] = max(high_price, effective_open_price, current_snapshot_price)
        except (ValueError, TypeError, AttributeError):
            und_data_dict_to_modify[high_field] = max(effective_open_price, current_snapshot_price) # Fallback
            ohlcv_fallback_logger.warning(f"Missing/invalid '{high_field}' (value: {current_high_val}). Using max(effective_open, current_snapshot_price) ({und_data_dict_to_modify[high_field]:.2f}) as fallback for HIGH.")

        effective_high_price = und_data_dict_to_modify[high_field]

        # --- Validate or Fallback for LOW ---
        low_field = ohlcv_fields_map["low"]
        current_low_val = und_data_dict_to_modify.get(low_field)
        try:
            low_price = float(current_low_val)
            if not (pd.notna(low_price) and low_price > 0): raise ValueError("Low price not positive")
            # Ensure Low is at most the open, at most the current snapshot price, and at most the high
            und_data_dict_to_modify[low_field] = min(low_price, effective_open_price, current_snapshot_price, effective_high_price)
        except (ValueError, TypeError, AttributeError):
            und_data_dict_to_modify[low_field] = min(effective_open_price, current_snapshot_price) # Fallback
            ohlcv_fallback_logger.warning(f"Missing/invalid '{low_field}' (value: {current_low_val}). Using min(effective_open, current_snapshot_price) ({und_data_dict_to_modify[low_field]:.2f}) as fallback for LOW.")
        
        # Ensure low is not greater than high after all fallbacks
        if und_data_dict_to_modify[low_field] > und_data_dict_to_modify[high_field]:
            ohlcv_fallback_logger.warning(f"Corrected LOW ({und_data_dict_to_modify[low_field]:.2f}) to be equal to HIGH ({und_data_dict_to_modify[high_field]:.2f}) as LOW > HIGH after fallbacks.")
            und_data_dict_to_modify[low_field] = und_data_dict_to_modify[high_field]


        # --- Validate or Fallback for CLOSE (current day's close) ---
        # For the current day's snapshot, 'close' is often the same as the 'last' price (self.current_und_price)
        close_field = ohlcv_fields_map["close"]
        current_close_val = und_data_dict_to_modify.get(close_field)
        try:
            close_price = float(current_close_val)
            if not (pd.notna(close_price) and close_price > 0): raise ValueError("Close price not positive")
            # Ensure close is within day's high/low range
            und_data_dict_to_modify[close_field] = np.clip(close_price, und_data_dict_to_modify[low_field], und_data_dict_to_modify[high_field])
        except (ValueError, TypeError, AttributeError):
            und_data_dict_to_modify[close_field] = current_snapshot_price # Fallback: Close = Current Snapshot Price
            ohlcv_fallback_logger.warning(f"Missing/invalid '{close_field}' (value: {current_close_val}). Using current snapshot price ({current_snapshot_price:.2f}) as fallback for CLOSE.")
            # Re-clip if fallback was used
            und_data_dict_to_modify[close_field] = np.clip(und_data_dict_to_modify[close_field], und_data_dict_to_modify[low_field], und_data_dict_to_modify[high_field])


        # --- Validate or Fallback for VOLUME ---
        volume_field = ohlcv_fields_map["volume"]
        current_volume_val = und_data_dict_to_modify.get(volume_field)
        try:
            volume = int(float(current_volume_val)) # Convert to float first for flexibility, then int
            if not (pd.notna(volume) and volume >= 0): raise ValueError("Volume not non-negative")
            und_data_dict_to_modify[volume_field] = volume
        except (ValueError, TypeError, AttributeError):
            und_data_dict_to_modify[volume_field] = 0 # Fallback: Volume = 0
            ohlcv_fallback_logger.warning(f"Missing/invalid '{volume_field}' (value: {current_volume_val}). Using 0 as fallback for VOLUME.")
        
        ohlcv_fallback_logger.debug(f"Final OHLCV for {self.current_processing_symbol}: "
                                   f"O:{und_data_dict_to_modify[ohlcv_fields_map['open']]:.2f}, "
                                   f"H:{und_data_dict_to_modify[ohlcv_fields_map['high']]:.2f}, "
                                   f"L:{und_data_dict_to_modify[ohlcv_fields_map['low']]:.2f}, "
                                   f"C:{und_data_dict_to_modify[ohlcv_fields_map['close']]:.2f}, "
                                   f"V:{und_data_dict_to_modify[ohlcv_fields_map['volume']]}")
        return und_data_dict_to_modify
    # --- END: Updated _ensure_ohlcv_fallbacks method ---

    def calculate_underlying_aggregate_metrics_v2_4(
        self,
        und_data_to_enrich: Dict[str, Any],
        df_chain_with_metrics: pd.DataFrame,
        df_strike_level_metrics: pd.DataFrame,
        current_market_time: time
    ) -> Dict[str, Any]:
        """
        Orchestrates the calculation of all underlying-level aggregate metrics.
        This method is called by `orchestrate_all_metric_calculations` (Step H)
        and is responsible for computing metrics that summarize the entire underlying's
        options market activity or dealer positioning.

        It sequentially calls specialized sub-methods to calculate:
        - Rolling Net Signed Flows for the underlying (summing per-contract rolling flows).
        - Net Customer Greek Flows (Delta, Gamma, Vega, Theta) for the underlying.
        - Specialized Flow Ratios (vflowratio, Granular PCRs).
        - GIB_OI_based_Und (Net Dealer Gamma from Open Interest).
        - td_gib_Und (Traded Dealer Gamma Imbalance).
        - HP_EOD_Und (End-of-Day Hedging Pressure).
        - VCI_0DTE_agg (Vanna Concentration Index for 0DTEs, aggregated).
        - Aggregates of key strike-level metrics (e.g., sum of MSPI, average of SSI/SAI).

        Each of these sub-calculations can be individually toggled on/off via specific keys
        within `self.metric_phases_activation_cfg` (e.g., "aggregate_rolling_flows",
        "dealer_positioning_metrics", etc.). This master orchestrator for underlying aggregates
        can also be globally toggled by "calculate_all_underlying_aggregates".

        It ensures that OHLCV fallbacks are applied first and that any pre-existing
        keys in `und_data_to_enrich` (like Tradier IVs) are preserved.

        Args:
            und_data_to_enrich (Dict[str, Any]): The underlying data dictionary to be enriched.
                                                 Starts as `self.current_und_data_api`.
            df_chain_with_metrics (pd.DataFrame): The fully processed options chain DataFrame.
            df_strike_level_metrics (pd.DataFrame): DataFrame with metrics aggregated at strike level.
            current_market_time (time): The current market time, used for time-sensitive
                                        calculations like HP_EOD.

        Returns:
            Dict[str, Any]: The `und_data_to_enrich` dictionary, now populated with all calculated
                            underlying aggregate metrics (respecting active toggles).
        """
        # Master Toggle Key for all underlying aggregate calculations: "calculate_all_underlying_aggregates"
        # Individual sub-phases also have their own toggles.
        if not self.metric_phases_activation_cfg.get("calculate_all_underlying_aggregates", True):
            self.logger.info(f"All Underlying Aggregate Metrics for {self.current_processing_symbol} SKIPPED by master config toggle.")
            # Ensure some essential keys are present if this whole block is skipped
            if 'symbol' not in und_data_to_enrich and self.current_processing_symbol:
                und_data_to_enrich['symbol'] = self.current_processing_symbol
            if 'underlying_metrics_calculation_timestamp' not in und_data_to_enrich and self.current_processing_time_dt:
                und_data_to_enrich['underlying_metrics_calculation_timestamp'] = self.current_processing_time_dt.isoformat()
            return und_data_to_enrich

        und_agg_logger = self.logger.getChild(f"CalcUndAggregates.{self.current_processing_symbol or 'UnknownSym'}")
        und_agg_logger.info(f"Starting calculation of all underlying-level aggregate metrics...")

        # IMPORTANT: Start with a copy of the input dictionary to preserve incoming keys (like Tradier IVs)
        # This `und_data_to_enrich` is `self.current_und_data_api` passed from `orchestrate_all_metric_calculations`
        enriched_data = und_data_to_enrich.copy() 
        
        # Log received Tradier IVs if present, to confirm pass-through
        # The key name for IV5 depends on target_dte, get it from config
        tradier_iv_target_dte_cfg = int(self._get_config_setting(['tradier_api_settings', 'iv_approximation_target_dte'], 5))
        tradier_iv5_key_check = f"tradier_iv{tradier_iv_target_dte_cfg}_approx_smv_avg"
        
        found_tradier_ivs_log_map_agg: Dict[str, Any] = {}
        for k_iv_check in [tradier_iv5_key_check, 'tradier_atm_call_smv_vol', 'tradier_atm_put_smv_vol', 'tradier_iv_approx_actual_dte']:
            if k_iv_check in enriched_data and pd.notna(enriched_data[k_iv_check]):
                found_tradier_ivs_log_map_agg[k_iv_check] = enriched_data[k_iv_check]
        
        if found_tradier_ivs_log_map_agg:
            und_agg_logger.info(f"Tradier IV metrics found in input to 'calculate_underlying_aggregate_metrics': {found_tradier_ivs_log_map_agg}")
        else:
            und_agg_logger.debug("No pre-fetched Tradier IV metrics found in input to 'calculate_underlying_aggregate_metrics'.")


        # --- Apply OHLCV Fallbacks First ---
        # This ensures that `enriched_data` has valid OHLCV fields before other aggregates
        # that might depend on them (like HP_EOD) are calculated.
        und_agg_logger.debug("   H.0 - Applying OHLCV Fallbacks (if needed) to enriched_data...")
        enriched_data = self._ensure_ohlcv_fallbacks(enriched_data) # Modifies enriched_data
        und_agg_logger.debug("   H.0 - OHLCV Fallbacks applied to enriched_data.")

        # --- Calculate various underlying aggregate metrics ---
        # (The following calls will add new keys to or update existing keys in `enriched_data`)

        # 1. Calculate Rolling Net Signed Flows for the Underlying (from per-contract rolling flows)
        #    This method sums up per-contract 'valuebs_Xm' and 'volmbs_Xm' from df_chain_with_metrics.
        und_agg_logger.debug("   H.1 - Calculating Rolling Net Signed Flows (Underlying)...")
        enriched_data = self.calculate_rolling_net_signed_flows_und_v2_4(df_chain_with_metrics, enriched_data)
        und_agg_logger.debug("   H.1 - Rolling Net Signed Flows (Underlying) complete.")

        # 2. Calculate Net Customer Greek Flows for the Underlying
        #    This method uses fields directly from self.current_und_data_api (which is the base for enriched_data).
        und_agg_logger.debug("   H.2 - Calculating Net Customer Greek Flows (Underlying)...")
        enriched_data = self.calculate_net_customer_greek_flows_und_v2_4(enriched_data)
        und_agg_logger.debug("   H.2 - Net Customer Greek Flows (Underlying) complete.")

        # 3. Calculate Specialized Flow Ratios for the Underlying
        #    This also uses fields directly from self.current_und_data_api.
        und_agg_logger.debug("   H.3 - Calculating Specialized Flow Ratios (Underlying)...")
        enriched_data = self.calculate_specialized_flow_ratios_und_v2_4(enriched_data)
        und_agg_logger.debug("   H.3 - Specialized Flow Ratios (Underlying) complete.")

        # 4. Calculate GIB_OI_based_Und (Net Dealer Gamma from Open Interest)
        #    Uses fields from self.current_und_data_api and self.current_und_price/multiplier.
        und_agg_logger.debug("   H.4 - Calculating GIB_OI_based_Und...")
        enriched_data = self.calculate_gib_oi_based_und_v2_4(enriched_data)
        und_agg_logger.debug("   H.4 - GIB_OI_based_Und complete.")

        # 5. Calculate td_gib_Und (Traded Dealer Gamma Imbalance)
        #    Uses fields from self.current_und_data_api and self.current_und_price/multiplier.
        und_agg_logger.debug("   H.5 - Calculating td_gib_Und...")
        enriched_data = self.calculate_td_gib_und_v2_4(enriched_data)
        und_agg_logger.debug("   H.5 - td_gib_Und complete.")

        # 6. Calculate HP_EOD_Und (End-of-Day Hedging Pressure)
        #    Depends on GIB_OI_based_Und (now in enriched_data), current market time,
        #    and price data from self.current_und_data_api / self.current_und_price.
        und_agg_logger.debug("   H.6 - Calculating HP_EOD_Und...")
        enriched_data = self.calculate_hp_eod_und_v2_4(enriched_data, current_market_time)
        und_agg_logger.debug("   H.6 - HP_EOD_Und complete.")

        # 7. Calculate VCI_0DTE_agg (Vanna Concentration Index - HHI style for 0DTE)
        #    Uses 'abs_vannaxoi_contract' column prepared in df_chain_with_metrics (Step C).
        und_agg_logger.debug("   H.7 - Calculating VCI_0DTE_agg (Underlying)...")
        output_key_vci_0dte_agg = 'vci_0dte_agg'
        enriched_data[output_key_vci_0dte_agg] = 0.0 # Initialize
        
        vci_input_cols_chain = ['dte_calc', 'abs_vannaxoi_contract', self.col_strike]
        if not df_chain_with_metrics.empty and \
        all(col in df_chain_with_metrics.columns for col in vci_input_cols_chain):
            
            df_0dte_for_vci_agg = df_chain_with_metrics[df_chain_with_metrics['dte_calc'] == 0].copy()
            if not df_0dte_for_vci_agg.empty:
                df_0dte_for_vci_agg['abs_vannaxoi_contract'] = pd.to_numeric(df_0dte_for_vci_agg['abs_vannaxoi_contract'], errors='coerce').fillna(0.0)
                df_0dte_for_vci_agg[self.col_strike] = pd.to_numeric(df_0dte_for_vci_agg[self.col_strike], errors='coerce')
                df_0dte_for_vci_agg.dropna(subset=[self.col_strike], inplace=True)

                if not df_0dte_for_vci_agg.empty:
                    abs_vannaxoi_sum_per_strike_0dte = df_0dte_for_vci_agg.groupby(self.col_strike)['abs_vannaxoi_contract'].sum()
                    total_abs_vannaxoi_underlying_0dte = abs_vannaxoi_sum_per_strike_0dte.sum()
                    if total_abs_vannaxoi_underlying_0dte > EPSILON:
                        strike_vanna_proportions_0dte = abs_vannaxoi_sum_per_strike_0dte / total_abs_vannaxoi_underlying_0dte
                        vci_0dte_agg_calculated_value = (strike_vanna_proportions_0dte**2).sum()
                        enriched_data[output_key_vci_0dte_agg] = float(vci_0dte_agg_calculated_value)
        # else:
            # und_agg_logger.debug(f"VCI_0DTE_agg: Required columns missing or chain empty for {self.current_processing_symbol}.")
        und_agg_logger.debug(f"   H.7 - VCI_0DTE_agg complete: {enriched_data[output_key_vci_0dte_agg]:.4f}")


        # 8. Aggregate key metrics from df_strike_level_metrics to underlying level
        und_agg_logger.debug("   H.8 - Aggregating strike-level metrics (MSPI sum, SSI/SAI avg, etc.)...")
        if not df_strike_level_metrics.empty:
            # Sum of GEX-like exposures (already calculated at strike level, now sum for underlying total)
            # These names (e.g., self.col_gxoi) now refer to columns in df_strike_level_metrics
            # which are sums of per-contract values. So, summing them again gives underlying total.
            gex_like_cols_to_sum_from_strike_df = [
                self.col_gxoi, # Total GXOI from all contracts
                self.col_sgxoi_calculated, # Total SGEXOI if calculated
            ] + [f"sdag_{m}" for m in self.enabled_sdag_methodologies] # Total for each SDAG method

            for col_s in gex_like_cols_to_sum_from_strike_df:
                if col_s in df_strike_level_metrics.columns:
                    enriched_data[f'{col_s}_und_sum'] = float(df_strike_level_metrics[col_s].sum())
            
            # Aggregate MSPI, SAI, SSI
            if 'mspi' in df_strike_level_metrics.columns:
                enriched_data['mspi_agg_und_sum'] = float(df_strike_level_metrics['mspi'].sum())
                enriched_data['mspi_agg_und_mean'] = float(df_strike_level_metrics['mspi'].mean())
            if 'sai' in df_strike_level_metrics.columns:
                enriched_data['sai_agg_und_avg'] = float(df_strike_level_metrics['sai'].mean())
            if 'ssi_agg' in df_strike_level_metrics.columns:
                enriched_data['ssi_agg_und_avg'] = float(df_strike_level_metrics['ssi_agg'].mean())

            if 'arfi_strike' in df_strike_level_metrics.columns:
                enriched_data['arfi_overall_und_avg'] = float(df_strike_level_metrics['arfi_strike'].mean())
            
            if 'nvp_strike' in df_strike_level_metrics.columns:
                enriched_data['nvp_total_und_sum'] = float(df_strike_level_metrics['nvp_strike'].sum())
            if 'nvp_vol_strike' in df_strike_level_metrics.columns:
                enriched_data['nvp_vol_total_und_sum'] = float(df_strike_level_metrics['nvp_vol_strike'].sum())
            
            # Aggregate 0DTE metrics from strike level (these were sums of per-contract values at strike)
            for col_0dte_s in ['vri_0dte', 'vfi_0dte', 'vvr_0dte']: 
                if col_0dte_s in df_strike_level_metrics.columns: # These columns in df_strike_level_metrics are sums from chain
                    enriched_data[f'{col_0dte_s}_und_sum'] = float(df_strike_level_metrics[col_0dte_s].sum())
                    # Store absolute sum for dynamic thresholding if tracked
                    if f'{col_0dte_s}_und_sum_abs' in self._get_config_setting("system_settings.metrics_for_dynamic_threshold_distribution_tracking", []):
                        enriched_data[f'{col_0dte_s}_und_sum_abs'] = float(df_strike_level_metrics[col_0dte_s].abs().sum())


            # TDPI at ATM for underlying
            if self.col_strike in df_strike_level_metrics.columns and 'tdpi' in df_strike_level_metrics.columns and self.current_und_price is not None and self.current_und_price > 0:
                # Find strike row closest to current_und_price
                # Ensure strike column is numeric for subtraction
                df_strike_level_metrics[self.col_strike] = pd.to_numeric(df_strike_level_metrics[self.col_strike], errors='coerce')
                df_valid_strikes_for_atm = df_strike_level_metrics.dropna(subset=[self.col_strike])
                if not df_valid_strikes_for_atm.empty:
                    atm_strike_row = df_valid_strikes_for_atm.iloc[(df_valid_strikes_for_atm[self.col_strike] - self.current_und_price).abs().argsort()[:1]]
                    if not atm_strike_row.empty:
                        enriched_data['tdpi_atm_strike_val'] = float(atm_strike_row['tdpi'].iloc[0])
                        enriched_data['tdpi_atm_strike_abs'] = float(abs(atm_strike_row['tdpi'].iloc[0]))
        else:
            und_agg_logger.warning(f"df_strike_level_metrics is empty for {self.current_processing_symbol}. Some underlying aggregates from strike data will be missing or zero.")
            # Initialize keys to prevent KeyErrors if other parts of system expect them
            keys_to_init_on_empty_strike_df = [
                'mspi_agg_und_sum', 'mspi_agg_und_mean', 'sai_agg_und_avg', 'ssi_agg_und_avg',
                'arfi_overall_und_avg', 'nvp_total_und_sum', 'nvp_vol_total_und_sum',
                'vri_0dte_und_sum', 'vfi_0dte_und_sum', 'vvr_0dte_und_sum',
                'vri_0dte_und_sum_abs', 'vfi_0dte_und_sum_abs', 'vvr_0dte_und_sum_abs', # Added _abs versions
                'tdpi_atm_strike_val', 'tdpi_atm_strike_abs'
            ] + [f'{col_s}_und_sum' for col_s in [self.col_gxoi, self.col_sgxoi_calculated] + [f"sdag_{m}" for m in self.enabled_sdag_methodologies]]

            for key_init_und in keys_to_init_on_empty_strike_df:
                if key_init_und not in enriched_data: enriched_data[key_init_und] = 0.0
        
        # Ensure absolute versions of key underlying metrics (for dynamic thresholding) exist
        # These are often derived from the already calculated underlying metrics.
        metrics_needing_abs_version = [
            'HP_EOD_Und', 'NetValueFlow_5m_Und', 'NetValueFlow_15m_Und', 
            'NetValueFlow_30m_Und', 'NetValueFlow_60m_Und',
            # Add other underlying metrics if their absolute sum/value is tracked.
            # 'vri_0dte_und_sum' (already has _abs version handled in its loop)
        ]
        for key_base in metrics_needing_abs_version:
            key_abs = f"{key_base}_abs"
            if key_abs in self._get_config_setting("system_settings.metrics_for_dynamic_threshold_distribution_tracking", []):
                if key_base in enriched_data and pd.notna(enriched_data[key_base]):
                    enriched_data[key_abs] = abs(float(enriched_data[key_base]))
                else: # Ensure the _abs key exists even if base is missing or NaN
                    enriched_data[key_abs] = 0.0

        # Ensure 'symbol' and timestamp are present
        if 'symbol' not in enriched_data or enriched_data.get('symbol') != self.current_processing_symbol:
            enriched_data['symbol'] = self.current_processing_symbol
        if 'underlying_metrics_calculation_timestamp' not in enriched_data and self.current_processing_time_dt:
            enriched_data['underlying_metrics_calculation_timestamp'] = self.current_processing_time_dt.isoformat()
        
        und_agg_logger.info(f"Underlying-level aggregate metric calculations complete for {self.current_processing_symbol}. Final keys: {len(enriched_data)}")
        return enriched_data
    
    # --- Sub-methods for calculate_underlying_aggregate_metrics_v2_4 ---
    def calculate_rolling_net_signed_flows_und_v2_4(
        self,
        df_chain_with_contract_flows: pd.DataFrame,
        und_data_to_enrich: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculates aggregate Rolling Net Signed Value and Volume Flows for the underlying.
        It sums up per-contract rolling flow data (e.g., 'valuebs_5m', 'volmbs_5m',
        which are net signed values) from the `df_chain_with_contract_flows`.

        The specific rolling intervals (e.g., "5m", "15m") are sourced from the
        `visualization_settings.mspi_visualizer.rolling_intervals` config.
        The base column names for value and volume (e.g., "valuebs_", "volmbs_") are
        from `strategy_settings.net_flow_cols_chain`.

        Output keys like 'NetValueFlow_5m_Und', 'NetVolFlow_5m_Und', and their
        absolute sum counterparts (e.g., 'NetValueFlow_5m_Und_abs') are added to
        `und_data_to_enrich`.

        This calculation can be toggled off via the "aggregate_rolling_flows" config setting.
        If skipped, the output keys are initialized to 0.0 in `und_data_to_enrich`.

        Args:
            df_chain_with_contract_flows (pd.DataFrame): Options chain DataFrame containing
                                                         per-contract rolling flow columns.
            und_data_to_enrich (Dict[str, Any]): Dictionary to add aggregated results to.

        Returns:
            Dict[str, Any]: The `und_data_to_enrich` dictionary populated with aggregate
                            rolling flow metrics.
        """
        # Toggle Key: "aggregate_rolling_flows"
        calc_name = "RollingFlows_Und_V2.4_MC"
        roll_flow_logger = self.logger.getChild(calc_name)

        # Initialize keys first, regardless of toggle, so they exist
        for interval in self.rolling_intervals_cfg:
            if f'NetValueFlow_{interval}_Und' not in und_data_to_enrich: und_data_to_enrich[f'NetValueFlow_{interval}_Und'] = 0.0
            if f'NetVolFlow_{interval}_Und' not in und_data_to_enrich: und_data_to_enrich[f'NetVolFlow_{interval}_Und'] = 0.0
            if f'NetValueFlow_{interval}_Und_abs' not in und_data_to_enrich: und_data_to_enrich[f'NetValueFlow_{interval}_Und_abs'] = 0.0
            if f'NetVolFlow_{interval}_Und_abs' not in und_data_to_enrich: und_data_to_enrich[f'NetVolFlow_{interval}_Und_abs'] = 0.0

        if not self.metric_phases_activation_cfg.get("aggregate_rolling_flows", True):
            roll_flow_logger.info(f"{calc_name} for {self.current_processing_symbol} SKIPPED by config.")
            return und_data_to_enrich

        # Prepare list of all rolling flow columns needed from the chain DataFrame
        all_rolling_flow_cols_needed_in_chain: List[str] = []
        for interval in self.rolling_intervals_cfg:
            # Construct column names based on config mapping (self.col_c_valuebs_base, self.col_c_volmbs_base)
            # e.g., valuebs_contract_5m, volmbs_contract_5m mapped from config strategy_settings.net_flow_cols_chain
            # The keys in net_flow_cols_chain are conceptual, values are actual API field names from chain
            # Example: config has "valuebs_5m_contract": "valuebs_5m"
            # So, self.col_c_valuebs_base would be "valuebs_" (from init)
            all_rolling_flow_cols_needed_in_chain.append(f"{self.col_c_valuebs_base}{interval}")
            all_rolling_flow_cols_needed_in_chain.append(f"{self.col_c_volmbs_base}{interval}")
            
        df_flows_prepared, cols_ok = self._ensure_columns_internal(
            df_chain_with_contract_flows, 
            all_rolling_flow_cols_needed_in_chain, # Use the dynamically built list
            calc_name + "_ChainInputCheck_Rolling", 
            fill_numeric_with=0.0 # Missing rolling flow data per contract defaults to 0
        )

        if not cols_ok:
            roll_flow_logger.warning(f"{calc_name}: One or more required rolling flow columns missing or invalid in chain data for {self.current_processing_symbol}. Results may be inaccurate.")
            # Proceeding with what's available, defaults are 0.0

        for interval in self.rolling_intervals_cfg: # From config, e.g., ["5m", "15m", "30m", "60m"]
            und_data_to_enrich[f'NetValueFlow_{interval}_Und'] = 0.0
            und_data_to_enrich[f'NetVolFlow_{interval}_Und'] = 0.0
            und_data_to_enrich[f'NetValueFlow_{interval}_Und_abs'] = 0.0
            und_data_to_enrich[f'NetVolFlow_{interval}_Und_abs'] = 0.0
        if df_chain_with_contract_flows.empty:
            roll_flow_logger.warning(f"{calc_name}: Input 'df_chain_with_contract_flows' is empty for {self.current_processing_symbol}. Rolling flows will remain zero.")
            return und_data_to_enrich
        all_rolling_flow_cols_needed_in_chain: List[str] = []
        for interval in self.rolling_intervals_cfg:
            all_rolling_flow_cols_needed_in_chain.append(f"{self.col_c_valuebs_base}{interval}")
            all_rolling_flow_cols_needed_in_chain.append(f"{self.col_c_volmbs_base}{interval}")
        df_flows_prepared, cols_ok = self._ensure_columns_internal(
            df_chain_with_contract_flows, 
            all_rolling_flow_cols_needed_in_chain, 
            calc_name + "_ChainInputCheck_Rolling", 
            fill_numeric_with=0.0 
        )
        if not cols_ok:
            roll_flow_logger.warning(f"{calc_name}: One or more required rolling flow columns missing or invalid in chain data for {self.current_processing_symbol}. Results may be inaccurate.")
        for interval in self.rolling_intervals_cfg:
            actual_col_val_bs_interval = f"{self.col_c_valuebs_base}{interval}"
            actual_col_vol_bs_interval = f"{self.col_c_volmbs_base}{interval}"
            if actual_col_val_bs_interval in df_flows_prepared.columns:
                value_series = pd.to_numeric(df_flows_prepared[actual_col_val_bs_interval], errors='coerce').fillna(0.0)
                sum_val = float(value_series.sum())
                und_data_to_enrich[f'NetValueFlow_{interval}_Und'] = sum_val
                und_data_to_enrich[f'NetValueFlow_{interval}_Und_abs'] = float(value_series.abs().sum())
            if actual_col_vol_bs_interval in df_flows_prepared.columns:
                volume_series = pd.to_numeric(df_flows_prepared[actual_col_vol_bs_interval], errors='coerce').fillna(0.0)
                sum_vol = float(volume_series.sum())
                und_data_to_enrich[f'NetVolFlow_{interval}_Und'] = sum_vol
                und_data_to_enrich[f'NetVolFlow_{interval}_Und_abs'] = float(volume_series.abs().sum())
        return und_data_to_enrich

    def calculate_net_customer_greek_flows_und_v2_4(self, und_data_to_enrich: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates the Net Customer Greek Flows (Delta, Gamma, Vega, Theta) for the underlying security.
        These metrics represent the net change in customers' aggregate Greek exposure due to
        their trading activity for the day.

        The calculation uses underlying-level aggregate sum of Greek_buy minus Greek_sell data,
        sourced from `self.current_und_data_api` (originally from the get_und API endpoint).
        For example, Net Customer Delta Flow = (sum of delta bought by customers) - (sum of delta sold by customers).
        A positive value indicates customers, on net, increased their exposure to that Greek,
        implying dealers absorbed the opposite exposure.

        Column names for the source Greek flows (e.g., 'deltas_buy_und', 'gammas_sell_und')
        are mapped from `strategy_settings.greeks_from_und` in the configuration.
        Output keys (e.g., 'NetCustDeltaFlow_Und', 'NetCustGammaFlow_Und') are added to
        `und_data_to_enrich`.

        This calculation can be toggled off via the "aggregate_net_cust_greek_flows" config setting.
        If skipped, the output keys are initialized to 0.0 in `und_data_to_enrich`.

        Args:
            und_data_to_enrich (Dict[str, Any]): The underlying data dictionary to be enriched.
                                                 This method primarily reads from `self.current_und_data_api`.
        Returns:
            Dict[str, Any]: The `und_data_to_enrich` dictionary populated with net customer
                            Greek flow metrics.
        """
        # Toggle Key in config: "aggregate_net_cust_greek_flows"
        calc_name = "NetCustGreekFlows_Und_V2.4_MC"
        net_greek_logger = self.logger.getChild(calc_name)

        # Define output keys and initialize them in und_data_to_enrich
        output_keys_map = {
            'NetCustDeltaFlow_Und': (self.col_u_deltas_buy, self.col_u_deltas_sell),
            'NetCustGammaFlow_Und': (self.col_u_gammas_buy, self.col_u_gammas_sell),
            'NetCustVegaFlow_Und':  (self.col_u_vegas_buy, self.col_u_vegas_sell),
            'NetCustThetaFlow_Und': (self.col_u_thetas_buy, self.col_u_thetas_sell)
        }
        for out_key in output_keys_map.keys():
            if out_key not in und_data_to_enrich:
                und_data_to_enrich[out_key] = 0.0
            # Also initialize _abs versions if they are tracked for dynamic thresholds
            abs_key = f"{out_key}_abs"
            if abs_key in self._get_config_setting("system_settings.metrics_for_dynamic_threshold_distribution_tracking", []) and \
               abs_key not in und_data_to_enrich:
                und_data_to_enrich[abs_key] = 0.0

        if not self.metric_phases_activation_cfg.get("aggregate_net_cust_greek_flows", True):
            net_greek_logger.info(f"{calc_name} for {self.current_processing_symbol} SKIPPED by config.")
            return und_data_to_enrich

        source_und_data_local = self.current_und_data_api # Use the instance variable
        if source_und_data_local is None:
        # --- End of Correction ---
            net_greek_logger.error(f"{calc_name}: 'self.current_und_data_api' is None. Cannot calculate Net Customer Greek Flows for {self.current_processing_symbol}.")
            return und_data_to_enrich

        for out_key, (buy_col_key, sell_col_key) in output_keys_map.items(): # Ensure output_keys_map is defined correctly earlier in your method
            # --- Start of Correction ---
            raw_buy_val = source_und_data_local.get(buy_col_key)
            raw_sell_val = source_und_data_local.get(sell_col_key)
            # --- End of Correction ---

            # Convert to numeric, default to 0.0 if None or conversion fails
            final_buy_val = 0.0
            if raw_buy_val is not None:
                try: final_buy_val = float(raw_buy_val)
                except (ValueError, TypeError): net_greek_logger.warning(f"Invalid value for {buy_col_key}: {raw_buy_val}. Using 0.0.")
            
            final_sell_val = 0.0
            if raw_sell_val is not None:
                try: final_sell_val = float(raw_sell_val)
                except (ValueError, TypeError): net_greek_logger.warning(f"Invalid value for {sell_col_key}: {raw_sell_val}. Using 0.0.")
            
            und_data_to_enrich[out_key] = final_buy_val - final_sell_val
            # net_greek_logger.debug(f"  {self.current_processing_symbol} - {out_key}: {und_data_to_enrich[out_key]:.3e} (Buy: {final_buy_val:.3e}, Sell: {final_sell_val:.3e})")
        
        # net_greek_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}.")
        return und_data_to_enrich
    
    def calculate_specialized_flow_ratios_und_v2_4(self, und_data_to_enrich: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates Specialized Flow Ratios for the underlying security, providing nuanced
        insights into customer sentiment and volatility appetite.

        Metrics calculated:
        - 'vflowratio_calc_mcal': Ratio of customer options volume effectively selling Vega
          (e.g., selling calls + selling puts) to volume buying Vega. A high ratio (>1)
          suggests customers are net sellers of volatility.
        - Granular Put/Call Ratios (PCRs):
            - 'PCR_CustBuy_Vol_calc_mcal': (Puts bought by customers) / (Calls bought by customers) by volume.
            - 'PCR_CustSell_Vol_calc_mcal': (Puts sold by customers) / (Calls sold by customers) by volume.
            - (Similar '_Val_' versions for value-based PCRs).
          These provide a more detailed sentiment picture than aggregate PCRs.

        The calculations use underlying-level aggregate buy/sell volume and value data for
        calls and puts, sourced from `self.current_und_data_api` (originally from get_und).
        Column names are mapped from `strategy_settings.greeks_from_und`.
        The API-provided 'vflowratio' (mapped by `self.col_u_vflowratio`) is also preserved
        or defaulted to the calculated version if missing.

        This calculation can be toggled off via the "aggregate_specialized_flow_ratios" config setting.
        If skipped, the output keys are initialized to 0.0 (or 1.0 for ratios) in `und_data_to_enrich`.

        Args:
            und_data_to_enrich (Dict[str, Any]): The underlying data dictionary to be enriched.
                                                 Reads from `self.current_und_data_api`.
        Returns:
            Dict[str, Any]: The `und_data_to_enrich` dictionary populated with specialized
                            flow ratio metrics.
        """
        # Toggle Key in config: "aggregate_specialized_flow_ratios"
        calc_name = "SpecFlowRatios_Und_V2.4_MC"
        spec_ratio_logger = self.logger.getChild(calc_name)

        # Define and initialize output keys
        ratio_output_keys = [
            'vflowratio_calc_mcal', self.col_u_vflowratio, # self.col_u_vflowratio comes from config
            'PCR_CustBuy_Val_calc_mcal', 'PCR_CustSell_Val_calc_mcal',
            'PCR_CustBuy_Vol_calc_mcal', 'PCR_CustSell_Vol_calc_mcal'
        ]
        for r_key in ratio_output_keys:
            if r_key not in und_data_to_enrich: # Avoid overwriting if API already provided some
                und_data_to_enrich[r_key] = 1.0 if "ratio" in r_key.lower() else 0.0 # Default for ratios often 1.0 (balance)

        if self.current_und_data_api is None: # Corrected: Use the instance variable
            spec_ratio_logger.error(f"{calc_name}: 'self.current_und_data_api' is None. Cannot calculate ratios for {self.current_processing_symbol}.")
            return und_data_to_enrich
        
        # This function is defined inside calculate_specialized_flow_ratios_und_v2_4
        def get_float_from_src_data(key: str, default_val: float = 0.0) -> float:
            val = self.current_und_data_api.get(key) # Make sure this uses self.current_und_data_api
            if val is None: return default_val
            try: return float(val)
            except (ValueError, TypeError):
                # spec_ratio_logger.debug(f"Invalid value for '{key}': {val}. Using default {default_val}.")
                return default_val
        
        def calculate_safe_ratio(numerator: float, denominator: float, default_for_zero_den: float = 1.0, high_val_for_inf: float = 1000.0) -> float:
            if abs(denominator) > EPSILON: return numerator / denominator
            elif abs(numerator) > EPSILON: return high_val_for_inf # Numerator non-zero, denominator zero
            return default_for_zero_den # Both zero or numerator zero, implying balance or no activity

        # vflowratio calculation (Customer Vol Selling / Vol Buying)
        # Vol Selling ~ Customers selling calls + customers selling puts
        # Vol Buying  ~ Customers buying calls + customers buying puts
        volm_cust_sell_calls = get_float_from_src_data(self.col_u_volm_call_sell)
        volm_cust_sell_puts = get_float_from_src_data(self.col_u_volm_put_sell)
        total_cust_vol_selling_proxy = volm_cust_sell_calls + volm_cust_sell_puts

        volm_cust_buy_calls = get_float_from_src_data(self.col_u_volm_call_buy)
        volm_cust_buy_puts = get_float_from_src_data(self.col_u_volm_put_buy)
        total_cust_vol_buying_proxy = volm_cust_buy_calls + volm_cust_buy_puts
        
        und_data_to_enrich['vflowratio_calc_mcal'] = calculate_safe_ratio(total_cust_vol_selling_proxy, total_cust_vol_buying_proxy, default_for_zero_den=1.0)
        
        # Store API provided vflowratio if exists, else use calculated
        # self.col_u_vflowratio is the key for the API field (e.g. "vflowratio")
        if self.col_u_vflowratio in self.current_und_data_api and self.current_und_data_api.get(self.col_u_vflowratio) is not None: # Corrected
            und_data_to_enrich[self.col_u_vflowratio] = get_float_from_src_data(self.col_u_vflowratio) # get_float_from_src_data also needs to use self.current_und_data_api as shown before
        else: # API didn't provide it or it was None
            und_data_to_enrich[self.col_u_vflowratio] = und_data_to_enrich['vflowratio_calc_mcal']
            # spec_ratio_logger.debug(f"API field '{self.col_u_vflowratio}' not found or None. Using calculated vflowratio.")

        # Granular PCRs (Value based)
        value_cust_buy_puts = get_float_from_src_data(self.col_u_value_put_buy)
        value_cust_buy_calls = get_float_from_src_data(self.col_u_value_call_buy)
        und_data_to_enrich['PCR_CustBuy_Val_calc_mcal'] = calculate_safe_ratio(value_cust_buy_puts, value_cust_buy_calls)

        value_cust_sell_puts = get_float_from_src_data(self.col_u_value_put_sell)
        value_cust_sell_calls = get_float_from_src_data(self.col_u_value_call_sell)
        und_data_to_enrich['PCR_CustSell_Val_calc_mcal'] = calculate_safe_ratio(value_cust_sell_puts, value_cust_sell_calls)

        # Granular PCRs (Volume based)
        und_data_to_enrich['PCR_CustBuy_Vol_calc_mcal'] = calculate_safe_ratio(volm_cust_buy_puts, volm_cust_buy_calls)
        und_data_to_enrich['PCR_CustSell_Vol_calc_mcal'] = calculate_safe_ratio(volm_cust_sell_puts, volm_cust_sell_calls)
        
        # spec_ratio_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}.")
        # spec_ratio_logger.debug(f"  vflowratio_calc_mcal: {und_data_to_enrich['vflowratio_calc_mcal']:.3f}, API vflowratio: {und_data_to_enrich.get(self.col_u_vflowratio):.3f}")
        # spec_ratio_logger.debug(f"  PCR_CustBuy_Vol: {und_data_to_enrich['PCR_CustBuy_Vol_calc_mcal']:.3f}, PCR_CustSell_Vol: {und_data_to_enrich['PCR_CustSell_Vol_calc_mcal']:.3f}")
        return und_data_to_enrich
    
    def calculate_gib_oi_based_und_v2_4(self, und_data_to_enrich: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates the Gamma Imbalance from Open Interest (GIB_OI_based_Und) for the underlying.
        This V2.4 metric quantifies the net aggregate gamma exposure held by market makers (dealers)
        stemming from all outstanding Open Interest. It's a critical indicator of systemic
        dealer gamma posture.

        The formula used is: (Und_Call_GXOI - Und_Put_GXOI) * Underlying_Price * Contract_Multiplier.
        - A negative GIB_OI_based indicates dealers are net short gamma, implying their hedging
          will be pro-cyclical (amplifying market moves).
        - A positive GIB_OI_based suggests dealers are net long gamma, leading to counter-cyclical
          hedging (dampening volatility).
        The inputs (call_gxoi, put_gxoi, price, multiplier) are sourced from
        `self.current_und_data_api` (originally from get_und API).

        This calculation can be toggled off via the "aggregate_gib_oi" config setting,
        or if its parent phase "dealer_positioning_metrics" is disabled. If skipped,
        'GIB_OI_based_Und' is initialized to 0.0 in `und_data_to_enrich`.

        Args:
            und_data_to_enrich (Dict[str, Any]): The underlying data dictionary to be enriched.
                                                 Reads from `self.current_und_data_api`.
        Returns:
            Dict[str, Any]: The `und_data_to_enrich` dictionary populated with 'GIB_OI_based_Und'.
        """
        # Toggle Key: "aggregate_gib_oi"
        # Part of phase: "dealer_positioning_metrics"
        output_key = 'GIB_OI_based_Und'
        if output_key not in und_data_to_enrich: # Initialize if key doesn't exist
            und_data_to_enrich[output_key] = 0.0

        if not self.metric_phases_activation_cfg.get("aggregate_gib_oi", True) and \
           not self.metric_phases_activation_cfg.get("dealer_positioning_metrics", True):
            self.logger.info(f"GIB OI Based Und calculation for {self.current_processing_symbol} SKIPPED by config.")
            return und_data_to_enrich
        
        calc_name = "GIB_OI_Und_V2.4_MC"
        gib_logger = self.logger.getChild(calc_name)
        # gib_logger.debug(f"Calculating {calc_name} for {self.current_processing_symbol}...")
        
        output_key_gib = 'GIB_OI_based_Und'
        und_data_to_enrich[output_key_gib] = 0.0 # Initialize

        source_und_data = self.current_und_data_api 
        if source_und_data is None:
            gib_logger.error(f"{calc_name}: 'self.current_und_data_api' is None. '{output_key_gib}' will be zero.")
            return und_data_to_enrich

        # Fetch values using configured column names
        # self.col_u_call_gxoi and self.col_u_put_gxoi are API field names for these sums from get_und
        call_gxoi_val = float(source_und_data.get(self.col_u_call_gxoi, 0.0))
        put_gxoi_val = float(source_und_data.get(self.col_u_put_gxoi, 0.0))
        
        # Current underlying price and multiplier from instance variables (set by orchestrator)
        price_val = self.current_und_price
        multiplier_val = self.current_und_multiplier 

        if price_val is None or price_val <= 0 or multiplier_val is None or multiplier_val <= 0:
            gib_logger.warning(f"{calc_name}: Invalid price ({price_val}) or multiplier ({multiplier_val}) for {self.current_processing_symbol}. '{output_key_gib}' remains zero.")
            return und_data_to_enrich
            
        # Formula application based on V2.4 Guide interpretation
        # Positive GIB = Dealers Net Long Gamma; Negative GIB = Dealers Net Short Gamma
        gib_oi_based_value = (call_gxoi_val - put_gxoi_val) * price_val * multiplier_val
        und_data_to_enrich[output_key_gib] = gib_oi_based_value
        
        # gib_logger.info(f"{calc_name} for {self.current_processing_symbol}: {output_key_gib} = {gib_oi_based_value:.3e} "
        #                 f"(CallGXOI_Und: {call_gxoi_val:.3e}, PutGXOI_Und: {put_gxoi_val:.3e}, Px: {price_val}, Mult: {multiplier_val})")
        return und_data_to_enrich
    
    def calculate_td_gib_und_v2_4(self, und_data_to_enrich: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates the Traded Dealer Gamma Imbalance (td_gib_Und) for the underlying.
        This V2.4 metric measures the net gamma units that dealers have effectively
        bought or sold as a result of the current day's customer options trading activity.
        It isolates the dynamic change in the aggregate dealer gamma position due to flow,
        distinct from their static gamma exposure from Open Interest (GIB_OI_based_Und).

        - A positive 'td_gib_Und' indicates dealers, on net, bought gamma from customers
          today (their gamma position became more positive/less negative).
        - A negative 'td_gib_Und' indicates dealers, on net, sold gamma to customers
          today (their gamma position became more negative/less positive).

        The calculation uses underlying-level aggregate sums of gamma from calls/puts
        bought and sold by customers (e.g., 'gammas_call_buy_und', 'gammas_put_sell_und'),
        sourced from `self.current_und_data_api` (originally from get_und API).
        It produces both raw gamma units ('td_gib_Und') and a dollarized version
        ('td_gib_dollar_Und').

        This calculation can be toggled off via the "aggregate_td_gib" config setting,
        or if its parent phase "dealer_positioning_metrics" is disabled. If skipped,
        'td_gib_Und' and 'td_gib_dollar_Und' are initialized to 0.0 in `und_data_to_enrich`.

        Args:
            und_data_to_enrich (Dict[str, Any]): The underlying data dictionary to be enriched.
                                                 Reads from `self.current_und_data_api`.
        Returns:
            Dict[str, Any]: The `und_data_to_enrich` dictionary populated with 'td_gib_Und'
                            and 'td_gib_dollar_Und'.
        """
        # Toggle Key: "aggregate_td_gib"
        # Part of phase: "dealer_positioning_metrics"
        calc_name = "td_gib_Und_V2.4_MC"
        tdgib_logger = self.logger.getChild(calc_name)

        output_key_units = 'td_gib_Und'
        output_key_dollar = 'td_gib_dollar_Und'
        if output_key_units not in und_data_to_enrich: und_data_to_enrich[output_key_units] = 0.0
        if output_key_dollar not in und_data_to_enrich: und_data_to_enrich[output_key_dollar] = 0.0

        if not self.metric_phases_activation_cfg.get("aggregate_td_gib", True) and \
           not self.metric_phases_activation_cfg.get("dealer_positioning_metrics", True):
            tdgib_logger.info(f"{calc_name} for {self.current_processing_symbol} SKIPPED by config.")
            return und_data_to_enrich

        source_und_data = self.current_und_data_api
        if source_und_data is None:
            tdgib_logger.error(f"{calc_name}: 'self.current_und_data_api' is None. td_gib metrics will be zero for {self.current_processing_symbol}.")
            return und_data_to_enrich

        # Fetch values using configured column names for granular gamma flows from get_und
        # Gamma from options CUSTOMERS SOLD (so dealers BOUGHT this gamma)
        g_call_sell_und = float(source_und_data.get(self.col_u_gammas_call_sell, 0.0))
        g_put_sell_und = float(source_und_data.get(self.col_u_gammas_put_sell, 0.0))
        total_gamma_dealer_bought_flow_units = g_call_sell_und + g_put_sell_und

        # Gamma from options CUSTOMERS BOUGHT (so dealers SOLD this gamma)
        g_call_buy_und = float(source_und_data.get(self.col_u_gammas_call_buy, 0.0))
        g_put_buy_und = float(source_und_data.get(self.col_u_gammas_put_buy, 0.0))
        total_gamma_dealer_sold_flow_units = g_call_buy_und + g_put_buy_und
        
        # Net gamma units ADDED to dealer book from today's customer flow
        td_gib_raw_gamma_units = total_gamma_dealer_bought_flow_units - total_gamma_dealer_sold_flow_units
        und_data_to_enrich[output_key_units] = td_gib_raw_gamma_units # Corrected: Use output_key_units
        
        # Dollarize
        price_val = self.current_und_price
        multiplier_val = self.current_und_multiplier

        if price_val is not None and price_val > 0 and multiplier_val is not None and multiplier_val > 0:
            und_data_to_enrich[output_key_dollar] = td_gib_raw_gamma_units * price_val * multiplier_val # Corrected: Use output_key_dollar
        # else:
            # tdgib_logger.warning(f"{calc_name}: Invalid price ({price_val}) or multiplier ({multiplier_val}) for {self.current_processing_symbol}. '{output_key_td_gib_dollar}' remains zero.")
        
        # tdgib_logger.info(f"{calc_name} for {self.current_processing_symbol}: Units={td_gib_raw_gamma_units:.3e}, Dollar={und_data_to_enrich[output_key_td_gib_dollar]:.3e}")
        return und_data_to_enrich
    
    def calculate_hp_eod_und_v2_4(
        self,
        und_data_to_enrich: Dict[str, Any],
        current_market_time: time
    ) -> Dict[str, Any]:
        """
        Calculates the End-of-Day Hedging Pressure (HP_EOD_Und) for the underlying.
        This V2.4 metric quantifies the expected dollar volume of market maker (dealer)
        delta hedging activity anticipated to be concentrated near the market close.

        It is calculated after a configured 'EOD trigger time' and depends on:
        1.  GIB_OI_based_Und: The dealers' net aggregate gamma exposure from Open Interest
            (must be pre-calculated and present in `und_data_to_enrich`).
        2.  Intraday Price Movement: The change in the underlying's price from a
            configured reference point (e.g., day's open, specified by
            `market_regime_engine_settings.eod_reference_price_field`) up to the
            current snapshot price (`self.current_und_price` at trigger time).

        The sign convention is crucial:
        - Negative HP_EOD_Und implies expected net dealer BUYING pressure.
        - Positive HP_EOD_Und implies expected net dealer SELLING pressure.

        This calculation can be toggled off via the "aggregate_hp_eod" config setting,
        or if its parent phase "dealer_positioning_metrics" is disabled. If skipped,
        'HP_EOD_Und' and 'HP_EOD_Und_abs' are initialized to 0.0 in `und_data_to_enrich`.

        Args:
            und_data_to_enrich (Dict[str, Any]): The underlying data dictionary to be enriched.
                                                 Must contain 'GIB_OI_based_Und'. Reads price
                                                 data from `self.current_und_data_api` and
                                                 `self.current_und_price`.
            current_market_time (time): The current market time, used to check against
                                        the EOD trigger time.
        Returns:
            Dict[str, Any]: The `und_data_to_enrich` dictionary populated with 'HP_EOD_Und'
                            and its absolute value if tracked.
        """
        # Toggle Key: "aggregate_hp_eod"
        # Part of phase: "dealer_positioning_metrics"
        calc_name = "HP_EOD_Und_V2.4_MC_Refined"
        hpeod_logger = self.logger.getChild(calc_name)

        # Get EOD trigger time and reference price field from MRE settings in config
        # self.mre_settings_cfg should be initialized from the main config object
        # and self.mre_time_defs_cfg from that.
        eod_calc_trigger_time_str = self.mre_time_defs_cfg.get("eod_pressure_calc_time", "15:30:00") # From init
        
        # The field name for the reference price (e.g., day's open) for HP_EOD calculation.
        # This key should exist in self.current_und_data_api (i.e., it was fetched by get_und).
        # The MRE config's 'eod_reference_price_field' tells us which conceptual field to use.
        # We then map this conceptual name to the actual API field name via greeks_from_und.
        conceptual_ref_price_field_key = self.mre_settings_cfg.get("eod_reference_price_field", "day_open_price_und")
        # self.col_u_day_open_price was initialized based on config:
        # greeks_from_und: {"day_open_price_und": "actual_api_field_for_day_open"}
        # So, if conceptual_ref_price_field_key is "day_open_price_und",
        # actual_api_field_for_ref_price = self.col_u_day_open_price.
        # Let's ensure we use the correctly mapped API field name.
        
        # This logic assumes that the value of "eod_reference_price_field" in mre_settings_cfg
        # is a *conceptual key* that exists within the "strategy_settings.greeks_from_und" mapping.
        # For example, if mre_settings_cfg.eod_reference_price_field = "day_open_price_und",
        # and strategy_settings.greeks_from_und.day_open_price_und = "day_open_price" (actual API field),
        # then we need to use "day_open_price" to look up in self.current_und_data_api.

        actual_api_field_for_ref_price = self._get_config_setting(
            ["strategy_settings", "greeks_from_und", conceptual_ref_price_field_key],
            default=conceptual_ref_price_field_key # Fallback to using the conceptual key directly if not mapped
        )
        # hpeod_logger.debug(f"{calc_name}: Conceptual ref price field '{conceptual_ref_price_field_key}' maps to actual API field '{actual_api_field_for_ref_price}' for HP_EOD.")


        try:
            eod_trigger_time_obj = time.fromisoformat(eod_calc_trigger_time_str)
        except ValueError:
            hpeod_logger.error(f"{calc_name}: Invalid 'eod_pressure_calc_time' format ('{eod_calc_trigger_time_str}') in config. HP_EOD not calculated for {self.current_processing_symbol}.")
            return und_data_to_enrich

        if not isinstance(current_market_time, time):
            hpeod_logger.error(f"{calc_name}: Invalid 'current_market_time' (type: {type(current_market_time)}). HP_EOD not calculated for {self.current_processing_symbol}.")
            return und_data_to_enrich
            
        if current_market_time < eod_trigger_time_obj:
            # hpeod_logger.debug(f"{calc_name}: Too early for HP_EOD ({current_market_time.strftime('%H:%M:%S')} vs trigger {eod_trigger_time_obj.strftime('%H:%M:%S')}) for {self.current_processing_symbol}.")
            return und_data_to_enrich # Output remains 0.0
        # else:
            # hpeod_logger.debug(f"{calc_name}: Current time is at or after EOD trigger time for {self.current_processing_symbol}. Proceeding with HP_EOD calculation.")

        # GIB_OI_based_Und ($ value change per 1 point underlying move due to OI gamma)
        # This MUST have been calculated earlier by calculate_gib_oi_based_und_v2_4 and be present in und_data_to_enrich
        gib_dollar_gamma_per_point_raw = und_data_to_enrich.get('GIB_OI_based_Und') 
        if gib_dollar_gamma_per_point_raw is None or pd.isna(gib_dollar_gamma_per_point_raw):
            hpeod_logger.error(f"{calc_name}: 'GIB_OI_based_Und' not found or NaN in enriched data for {self.current_processing_symbol}. Cannot calculate HP_EOD.")
            return und_data_to_enrich # HP_EOD_Und remains 0.0
        gib_dollar_gamma_per_point = float(gib_dollar_gamma_per_point_raw)

        # Current underlying price at trigger time (from instance variable set by orchestrator)
        price_at_trigger_time = self.current_und_price 
        
        # Reference price (e.g., day's open) sourced from self.current_und_data_api using the mapped field name
        reference_price_start_of_day_val = None
        if self.current_und_data_api: # This holds the raw get_und data
            raw_ref_price = self.current_und_data_api.get(actual_api_field_for_ref_price) # Use the mapped actual API field name
            if raw_ref_price is not None:
                try: 
                    reference_price_start_of_day_val = float(raw_ref_price)
                except (ValueError, TypeError):
                    hpeod_logger.warning(f"{calc_name}: Could not convert reference price from field '{actual_api_field_for_ref_price}' (value: {raw_ref_price}) to float for {self.current_processing_symbol}.")
            # else:
                # hpeod_logger.warning(f"{calc_name}: Reference price field '{actual_api_field_for_ref_price}' not found in self.current_und_data_api for {self.current_processing_symbol}.")
        # else:
            # hpeod_logger.error(f"{calc_name}: self.current_und_data_api is None. Cannot get reference price for {self.current_processing_symbol}.")


        if price_at_trigger_time is None or price_at_trigger_time <= 0 or \
           reference_price_start_of_day_val is None or reference_price_start_of_day_val <= 0:
            hpeod_logger.warning(f"{calc_name}: Invalid prices for HP_EOD for {self.current_processing_symbol} "
                                 f"(TriggerPx: {price_at_trigger_time}, "
                                 f"RefPxField(actual API): '{actual_api_field_for_ref_price}', RefPxVal: {reference_price_start_of_day_val}). "
                                 f"HP_EOD set to 0.")
            return und_data_to_enrich # HP_EOD_Und remains 0.0
        
        price_difference = price_at_trigger_time - reference_price_start_of_day_val
        
        # Formula: HP_EOD ($) = GIB_OI_based_Und * Price_Difference
        # Sign convention:
        # - GIB_OI_based_Und: Negative means dealers short gamma. Positive means dealers long gamma.
        # - HP_EOD_Und: Negative value means expected dealer BUYING. Positive value means expected dealer SELLING.
        # If GIB < 0 (short gamma) and Price_Difference > 0 (rally): HP_EOD = (-) * (+) = Negative => Buying. Correct.
        # If GIB < 0 (short gamma) and Price_Difference < 0 (selloff): HP_EOD = (-) * (-) = Positive => Selling. Correct.
        # If GIB > 0 (long gamma) and Price_Difference > 0 (rally): HP_EOD = (+) * (+) = Positive => Selling. Correct.
        # If GIB > 0 (long gamma) and Price_Difference < 0 (selloff): HP_EOD = (+) * (-) = Negative => Buying. Correct.
        # The direct multiplication yields the correct directional implication for dealer hedging.
        hp_eod_value = gib_dollar_gamma_per_point * price_difference
        
        und_data_to_enrich[output_key_hp_eod] = hp_eod_value
        # Store the absolute value as well if it's tracked for dynamic thresholds
        if f"{output_key_hp_eod}_abs" in self._get_config_setting("system_settings.metrics_for_dynamic_threshold_distribution_tracking", []):
            und_data_to_enrich[f"{output_key_hp_eod}_abs"] = abs(hp_eod_value)
        
        hpeod_logger.info(f"{calc_name} calculated for {self.current_processing_symbol}: {output_key_hp_eod} = {hp_eod_value:.3e} "
                          f"(GIB_OI_Und: {gib_dollar_gamma_per_point:.3e}, PxAtTrigger: {price_at_trigger_time:.2f}, "
                          f"RefPxKey='{actual_api_field_for_ref_price}', RefPxVal={reference_price_start_of_day_val:.2f}, PxDiff: {price_difference:.2f})")
        return und_data_to_enrich

# --- Test Block (already well-defined in your provided file, will be kept for standalone testing) ---
# (The __main__ block from your provided metrics_calculator.py would go here,
#  updated to instantiate MetricsCalculatorV2_4 with a mock ConfigManager
#  that provides the necessary strategy_settings, data_processor_settings, etc.)

if __name__ == '__main__': # pragma: no cover
    # This block is for direct testing of MetricsCalculatorV2_4.
    # It requires setting up a mock ConfigManager and sample data.

    if not logging.getLogger("EOTS_SystemRunnerV2.4").handlers and not logging.getLogger(__name__).handlers :
        test_handler = logging.StreamHandler(sys.stdout) 
        test_formatter = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s - L%(lineno)d - %(message)s')
        test_handler.setFormatter(test_formatter)
        logging.getLogger().addHandler(test_handler); logging.getLogger().setLevel(logging.DEBUG)

    main_test_logger = logging.getLogger(f"{__name__}_TestMain")
    main_test_logger.info("--- Starting MetricsCalculatorV2_4 Standalone Test (Phase 5 Structure) ---")

    # Simplified Mock ConfigManager for testing MetricsCalculator
    class MockConfigManagerForMetricsTest:
        _config_data: Dict[str, Any]
        
        def __init__(self):
            # Populate with enough config from your actual config_v2_4.json for metrics to run
            self._config_data = {
                "strategy_settings": { # Copied from your provided full config
                    "strike_col_name": "strike", "option_kind_col_name": "opt_kind",
                    "underlying_price_col_name": "und_price", # To match sample data
                    "contract_multiplier_col_name": "multiplier",
                    "contract_multiplier_default_value": 100.0,
                    "oi_col_name": "oi", "option_price_col_name": "opt_price", # Changed for sample data
                    "option_volatility_col_name": "iv", # Changed for sample data
                    "expiration_col_name":"expiration_days_from_epoch_calc", # This is what InitialProcessor creates
                    "gamma_exposure_source_col": "gxoi", "delta_exposure_source_col": "dxoi",
                    "theta_exposure_source_col": "txoi", "vega_exposure_source_col": "vxoi",
                    "charm_exposure_source_col": "charmxoi", "vanna_exposure_source_col": "vannaxoi",
                    "vomma_exposure_source_col": "vommaxoi",
                    "delta_flow_proxy_col": "dxvolm", "gamma_flow_proxy_col": "gxvolm",
                    "theta_flow_proxy_col": "txvolm", "vega_flow_proxy_col": "vxvolm",
                    "charm_flow_proxy_col": "charmxvolm", "vanna_flow_proxy_col": "vannaxvolm",
                    "vomma_flow_proxy_col": "vommaxvolm",
                    "net_flow_cols_chain": {
                        "value_bs_contract": "c_value_bs", "volm_bs_contract": "c_volm_bs",
                        "deltas_buy_contract": "c_deltas_buy", "deltas_sell_contract": "c_deltas_sell",
                        "gammas_buy_contract": "c_gammas_buy", "gammas_sell_contract": "c_gammas_sell",
                        "vegas_buy_contract": "c_vegas_buy", "vegas_sell_contract": "c_vegas_sell",
                        "thetas_buy_contract": "c_thetas_buy", "thetas_sell_contract": "c_thetas_sell",
                        "valuebs_Xm_base": "valuebs_", "volmbs_Xm_base": "volmbs_"
                    },
                    "greeks_from_und": { # From your full config, map to sample_und_data keys
                        "price_und": "und_price", "volatility_und": "iv_und", "multiplier_und": "und_multiplier",
                        "day_open_price_und": "u_day_open_price",
                        "call_gxoi_und": "u_call_gxoi", "put_gxoi_und": "u_put_gxoi",
                        "call_vxoi_und": "u_call_vxoi", "put_vxoi_und": "u_put_vxoi",
                        "deltas_buy_und": "u_deltas_buy", "deltas_sell_und": "u_deltas_sell",
                        "gammas_buy_und": "u_gammas_buy", "gammas_sell_und": "u_gammas_sell",
                        "gammas_call_buy_und": "u_gammas_call_buy", "gammas_call_sell_und": "u_gammas_call_sell",
                        "gammas_put_buy_und": "u_gammas_put_buy", "gammas_put_sell_und": "u_gammas_put_sell",
                        "vegas_buy_und": "u_vegas_buy", "vegas_sell_und": "u_vegas_sell",
                        "thetas_buy_und": "u_thetas_buy", "thetas_sell_und": "u_thetas_sell",
                        "vflowratio_und": "u_vflowratio",
                        "volm_call_buy_und": "u_volm_cb", "volm_put_sell_und": "u_volm_ps",
                        "volm_put_buy_und": "u_volm_pb", "volm_call_sell_und": "u_volm_cs",
                         # Add other greeks_from_und mappings used by calculator
                    },
                    "use_skew_adjusted_for_sdag": True,
                    "skew_adjusted_gamma_source_col": "sgxoi_calc",
                    "dag_methodologies": {
                        "enabled": ["multiplicative", "directional", "weighted", "volatility_focused"],
                        "multiplicative": {"delta_weight_factor": 0.5}, "directional": {"delta_weight_factor": 0.6},
                        "weighted": {"w1_gamma": 0.6, "w2_delta": 0.4}, "volatility_focused": {"delta_weight_factor": 0.7}
                    }
                },
                "data_processor_settings": { # From your full config
                    "weights": { 
                        "selection_logic": "regime_then_time_based", "regime_specific_weights_enabled": True,
                        "default_fallback_weights": { "dag_custom_norm": 0.30, "tdpi_norm": 0.25, "vri_sensitivity_norm": 0.20, "arfi_strike_norm": 0.10, "sdag_directional_norm":0.05, "vri_0dte_norm": 0.05, "vfi_0dte_norm": 0.05},
                        "regime_weights": { "NEUTRAL_REGIME": { "dag_custom_norm": 0.25, "tdpi_norm": 0.25, "vri_sensitivity_norm": 0.2, "arfi_strike_norm": 0.15, "sdag_directional_norm": 0.15}},
                        "time_based": { "morning": {"dag_custom_norm": 0.5}, "midday": {"tdpi_norm":0.5}, "final_hour": {"vri_sensitivity_norm":0.5}}
                    },
                    "coefficients": { "dag_alpha": { "aligned": 1.3, "opposed": 0.7, "neutral": 1.0 }, "tdpi_beta": { "aligned": 1.2, "opposed": 0.8, "neutral": 1.0 }, "vri_gamma": { "aligned": 1.2, "opposed": 0.8, "neutral": 1.0 }},
                    "factors": { "tdpi_gaussian_width": -0.5, "vri_vol_trend_fallback_factor": 1.0, "vri_0dte_gamma_align_reinforcing": 1.5, "vri_0dte_gamma_align_contradicting": 0.5, "vri_0dte_vol_trend_fallback_factor_no_history": 1.0 },
                    "approximations": { "tdpi_atr_fallback": {"type": "percentage_of_price", "percentage": 0.005, "min_value": 0.01, "atr_period": 10}, "generic_atr_period": 14 },
                    "iv_context_parameters": { "iv_rank_col_from_und": "u_iv_rank_3m", "vol_trend_avg_days_vri0dte": 5, "vol_trend_avg_days_vri_sens": 20 },
                    "normalization_clip_percentile": 99.5
                },
                "market_regime_engine_settings": { # Minimal for _get_mspi_weights
                    "time_of_day_definitions": {"morning_start_time": "09:30:00", "morning_end_time": "11:00:00", "midday_end_time": "14:00:00", "market_close_time": "16:00:00", "eod_trigger_time": "15:30:00"},
                    "eod_reference_price_field": "u_day_open_price", # Needs to be in sample_und_data
                    "default_regime": "NEUTRAL_REGIME"
                },
                "visualization_settings": { # For rolling intervals
                    "mspi_visualizer": {"rolling_intervals": ["5m", "15m"]} # Simplified for test
                }
            }
            main_test_logger.info("MockConfigManagerForMetricsTest created with sample config.")

        def get_setting(self, key_path: Union[str, List[str]], default: Any = None, quiet: bool = False) -> Any:
            keys = key_path.split('.') if isinstance(key_path, str) else key_path; val = self._config_data
            try:
                for k in keys: val = val[k]
                return val if val is not None else default
            except KeyError: 
                if not quiet: main_test_logger.debug(f"MockCM: Key '{key_path}' not found, returning default {default}.")
                return default
            except TypeError:
                if not quiet: main_test_logger.debug(f"MockCM: Path segment invalid for '{key_path}', returning default {default}.")
                return default
    
    test_calc_cm = MockConfigManagerForMetricsTest()

    class MockHistoricalDataManagerForMetricsTest:
        def __init__(self, config_mgr): self.logger = logging.getLogger("MockHDM_MetricsTest"); self.cm = config_mgr
        def get_ohlc_history_for_atr(self, symbol, num_days_fetch, current_trading_date):
            self.logger.info(f"MockHDM: get_ohlc_history_for_atr for {symbol}, {num_days_fetch} days until {current_trading_date-timedelta(days=1)}.")
            # Return minimal DataFrame for ATR calculation
            dates = pd.to_datetime([current_trading_date - timedelta(days=i+1) for i in range(num_days_fetch)])
            data = { 'date': dates, 'high': np.random.rand(num_days_fetch) * 2 + 150, 'low': np.random.rand(num_days_fetch) * 2 + 148, 'close': np.random.rand(num_days_fetch) * 2 + 149 }
            return pd.DataFrame(data)
        def get_average_iv(self, symbol, period_days): self.logger.info(f"MockHDM: get_average_iv for {symbol}, {period_days} days."); return 0.22
        def get_metric_distribution_for_threshold(self, symbol, metric_key, days_history, current_trading_date):
            self.logger.info(f"MockHDM: get_metric_distribution for {symbol} {metric_key}, {days_history} days until {current_trading_date-timedelta(days=1)}.")
            return pd.Series(np.random.rand(days_history) * 0.5 + 0.1) # Sample distribution
    
    mock_calc_hdm = MockHistoricalDataManagerForMetricsTest(test_calc_cm)
    calculator_instance = MetricsCalculatorV2_4(config_manager_instance=test_calc_cm, historical_data_manager_instance=mock_calc_hdm)

    # Create sample input DataFrames and Dicts (as if from InitialDataProcessorV2_4)
    num_test_contracts = 10
    current_test_time = datetime.now()
    und_px_test = 200.0
    mult_test = 100.0

    options_df_input = pd.DataFrame({
        "strike": np.linspace(190, 210, num_test_contracts).round(0),
        "opt_kind": ['c', 'p'] * (num_test_contracts // 2),
        "expiration_days_from_epoch_calc": [(current_test_time.date() - date(1970,1,1)).days + d for d in [0,0,1,1,7,7,14,14,30,30]], # some 0DTE
        "oi": np.random.randint(50, 200, num_test_contracts),
        "opt_price": np.random.rand(num_test_contracts) * 5 + 0.1,
        "iv": np.random.rand(num_test_contracts) * 0.3 + 0.15,
        "multiplier": [mult_test] * num_test_contracts,
        "und_price": [und_px_test] * num_test_contracts, # As added by InitialProcessor
        "current_time_dt": [current_test_time] * num_test_contracts, # As added by InitialProcessor
        "underlying_symbol_calc": ["TESTCALC"] * num_test_contracts, # As added by InitialProcessor
        "processing_time_dt_obj": [current_test_time] * num_test_contracts, # As added by InitialProcessor
        # Base Greeks
        "delta": np.random.randn(num_test_contracts) * 0.4 + 0.1, "gamma": np.random.rand(num_test_contracts) * 0.05,
        "theta": np.random.rand(num_test_contracts) * -0.02, "vega": np.random.rand(num_test_contracts) * 0.1,
        "vanna": np.random.randn(num_test_contracts) * 0.01, "vomma": np.random.randn(num_test_contracts) * 0.005,
        "charm": np.random.randn(num_test_contracts) * -0.001,
        # OI Greeks
        "gxoi": np.random.randn(num_test_contracts) * 1000, "dxoi": np.random.randn(num_test_contracts) * 5000,
        "txoi": np.random.randn(num_test_contracts) * -200, "vxoi": np.random.randn(num_test_contracts) * 3000,
        "charmxoi": np.random.randn(num_test_contracts) * 100, "vannaxoi": np.random.randn(num_test_contracts) * 200,
        "vommaxoi": np.random.randn(num_test_contracts) * 50,
        # Flow Proxies
        "dxvolm": np.random.randn(num_test_contracts) * 100, "gxvolm": np.random.randn(num_test_contracts) * 50,
        "txvolm": np.random.randn(num_test_contracts) * -10, "vxvolm": np.random.randn(num_test_contracts) * 80,
        "charmxvolm": np.random.randn(num_test_contracts) * 5, "vannaxvolm": np.random.randn(num_test_contracts) * 10,
        "vommaxvolm": np.random.randn(num_test_contracts) * 3,
        # Signed Contract Flows
        "c_value_bs": np.random.randn(num_test_contracts) * 10000, "c_volm_bs": np.random.randn(num_test_contracts) * 100,
        "c_deltas_buy": np.random.rand(num_test_contracts) * 100, "c_deltas_sell": np.random.rand(num_test_contracts) * 120,
        "c_gammas_buy": np.random.rand(num_test_contracts) * 10, "c_gammas_sell": np.random.rand(num_test_contracts) * 12,
        "c_vegas_buy": np.random.rand(num_test_contracts) * 500, "c_vegas_sell": np.random.rand(num_test_contracts) * 550,
        "c_thetas_buy": np.random.rand(num_test_contracts) * -20, "c_thetas_sell": np.random.rand(num_test_contracts) * -22,
        # Rolling Flows Per Contract
        "valuebs_5m": np.random.randn(num_test_contracts) * 2000, "volmbs_5m": np.random.randn(num_test_contracts) * 20,
        "valuebs_15m": np.random.randn(num_test_contracts) * 6000, "volmbs_15m": np.random.randn(num_test_contracts) * 60,
    })
    
    und_data_input_raw = { # As prepared by InitialProcessor (includes multiplier from chain)
        "symbol": "TESTCALC",
        "und_price": und_px_test, 
        "multiplier": mult_test, # This is CRITICAL here
        "iv_und": 0.25, # Renamed to match greeks_from_und.volatility_und for example
        "u_call_gxoi": 6e5, "u_put_gxoi": 5e5,
        "u_call_vxoi": 3e5, "u_put_vxoi": 3.2e5,
        "u_deltas_buy": 2e6, "u_deltas_sell": 1.8e6,
        "u_gammas_buy": 1.5e4, "u_gammas_sell": 1.3e4,
        "u_gammas_call_buy": 0.8e4, "u_gammas_call_sell": 0.7e4,
        "u_gammas_put_buy": 0.7e4, "u_gammas_put_sell": 0.6e4,
        "u_vegas_buy": 1e5, "u_vegas_sell": 0.9e5,
        "u_thetas_buy": -2e4, "u_thetas_sell": -2.1e4,
        "u_vflowratio": 1.05,
        "u_volm_cb": 1200, "u_volm_ps": 1100, "u_volm_pb": 1000, "u_volm_cs": 1050,
        "u_day_open_price": und_px_test - 1.0, # For HP_EOD test
        "u_iv_rank_3m": 55.0, # For MSPI vol-based weights test
        "current_market_regime": "NEUTRAL_REGIME" # Example, MRE would set this
    }

    main_test_logger.info(f"Sample options_df_input created, shape: {options_df_input.shape}")
    main_test_logger.info(f"Sample und_data_input_raw created with keys: {list(und_data_input_raw.keys())}")

    try:
        df_chain_final, df_strike_final, und_data_final = calculator_instance.orchestrate_all_metric_calculations(
            options_df_raw=options_df_input,
            und_data_api_raw=und_data_input_raw,
            current_time_dt=current_test_time,
            symbol="TESTCALC"
        )
        main_test_logger.info("--- Orchestration Test Complete ---")
        main_test_logger.info(f"Final df_chain_final shape: {df_chain_final.shape}")
        if not df_chain_final.empty: main_test_logger.info(f"  Cols: {df_chain_final.columns.tolist()}")
        main_test_logger.info(f"Final df_strike_final shape: {df_strike_final.shape}")
        if not df_strike_final.empty: main_test_logger.info(f"  Cols: {df_strike_final.columns.tolist()}")
        main_test_logger.info(f"Final und_data_final keys ({len(und_data_final.keys())}): {list(und_data_final.keys())}")
        # Example checks
        if 'mspi' in df_strike_final.columns: main_test_logger.info(f"  MSPI sample: {df_strike_final['mspi'].head(2).values}")
        if 'GIB_OI_based_Und' in und_data_final: main_test_logger.info(f"  GIB_OI_based_Und: {und_data_final['GIB_OI_based_Und']}")
        if 'HP_EOD_Und' in und_data_final: main_test_logger.info(f"  HP_EOD_Und: {und_data_final['HP_EOD_Und']}")
        if 'NetValueFlow_5m_Und' in und_data_final: main_test_logger.info(f"  NetValueFlow_5m_Und: {und_data_final['NetValueFlow_5m_Und']}")

    except Exception as e_orch_test:
        main_test_logger.critical(f"Error during test orchestration of metrics: {e_orch_test}", exc_info=True)

    main_test_logger.info("--- MetricsCalculatorV2_4 Standalone Test Finished ---")