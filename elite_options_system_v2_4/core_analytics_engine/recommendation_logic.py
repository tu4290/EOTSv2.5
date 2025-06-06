# core_analytics_engine/recommendation_logic.py
# (Elite Version 2.4 - Co-Pilot - Canonical Recommendation Formulation - Phase 9 Revamp)

import logging
from typing import Dict, Any, List, Tuple, Optional, Union
import pandas as pd # type: ignore
import numpy as np # type: ignore
import math
from datetime import datetime # For timestamping recommendations

logger = logging.getLogger(__name__)
EPSILON_RECO: float = 1e-9 # Local epsilon for floating point comparisons

class RecommendationGeneratorV2_4:
    """
    Formulates categorized strategy recommendations (Directional, Volatility, Range-Bound, Cautionary)
    based on input signals, the current market regime, and a comprehensive suite of V2.4 metrics.
    Implements multi-factor dynamic conviction scoring and prepares payloads for parameter optimization.
    """

    def __init__(self, config_manager_instance: Any, orchestrator_ref: Any):
        self.logger = logger.getChild(self.__class__.__name__)
        self.initialization_failed = False # Assume success initially

        # Validate and set up config_manager_instance
        if not hasattr(config_manager_instance, 'get_setting') or not hasattr(config_manager_instance, 'get_config'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManager. Critical failure.")
            class DummyCM: 
                def get_setting(self, *args, **kwargs):
                    return kwargs.get('default_value_to_return') # Match ConfigManager's param name
                def get_config(self, *args, **kwargs): return {}
            
            self.config_manager = DummyCM() # type: ignore
            self.initialization_failed = True
        else:
            self.config_manager = config_manager_instance
            self.logger.debug("ConfigManager instance received and seems valid.")

        # Validate and set up orchestrator_ref
        if orchestrator_ref is None or not hasattr(orchestrator_ref, 'map_score_to_stars'): 
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid Orchestrator reference. Critical failure.")
            self.initialization_failed = True
            class DummyOrchestrator: 
                def map_score_to_stars(self, score, category): return 0
                # Add dummy attributes for column names if accessed directly
                col_strike_orch = "strike"; col_und_price_orch = "price"; mspi_col = "mspi"; 
                nvp_strike_col = "nvp_strike"; ssi_col = "ssi_agg"; gib_oi_und_col = "GIB_OI_based_Und"
                rolling_net_value_flow_15m_col = "NetValueFlow_15m_Und"
                def _get_config_setting_its(self, path, default_val_param=None, quiet=False): return default_val_param # Mimic orchestrator's helper

            self.orchestrator_ref = DummyOrchestrator()
        else:
            self.orchestrator_ref = orchestrator_ref
            self.logger.debug("Orchestrator reference received and seems valid.")
        
        self.logger.info("RecommendationGeneratorV2_4 (Canonical - Phase 9) initialized.")

        if not self.initialization_failed:
            self._initialize_settings_and_mappings()
            self.recommendation_id_counter: int = 0 
        else:
            self.logger.error("RecommendationGeneratorV2_4 initialization failed due to missing or invalid dependencies. Configs will be empty.")
            # Ensure critical attributes exist even if empty
            self.reco_config: Dict[str, Any] = {}
            self.exit_config: Dict[str, Any] = {}
            self.target_config: Dict[str, Any] = {}
            self.threshold_configs_static_reco: Dict[str, Any] = {}
            self.signal_to_category_map: Dict[str, str] = {}
            self.col_strike: str = "strike" # Fallback
            self.col_und_price: str = "price" # Fallback
            self.recommendation_id_counter: int = 0


    def _get_config_setting_reco(self, key_path: Union[str, List[str]], default: Any = None, quiet:bool=False) -> Any:
        """Convenience wrapper for ConfigManager get_setting for this class."""
        # Ensure that when RecoLogic itself wants a config value, it uses the correct parameter name
        # for the default value when calling the ConfigManager.
        return self.config_manager.get_setting(key_path, default_value_to_return=default, quiet=quiet)


    def _initialize_settings_and_mappings(self) -> None:
        """Loads configurations relevant to recommendation logic."""
        self.logger.debug("Initializing settings and mappings for RecommendationGeneratorV2_4...")
        
        # --- CORRECTED CONFIG LOADING ---
        # Use the _get_config_setting_reco helper which calls self.config_manager.get_setting
        reco_base_path = "strategy_settings.recommendations"
        self.reco_config = self._get_config_setting_reco(reco_base_path, {})
        if not self.reco_config:
             self.logger.error(f"Failed to load 'reco_config' from path '{reco_base_path}'. It's empty. Recommendation logic will be impaired.")
        
        self.exit_config = self._get_config_setting_reco("strategy_settings.exits", {})
        if not self.exit_config:
            self.logger.warning("Failed to load 'exit_config'. Exit logic may use defaults or fail.")

        self.target_config = self._get_config_setting_reco("strategy_settings.targets", {})
        if not self.target_config:
            self.logger.warning("Failed to load 'target_config'. Target logic may use defaults or fail.")
        
        self.threshold_configs_static_reco = self._get_config_setting_reco("strategy_settings.thresholds", {})
        if not self.threshold_configs_static_reco:
            self.logger.warning("Failed to load 'threshold_configs_static_reco'. Threshold-based logic may use defaults or fail.")

        self.signal_to_category_map = self.reco_config.get("signal_to_category_mapping", {})
        if not self.signal_to_category_map:
            self.logger.warning("Signal-to-category mapping is empty. Recommendations might default to 'Cautionary Notes'.")

        # Column names
        s_cfg_path = "strategy_settings" # Base path for strategy settings
        self.col_strike = self._get_config_setting_reco(f"{s_cfg_path}.strike_col_name", "strike")
        self.col_und_price = self._get_config_setting_reco(f"{s_cfg_path}.underlying_price_col_name", "price")
        
        # Metric column names (these are standard output names from MetricsCalculator)
        self.mspi_col = "mspi"
        self.sai_col = "sai" 
        self.ssi_col = "ssi_agg"
        self.nvp_strike_col = "nvp_strike"
        self.arfi_strike_col = "arfi_strike"
        
        # Metric keys from und_data_aggregates
        self.gib_oi_und_key = "GIB_OI_based_Und"
        self.rolling_net_value_flow_15m_key = "NetValueFlow_15m_Und" 
        self.vri_0dte_agg_key = "vri_0dte_und_sum" 
        self.vfi_0dte_agg_key = "vfi_0dte_und_sum"
        self.vci_0dte_agg_key = "vci_0dte_agg"
        self.hp_eod_und_key = "HP_EOD_Und"
        
        self.logger.debug(f"RecommendationGeneratorV2_4 settings and mappings initialized. Reco config keys: {list(self.reco_config.keys())}")


    # --- Conviction Modifier Helper Methods ---
    def _apply_gib_conviction_mod(self, signal_name_full: str, gib_value: Optional[float]) -> Tuple[float, Optional[str]]:
        mod = 0.0; rationale = None; cfg = self.reco_config
        if gib_value is None or pd.isna(gib_value): return mod, rationale

        is_bullish = "bullish" in signal_name_full.lower()
        is_bearish = "bearish" in signal_name_full.lower()
        
        pos_gib_thresh = float(cfg.get("conv_mod_positive_gib_thresh", 15e9))
        neg_gib_thresh = float(cfg.get("conv_mod_negative_gib_thresh", -15e9)) 
        very_neg_gib_thresh = float(cfg.get("conv_mod_very_negative_gib_thresh", -60e9)) 

        if is_bullish:
            if gib_value > pos_gib_thresh: mod = float(cfg.get("conv_mod_positive_gib", 0.5))
            elif gib_value < very_neg_gib_thresh: mod = float(cfg.get("conv_mod_very_negative_gib", -1.25))
            elif gib_value < neg_gib_thresh : mod = float(cfg.get("conv_mod_negative_gib", -0.5)) 

        elif is_bearish:
            if gib_value < neg_gib_thresh: mod = float(cfg.get("conv_mod_positive_gib", 0.5)) 
            elif gib_value > pos_gib_thresh: mod = float(cfg.get("conv_mod_negative_gib", -0.5)) 

        if abs(mod) > EPSILON_RECO: rationale = f"GIB({gib_value:.1e}):{mod:+.2f}"
        return mod, rationale

    def _apply_nvp_conviction_mod(self, signal_name_full: str, nvp_strike_val: Optional[float]) -> Tuple[float, Optional[str]]:
        mod = 0.0; rationale = None; cfg = self.reco_config
        if nvp_strike_val is None or pd.isna(nvp_strike_val): return mod, rationale

        is_bullish = "bullish" in signal_name_full.lower()
        is_bearish = "bearish" in signal_name_full.lower()
        
        confirm_pos = float(cfg.get("conv_mod_high_nvp_thresh_pos", 25e6))
        confirm_neg = float(cfg.get("conv_mod_high_nvp_thresh_neg", -25e6))
        oppose_pos_for_bearish = float(cfg.get("conv_mod_opposing_nvp_thresh_pos", 10e6)) 
        oppose_neg_for_bullish = float(cfg.get("conv_mod_opposing_nvp_thresh_neg", -10e6)) 

        nvp_confirms_mod = float(cfg.get("conv_mod_nvp_confirms_strike", 0.75))
        nvp_opposes_mod = float(cfg.get("conv_mod_nvp_opposes_strike", -1.0))

        if is_bullish:
            if nvp_strike_val > confirm_pos: mod = nvp_confirms_mod
            elif nvp_strike_val < oppose_neg_for_bullish: mod = nvp_opposes_mod
        elif is_bearish:
            if nvp_strike_val < confirm_neg: mod = nvp_confirms_mod
            elif nvp_strike_val > oppose_pos_for_bearish: mod = nvp_opposes_mod
        
        if abs(mod) > EPSILON_RECO: rationale = f"NVP_Strike({nvp_strike_val:.1e}):{mod:+.2f}"
        return mod, rationale

    def _apply_ssi_conviction_mod(self, ssi_strike_val: Optional[float]) -> Tuple[float, Optional[str]]:
        mod = 0.0; rationale = None; cfg = self.reco_config
        if ssi_strike_val is None or pd.isna(ssi_strike_val): return mod, rationale
        
        low_ssi_thresh = float(cfg.get("conv_mod_ssi_low_thresh", 0.35))
        high_ssi_thresh = float(cfg.get("conv_mod_ssi_high_thresh", 0.7))

        if ssi_strike_val < low_ssi_thresh: mod = float(cfg.get("conv_mod_ssi_low", -1.0))
        elif ssi_strike_val > high_ssi_thresh: mod = float(cfg.get("conv_mod_ssi_high", 0.25))
        
        if abs(mod) > EPSILON_RECO: rationale = f"SSI_Strike({ssi_strike_val:.2f}):{mod:+.2f}"
        return mod, rationale

    def _apply_sdag_alignment_mod(self, signal_name_full: str, strike_metrics_row_data: Optional[pd.Series]) -> Tuple[float, Optional[str]]:
        mod = 0.0; rationale = None
        if strike_metrics_row_data is None: return mod, rationale
        
        sdag_dominant_dir = strike_metrics_row_data.get("sdag_dominant_direction") 

        if sdag_dominant_dir:
            if ("bullish" in signal_name_full.lower() and sdag_dominant_dir == "bullish") or \
               ("bearish" in signal_name_full.lower() and sdag_dominant_dir == "bearish"):
                mod = self.reco_config.get("conv_mod_sdag_align", 0.5)
                rationale = f"SDAG_Align({sdag_dominant_dir}):{mod:+.2f}"
            elif ("bullish" in signal_name_full.lower() and sdag_dominant_dir == "bearish") or \
                 ("bearish" in signal_name_full.lower() and sdag_dominant_dir == "bullish"):
                mod = self.reco_config.get("conv_mod_sdag_oppose", -0.75)
                rationale = f"SDAG_Oppose({sdag_dominant_dir}):{mod:+.2f}"
        return mod, rationale

    def _apply_rolling_flow_conviction_mod(self, signal_name_full: str, rolling_flow_val: Optional[float]) -> Tuple[float, Optional[str]]:
        mod = 0.0; rationale = None; cfg = self.reco_config
        if rolling_flow_val is None or pd.isna(rolling_flow_val): return mod, rationale

        is_bullish = "bullish" in signal_name_full.lower()
        is_bearish = "bearish" in signal_name_full.lower()
        strong_flow_thresh = float(cfg.get("conv_mod_strong_rolling_flow_thresh_abs", 100e6))
        opposing_flow_thresh = strong_flow_thresh * float(cfg.get("conv_mod_opposing_rolling_flow_factor", 0.5))

        if is_bullish:
            if rolling_flow_val > strong_flow_thresh: mod = float(cfg.get("conv_mod_rolling_flow_confirms", 0.75))
            elif rolling_flow_val < -opposing_flow_thresh: mod = float(cfg.get("conv_mod_rolling_flow_opposes", -1.0))
        elif is_bearish:
            if rolling_flow_val < -strong_flow_thresh: mod = float(cfg.get("conv_mod_rolling_flow_confirms", 0.75))
            elif rolling_flow_val > opposing_flow_thresh: mod = float(cfg.get("conv_mod_rolling_flow_opposes", -1.0))
            
        if abs(mod) > EPSILON_RECO: rationale = f"RollFlow15m({rolling_flow_val:.1e}):{mod:+.2f}" 
        return mod, rationale

    def _check_arfi_divergence_against_signal(
        self, signal_name_full: str, 
        signal_strike_val: Optional[float], 
        all_generated_signals_this_cycle: Dict[str, Dict[str, List[Dict[str, Any]]]]
        ) -> bool:
        flow_divergence_signals_list = all_generated_signals_this_cycle.get('complex', {}).get('flow_divergence', [])
        
        for div_signal_payload in flow_divergence_signals_list:
            div_signal_type_full = div_signal_payload.get('type','').lower() 
            div_signal_payload_strike_raw = div_signal_payload.get(self.col_strike)
            
            div_signal_payload_strike_val = None
            if div_signal_payload_strike_raw is not None:
                 try: div_signal_payload_strike_val = float(div_signal_payload_strike_raw)
                 except: pass 

            is_relevant_strike = False
            if signal_strike_val is None or pd.isna(signal_strike_val):
                if div_signal_payload_strike_val is None or pd.isna(div_signal_payload_strike_val) or div_signal_payload.get("is_underlying_divergence", False):
                    is_relevant_strike = True
            elif div_signal_payload_strike_val is not None and pd.notna(div_signal_payload_strike_val):
                if math.isclose(signal_strike_val, div_signal_payload_strike_val):
                    is_relevant_strike = True
            
            if is_relevant_strike:
                main_is_bullish = "bullish" in signal_name_full.lower()
                main_is_bearish = "bearish" in signal_name_full.lower()
                div_is_bullish_warn = "bullish_warning" in div_signal_type_full 
                div_is_bearish_warn = "bearish_warning" in div_signal_type_full 

                if (main_is_bullish and div_is_bearish_warn) or \
                   (main_is_bearish and div_is_bullish_warn):
                    self.logger.debug(f"RecoGen: ARFI Divergence signal '{div_signal_type_full}' found opposing primary signal '{signal_name_full}'.")
                    return True 
        return False 

    def formulate_recommendations_v2_4(
        self, 
        generated_signals_dict_from_sg: Dict[str, Dict[str, List[Dict[str, Any]]]], 
        df_strike_level_metrics_input: pd.DataFrame, 
        und_data_aggregates_input: Dict[str, Any],
        current_market_regime_input: str, 
        current_time_dt_input: datetime, 
        symbol_for_reco: str
    ) -> List[Dict[str, Any]]:
        reco_form_logger = self.logger.getChild(f"FormulateRecos.{symbol_for_reco}")
        new_recommendations: List[Dict[str, Any]] = []
        
        if self.initialization_failed:
            reco_form_logger.error("RecommendationGenerator not properly initialized. Cannot formulate recommendations.")
            return new_recommendations

        current_und_price_for_reco = und_data_aggregates_input.get(self.col_und_price) 
        if current_und_price_for_reco is None or pd.isna(current_und_price_for_reco) or float(current_und_price_for_reco) <= 0:
            reco_form_logger.error(f"Underlying price ('{self.col_und_price}') missing or invalid. Cannot formulate recommendations.")
            return new_recommendations

        if not self.reco_config: # Check if reco_config was loaded
            reco_form_logger.error("Recommendation config (self.reco_config) is empty. Aborting.")
            return []

        for signal_cat_key, signals_by_type_map in generated_signals_dict_from_sg.items():
            for signal_type_key, list_of_signal_payloads in signals_by_type_map.items():
                for raw_signal_data_payload in list_of_signal_payloads:
                    signal_full_name_from_payload = raw_signal_data_payload.get('type', f"{signal_cat_key}_{signal_type_key}")
                    base_conv_score_from_signal = float(raw_signal_data_payload.get('base_conviction_score_signal_level', 1.0)) 
                    
                    mapped_reco_category = self.signal_to_category_map.get(signal_full_name_from_payload, 
                                                                         self.signal_to_category_map.get(signal_type_key, "Cautionary Notes")) 

                    entry_price_at_signal_time = float(current_und_price_for_reco)
                    
                    signal_strike_raw = raw_signal_data_payload.get(self.col_strike) 
                    signal_strike_val_float: Optional[float] = None
                    if signal_strike_raw is not None and pd.notna(signal_strike_raw):
                        try: signal_strike_val_float = float(signal_strike_raw)
                        except: pass 
                    
                    current_total_conviction_score = base_conv_score_from_signal
                    rationale_list: List[str] = [f"BaseSignal:'{signal_full_name_from_payload}'(Score:{base_conv_score_from_signal:.2f})",
                                                 f"Regime:'{current_market_regime_input}'"]

                    regime_boost_pen_map = self.reco_config.get("regime_specific_conviction_boosters_penalties", {})
                    current_regime_mods = regime_boost_pen_map.get(current_market_regime_input, {})
                    
                    global_mod_val = float(current_regime_mods.get("all_categories_penalty", 0.0)) 
                    current_total_conviction_score += global_mod_val
                    if abs(global_mod_val) > EPSILON_RECO: rationale_list.append(f"RegimeGlobalMod:{global_mod_val:+.2f}")
                    
                    cat_bias_mod_val = 0.0
                    is_bullish_nature = "bullish" in signal_full_name_from_payload.lower()
                    is_bearish_nature = "bearish" in signal_full_name_from_payload.lower()
                    
                    reco_cat_config_key_base = mapped_reco_category.lower().replace(' ', '_') 
                    if is_bullish_nature: cat_bias_mod_val = float(current_regime_mods.get(f"{reco_cat_config_key_base}_bullish_boost", 0.0))
                    elif is_bearish_nature: cat_bias_mod_val = float(current_regime_mods.get(f"{reco_cat_config_key_base}_bearish_penalty", current_regime_mods.get(f"{reco_cat_config_key_base}_bearish_boost",0.0))) 
                    else: 
                        cat_bias_mod_val = float(current_regime_mods.get(f"{reco_cat_config_key_base}_boost", current_regime_mods.get(f"{reco_cat_config_key_base}_penalty", 0.0)))
                    
                    current_total_conviction_score += cat_bias_mod_val
                    if abs(cat_bias_mod_val) > EPSILON_RECO: rationale_list.append(f"RegimeCatMod({mapped_reco_category}):{cat_bias_mod_val:+.2f}")

                    gib_val_und = und_data_aggregates_input.get(self.gib_oi_und_key)
                    gib_mod, gib_rat = self._apply_gib_conviction_mod(signal_full_name_from_payload, gib_val_und)
                    current_total_conviction_score += gib_mod; 
                    if gib_rat: rationale_list.append(gib_rat)
                    
                    strike_metrics_for_reco: Optional[pd.Series] = None
                    if signal_strike_val_float is not None and isinstance(df_strike_level_metrics_input, pd.DataFrame) and not df_strike_level_metrics_input.empty:
                        df_strike_level_metrics_input[self.col_strike] = pd.to_numeric(df_strike_level_metrics_input[self.col_strike], errors='coerce')
                        matched_strike_rows = df_strike_level_metrics_input[
                            np.isclose(df_strike_level_metrics_input[self.col_strike].fillna(np.nan), signal_strike_val_float)
                        ]
                        if not matched_strike_rows.empty: strike_metrics_for_reco = matched_strike_rows.iloc[0]
                    
                    if strike_metrics_for_reco is not None:
                        nvp_s_val = strike_metrics_for_reco.get(self.nvp_strike_col)
                        nvp_mod, nvp_rat = self._apply_nvp_conviction_mod(signal_full_name_from_payload, nvp_s_val)
                        current_total_conviction_score += nvp_mod; 
                        if nvp_rat: rationale_list.append(nvp_rat)
                        
                        ssi_s_val = strike_metrics_for_reco.get(self.ssi_col)
                        ssi_mod, ssi_rat = self._apply_ssi_conviction_mod(ssi_s_val)
                        current_total_conviction_score += ssi_mod; 
                        if ssi_rat: rationale_list.append(ssi_rat)
                        
                        if "directional" in mapped_reco_category.lower() and "sdag_conviction" not in signal_full_name_from_payload:
                            sdag_mod, sdag_rat = self._apply_sdag_alignment_mod(signal_full_name_from_payload, strike_metrics_for_reco)
                            current_total_conviction_score += sdag_mod
                            if sdag_rat: rationale_list.append(sdag_rat)

                    if "directional" in mapped_reco_category.lower(): 
                        flow_15m_val_und = und_data_aggregates_input.get(self.rolling_net_value_flow_15m_key)
                        flow_mod, flow_rat = self._apply_rolling_flow_conviction_mod(signal_full_name_from_payload, flow_15m_val_und)
                        current_total_conviction_score += flow_mod; 
                        if flow_rat: rationale_list.append(flow_rat)
                    
                    if self._check_arfi_divergence_against_signal(signal_full_name_from_payload, signal_strike_val_float, generated_signals_dict_from_sg):
                         arfi_pen_val = float(self.reco_config.get("conv_mod_arfi_divergence_penalty", -1.5))
                         current_total_conviction_score += arfi_pen_val
                         rationale_list.append(f"ARFIDivPenalty:{arfi_pen_val:+.2f}")
                    
                    if mapped_reco_category == "Volatility Plays" and "expansion" in signal_full_name_from_payload.lower():
                        vri0_agg_val = und_data_aggregates_input.get(self.vri_0dte_agg_key)
                        vri0_thresh_vol = float(self.reco_config.get("conv_mod_vri0dte_high_thresh_for_vol", 0.75))
                        if vri0_agg_val is not None and abs(vri0_agg_val) > vri0_thresh_vol:
                             v0_mod_val = float(self.reco_config.get("conv_mod_vri0dte_confirms_vol_play", 0.5))
                             current_total_conviction_score += v0_mod_val
                             rationale_list.append(f"VRI0DTE_Agg({vri0_agg_val:.2f}):{v0_mod_val:+.2f}")
                    
                    if mapped_reco_category == "Range Bound Ideas" and "pin_risk" in signal_full_name_from_payload.lower():
                        vci0_agg_val = und_data_aggregates_input.get(self.vci_0dte_agg_key)
                        vci0_thresh_pin = float(self.reco_config.get("conv_mod_vci0dte_high_thresh_for_pin", 0.25))
                        if vci0_agg_val is not None and vci0_agg_val > vci0_thresh_pin:
                             vci_mod_val = float(self.reco_config.get("conv_mod_vci0dte_confirms_pin", 0.75))
                             current_total_conviction_score += vci_mod_val
                             rationale_list.append(f"VCI0DTE_Agg({vci0_agg_val:.2f}):{vci_mod_val:+.2f}")

                    if "directional" in mapped_reco_category.lower() and "eod_hedging" not in signal_full_name_from_payload:
                        hp_eod_val_und = und_data_aggregates_input.get(self.hp_eod_und_key)
                        if hp_eod_val_und is not None:
                            hp_eod_mod = 0.0
                            is_bullish_sig = "bullish" in signal_full_name_from_payload.lower()
                            hp_scale = float(self.reco_config.get("conv_mod_hp_eod_scale_factor", 200e6)) 
                            hp_conf_mod = float(self.reco_config.get("conv_mod_hp_eod_confirms", 0.5))
                            hp_opp_mod = float(self.reco_config.get("conv_mod_hp_eod_opposes", -0.75))

                            if is_bullish_sig and hp_eod_val_und < -hp_scale / 4 : hp_eod_mod = hp_conf_mod 
                            elif not is_bullish_sig and hp_eod_val_und > hp_scale / 4 : hp_eod_mod = hp_conf_mod 
                            elif (is_bullish_sig and hp_eod_val_und > hp_scale / 4) or \
                                 (not is_bullish_sig and hp_eod_val_und < -hp_scale / 4) : hp_eod_mod = hp_opp_mod 
                            
                            if abs(hp_eod_mod) > EPSILON_RECO:
                                current_total_conviction_score += hp_eod_mod
                                rationale_list.append(f"HP_EOD_Ctx({hp_eod_val_und:.1e}):{hp_eod_mod:+.2f}")
                    
                    final_stars_val = self.orchestrator_ref.map_score_to_stars(current_total_conviction_score, category=mapped_reco_category)
                    
                    min_stars_key_config = f"min_{mapped_reco_category.lower().replace(' ', '_')}_stars_to_issue"
                    min_stars_required = int(self.reco_config.get(min_stars_key_config, 2)) 
                    
                    if final_stars_val >= min_stars_required:
                        self.recommendation_id_counter += 1
                        reco_id_ts_suffix = f"{current_time_dt_input.strftime('%H%M%S%f')[:-3]}" 
                        reco_id_num_suffix = f"{self.recommendation_id_counter:04d}"
                        reco_id_cat_prefix = "".join([word[0] for word in mapped_reco_category.split()]).upper() if mapped_reco_category else "UNK"
                        
                        reco_unique_id = f"{reco_id_cat_prefix}_{symbol_for_reco}_{current_time_dt_input.strftime('%Y%m%d')}_{reco_id_ts_suffix}_{reco_id_num_suffix}"
                        
                        reco_payload_final = {
                            "id": reco_unique_id, "timestamp_issued": current_time_dt_input.isoformat(), "symbol": symbol_for_reco,
                            "category": mapped_reco_category, 
                            "bias": "Bullish" if is_bullish_nature else ("Bearish" if is_bearish_nature else "Neutral"),
                            "trigger_signal_name": signal_full_name_from_payload,
                            "strike_price_signal": signal_strike_val_float, 
                            "entry_price_at_signal": entry_price_at_signal_time,
                            "conviction_score_final": round(current_total_conviction_score, 3),
                            "conviction_stars_final": final_stars_val,
                            "rationale_full": "; ".join(rationale_list), 
                            "status": "PENDING_PARAMETERS", 
                            "status_update": "Awaiting Target/Stop Loss optimization.",
                            "target_1": None, "target_2": None, "stop_loss": None, "target_rationale": None,
                            "current_market_regime_at_issuance": current_market_regime_input,
                            "key_metrics_at_issuance": { 
                                "GIB_OI_Und": und_data_aggregates_input.get(self.gib_oi_und_key),
                                "NVP_at_strike": strike_metrics_for_reco.get(self.nvp_strike_col) if strike_metrics_for_reco is not None else None,
                                "RollFlow15m_Und": und_data_aggregates_input.get(self.rolling_net_value_flow_15m_key),
                                "SSI_at_strike": strike_metrics_for_reco.get(self.ssi_col) if strike_metrics_for_reco is not None else None,
                                "MSPI_at_strike": strike_metrics_for_reco.get(self.mspi_col) if strike_metrics_for_reco is not None else None,
                                "vri_0dte_agg": und_data_aggregates_input.get(self.vri_0dte_agg_key),
                                "vfi_0dte_agg": und_data_aggregates_input.get(self.vfi_0dte_agg_key),
                                "HP_EOD_Und": und_data_aggregates_input.get(self.hp_eod_und_key)
                            },
                            "last_adjusted_ts": current_time_dt_input.isoformat(), 
                            "exit_reason": None, "exit_price": None, "exit_timestamp": None,
                            "t1_hit_sl_adjusted": False, "t2_hit_sl_adjusted": False 
                        }
                        new_recommendations.append(reco_payload_final)
                        reco_form_logger.info(f"Formulated Reco ID {reco_unique_id}: Trigger='{signal_full_name_from_payload}', Cat='{mapped_reco_category}', "
                                         f"Strike={signal_strike_val_float if signal_strike_val_float else 'N/A'}, Entry ~{entry_price_at_signal_time:.2f}, "
                                         f"{final_stars_val}* ({current_total_conviction_score:.2f})")
        
        reco_form_logger.info(f"RecommendationGenerator: Formulation complete for {symbol_for_reco}. Generated {len(new_recommendations)} potential recommendations this cycle.")
        return new_recommendations

# --- Main Test Block (Conceptual - actual testing would be more involved) ---
if __name__ == '__main__': # pragma: no cover
    # Setup basic logging for the test
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
                            format='[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S")

    test_logger_reco = logging.getLogger(__name__)
    test_logger_reco.info("RecommendationGeneratorV2_4 - Standalone test execution started.")

    # Mock ConfigManager
    class MockCMForReco:
        _cfg = {
            "strategy_settings": {
                "strike_col_name": "strike_val_test", 
                "underlying_price_col_name": "px_last_test",
                "recommendations": {
                    "signal_to_category_mapping": {
                        "directional_bullish_mspi": "Directional Trades", "directional_bearish_mspi": "Directional Trades",
                        "vol_expansion_vri0": "Volatility Plays", "pin_risk_tdpi_vci": "Range Bound Ideas",
                        "low_ssi_warning": "Cautionary Notes"
                    },
                    "min_directional_trades_stars_to_issue": 3, "min_volatility_plays_stars_to_issue": 2,
                    "min_range_bound_ideas_stars_to_issue": 2, "min_cautionary_notes_stars_to_issue": 1,
                    "conviction_map_high": 3.8, "conviction_map_high_medium": 2.8, "conviction_map_medium": 1.8,
                    "conviction_map_medium_low": 0.8, "conviction_map_low": 0.3,
                    "conv_mod_positive_gib": 0.6, "conv_mod_negative_gib": -0.4,
                    "conv_mod_positive_gib_thresh": 10e9, "conv_mod_negative_gib_thresh": -10e9,
                    "conv_mod_very_negative_gib": -1.0, "conv_mod_very_negative_gib_thresh": -50e9,
                    "conv_mod_nvp_confirms_strike": 0.5, "conv_mod_nvp_opposes_strike": -0.8,
                    "conv_mod_high_nvp_thresh_pos": 20e6, "conv_mod_high_nvp_thresh_neg": -20e6,
                    "conv_mod_opposing_nvp_thresh_pos": 5e6, "conv_mod_opposing_nvp_thresh_neg": -5e6,
                    "conv_mod_ssi_low": -0.7, "conv_mod_ssi_high": 0.15,
                    "conv_mod_ssi_low_thresh": 0.4, "conv_mod_ssi_high_thresh": 0.65,
                    "conv_mod_rolling_flow_confirms": 0.6, "conv_mod_rolling_flow_opposes": -0.9,
                    "conv_mod_strong_rolling_flow_thresh_abs": 80e6,
                    "conv_mod_arfi_divergence_penalty": -1.2,
                    "regime_specific_conviction_boosters_penalties": {
                        "REGIME_BULL_TREND_CONFIRMED": {"directional_trades_bullish_boost": 0.75},
                        "REGIME_BEAR_VOL_EXPANSION": {"directional_trades_bearish_boost": 0.5, "volatility_plays_expansion_boost": 0.5, "all_categories_penalty": -0.2}
                    },
                    "regime_signal_initial_star_boosts": { 
                        "REGIME_BULL_TREND_CONFIRMED": {"directional_bullish_mspi": 0.5}
                    }
                }
            }
        }
        def get_setting(self, key_path: Union[str, List[str]], default_value_to_return: Any = None, quiet: bool = False) -> Any: # Added default_value_to_return
            keys = key_path.split('.') if isinstance(key_path, str) else key_path; val = self._cfg
            try:
                for k in keys: val = val[k]
                return val if val is not None else default_value_to_return
            except KeyError: return default_value_to_return
            except TypeError: return default_value_to_return # Handle if intermediate key is not a dict
    
    class MockOrchestratorForReco:
        def __init__(self, cfg_mgr): self.cm = cfg_mgr
        def map_score_to_stars(self, score: float, category: str = "") -> int:
            reco_cfg = self.cm.get_setting("strategy_settings.recommendations", {})
            if score >= reco_cfg.get("conviction_map_high", 4.0): return 5
            if score >= reco_cfg.get("conviction_map_high_medium", 3.0): return 4
            if score >= reco_cfg.get("conviction_map_medium", 2.0): return 3
            if score >= reco_cfg.get("conviction_map_medium_low", 1.0): return 2
            if score >= reco_cfg.get("conviction_map_low", 0.5): return 1
            return 0
        col_strike_orch = "strike_val_test"; col_und_price_orch = "px_last_test"; mspi_col = "mspi"
        nvp_strike_col = "nvp_strike"; ssi_col = "ssi_agg"; gib_oi_und_col = "GIB_OI_based_Und"
        rolling_net_value_flow_15m_col = "NetValueFlow_15m_Und"
        def _get_config_setting_its(self, path: List[str], default_val_param: Any = None, quiet: bool = False) -> Any: # Renamed param
            return self.cm.get_setting(path, default_value_to_return=default_val_param, quiet=quiet)


    test_reco_cm = MockCMForReco()
    test_reco_orch_ref = MockOrchestratorForReco(test_reco_cm)
    reco_gen = RecommendationGeneratorV2_4(config_manager_instance=test_reco_cm, orchestrator_ref=test_reco_orch_ref)

    sample_signals_dict = {
        'directional': {
            'bullish': [
                {'type': 'directional_bullish_mspi', 'strike_val_test': 150.0, 'base_conviction_score_signal_level': 2.5, 'current_market_regime_at_signal_time': 'REGIME_BULL_TREND_CONFIRMED'},
                {'type': 'directional_bullish_sdag', 'strike_val_test': 152.0, 'base_conviction_score_signal_level': 2.0, 'current_market_regime_at_signal_time': 'REGIME_NEUTRAL'}
            ],
            'bearish': []
        },
        'complex': {
            'flow_divergence': [ 
                 {'type': 'flow_divergence_bearish_warning', 'strike_val_test': 150.0, 'base_conviction_score_signal_level': 1.0, 'current_market_regime_at_signal_time': 'REGIME_BULL_TREND_CONFIRMED'}
            ]
        }
    }
    sample_strikes_df = pd.DataFrame({
        "strike_val_test": [150.0, 152.0], 
        "mspi": [0.7, 0.65],
        "nvp_strike": [30e6, 5e6],
        "ssi_agg": [0.75, 0.5]
    })
    sample_und_data = {
        "px_last_test": 151.00, 
        "GIB_OI_based_Und": 20e9, 
        "NetValueFlow_15m_Und": 90e6, 
        "vri_0dte_und_sum": 0.0, "vfi_0dte_und_sum": 0.0, "vci_0dte_agg": 0.0, "HP_EOD_Und": 0.0
    }
    sample_regime = "REGIME_BULL_TREND_CONFIRMED"
    sample_time = datetime.now()
    sample_symbol = "TESTRECO"

    recommendations_out = reco_gen.formulate_recommendations_v2_4(
        sample_signals_dict, sample_strikes_df, sample_und_data, sample_regime, sample_time, sample_symbol
    )

    test_logger_reco.info(f"\n--- Generated Recommendations ({len(recommendations_out)}) ---")
    for i, reco in enumerate(recommendations_out):
        test_logger_reco.info(f"Reco {i+1}: ID={reco['id']}, Cat={reco['category']}, Bias={reco['bias']}, "
                              f"Stars={reco['conviction_stars_final']}, Score={reco['conviction_score_final']:.2f}")
        test_logger_reco.info(f"  Rationale: {reco['rationale_full']}")
        test_logger_reco.info(f"  Key Metrics: {reco['key_metrics_at_issuance']}")

    assert len(recommendations_out) > 0, "Expected at least one recommendation from test."
    test_logger_reco.info("RecommendationGeneratorV2_4 - Standalone test execution finished.")
