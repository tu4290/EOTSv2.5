# core_analytics_engine/metrics_calculator_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union

import pandas as pd # type: ignore
import numpy as np # type: ignore

# Assuming Pydantic models might be used for structured inputs/outputs eventually
# from ..pydantic_models_v2_5 import ...

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class MetricsCalculatorV2_5:
    '''
    Central engine for computing all EOTS v2.5 metrics.
    Orchestrates the calculation of Tier 1, Tier 2 (Adaptive),
    and Tier 3 (Enhanced Flow) metrics, as well as data for Enhanced Heatmaps.
    '''

    def __init__(self,
                 config_manager_v2_5_instance: Any,
                 historical_data_manager_v2_5_instance: Optional[Any] = None # Optional for now
                ):
        self.logger = logger.getChild(self.__class__.__name__)
        self.initialization_failed = False

        if not hasattr(config_manager_v2_5_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5. Critical failure.")
            self.initialization_failed = True
            class DummyCM:
                def get_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    return default_value_to_return
                # Adding a dummy get_resolved_path_setting for completeness
                def get_resolved_path_setting(self, *args, symbol_context=None, default_value_to_return=None, **kwargs):
                    return None
            self.config_manager = DummyCM() # type: ignore
        else:
            self.config_manager = config_manager_v2_5_instance

        self.logger.info(f"Initializing MetricsCalculatorV2_5...")

        if historical_data_manager_v2_5_instance is None or not hasattr(historical_data_manager_v2_5_instance, 'get_ohlc_history_for_atr'):
            self.logger.warning("HistoricalDataManagerV2_5 instance not provided or invalid. Some metrics requiring historical data (e.g., ATR, Z-scores) may be impaired or use defaults.")
            # Create a dummy HDM if needed for stubbed operations
            class DummyHDM:
                def get_ohlc_history_for_atr(self, *args, **kwargs) -> Optional[pd.DataFrame]: return None
                def get_metric_distribution_for_threshold(self, *args, **kwargs) -> pd.Series: return pd.Series(dtype=float)
            self.historical_data_manager = DummyHDM() # type: ignore
        else:
            self.historical_data_manager = historical_data_manager_v2_5_instance

        self._load_metric_calculation_configs()

        # Per-cycle state, reset by orchestrate_all_metric_calculations_v2_5
        self.current_symbol: Optional[str] = None
        self.current_time_dt: Optional[datetime] = None
        self.current_und_price: Optional[float] = None
        self.current_und_multiplier: Optional[float] = None
        self.current_und_data_api_prepared: Optional[Dict[str, Any]] = None # From InitialProcessor
        self.options_df_prepared_input: Optional[pd.DataFrame] = None # From InitialProcessor

        # Contexts to be received from other modules (via Orchestrator -> InitialProcessor -> MetricsCalculator)
        self.current_market_regime: Optional[str] = None # Will be set by Orchestrator/MRE
        self.current_ticker_context: Optional[Dict[str, Any]] = None # Will be set by Orchestrator/TCA

        self.logger.info("MetricsCalculatorV2_5 Initialized.")

    def _load_metric_calculation_configs(self):
        '''Loads configurations relevant to metric calculations.'''
        self.logger.debug("Loading metric calculation specific configurations...")
        # Example: Parameters for ATR calculation
        self.atr_period_cfg = int(self.config_manager.get_setting("metrics_calculator_settings", "atr_calculation", "period", default_value_to_return=14))

        # Example: Config for Z-score normalization lookbacks for Tier 3 flow metrics
        self.vapi_fa_z_lookback = int(self.config_manager.get_setting("enhanced_flow_metric_settings", "vapi_fa_params", "z_score_lookback_periods", default_value_to_return=100))
        # ... similar for DWFD, TW-LAF ...

        # Column name mappings (essential for finding data in input DataFrames/dicts)
        # These should align with what InitialDataProcessorV2_5 sets up
        # And what fetchers provide initially for raw field names
        # Using some examples, full set needs to be robustly defined in config and loaded here.

        # From input options_df_prepared
        # These are after InitialProcessor has potentially renamed/added some from raw fetcher output
        input_chain_map_path = ["column_name_mappings", "input_chain_fields"]
        self.col_strike: str = self.config_manager.get_setting(*input_chain_map_path, "strike_col", default_value_to_return="strike")
        self.col_opt_kind: str = self.config_manager.get_setting(*input_chain_map_path, "option_kind_col", default_value_to_return="opt_kind")
        self.col_dte_calc: str = self.config_manager.get_setting(*input_chain_map_path, "dte_calculated_col", default_value_to_return="dte_calculated") # DTE added by InitialProcessor
        self.col_option_price: str = self.config_manager.get_setting(*input_chain_map_path, "option_price_col", default_value_to_return="price") # Option price
        self.col_oi: str = self.config_manager.get_setting(*input_chain_map_path, "oi_col", default_value_to_return="oi")
        self.col_iv: str = self.config_manager.get_setting(*input_chain_map_path, "iv_col", default_value_to_return="volatility") # Option IV

        # Greeks from input options_df_prepared (assuming they are direct column names from CV)
        greeks_config_path = ["metrics_io_params", "convexvalue_fields", "get_chain_additional_params"] # Example path
        # We need specific keys for each greek, e.g. "delta_col_name_cv" : "delta"
        # For now, assume direct names:
        self.col_delta: str = "delta"
        self.col_gamma: str = "gamma"
        self.col_theta: str = "theta"
        self.col_vega: str = "vega"
        self.col_charm: str = "charm"
        self.col_vanna: str = "vanna"
        self.col_vomma: str = "vomma"

        # OI-weighted Greeks (xOI)
        self.col_dxoi: str = "dxoi"
        self.col_gxoi: str = "gxoi"
        # ... etc. for txoi, vxoi, charmxoi, vannaxoi, vommaxoi

        # Volume-weighted Greeks (xVOLM) - proxies for some Greek flows
        self.col_dxvolm: str = "dxvolm"
        self.col_gxvolm: str = "gxvolm"
        # ... etc.

        # Rolling signed flows per contract (e.g., valuebs_5m, volmbs_5m)
        # These will be iterated over based on configured intervals.
        # Example: self.config_manager.get_setting("metrics_io_params", "convexvalue_fields", "rolling_flow_intervals_config")
        # Example: {"valuebs_5m": "valuebs_5m_cv_key", "volmbs_5m": "volmbs_5m_cv_key", ...}

        # From input underlying_data_prepared
        und_fields_map_path = ["column_name_mappings", "underlying_fields"]
        self.col_und_price: str = self.config_manager.get_setting(*und_fields_map_path, "price_col", default_value_to_return="price") # Underlying price
        self.col_und_multiplier: str = self.config_manager.get_setting(*input_chain_map_path, "multiplier_col", default_value_to_return="multiplier") # Already used by InitialProcessor too
        self.col_und_iv_cv: str = self.config_manager.get_setting(*und_fields_map_path, "cv_implied_vol_col", default_value_to_return="u_volatility") # Example for CV's u_volatility
        self.col_tradier_iv_approx: str = self.config_manager.get_setting(*und_fields_map_path, "tradier_iv_approx_col", default_value_to_return="tradier_iv5_approx_smv_avg") # Example for Tradier IV

        self.logger.debug("Metric calculation configurations and column mappings loaded.")

    def _get_current_und_price(self) -> Optional[float]:
        if self.current_und_data_api_prepared:
            price = self.current_und_data_api_prepared.get(self.col_und_price)
            if isinstance(price, (int, float)) and pd.notna(price):
                return float(price)
        self.logger.warning(f"Could not retrieve valid current underlying price for {self.current_symbol} from prepared data.")
        return None

    def _get_current_und_multiplier(self) -> Optional[float]:
        if self.current_und_data_api_prepared:
            mult = self.current_und_data_api_prepared.get(self.col_und_multiplier)
            if isinstance(mult, (int, float)) and pd.notna(mult) and mult > 0:
                return float(mult)
        self.logger.warning(f"Could not retrieve valid contract multiplier for {self.current_symbol} from prepared data. Using default.")
        return float(self.config_manager.get_setting("strategy_settings", "contract_multiplier_default_value", default_value_to_return=100.0))


    def _calculate_atr_for_underlying(self) -> Optional[float]:
        '''Calculates ATR for the current symbol using HistoricalDataManager.'''
        if self.current_symbol is None or self.current_time_dt is None:
            self.logger.error("Cannot calculate ATR: current_symbol or current_time_dt not set.")
            return None
        if self.historical_data_manager is None:
            self.logger.warning("HistoricalDataManager not available, cannot calculate ATR.")
            return None

        ohlcv_hist_df = self.historical_data_manager.get_ohlc_history_for_atr(
            symbol=self.current_symbol,
            num_days_for_atr=self.atr_period_cfg, # e.g., 14
            current_trading_date=self.current_time_dt.date()
        )
        if ohlcv_hist_df is None or ohlcv_hist_df.empty or len(ohlcv_hist_df) < self.atr_period_cfg:
            self.logger.warning(f"Not enough OHLCV data for {self.current_symbol} to calculate ATR({self.atr_period_cfg}).")
            return None

        # Ensure columns are named as expected by ATR calculation (H, L, C)
        # This assumes standard 'high', 'low', 'close' from historical_data_manager
        high = ohlcv_hist_df['high']
        low = ohlcv_hist_df['low']
        close = ohlcv_hist_df['close']

        tr1 = pd.DataFrame(high - low)
        tr2 = pd.DataFrame(abs(high - close.shift()))
        tr3 = pd.DataFrame(abs(low - close.shift()))

        tr_df = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr_df.ewm(alpha=1/self.atr_period_cfg, adjust=False).mean().iloc[-1]
        # Could also use simple mean: atr = tr_df.tail(self.atr_period_cfg).mean()

        if pd.notna(atr) and atr > 0:
            self.logger.debug(f"Calculated ATR({self.atr_period_cfg}) for {self.current_symbol}: {atr:.4f}")
            return float(atr)
        else:
            self.logger.warning(f"ATR calculation for {self.current_symbol} resulted in NaN or zero.")
            return None

    # --- Tier 1 Metric Calculation Methods (Stubs/Basic Examples) ---
    def _calculate_gib_oi_based_und(self, options_df: pd.DataFrame) -> Optional[float]:
        self.logger.debug(f"Calculating GIB_OI_based_Und for {self.current_symbol}...")
        if options_df.empty or self.col_gxoi not in options_df.columns or self.col_opt_kind not in options_df.columns:
            self.logger.warning("GIB: Missing required columns (gxoi, opt_kind) or empty options_df.")
            return None

        # Simplified GIB calculation (v2.4 style: call_gxoi - put_gxoi)
        # This needs to align with the exact GIB definition from the EOTS v2.5 guide (Sec 5.2.1)
        # which emphasizes summing per-contract gxoi from get_chain
        # The input options_df IS the get_chain data here.

        call_gxoi_sum = options_df[options_df[self.col_opt_kind] == 'call'][self.col_gxoi].sum()
        put_gxoi_sum = options_df[options_df[self.col_opt_kind] == 'put'][self.col_gxoi].sum()

        # Dealer perspective: net short gamma if they sold calls (negative contribution to their gamma)
        # and sold puts (negative contribution to their gamma).
        # If gxoi is (gamma * OI), and positive gamma is standard:
        # If dealers are net sellers of options, their gamma exposure is typically negative.
        # A common convention for GIB: (Total Call Gamma OI) - (Total Put Gamma OI).
        # If this is negative, it implies puts have more gamma, or dealers are shorter calls / longer puts gamma-wise.
        # The EOTS v2.5 guide needs to be the source of truth for the exact dealer inference.
        # Assuming the guide's formula: GIB_Raw_Gamma = Sum_Call_GXOI - Sum_Put_GXOI
        # This means positive GIB if Call GXOI > Put GXOI.
        # Interpretation: if dealers are net short calls and net short puts (typical market making),
        # and calls have more gamma, this would be positive.
        # If GIB is defined as dealer's gamma position: GIB = -(call_gxoi_sum + put_gxoi_sum) if they are short both.
        # Let's stick to a common interpretation used in many systems:
        # GIB_raw_units = call_gxoi_sum - put_gxoi_sum (This is often what's meant by "Gamma Imbalance")

        # The guide section 5.2.1 for GIB states: "GIB (Raw Gamma Units from OI) = Sum_of_Call_GXOI - Sum_of_Put_GXOI".
        # "A negative GIB typically indicates dealers are net short gamma systemically"
        # This implies that if Sum_Call_GXOI < Sum_Put_GXOI (more Put Gamma OI), GIB is negative -> dealers short gamma.

        gib_raw_units = call_gxoi_sum - put_gxoi_sum

        if self.current_und_price is not None and self.current_und_multiplier is not None:
            # Dollarize per 1-point move of underlying
            # GIB_Dollar_Value_Per_Point = gib_raw_units * self.current_und_price * 0.01 * self.current_und_multiplier # If gxoi is per 1% IV change
            # GIB_Dollar_Value_Per_Point = gib_raw_units * self.current_und_multiplier # If gxoi is already per  und move
            # The guide (5.2.1, step 4) says: GIB_Dollar_Value = GIB (Raw Gamma Units from OI) * Underlying_Price * Contract_Multiplier.
            # This seems like total dollar gamma, not per point.
            # Let's assume for now GIB_OI_based_Und is the raw gamma units * multiplier for total contracts.
            # The dollarization for HP_EOD is GIB_Dollar_Value_Per_Point * Price_Difference.
            # So, GIB_Dollar_Value_Per_Point should be gib_raw_units * self.current_und_multiplier (gamma amount for all contracts)
            # This means if underlying moves , the delta exposure changes by this GIB amount.

            # For now, let's store GIB as dollarized gamma exposure for a  move in underlying
            # This is effectively total gamma units * multiplier
            gib_dollarized_per_point = gib_raw_units * self.current_und_multiplier
            self.logger.info(f"GIB_OI_based_Und for {self.current_symbol}: {gib_dollarized_per_point:.2f} (Call GXOI: {call_gxoi_sum:.0f}, Put GXOI: {put_gxoi_sum:.0f})")
            return float(gib_dollarized_per_point)
        return None

    # ... other Tier 1 stubs: _calculate_nvp_strike, _calculate_standard_rolling_flows_und, _calculate_hp_eod_und etc.

    # --- Tier 2 Metric Calculation Methods (Stubs) ---
    def _calculate_adaptive_metrics_per_contract(self, options_df: pd.DataFrame) -> pd.DataFrame:
        self.logger.debug(f"Calculating Tier 2 Adaptive Metrics per contract for {self.current_symbol} (STUBBED).")
        # Placeholder: A-DAG, E-SDAGs (if contract level), D-TDPI, VRI 2.0 (if contract level)
        # These will use self.current_market_regime, self.current_ticker_context
        # Example: options_df['a_dag_contract'] = np.random.rand(len(options_df))
        return options_df

    # --- Tier 3 Metric Calculation Methods (Stubs) ---
    def _calculate_enhanced_rolling_flows_und(self, options_df: pd.DataFrame) -> Dict[str, Optional[float]]:
        self.logger.debug(f"Calculating Tier 3 Enhanced Rolling Flow Metrics for {self.current_symbol} (STUBBED).")
        # Placeholder: VAPI-FA, DWFD, TW-LAF
        # These will use self.historical_data_manager for Z-score normalization if needed.
        # Example: vapi_fa_z = np.random.randn()
        return {"VAPI_FA_ZScore_Und": None, "DWFD_Z_Score_Und": None, "TW_LAF_Z_Score_Und": None}

    # --- Heatmap Data Calculation Methods (Stubs) ---
    def _calculate_data_for_enhanced_heatmaps(self, strike_df_with_base_metrics: pd.DataFrame) -> pd.DataFrame:
        self.logger.debug(f"Calculating Data Components for Enhanced Heatmaps for {self.current_symbol} (STUBBED).")
        # Placeholder: SGDHP_Score, UGCH_Score added to strike_df
        # IVSDH data might be a separate structure
        # Example: strike_df_with_base_metrics['sgdhp_score'] = np.random.randn(len(strike_df_with_base_metrics))
        return strike_df_with_base_metrics


    def orchestrate_all_metric_calculations_v2_5(
        self,
        options_df_prepared: pd.DataFrame,          # From InitialProcessorV2_5
        underlying_data_prepared: Dict[str, Any],   # From InitialProcessorV2_5
        current_time_dt: datetime,                  # Current processing time
        symbol: str,                                # Symbol context
        market_regime_v2_5: Optional[str] = None,   # Passed by Orchestrator after MRE run
        ticker_context_v2_5: Optional[Dict[str, Any]] = None # Passed by Orchestrator after TCA run
        ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        '''
        Main orchestration method for calculating all metrics.
        Returns:
            - options_df_with_all_metrics: DataFrame with per-contract metrics.
            - df_strike_level_all_metrics: DataFrame with strike-level aggregated metrics.
            - underlying_data_enriched_final: Dict with all underlying-level aggregate metrics.
        '''
        self.logger.info(f"--- MetricsCalculatorV2_5 START for: {symbol} at {current_time_dt.isoformat()} ---")

        # Set per-cycle state
        self.current_symbol = symbol
        self.current_time_dt = current_time_dt
        self.current_und_data_api_prepared = underlying_data_prepared.copy() # Work on a copy
        self.options_df_prepared_input = options_df_prepared.copy() # Work on a copy

        self.current_und_price = self._get_current_und_price()
        self.current_und_multiplier = self._get_current_und_multiplier()

        # Store context if provided (will be used by adaptive metrics)
        self.current_market_regime = market_regime_v2_5
        self.current_ticker_context = ticker_context_v2_5
        self.logger.debug(f"Context for {symbol}: Regime='{market_regime_v2_5}', TickerContext provided: {ticker_context_v2_5 is not None}")


        # Initialize output structures
        # Start with copies of prepared inputs, then add metrics
        df_chain_metrics = self.options_df_prepared_input.copy()
        und_data_enriched = self.current_und_data_api_prepared.copy()

        # Calculate ATR first if needed by other metrics or for context
        und_data_enriched['underlying_atr_value'] = self._calculate_atr_for_underlying()

        # --- Tier 1 Calculations ---
        # Example: GIB (Underlying level)
        und_data_enriched['GIB_OI_based_Und'] = self._calculate_gib_oi_based_und(df_chain_metrics)
        # ... Call other Tier 1 calculation methods ...
        # These methods might modify df_chain_metrics (e.g., adding NVP per contract before strike aggregation)
        # or directly populate und_data_enriched.

        # --- Tier 2 Adaptive Metric Calculations (Per-Contract if applicable) ---
        # This step might add columns to df_chain_metrics
        df_chain_metrics = self._calculate_adaptive_metrics_per_contract(df_chain_metrics)

        # --- Aggregation to Strike Level (Example) ---
        # This needs to be robust: group by strike, then aggregate relevant per-contract metrics
        # and calculate strike-specific metrics (A-MSPI, E-SDAGs etc.)
        df_strike_metrics = pd.DataFrame() # Placeholder
        if not df_chain_metrics.empty and self.col_strike in df_chain_metrics.columns:
            try:
                # Example aggregation: sum of OI per strike
                # Real aggregation will be much more complex, summing calculated contract metrics
                # df_strike_metrics = df_chain_metrics.groupby(self.col_strike)[[self.col_oi]].sum().reset_index()
                # For now, just pass a placeholder or a basic group
                df_strike_metrics = df_chain_metrics.groupby(self.col_strike).first().reset_index() # Very basic stub
                self.logger.info(f"Generated STUB strike level metrics for {symbol}. Shape: {df_strike_metrics.shape}")

                # --- Tier 2 Adaptive Metrics (Strike Level, using df_strike_metrics or df_chain_metrics) ---
                # Example: Calculate A-MSPI (which uses A-DAG, D-TDPI etc. that might be on strike_df)
                # df_strike_metrics['A_MSPI_Strike'] = np.random.randn(len(df_strike_metrics)) # Stub
            except KeyError as e_strike_agg:
                self.logger.error(f"KeyError during basic strike aggregation for {symbol}: {e_strike_agg}. Strike metrics will be empty.")
                df_strike_metrics = pd.DataFrame()
        else:
            self.logger.warning(f"Cannot generate strike level metrics for {symbol}: input chain is empty or missing strike column.")


        # --- Data for Enhanced Heatmaps (Operates on strike-level data) ---
        df_strike_metrics = self._calculate_data_for_enhanced_heatmaps(df_strike_metrics)

        # --- Tier 3 Enhanced Rolling Flow Metric Calculations (Underlying level) ---
        tier3_flows = self._calculate_enhanced_rolling_flows_und(df_chain_metrics) # Pass chain for base flows
        und_data_enriched.update(tier3_flows)

        self.logger.info(f"--- MetricsCalculatorV2_5 END for: {symbol}. ---")
        return df_chain_metrics, df_strike_metrics, und_data_enriched

    def shutdown(self):
        self.logger.info(f"MetricsCalculatorV2_5 ({self.__class__.__name__}) shutdown called.")
