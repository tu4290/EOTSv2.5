# core_analytics_engine/signal_generator.py
# (Elite Version 2.4 - Co-Pilot - Canonical Signal Generation Engine - Phase 7 Revamp)

# Standard Library Imports
import logging
from typing import Dict, Any, Optional, List, Union, Tuple, Callable
from datetime import time, datetime, date
import math
import pandas as pd # type: ignore
import numpy as np # type: ignore

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

# --- Helper Constants ---
EPSILON_SIG_GEN: float = 1e-9 # Local epsilon for this module

class SignalGeneratorV2_4:
    """
    Generates discrete trading signals based on calculated metrics, configured thresholds
    (static or dynamically resolved), and the current market regime.
    V2.4 emphasizes refined inputs, regime context for initial signal strength,
    and new signal types based on advanced V2.4 metrics.
    """

    def __init__(self, config_manager_instance: Any): # Expecting a ConfigManager instance
        self.logger = logger.getChild(self.__class__.__name__)
        
        if not hasattr(config_manager_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager. Critical failure.")
            class DummyCM: # Fallback
                def get_setting(self, *args, **kwargs): return kwargs.get('default')
            self.config_manager = DummyCM() # type: ignore
        else:
            self.config_manager = config_manager_instance

        self.logger.info("SignalGeneratorV2_4 (Canonical - Phase 7) initialized.")

        # Load configurations needed by SignalGenerator
        self.signal_activation_flags: Dict[str, bool] = self._get_config_setting_sg(["system_settings", "signal_activation"], {})
        self.threshold_configs_all_static: Dict[str, Any] = self._get_config_setting_sg(["strategy_settings", "thresholds"], {}) # Static fallbacks
        
        s_cfg = "strategy_settings"
        self.strike_col_name: str = self._get_config_setting_sg(f"{s_cfg}.strike_col_name", "strike")
        # self.opt_kind_col_name: str = self._get_config_setting_sg(f"{s_cfg}.option_kind_col_name", "opt_kind") # Not directly used in most signals here

        # Define expected metric column names from MetricsCalculator's output DataFrames/Dicts
        # Strike-Level Metrics (from df_metrics_strike_level)
        self.mspi_col: str = "mspi"
        self.sai_col: str = "sai"
        self.ssi_col: str = "ssi_agg"
        self.arfi_strike_col: str = "arfi_strike"
        self.vri_sens_strike_col: str = "vri_sensitivity"
        self.vfi_sens_strike_col: str = "vfi_sens_strike" # VFI from VRI_Sensitivity logic
        self.tdpi_strike_col: str = "tdpi"
        self.ctr_strike_col: str = "ctr_strike"
        self.tdfi_strike_col: str = "tdfi_strike"
        self.sdag_vf_col: str = "sdag_volatility_focused" # Example for SDAG Vol Focused

        # Underlying Aggregate Metrics (from und_data_aggregates)
        self.und_price_col: str = self._get_config_setting_sg(f"{s_cfg}.underlying_price_col_name", "price")
        # Using keys directly as they appear in und_data_aggregates from MetricsCalculator
        self.vri_0dte_agg_key: str = "vri_0dte_und_sum" # Example from config
        self.vfi_0dte_agg_key: str = "vfi_0dte_und_sum" # Example from config
        self.vci_0dte_agg_key: str = "vci_0dte_agg"
        self.hp_eod_und_key: str = "HP_EOD_Und"
        self.arfi_overall_und_key: str = "arfi_overall_und_avg"
        self.ssi_overall_und_key: str = "ssi_agg_und_avg" # Corrected to match log
        self.rolling_net_value_flow_5m_key: str = "NetValueFlow_5m_Und"
        self.rolling_net_value_flow_15m_key: str = "NetValueFlow_15m_Und"
        self.rolling_net_value_flow_30m_key: str = "NetValueFlow_30m_Und"
        self.rolling_net_value_flow_60m_key: str = "NetValueFlow_60m_Und"
        self.net_cust_delta_flow_key: str = "NetCustDeltaFlow_Und"
        self.skew_factor_global_key: str = "SkewFactor_Global" # Assuming MetricsCalculator adds this
        self.gib_oi_und_key: str = "GIB_OI_based_Und"
        self.u_vflowratio_key: str = self._get_config_setting_sg(f"{s_cfg}.greeks_from_und.vflowratio_und", "vflowratio") # API field name
        
        # Per-cycle state
        self.current_processing_symbol: Optional[str] = None


        self.logger.debug("SignalGeneratorV2_4 column names and keys initialized.")

    def _get_config_setting_sg(self, key_path: Union[str, List[str]], default: Any = None, quiet:bool = False) -> Any:
        return self.config_manager.get_setting(key_path, default_value_to_return=default, quiet=quiet) # Pass correct param name

    def _get_threshold_value(self, threshold_name_in_config: str, 
                           resolved_dynamic_thresholds: Dict[str, Any],
                           default_static_value_override: Optional[Union[float, List[float]]] = None
                           ) -> Any: # Returns float, list of floats, or None
        """
        Retrieves a threshold. Priority:
        1. Dynamically resolved value (if threshold_name_in_config is a key in resolved_dynamic_thresholds).
        2. Static value from strategy_settings.thresholds[threshold_name_in_config].value.
        3. Static value from strategy_settings.thresholds[threshold_name_in_config].tiers (if list).
        4. Programmer-provided default_static_value_override.
        5. None if not found.
        """
        # 1. Check pre-resolved dynamic thresholds
        if threshold_name_in_config in resolved_dynamic_thresholds:
            val = resolved_dynamic_thresholds[threshold_name_in_config]
            self.logger.debug(f"SignalGen: Using dynamic threshold '{threshold_name_in_config}' = {val}")
            return val # This should already be the correct type (float or list of floats)

        # 2. Fallback to static configuration from self.threshold_configs_all_static
        #    The threshold_name_in_config (e.g., "sai_high_conviction") should directly be a key.
        threshold_definition_dict = self.threshold_configs_all_static.get(threshold_name_in_config)
        
        if isinstance(threshold_definition_dict, dict):
            # This is the V2.4 structure: {"type": "fixed", "value": X, "fallback_value": Y}
            # Or {"type": "relative_...", "percentile": P, "fallback_value": Y}
            # If type is "fixed", use its "value". Otherwise, it should have been in resolved_dynamic_thresholds.
            # This function is now primarily for *consuming* those resolved values or static "value" fields.
            if threshold_definition_dict.get("type") == "fixed":
                fixed_val = threshold_definition_dict.get("value")
                if fixed_val is not None:
                    self.logger.debug(f"SignalGen: Using static fixed threshold '{threshold_name_in_config}' = {fixed_val}")
                    try: return float(fixed_val) # Ensure float for single values
                    except (ValueError, TypeError): self.logger.warning(f"Non-numeric fixed value for {threshold_name_in_config}"); return None
            # If it's a dynamic type but not in resolved_dynamic_thresholds, means resolution failed or wasn't attempted by caller.
            # Fallback to its own fallback_value.
            fallback_val = threshold_definition_dict.get("fallback_value")
            if fallback_val is not None:
                 self.logger.debug(f"SignalGen: Using fallback_value for '{threshold_name_in_config}' = {fallback_val} (dynamic resolve may have failed or not applicable).")
                 try: return float(fallback_val)
                 except (ValueError, TypeError): self.logger.warning(f"Non-numeric fallback_value for {threshold_name_in_config}"); return None

        # 3. Fallback to programmer's default if provided to this function
        if default_static_value_override is not None:
            self.logger.debug(f"SignalGen: Using programmer default for '{threshold_name_in_config}' = {default_static_value_override}")
            return default_static_value_override
            
        self.logger.warning(f"SignalGen: Threshold '{threshold_name_in_config}' not found dynamically or in static config as 'value' or 'fallback_value', and no programmer default provided. Returning None.")
        return None

    def _create_signal_payload_sg(self, 
                               base_payload_dict: Dict[str,Any],  # Typically a strike row or und_data dict
                               signal_name_str: str,
                               current_market_regime: str, 
                               initial_stars_val: int = 1,       # Base stars if no specific score
                               conviction_score_override: Optional[float] = None, # More precise score
                               signal_details: Optional[Dict[str, Any]] = None # Extra info
                               ) -> Dict[str,Any]:
        payload = base_payload_dict.copy() 
        payload['type'] = signal_name_str
        payload['current_market_regime_at_signal_time'] = current_market_regime
        
        base_score_for_stars = float(conviction_score_override if conviction_score_override is not None else initial_stars_val)
            
        reco_cfg = self._get_config_setting_sg("strategy_settings.recommendations", {})
        regime_signal_boosts_cfg = reco_cfg.get("regime_signal_initial_star_boosts", {})
        
        # Specific boost for this signal type within this regime
        specific_boost = regime_signal_boosts_cfg.get(current_market_regime, {}).get(signal_name_str, 0.0)
        
        # General directional/volatility boost for this regime
        general_boost_type: Optional[str] = None
        if "bullish" in signal_name_str.lower(): general_boost_type = "bullish_general_boost"
        elif "bearish" in signal_name_str.lower(): general_boost_type = "bearish_general_boost"
        elif "expansion" in signal_name_str.lower(): general_boost_type = "vol_expansion_general_boost"
        elif "contraction" in signal_name_str.lower(): general_boost_type = "vol_contraction_general_boost"
        
        general_boost = regime_signal_boosts_cfg.get(current_market_regime, {}).get(general_boost_type, 0.0) if general_boost_type else 0.0
        
        final_base_score_for_stars = base_score_for_stars + specific_boost + general_boost
        
        # Star mapping logic (simplified, RecommendationLogic might do more complex mapping)
        # These are thresholds for achieving a certain star rating based on the score.
        conv_map_5star = float(reco_cfg.get("conviction_map_high", 4.0)) 
        conv_map_4star = float(reco_cfg.get("conviction_map_high_medium", 3.0))
        conv_map_3star = float(reco_cfg.get("conviction_map_medium", 2.0))
        conv_map_2star = float(reco_cfg.get("conviction_map_medium_low", 1.0))
        conv_map_1star = float(reco_cfg.get("conviction_map_low", 0.5))
        
        stars = 0
        if final_base_score_for_stars >= conv_map_5star: stars = 5
        elif final_base_score_for_stars >= conv_map_4star: stars = 4
        elif final_base_score_for_stars >= conv_map_3star: stars = 3
        elif final_base_score_for_stars >= conv_map_2star: stars = 2
        elif final_base_score_for_stars >= conv_map_1star: stars = 1

        payload['initial_stars'] = stars # Initial star rating (can be further refined by RecoLogic)
        payload['base_conviction_score_signal_level'] = round(final_base_score_for_stars, 3)
        payload['signal_timestamp'] = datetime.now().isoformat()
        if signal_details: payload.update(signal_details) # Add any extra signal-specific details

        return payload

    def generate_all_signals_v2_4(
        self,
        df_metrics_strike_level: pd.DataFrame, # Contains strike-level metrics (MSPI, SAI, SSI, ARFI, NVP, etc.)
        und_data_aggregates: Dict[str, Any],   # Contains underlying-level aggregate metrics
        current_market_regime: str,            # Classified market regime
        current_time_dt: datetime,             # Current processing time
        resolved_dynamic_thresholds: Dict[str, Any] # Pre-resolved dynamic thresholds
    ) -> Dict[str, Dict[str, List[Dict[str,Any]]]]:
        """
        Main method to generate all V2.4 signals based on input metrics, regime, and thresholds.
        """
        # *** ADDED calc_name DEFINITION ***
        calc_name = self.__class__.__name__ # For logging
        # **********************************

        sg_logger = self.logger.getChild("GenerateAllSignals") # Use child logger for this method
        sg_logger.info(f"Generating all V2.4 signals for Regime: '{current_market_regime}' at {current_time_dt.strftime('%H:%M:%S')}.")
        sg_logger.debug(f"Received {len(resolved_dynamic_thresholds)} resolved dynamic thresholds.")
        self.current_processing_symbol = und_data_aggregates.get('symbol', 'UNKNOWN_SYM_SG') # Set for logging within methods


        signals_output: Dict[str, Dict[str, List[Dict[str,Any]]]] = {
            'directional': {'bullish': [], 'bearish': []}, # From MSPI+SAI
            'volatility': {'expansion': [], 'contraction': []}, # From VRI_sens, VFI_sens, SSI OR Regime-driven
            'time_decay': {'pin_risk': [], 'charm_cascade': []}, # From TDPI, CTR, TDFI
            'complex': {'structure_change': [], 'flow_divergence': [], 'sdag_conviction': []}, # From SSI, ARFI, SDAGs
            'v2_4_new': { # New signals often regime-driven or from new metrics
                'vanna_cascade_alert': [], 'volatility_skew_shift_alert': [],
                'eod_hedging_pressure': [], 'bubble_warning_signal': [],
                'rolling_flow_momentum_signal': [], 'unusual_customer_greek_flow_signal': []
            }
        }
        
        current_und_price_val = und_data_aggregates.get(self.und_price_col)
        if current_und_price_val is None or pd.isna(current_und_price_val):
            sg_logger.error("Underlying price missing. Many signals cannot be properly generated.")
            # Continue for signals that don't strictly need current price for their trigger (e.g. some regime-driven)

        # --- Strike-Level Signal Processing ---
        if isinstance(df_metrics_strike_level, pd.DataFrame) and not df_metrics_strike_level.empty:
            for _, strike_row_data in df_metrics_strike_level.iterrows():
                strike_payload_base = strike_row_data.to_dict() # Base for signal payloads from this strike

                # 1. Directional Signal (MSPI + SAI)
                if self.signal_activation_flags.get("directional", False):
                    mspi_val = strike_row_data.get(self.mspi_col, 0.0)
                    sai_val = strike_row_data.get(self.sai_col, 0.0)
                    sai_thresh = self._get_threshold_value("sai_high_conviction", resolved_dynamic_thresholds, 0.7)
                    mspi_pos_thresh = self._get_threshold_value("mspi_strength_thresh_pos", resolved_dynamic_thresholds, 0.5)
                    mspi_neg_thresh = self._get_threshold_value("mspi_strength_thresh_neg", resolved_dynamic_thresholds, -0.5)
                    
                    if sai_thresh is not None and mspi_pos_thresh is not None and mspi_neg_thresh is not None:
                        if sai_val > sai_thresh: # SAI > 0 indicates alignment
                            if mspi_val > mspi_pos_thresh:
                                signals_output['directional']['bullish'].append(self._create_signal_payload_sg(strike_payload_base, "directional_bullish", current_market_regime, 3))
                            elif mspi_val < mspi_neg_thresh:
                                signals_output['directional']['bearish'].append(self._create_signal_payload_sg(strike_payload_base, "directional_bearish", current_market_regime, 3))
                
                # 2. SDAG Conviction Signal
                if self.signal_activation_flags.get("sdag_conviction", False):
                    min_sdags_agree = int(self._get_config_setting_sg(["strategy_settings", "dag_methodologies", "min_agreement_for_conviction_signal"], 2))
                    enabled_sdags = self._get_config_setting_sg(["strategy_settings", "dag_methodologies", "enabled"], [])
                    
                    positive_sdags_count = 0; negative_sdags_count = 0
                    for sdag_method_name in enabled_sdags:
                        sdag_col_key = f"sdag_{sdag_method_name}"
                        sdag_val = strike_row_data.get(sdag_col_key, 0.0)
                        if sdag_val > EPSILON_SIG_GEN: positive_sdags_count += 1
                        elif sdag_val < -EPSILON_SIG_GEN: negative_sdags_count += 1
                    
                    if positive_sdags_count >= min_sdags_agree:
                        signals_output['complex']['sdag_conviction'].append(self._create_signal_payload_sg(strike_payload_base, "sdag_conviction_bullish", current_market_regime, conviction_score_override=float(positive_sdags_count)))
                    if negative_sdags_count >= min_sdags_agree:
                        signals_output['complex']['sdag_conviction'].append(self._create_signal_payload_sg(strike_payload_base, "sdag_conviction_bearish", current_market_regime, conviction_score_override=float(negative_sdags_count)))

                # 3. Time Decay Pin Risk Signal
                if self.signal_activation_flags.get("time_decay_pin_risk", False):
                    tdpi_val = strike_row_data.get(self.tdpi_strike_col, 0.0)
                    tdpi_thresh = self._get_threshold_value("pin_risk_tdpi_trigger", resolved_dynamic_thresholds, 5e5)
                    # Additional V2.4 context: VCI_0DTE (aggregate) and if it's final hour
                    vci_0dte_agg_val = und_data_aggregates.get(self.vci_0dte_agg_key, 0.0)
                    vci_context_thresh = self._get_threshold_value("pin_risk_vci_0dte_context_thresh", resolved_dynamic_thresholds, 0.15)
                    is_final_hour = "FINAL_HOUR" in current_market_regime.upper() # Simple check based on regime name
                    
                    if tdpi_thresh is not None and abs(tdpi_val) > tdpi_thresh:
                        pin_conv_score = 2.0
                        if is_final_hour: pin_conv_score += 0.5
                        if vci_context_thresh is not None and vci_0dte_agg_val > vci_context_thresh: pin_conv_score += 0.5
                        signals_output['time_decay']['pin_risk'].append(self._create_signal_payload_sg(strike_payload_base, "time_decay_pin_risk", current_market_regime, conviction_score_override=pin_conv_score))
                
                # 4. Time Decay Charm Cascade Signal
                if self.signal_activation_flags.get("time_decay_charm_cascade", False):
                    ctr_val = strike_row_data.get(self.ctr_strike_col, 0.0)
                    tdfi_val = strike_row_data.get(self.tdfi_strike_col, 0.0)
                    ctr_thresh = self._get_threshold_value("charm_cascade_ctr_trigger", resolved_dynamic_thresholds, 2.0)
                    tdfi_thresh = self._get_threshold_value("charm_cascade_tdfi_trigger", resolved_dynamic_thresholds, 1.0)
                    if ctr_thresh is not None and tdfi_thresh is not None and ctr_val > ctr_thresh and tdfi_val > tdfi_thresh:
                        signals_output['time_decay']['charm_cascade'].append(self._create_signal_payload_sg(strike_payload_base, "time_decay_charm_cascade", current_market_regime, 3))

                # 5. Complex Structure Change Signal (Low SSI)
                if self.signal_activation_flags.get("complex_structure_change", False):
                    ssi_val = strike_row_data.get(self.ssi_col, 1.0) # Default to stable if not found
                    ssi_thresh = self._get_threshold_value("ssi_structure_change", resolved_dynamic_thresholds, 0.3)
                    if ssi_thresh is not None and ssi_val < ssi_thresh:
                        signals_output['complex']['structure_change'].append(self._create_signal_payload_sg(strike_payload_base, "complex_structure_change", current_market_regime, 2))
                
                # 6. Complex Flow Divergence Signal (Simplified: MSPI high, ARFI low at strike)
                if self.signal_activation_flags.get("complex_flow_divergence", False):
                    mspi_val = strike_row_data.get(self.mspi_col, 0.0)
                    arfi_val = strike_row_data.get(self.arfi_strike_col, 1.0) # Default to supportive if not found
                    mspi_strong_thresh = 0.7 # Example fixed threshold
                    arfi_low_thresh = self._get_threshold_value("arfi_divergence_low_thresh", resolved_dynamic_thresholds, 0.5)
                    
                    divergence_detected = False
                    divergence_type = "flow_divergence" # Generic
                    if mspi_val > mspi_strong_thresh and arfi_low_thresh is not None and arfi_val < arfi_low_thresh: # Bullish MSPI, weak ARFI
                        divergence_detected = True; divergence_type = "flow_divergence_bearish_warning"
                    elif mspi_val < -mspi_strong_thresh and arfi_low_thresh is not None and arfi_val < arfi_low_thresh: # Bearish MSPI, weak ARFI
                        divergence_detected = True; divergence_type = "flow_divergence_bullish_warning"
                    
                    if divergence_detected:
                        signals_output['complex']['flow_divergence'].append(self._create_signal_payload_sg(strike_payload_base, divergence_type, current_market_regime, 2))
        else: # df_metrics_strike_level is empty
             sg_logger.warning(f"{calc_name}: Strike-level metrics DataFrame is empty. Skipping all strike-level signal generation for {self.current_processing_symbol}.")


        # --- Underlying-Level Signal Processing ---
        # These signals use und_data_aggregates and current_market_regime
        und_payload_base = und_data_aggregates.copy()
        # Add current price to payload for context, even if signal is underlying-wide
        und_payload_base[self.strike_col_name] = current_und_price_val if current_und_price_val is not None else "N/A"

        # Volatility Expansion (can be from VRI_sens + VFI_sens OR regime-driven from VRI_0DTE/VFI_0DTE)
        if self.signal_activation_flags.get("volatility_expansion", False):
            if "VOL_EXPANSION_IMMINENT" in current_market_regime.upper():
                vri0_val = und_data_aggregates.get(self.vri_0dte_agg_key, 0.0)
                vfi0_val = und_data_aggregates.get(self.vfi_0dte_agg_key, 0.0)
                # Example conviction: base 2, boosted by metric strength
                conv_score = 2.0 + (abs(vri0_val) * 0.3) + (vfi0_val * 0.3) if vri0_val is not None and vfi0_val is not None else 2.0
                signal_name_vol_exp = "vol_expansion_regime_driven"
                if "BULLISH" in current_market_regime.upper(): signal_name_vol_exp += "_bullish_bias"
                elif "BEARISH" in current_market_regime.upper(): signal_name_vol_exp += "_bearish_bias"
                signals_output['volatility']['expansion'].append(self._create_signal_payload_sg(und_payload_base, signal_name_vol_exp, current_market_regime, conviction_score_override=conv_score))
            else: # VRI_sens based pathway (conceptual, using aggregated values from und_data)
                vri_s_agg = und_data_aggregates.get("vri_sensitivity_und_avg", 0.0) # Assuming this aggregate exists
                vfi_s_agg = und_data_aggregates.get("vfi_sens_strike_und_avg", 0.0) # Assuming this aggregate exists
                vri_s_thresh = self._get_threshold_value("vol_expansion_vri_sens_trigger", resolved_dynamic_thresholds, 0.5)
                vfi_s_thresh = self._get_threshold_value("vol_expansion_vfi_sens_trigger_alt", resolved_dynamic_thresholds, 0.6) # Separate threshold for this path's VFI
                if vri_s_thresh is not None and vfi_s_thresh is not None and \
                   vri_s_agg is not None and vfi_s_agg is not None and \
                   abs(vri_s_agg) > vri_s_thresh and vfi_s_agg > vfi_s_thresh:
                    signals_output['volatility']['expansion'].append(self._create_signal_payload_sg(und_payload_base, "vol_expansion_vri_sens_driven", current_market_regime, 2))
        
        # Volatility Contraction
        if self.signal_activation_flags.get("volatility_contraction", False):
            # Check specific metrics if not covered by a "STABLE_LOW_VOL" type regime
            if "STABLE" in current_market_regime.upper() and ("LOW_VOL" in current_market_regime.upper() or "POSITIVE_GAMMA" in current_market_regime.upper()):
                 signals_output['volatility']['contraction'].append(self._create_signal_payload_sg(und_payload_base, "vol_contraction_regime_driven", current_market_regime, 2))
            else:
                vri_s_agg = und_data_aggregates.get("vri_sensitivity_und_avg", 1.0) # Default high if missing
                ssi_o_agg = und_data_aggregates.get(self.ssi_overall_und_key, 0.0) 
                vri_s_contr_thresh = self._get_threshold_value("vol_contraction_vri_sens_max", resolved_dynamic_thresholds, 0.15)
                ssi_contr_thresh = self._get_threshold_value("ssi_vol_contraction", resolved_dynamic_thresholds, 0.75)
                if vri_s_contr_thresh is not None and ssi_contr_thresh is not None and \
                   vri_s_agg is not None and ssi_o_agg is not None and \
                   abs(vri_s_agg) < vri_s_contr_thresh and ssi_o_agg > ssi_contr_thresh:
                    signals_output['volatility']['contraction'].append(self._create_signal_payload_sg(und_payload_base, "vol_contraction_metrics_driven", current_market_regime, 2))

        # New V2.4 Signals (Underlying Level - Mostly Regime Driven as per guide)
        # Vanna Cascade Alert
        if self.signal_activation_flags.get("vanna_cascade_alert", False):
            if "VANNA_CASCADE_ALERT_BULLISH" in current_market_regime.upper():
                signals_output['v2_4_new']['vanna_cascade_alert'].append(self._create_signal_payload_sg(und_payload_base, "vanna_cascade_bullish", current_market_regime, 4))
            elif "VANNA_CASCADE_ALERT_BEARISH" in current_market_regime.upper():
                signals_output['v2_4_new']['vanna_cascade_alert'].append(self._create_signal_payload_sg(und_payload_base, "vanna_cascade_bearish", current_market_regime, 4))

        # EOD Hedging Pressure
        if self.signal_activation_flags.get("eod_hedging_pressure", False):
            if "EOD_HEDGING_BUY_PRESSURE" in current_market_regime.upper():
                 signals_output['v2_4_new']['eod_hedging_pressure'].append(self._create_signal_payload_sg(und_payload_base, "eod_hedging_buy", current_market_regime, 3))
            elif "EOD_HEDGING_SELL_PRESSURE" in current_market_regime.upper():
                 signals_output['v2_4_new']['eod_hedging_pressure'].append(self._create_signal_payload_sg(und_payload_base, "eod_hedging_sell", current_market_regime, 3))
        
        # Sustained Rolling Flow Momentum
        if self.signal_activation_flags.get("rolling_flow_momentum_signal", False):
            if "SUSTAINED_BULLISH_ROLLING_FLOW" in current_market_regime.upper(): # Ensure this regime name matches MRE
                 signals_output['v2_4_new']['rolling_flow_momentum_signal'].append(self._create_signal_payload_sg(und_payload_base, "rolling_flow_bullish", current_market_regime, 3))
            elif "SUSTAINED_BEARISH_ROLLING_FLOW" in current_market_regime.upper(): # Ensure this regime name matches MRE
                 signals_output['v2_4_new']['rolling_flow_momentum_signal'].append(self._create_signal_payload_sg(und_payload_base, "rolling_flow_bearish", current_market_regime, 3))
        
        # Volatility Skew Shift Alert (Metric Driven)
        if self.signal_activation_flags.get("volatility_skew_shift_alert", False):
            skew_factor = und_data_aggregates.get(self.skew_factor_global_key) # From MetricsCalculator
            skew_pos_thresh = self._get_threshold_value('skew_extreme_positive_thresh', resolved_dynamic_thresholds, 0.2)
            skew_neg_thresh = self._get_threshold_value('skew_extreme_negative_thresh', resolved_dynamic_thresholds, -0.2)
            if skew_factor is not None and skew_pos_thresh is not None and skew_neg_thresh is not None:
                if skew_factor > skew_pos_thresh:
                    signals_output['v2_4_new']['volatility_skew_shift_alert'].append(self._create_signal_payload_sg(und_payload_base, "vol_skew_shift_extreme_put_bias", current_market_regime, 2))
                elif skew_factor < skew_neg_thresh:
                    signals_output['v2_4_new']['volatility_skew_shift_alert'].append(self._create_signal_payload_sg(und_payload_base, "vol_skew_shift_extreme_call_bias", current_market_regime, 2))

        # Bubble/Mispricing Warning (Regime or complex condition)
        if self.signal_activation_flags.get("bubble_warning_signal", False):
            if "TREND_EXHAUSTION" in current_market_regime.upper() or "BUBBLE_RISK" in current_market_regime.upper() : # Example regime check
                 arfi_overall = und_data_aggregates.get(self.arfi_overall_und_key, 1.0)
                 ssi_overall = und_data_aggregates.get(self.ssi_overall_und_key, 1.0)
                 arfi_bubble_thresh = self._get_threshold_value("bubble_arfi_low_thresh", resolved_dynamic_thresholds, 0.35)
                 ssi_bubble_thresh = self._get_threshold_value("bubble_ssi_low_thresh", resolved_dynamic_thresholds, 0.4)
                 if arfi_bubble_thresh is not None and ssi_bubble_thresh is not None and \
                    arfi_overall < arfi_bubble_thresh and ssi_overall < ssi_bubble_thresh:
                    signals_output['v2_4_new']['bubble_warning_signal'].append(self._create_signal_payload_sg(und_payload_base, "bubble_warning_metrics_confirm", current_market_regime, 3))
            
        # Unusual Customer Greek Flow Signal
        if self.signal_activation_flags.get("unusual_customer_greek_flow_signal", False):
            delta_flow_z = und_data_aggregates.get("NetCustDeltaFlow_Und_zscore")
            gamma_flow_z = und_data_aggregates.get("NetCustGammaFlow_Und_zscore")
            z_thresh = self._get_threshold_value("unusual_cust_delta_flow_zscore_thresh", resolved_dynamic_thresholds, 2.0) 

            if z_thresh is not None:
                if delta_flow_z is not None and abs(delta_flow_z) > z_thresh:
                    signals_output['v2_4_new']['unusual_customer_greek_flow_signal'].append(self._create_signal_payload_sg(und_payload_base, f"unusual_delta_flow_z{delta_flow_z:.1f}", current_market_regime, 2))
                if gamma_flow_z is not None and abs(gamma_flow_z) > z_thresh:
                    signals_output['v2_4_new']['unusual_customer_greek_flow_signal'].append(self._create_signal_payload_sg(und_payload_base, f"unusual_gamma_flow_z{gamma_flow_z:.1f}", current_market_regime, 2))

        sg_logger.info(f"{calc_name} for '{self.current_processing_symbol}' finished generating signals. Output structure populated.")
        return signals_output

# --- Main Test Block (Conceptual) ---
if __name__ == '__main__': # pragma: no cover
    import sys
    import json
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, 
                            format='[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S")
    
    main_test_logger = logging.getLogger(__name__)
    main_test_logger.info("SignalGeneratorV2_4 (Enhanced) - Standalone test execution started.")

    # Example config for testing SignalGenerator
    class TestCMForSignalGen:
        _cfg = { "system_settings": { "signal_activation": { "directional": True, "sdag_conviction": True, "volatility_expansion": True, "volatility_contraction": True, "time_decay_pin_risk": True, "time_decay_charm_cascade": True, "complex_structure_change": True, "complex_flow_divergence": True, "vanna_cascade_alert": True, "volatility_skew_shift_alert": True, "eod_hedging_pressure": True, "bubble_warning_signal": True, "rolling_flow_momentum_signal": True, "unusual_customer_greek_flow_signal": True }},
                 "strategy_settings": { "strike_col_name": "strike", "option_kind_col_name": "opt_kind", "underlying_price_col_name": "price",
                                       "thresholds": { "sai_high_conviction": {"type":"fixed", "value":0.7, "fallback_value":0.7}, "mspi_strength_thresh_pos": {"type":"fixed", "value":0.6, "fallback_value":0.6}, "mspi_strength_thresh_neg": {"type":"fixed", "value":-0.6, "fallback_value":-0.6}, "pin_risk_tdpi_trigger": {"type":"fixed", "value":6e5, "fallback_value":6e5}, "charm_cascade_ctr_trigger": {"type":"fixed", "value":2.5, "fallback_value":2.5}, "charm_cascade_tdfi_trigger": {"type":"fixed", "value":1.2, "fallback_value":1.2}, "ssi_structure_change": {"type":"fixed", "value":0.25, "fallback_value":0.25}, "arfi_divergence_low_thresh": {"type":"fixed", "value":0.4, "fallback_value":0.4}},
                                       "dag_methodologies": {"min_agreement_for_conviction_signal": 2, "enabled": ["multiplicative", "directional"]},
                                       "recommendations": { "conviction_map_high": 4.0, "conviction_map_high_medium": 3.0, "conviction_map_medium": 2.0, "conviction_map_medium_low": 1.0, "conviction_map_low": 0.5, "regime_signal_initial_star_boosts": { "REGIME_TRENDING_UP_STRONG_FLOW": {"directional_bullish": 0.5}}}
                                     },
                 "market_regime_engine_settings": { # Added for _get_config_setting_sg in _create_signal_payload_sg if it tries to access it
                     "default_regime": "REGIME_TEST_DEFAULT_SG"
                 }
                }
        def get_setting(self, key_path: Union[str, List[str]], default_value_to_return: Any = None, quiet: bool = False) -> Any: # Added default_value_to_return
            keys = key_path.split('.') if isinstance(key_path, str) else key_path; val = self._cfg
            try:
                for k in keys: val = val[k]
                return val if val is not None else default_value_to_return
            except KeyError: return default_value_to_return
    
    test_sg_cm = TestCMForSignalGen()
    generator = SignalGeneratorV2_4(config_manager_instance=test_sg_cm)

    mock_strikes_df = pd.DataFrame({ "strike": [100, 105, 110], "mspi": [0.7, 0.2, -0.8], "sai": [0.8, 0.5, 0.75], "sdag_multiplicative": [0.5,0.1,-0.4], "sdag_directional": [0.6,-0.05,-0.3], "tdpi": [1e5,7e5,2e5], "ctr_strike": [1.0,3.0,0.5], "tdfi_strike": [0.5,1.5,0.2], "ssi_agg": [0.7,0.2,0.8], "arfi_strike": [1.2,0.3,0.9] })
    mock_und_data = { "symbol": "TESTSIG", "price": 104.5, "current_processing_dte_context": 1, "vri_0dte_und_sum": 0.1, "vfi_0dte_und_sum": 0.2 } # Add other needed und_data keys
    mock_resolved_dyn_thresh = { "sai_high_conviction": 0.65, "mspi_strength_thresh_pos": 0.55 } # Example resolved
    
    signals = generator.generate_all_signals_v2_4(mock_strikes_df, mock_und_data, "REGIME_TRENDING_UP_STRONG_FLOW", datetime.now(), mock_resolved_dyn_thresh)
    main_test_logger.info(f"Test Generated Signals:\n{json.dumps(signals, indent=2)}")
    assert len(signals['directional']['bullish']) > 0, "Expected bullish directional signal"
    
    main_test_logger.info("SignalGeneratorV2_4 (Enhanced) - Standalone test execution finished.")
