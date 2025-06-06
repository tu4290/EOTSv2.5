# core_analytics_engine/trade_parameter_optimizer.py

import logging
from typing import Dict, Any, Tuple, Optional, List, Union
import pandas as pd # type: ignore
import numpy as np # type: ignore
import math
from datetime import date, datetime

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

# --- Constants ---
MIN_ATR_FOR_CALCS_TPO: float = 0.001
DEFAULT_STOP_LOSS_ATR_MULT_TPO: float = 1.5
DEFAULT_TARGET_1_ATR_MULT_TPO: float = 1.0
DEFAULT_TARGET_2_ATR_MULT_TPO: float = 2.0
EPSILON_TPO: float = 1e-9

class TradeParameterOptimizerV2_4:
    """
    Calculates initial and dynamically adjusted stop-loss and target levels for recommendations.
    V2.4: Incorporates market regime, ATR, and S/R levels from MSPI, NVP, Pin Zones.
    Relies on a ConfigManager instance for configuration and an Orchestrator reference
    for accessing its MetricsCalculator (for ATR).
    """

    def __init__(self, config_manager_instance: Any, orchestrator_ref: Any):
        self.logger = logger.getChild(self.__class__.__name__)
        self.initialization_failed_tpo = False # Assume success initially

        # Validate and set up config_manager_instance
        if not hasattr(config_manager_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager.")
            class DummyCMTPO:
                def get_setting(self, p, default_value_to_return, q=False): return default_value_to_return
            self.config_manager = DummyCMTPO() # type: ignore
            self.initialization_failed_tpo = True
        else:
            self.config_manager = config_manager_instance

        # Validate and set up orchestrator_ref
        if orchestrator_ref is None or \
           not hasattr(orchestrator_ref, 'metrics_calculator') or \
           (orchestrator_ref.metrics_calculator is not None and not hasattr(orchestrator_ref.metrics_calculator, '_get_atr_internal')): # Check if metrics_calculator itself is None
            self.logger.critical(f"{self.__class__.__name__} has invalid Orchestrator ref or MetricsCalculator setup.")
            self.initialization_failed_tpo = True 
            class DummyMetricsCalculatorForTPOFallback: 
                generic_atr_period=14
                tdpi_atr_fallback_cfg={}
                def _get_atr_internal(self, sym, px, per, date_val): 
                    self.logger.warning("TPO using DUMMY _get_atr_internal from fallback MetricsCalculator.")
                    return px * 0.01 if px else 0.01 # Handle px being None
            class DummyOrchestratorForTPOFallback: 
                metrics_calculator = DummyMetricsCalculatorForTPOFallback()
            self.orchestrator_ref = DummyOrchestratorForTPOFallback()
        else:
            self.orchestrator_ref = orchestrator_ref
            if not self.initialization_failed_tpo:
                 self.logger.info("TradeParameterOptimizerV2_4 (Canonical - Phase 10) preliminarily initialized with valid CM and Orchestrator.")


        if self.initialization_failed_tpo:
            self.logger.error("TradeParameterOptimizerV2_4 initialization failed. Parameter optimization will be impaired. Ensure ConfigManager and OrchestratorRef (with valid MetricsCalculator) are provided.")
            self.target_params_config: Dict[str, Any] = {}
            self.strike_col_name: str = "strike"
            self.mspi_col_name: str = "mspi"
            self.nvp_strike_col_name: str = "nvp_strike"
            self.tdpi_col_name: str = "tdpi"
            self.vci_0dte_col_name: str = "vci_0dte_agg"
            self.generic_atr_period_tpo: int = 14
            return 

        self.logger.info("TradeParameterOptimizerV2_4 proceeding with full configuration loading.")

        self.target_params_config = self._get_config_setting_tpo("strategy_settings.targets", {})
        
        s_cfg_path_base = "strategy_settings"
        self.strike_col_name = self._get_config_setting_tpo(f"{s_cfg_path_base}.strike_col_name", "strike")
        
        self.mspi_col_name = "mspi" 
        self.nvp_strike_col_name = "nvp_strike"
        self.tdpi_col_name = "tdpi"
        self.vci_0dte_col_name = "vci_0dte_agg" # From MetricsCalculator output (underlying aggregates)

        dp_cfg_path_base = "data_processor_settings"
        self.generic_atr_period_tpo = int(self._get_config_setting_tpo(f"{dp_cfg_path_base}.approximations.generic_atr_period", 14))

        self.logger.debug("TradeParameterOptimizerV2_4 configuration and column names fully initialized.")

    def _get_config_setting_tpo(self, key_path: Union[str,List[str]], default: Any = None, quiet: bool = False) -> Any:
        if self.initialization_failed_tpo and not hasattr(self.config_manager, 'get_setting'):
            return default
        if isinstance(self.config_manager, type) and self.config_manager.__name__ == 'DummyCMTPO': 
            return default
        return self.config_manager.get_setting(key_path, default_value_to_return=default, quiet=quiet)


    def _get_sr_levels_from_strike_data(
        self, 
        current_price: float, 
        trade_bias: str, 
        df_strike_level_metrics_tpo: pd.DataFrame,
        num_levels_to_return: int = 3
    ) -> Tuple[List[float], List[float]]:
        sr_logger = self.logger.getChild("SRLevelFinder")
        supports: List[float] = []
        resistances: List[float] = []

        if not isinstance(df_strike_level_metrics_tpo, pd.DataFrame) or \
           df_strike_level_metrics_tpo.empty or \
           self.strike_col_name not in df_strike_level_metrics_tpo.columns:
            sr_logger.warning("Strike data empty or missing strike column for S/R identification.")
            return supports, resistances
        
        df_sorted_strikes = df_strike_level_metrics_tpo.copy()
        try:
            df_sorted_strikes[self.strike_col_name] = pd.to_numeric(df_sorted_strikes[self.strike_col_name], errors='coerce')
        except Exception as e_conv_strike: 
            sr_logger.error(f"Error converting strike column '{self.strike_col_name}' to numeric: {e_conv_strike}. S/R may be inaccurate.")
            df_sorted_strikes[self.strike_col_name] = np.nan 
            
        df_sorted_strikes = df_sorted_strikes.dropna(subset=[self.strike_col_name])
        if df_sorted_strikes.empty: 
            sr_logger.debug("No valid strikes after attempting numeric conversion for S/R identification.")
            return supports, resistances
        
        df_sorted_strikes['distance_from_price'] = (df_sorted_strikes[self.strike_col_name] - current_price).abs()
        df_sorted_strikes = df_sorted_strikes.sort_values(by='distance_from_price')

        mspi_support_thresh = float(self.target_params_config.get("mspi_sr_support_threshold_target", 0.5))
        mspi_resistance_thresh = float(self.target_params_config.get("mspi_sr_resistance_threshold_target", -0.5))
        if self.mspi_col_name in df_sorted_strikes.columns:
            mspi_series = pd.to_numeric(df_sorted_strikes[self.mspi_col_name], errors='coerce').fillna(0.0)
            potential_mspi_supports = df_sorted_strikes.loc[mspi_series >= mspi_support_thresh, self.strike_col_name].tolist()
            potential_mspi_resistances = df_sorted_strikes.loc[mspi_series <= mspi_resistance_thresh, self.strike_col_name].tolist()
            supports.extend(s for s in potential_mspi_supports if pd.notna(s) and s < current_price)
            resistances.extend(r for r in potential_mspi_resistances if pd.notna(r) and r > current_price)
        
        if bool(self.target_params_config.get("nvp_active_as_sr_source", False)) and self.nvp_strike_col_name in df_sorted_strikes.columns:
            nvp_support_thresh = float(self.target_params_config.get("nvp_sr_strength_threshold_abs_support", 30e6))
            nvp_resistance_thresh = float(self.target_params_config.get("nvp_sr_strength_threshold_abs_resistance", -30e6))
            
            nvp_series = pd.to_numeric(df_sorted_strikes[self.nvp_strike_col_name], errors='coerce').fillna(0.0)
            potential_nvp_supports = df_sorted_strikes.loc[nvp_series >= nvp_support_thresh, self.strike_col_name].tolist()
            potential_nvp_resistances = df_sorted_strikes.loc[nvp_series <= nvp_resistance_thresh, self.strike_col_name].tolist()
            supports.extend(s for s in potential_nvp_supports if pd.notna(s) and s < current_price)
            resistances.extend(r for r in potential_nvp_resistances if pd.notna(r) and r > current_price)

        if bool(self.target_params_config.get("pin_zone_active_as_sr_source", False)) and \
           self.tdpi_col_name in df_sorted_strikes.columns and \
           'dte_calc' in df_sorted_strikes.columns: # dte_calc should be in strike_level_metrics
            
            pin_tdpi_thresh = float(self.target_params_config.get("pin_zone_tdpi_abs_thresh", 5e5))
            pin_max_dte_for_sr_val = int(self.target_params_config.get("pin_zone_max_dte_for_sr", 1))
            
            tdpi_abs_series = pd.to_numeric(df_sorted_strikes[self.tdpi_col_name], errors='coerce').abs().fillna(0.0)
            dte_series = pd.to_numeric(df_sorted_strikes['dte_calc'], errors='coerce').fillna(999)

            is_pin_candidate_strike = (tdpi_abs_series >= pin_tdpi_thresh) & (dte_series <= pin_max_dte_for_sr_val)
            potential_pin_strikes = df_sorted_strikes.loc[is_pin_candidate_strike, self.strike_col_name].tolist()
            
            for pin_s_val in potential_pin_strikes:
                if pd.notna(pin_s_val):
                    if pin_s_val < current_price: supports.append(pin_s_val)
                    elif pin_s_val > current_price: resistances.append(pin_s_val)
        
        unique_supports = sorted(list(set(s for s in supports if pd.notna(s))), reverse=True)
        unique_resistances = sorted(list(set(r for r in resistances if pd.notna(r))))

        final_supports = unique_supports[:num_levels_to_return]
        final_resistances = unique_resistances[:num_levels_to_return]
        
        sr_logger.info(f"S/R Levels for Px {current_price:.2f} ({trade_bias}): Supports={final_supports}, Resistances={final_resistances}")
        return final_supports, final_resistances

    def _calculate_atr_for_trade_params(self, symbol: str, current_price: float, current_trading_date: date) -> float:
        atr_calc_logger = self.logger.getChild("ATRCalcForParams")
        
        if self.initialization_failed_tpo or self.orchestrator_ref is None or self.orchestrator_ref.metrics_calculator is None:
            atr_calc_logger.error(f"TPO or Orchestrator Ref/MetricsCalculator not initialized. Falling back to basic % price ATR for {symbol}.")
            return max(MIN_ATR_FOR_CALCS_TPO, current_price * 0.005 if current_price else 0.01)

        atr_period_to_use = self.generic_atr_period_tpo
        
        try:
            # Ensure metrics_calculator is not the dummy one before calling
            if hasattr(self.orchestrator_ref.metrics_calculator, '_get_atr_internal') and \
               not (isinstance(self.orchestrator_ref.metrics_calculator, type) and self.orchestrator_ref.metrics_calculator.__name__ == 'DummyMetricsCalculatorForTPOFallback'):
                atr_value = self.orchestrator_ref.metrics_calculator._get_atr_internal(
                    symbol, current_price, period=atr_period_to_use, current_trading_date=current_trading_date
                )
            else: # Fallback if the real metrics_calculator or its method is missing
                atr_calc_logger.warning(f"MetricsCalculator._get_atr_internal not available. Using fallback ATR for {symbol}.")
                atr_value = max(MIN_ATR_FOR_CALCS_TPO, current_price * 0.005 if current_price else 0.01)

        except Exception as e_atr_call:
            atr_calc_logger.error(f"Error calling MetricsCalculator._get_atr_internal for {symbol}: {e_atr_call}. Using fallback.")
            atr_value = max(MIN_ATR_FOR_CALCS_TPO, current_price * 0.005 if current_price else 0.01)
        
        if atr_value < MIN_ATR_FOR_CALCS_TPO:
            atr_calc_logger.warning(f"Calculated ATR for {symbol} is very small ({atr_value:.4f}). Using min ATR fallback.")
            min_atr_abs = max(MIN_ATR_FOR_CALCS_TPO, current_price * 0.001 if current_price else 0.01)
            return min_atr_abs
            
        return atr_value

    def optimize_parameters_for_recommendation(
        self,
        recommendation_payload: Dict[str, Any],
        df_strike_level_metrics: pd.DataFrame,
        und_data_aggregates: Dict[str, Any], # Added, may contain current_market_regime
        symbol: str,
        current_time: datetime # Changed from current_trading_date to datetime
    ) -> Dict[str, Any]:
        """
        Optimizes trade parameters (stop-loss, targets) for a given recommendation payload.
        Updates and returns the recommendation_payload dictionary.
        """
        params_logger = self.logger.getChild(f"OptimizeParams.{symbol}.RecoID_{recommendation_payload.get('id','N/A')}")
        updated_reco_payload = recommendation_payload.copy()

        if self.initialization_failed_tpo:
            params_logger.error("TPO initialization failed. Cannot calculate targets/stops. Returning payload with error status.")
            updated_reco_payload["status"] = "ERROR_PARAMETERS"
            updated_reco_payload["target_rationale"] = "TradeParameterOptimizer initialization failed."
            updated_reco_payload["stop_loss"] = None
            updated_reco_payload["target_1"] = None
            updated_reco_payload["target_2"] = None
            return updated_reco_payload

        entry_price = recommendation_payload.get("entry_price_at_signal")
        trade_bias = recommendation_payload.get("bias")
        current_market_regime = recommendation_payload.get("current_market_regime_at_issuance") or \
                                und_data_aggregates.get("current_market_regime", "REGIME_UNKNOWN_TPO") # Fallback for regime
        current_trading_date = current_time.date()


        if not all([isinstance(entry_price, (float, int)), isinstance(trade_bias, str), entry_price > 0]):
            params_logger.error(f"Invalid inputs for parameter optimization: EntryPx={entry_price}, Bias={trade_bias}. Skipping.")
            updated_reco_payload["status"] = "ERROR_PARAMETERS"
            updated_reco_payload["target_rationale"] = "Invalid entry price or bias for TPO."
            return updated_reco_payload
        
        entry_price = float(entry_price)

        atr = self._calculate_atr_for_trade_params(symbol, entry_price, current_trading_date)
        if atr <= EPSILON_TPO:
            params_logger.error(f"ATR for {symbol} is zero or invalid ({atr}). Cannot set meaningful targets/stops.")
            updated_reco_payload["status"] = "ERROR_PARAMETERS"
            updated_reco_payload["target_rationale"] = "ATR calculation failed or resulted in zero."
            return updated_reco_payload

        regime_specific_mults_cfg = self.target_params_config.get("regime_specific_target_multipliers", {})
        regime_mults_for_current = regime_specific_mults_cfg.get(current_market_regime, {}) if isinstance(regime_specific_mults_cfg, dict) else {}
        
        sl_atr_mult = float(regime_mults_for_current.get("sl_mult", self.target_params_config.get("target_atr_stop_loss_multiplier", DEFAULT_STOP_LOSS_ATR_MULT_TPO)))
        t1_atr_mult_no_sr = float(regime_mults_for_current.get("t1_mult_no_sr", self.target_params_config.get("target_atr_target1_multiplier_no_sr", DEFAULT_TARGET_1_ATR_MULT_TPO)))
        t2_atr_mult_no_sr = float(regime_mults_for_current.get("t2_mult_no_sr", self.target_params_config.get("target_atr_target2_multiplier_no_sr", DEFAULT_TARGET_2_ATR_MULT_TPO)))
        t2_atr_mult_from_t1_sr = float(regime_mults_for_current.get("t2_mult_from_t1_sr", self.target_params_config.get("target_atr_target2_multiplier_from_t1_sr", 1.25)))

        params_logger.debug(f"Params for {symbol} ({trade_bias}, Regime: {current_market_regime}): ATR={atr:.3f}, SL_Mult={sl_atr_mult}, T1_NoSR_Mult={t1_atr_mult_no_sr}, T2_NoSR_Mult={t2_atr_mult_no_sr}")

        stop_loss: Optional[float] = None
        if trade_bias == "Bullish":
            stop_loss = entry_price - (atr * sl_atr_mult)
        elif trade_bias == "Bearish":
            stop_loss = entry_price + (atr * sl_atr_mult)
        else:
            params_logger.warning(f"Unknown trade bias '{trade_bias}'. Cannot calculate SL.")
            updated_reco_payload["status"] = "ERROR_PARAMETERS"
            updated_reco_payload["target_rationale"] = f"Invalid trade bias: {trade_bias}"
            return updated_reco_payload
        
        supports, resistances = self._get_sr_levels_from_strike_data(entry_price, trade_bias, df_strike_level_metrics)

        target_1: Optional[float] = None
        target_2: Optional[float] = None
        rationale_parts: List[str] = [f"ATR({self.generic_atr_period_tpo}d)={atr:.3f}."]

        min_target_dist_atr_mult = float(self.target_params_config.get("min_target_atr_distance_mult", 0.35))
        min_target_distance = atr * min_target_dist_atr_mult

        if trade_bias == "Bullish":
            atr_based_t1 = entry_price + (atr * t1_atr_mult_no_sr)
            candidate_t1 = atr_based_t1
            sr_t1_source = "ATR"
            if resistances:
                for res_level in resistances: # Resistances are sorted ascending
                    if res_level > entry_price + min_target_distance:
                        candidate_t1 = min(atr_based_t1, res_level)
                        sr_t1_source = "S/R" if math.isclose(candidate_t1, res_level) else "ATR"
                        break 
            target_1 = candidate_t1
            rationale_parts.append(f"T1({target_1:.2f}) via {sr_t1_source}.")

            atr_based_t2_from_entry = entry_price + (atr * t2_atr_mult_no_sr)
            atr_based_t2_from_t1 = target_1 + (atr * t2_atr_mult_from_t1_sr) if target_1 is not None else atr_based_t2_from_entry
            candidate_t2 = min(atr_based_t2_from_entry, atr_based_t2_from_t1) # Start with tighter of ATR-based T2s
            sr_t2_source = "ATR"
            
            further_resistances = [r for r in resistances if target_1 is not None and r > target_1 + min_target_distance]
            if further_resistances:
                for res_level_t2 in further_resistances:
                    if res_level_t2 > target_1 + min_target_distance: # Ensure T2 is beyond T1 + buffer
                        candidate_t2 = min(candidate_t2, res_level_t2)
                        sr_t2_source = "S/R" if math.isclose(candidate_t2, res_level_t2) else "ATR"
                        break
            target_2 = candidate_t2
            if target_1 is not None and target_2 <= target_1 + EPSILON_TPO : 
                target_2 = target_1 + (atr * max(0.5, (t2_atr_mult_no_sr - t1_atr_mult_no_sr)/2.0 if t1_atr_mult_no_sr > 0 else 0.5)) # Ensure T2 is beyond T1
            rationale_parts.append(f"T2({target_2:.2f}) via {sr_t2_source}.")

        elif trade_bias == "Bearish":
            atr_based_t1 = entry_price - (atr * t1_atr_mult_no_sr)
            candidate_t1 = atr_based_t1
            sr_t1_source = "ATR"
            if supports: # Supports are sorted descending
                for sup_level in supports:
                    if sup_level < entry_price - min_target_distance:
                        candidate_t1 = max(atr_based_t1, sup_level)
                        sr_t1_source = "S/R" if math.isclose(candidate_t1, sup_level) else "ATR"
                        break
            target_1 = candidate_t1
            rationale_parts.append(f"T1({target_1:.2f}) via {sr_t1_source}.")

            atr_based_t2_from_entry = entry_price - (atr * t2_atr_mult_no_sr)
            atr_based_t2_from_t1 = target_1 - (atr * t2_atr_mult_from_t1_sr) if target_1 is not None else atr_based_t2_from_entry
            candidate_t2 = max(atr_based_t2_from_entry, atr_based_t2_from_t1) # Start with tighter (further from entry)
            sr_t2_source = "ATR"

            further_supports = [s for s in supports if target_1 is not None and s < target_1 - min_target_distance]
            if further_supports:
                for sup_level_t2 in further_supports:
                    if sup_level_t2 < target_1 - min_target_distance: # Ensure T2 is beyond T1 + buffer
                        candidate_t2 = max(candidate_t2, sup_level_t2)
                        sr_t2_source = "S/R" if math.isclose(candidate_t2, sup_level_t2) else "ATR"
                        break
            target_2 = candidate_t2
            if target_1 is not None and target_2 >= target_1 - EPSILON_TPO: 
                target_2 = target_1 - (atr * max(0.5, (t2_atr_mult_no_sr - t1_atr_mult_no_sr)/2.0 if t1_atr_mult_no_sr > 0 else 0.5)) # Ensure T2 is beyond T1
            rationale_parts.append(f"T2({target_2:.2f}) via {sr_t2_source}.")
            
        final_rationale = " ".join(rationale_parts)
        
        # Final SL check against entry price (should not be through entry)
        if stop_loss is not None and target_1 is not None: # Check only if T1 is valid
            if trade_bias == "Bullish" and stop_loss >= entry_price:
                params_logger.warning(f"Adjusted Bullish SL for {symbol} as it was >= entry. Old SL: {stop_loss:.2f}.")
                stop_loss = entry_price - min(atr * 0.5, abs(target_1 - entry_price) * 0.5) if target_1 > entry_price else entry_price - (atr * 0.5) # More conservative SL adjustment
            elif trade_bias == "Bearish" and stop_loss <= entry_price:
                params_logger.warning(f"Adjusted Bearish SL for {symbol} as it was <= entry. Old SL: {stop_loss:.2f}.")
                stop_loss = entry_price + min(atr * 0.5, abs(entry_price - target_1) * 0.5) if target_1 < entry_price else entry_price + (atr * 0.5)
        
        # Update the recommendation payload
        updated_reco_payload["stop_loss"] = round(stop_loss, 2) if stop_loss is not None else None
        updated_reco_payload["target_1"] = round(target_1, 2) if target_1 is not None else None
        updated_reco_payload["target_2"] = round(target_2, 2) if target_2 is not None else None
        updated_reco_payload["target_rationale"] = final_rationale
        updated_reco_payload["status"] = "ACTIVE_NEW_NO_TSL" # Initial status after TPO
        updated_reco_payload["status_update"] = "Parameters optimized."


        params_logger.info(f"Final Params for {symbol} ({trade_bias}): SL={updated_reco_payload['stop_loss']}, T1={updated_reco_payload['target_1']}, T2={updated_reco_payload['target_2']}. Rationale: {final_rationale}")
        return updated_reco_payload

# --- Main Test Block (Conceptual) ---
if __name__ == '__main__': # pragma: no cover
    import sys 
    if not logging.getLogger().handlers: 
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, 
                            format='[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S")
    
    main_test_logger_tpo_canon = logging.getLogger(__name__) 
    main_test_logger_tpo_canon.info("TradeParameterOptimizerV2_4 (Canonical - Phase 10) - Standalone test execution started.")

    class MockCMForTPOTestCanon: 
        _cfg = {
            "strategy_settings": {
                "strike_col_name": "strike", 
                "targets": {
                    "mspi_sr_support_threshold_target": 0.4, "mspi_sr_resistance_threshold_target": -0.4,
                    "nvp_active_as_sr_source": True, "nvp_sr_strength_threshold_abs_support": 10e6, "nvp_sr_strength_threshold_abs_resistance": -10e6,
                    "pin_zone_active_as_sr_source": True, "pin_zone_tdpi_abs_thresh": 4e5, "pin_zone_max_dte_for_sr":1,
                    "target_atr_stop_loss_multiplier": 1.5, "target_atr_target1_multiplier_no_sr": 1.0,
                    "target_atr_target2_multiplier_no_sr": 2.0, "min_target_atr_distance_mult": 0.25,
                    "target_atr_target2_multiplier_from_t1_sr": 1.25,
                    "regime_specific_target_multipliers": {
                        "REGIME_TRENDING_STRONG": {"sl_mult": 1.2, "t1_mult_no_sr": 1.5, "t2_mult_no_sr": 3.0, "t2_mult_from_t1_sr": 1.5}
                    }
                }
            },
            "data_processor_settings":{"approximations":{"generic_atr_period":10}}
        }
        def get_setting(self, key_path: Union[str, List[str]], default_value_to_return: Any = None, quiet: bool = False) -> Any:
            keys = key_path.split('.') if isinstance(key_path, str) else key_path; val = self._cfg
            try:
                for k in keys: val = val[k]
                return val if val is not None else default_value_to_return
            except KeyError: return default_value_to_return
            except TypeError: return default_value_to_return 
    
    class MockMetricsCalculatorForTPOTestCanon: 
        def __init__(self): self.generic_atr_period=10; self.tdpi_atr_fallback_cfg={}; self.logger = logging.getLogger("MockMetricsCalcForTPO")
        def _get_atr_internal(self, symbol, current_price, period, current_trading_date): 
            self.logger.debug(f"Mock _get_atr_internal called for {symbol} with Px:{current_price}, Per:{period}, Date:{current_trading_date}")
            return current_price * 0.01 if current_price else 0.01
    class MockOrchestratorRefForTPOTestCanon: 
        def __init__(self): self.metrics_calculator = MockMetricsCalculatorForTPOTestCanon()

    test_cm_tpo_main_canon = MockCMForTPOTestCanon()
    mock_orchestrator_ref_tpo_canon = MockOrchestratorRefForTPOTestCanon()
    optimizer_tpo_canon = TradeParameterOptimizerV2_4(config_manager_instance=test_cm_tpo_main_canon, orchestrator_ref=mock_orchestrator_ref_tpo_canon)

    sample_strikes_df_tpo_canon = pd.DataFrame({
        "strike": [95.0, 98.0, 99.0, 100.0, 101.0, 102.0, 105.0],
        "mspi": [-0.2, 0.6, 0.7, 0.1, -0.6, -0.7, 0.3],
        "nvp_strike": [5e6, 15e6, 2e6, -1e6, -12e6, -5e6, 3e6],
        "tdpi": [1e5, 2e5, 6e5, 0.5e5, 5e5, 1e5, 0.8e5],
        "dte_calc": [0, 0, 0, 1, 1, 5, 5]
    })
    
    sample_reco_payload_bullish = {
        "id": "TEST_BULL_001", "symbol": "TESTTPOCANON", "category": "Directional Trades", "bias": "Bullish",
        "trigger_signal_name": "test_bull_signal", "strike_price_signal": 100.0,
        "entry_price_at_signal": 100.5, "current_market_regime_at_issuance": "REGIME_TRENDING_STRONG",
        "status": "PENDING_PARAMETERS"
    }
    sample_reco_payload_bearish = {
        "id": "TEST_BEAR_001", "symbol": "TESTTPOCANON", "category": "Directional Trades", "bias": "Bearish",
        "trigger_signal_name": "test_bear_signal", "strike_price_signal": 100.0,
        "entry_price_at_signal": 99.5, "current_market_regime_at_issuance": "REGIME_NORMAL",
        "status": "PENDING_PARAMETERS"
    }
    
    test_date_tpo_canon = date.today()
    test_datetime_tpo_canon = datetime.combine(test_date_tpo_canon, time(10,0,0))


    main_test_logger_tpo_canon.info("\n--- Testing Bullish Trade Params (TPO - Canonical Test) ---")
    updated_bullish_reco = optimizer_tpo_canon.optimize_parameters_for_recommendation(
        recommendation_payload=sample_reco_payload_bullish,
        df_strike_level_metrics=sample_strikes_df_tpo_canon,
        und_data_aggregates={"price": 100.5, "current_market_regime": "REGIME_TRENDING_STRONG"}, # Add current_market_regime here
        symbol="TESTTPOCANON",
        current_time=test_datetime_tpo_canon
    )
    main_test_logger_tpo_canon.info(f"Bullish (TPO Canon): SL={updated_bullish_reco.get('stop_loss')}, T1={updated_bullish_reco.get('target_1')}, T2={updated_bullish_reco.get('target_2')}, Rationale: {updated_bullish_reco.get('target_rationale')}")
    assert updated_bullish_reco.get('stop_loss') is not None and updated_bullish_reco.get('target_1') is not None
    if updated_bullish_reco.get('stop_loss') is not None: assert updated_bullish_reco['stop_loss'] < sample_reco_payload_bullish['entry_price_at_signal']
    if updated_bullish_reco.get('target_1') is not None: assert updated_bullish_reco['target_1'] > sample_reco_payload_bullish['entry_price_at_signal']
    

    main_test_logger_tpo_canon.info("\n--- Testing Bearish Trade Params (TPO - Canonical Test) ---")
    updated_bearish_reco = optimizer_tpo_canon.optimize_parameters_for_recommendation(
        recommendation_payload=sample_reco_payload_bearish,
        df_strike_level_metrics=sample_strikes_df_tpo_canon,
        und_data_aggregates={"price": 99.5, "current_market_regime": "REGIME_NORMAL"}, # Add current_market_regime here
        symbol="TESTTPOCANON",
        current_time=test_datetime_tpo_canon
    )
    main_test_logger_tpo_canon.info(f"Bearish (TPO Canon): SL={updated_bearish_reco.get('stop_loss')}, T1={updated_bearish_reco.get('target_1')}, T2={updated_bearish_reco.get('target_2')}, Rationale: {updated_bearish_reco.get('target_rationale')}")
    assert updated_bearish_reco.get('stop_loss') is not None and updated_bearish_reco.get('target_1') is not None
    if updated_bearish_reco.get('stop_loss') is not None: assert updated_bearish_reco['stop_loss'] > sample_reco_payload_bearish['entry_price_at_signal']
    if updated_bearish_reco.get('target_1') is not None: assert updated_bearish_reco['target_1'] < sample_reco_payload_bearish['entry_price_at_signal']
    
    main_test_logger_tpo_canon.info("TradeParameterOptimizerV2_4 (Canonical - Phase 10) - Standalone test execution finished.")
