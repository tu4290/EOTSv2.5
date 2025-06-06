# core_analytics_engine/key_level_identifier_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Union

import pandas as pd # type: ignore
import numpy as np # type: ignore

# Assuming Pydantic models are accessible
try:
    from ..pydantic_models_v2_5 import KeyLevelV2_5
except ImportError:
    # Fallback placeholder if direct run or structure issue
    class KeyLevelV2_5(BaseModel): # type: ignore
        level_price: float
        level_type: str
        conviction_score: float
        contributing_metrics: List[str] = []
        source_component: Optional[str] = None

        class Config: # Basic Pydantic config
            extra = 'ignore'


# --- Module-Specific Logger ---
logger = logging.getLogger(__name__)

class KeyLevelIdentifierV2_5:
    '''
    Identifies and scores significant price levels (Support, Resistance, Walls, Triggers, PinZones)
    for EOTS V2.5, using a variety of metrics and confluence analysis.
    '''

    def __init__(self, config_manager_v2_5_instance: Any):
        self.logger = logger.getChild(self.__class__.__name__)

        if not hasattr(config_manager_v2_5_instance, 'get_setting'):
            self.logger.critical(f"{self.__class__.__name__} initialized with an invalid ConfigManagerV2_5. Critical failure.")
            class DummyCM:
                def get_setting(self, *args, default_value_to_return=None, **kwargs): return default_value_to_return
            self.config_manager = DummyCM() # type: ignore
        else:
            self.config_manager = config_manager_v2_5_instance

        self.logger.info(f"Initializing KeyLevelIdentifierV2_5...")
        self._load_config_settings()
        self.logger.info("KeyLevelIdentifierV2_5 Initialized.")

    def _load_config_settings(self):
        '''Loads settings specific to the Key Level Identifier.'''
        self.logger.debug("Loading Key Level Identifier specific configurations...")
        base_path = ["key_level_identifier_settings"] # Path in config_v2_5.json

        self.enabled_level_sources: List[str] = self.config_manager.get_setting(
            *base_path, "enabled_sources",
            default_value_to_return=["A_MSPI", "NVP", "SGDHP_Data", "UGCH_Data", "E_SDAG_VF_Triggers", "0DTE_Pin_Zones"]
        )

        # Thresholds for identifying levels from different sources
        # Example: A-MSPI peak significance
        self.a_mspi_threshold_abs: float = float(self.config_manager.get_setting(*base_path, "a_mspi_peak_threshold_abs", default_value_to_return=30.0))
        # Example: NVP peak significance (e.g., top N peaks or percentile)
        self.nvp_num_peaks_to_consider: int = int(self.config_manager.get_setting(*base_path, "nvp_num_peaks", default_value_to_return=5))
        # Example: SGDHP/UGCH score thresholds
        self.sgdhp_score_threshold_strong: float = float(self.config_manager.get_setting(*base_path, "sgdhp_score_strong_abs", default_value_to_return=70.0))
        self.ugch_score_threshold_strong: float = float(self.config_manager.get_setting(*base_path, "ugch_score_strong_abs", default_value_to_return=60.0))
        # Example: E-SDAG_VF trigger threshold
        self.e_sdag_vf_trigger_threshold: float = float(self.config_manager.get_setting(*base_path, "e_sdag_vf_trigger_level", default_value_to_return=-0.8)) # Typically very negative

        # Conviction scoring parameters
        self.conviction_base_score: Dict[str, float] = self.config_manager.get_setting(*base_path, "conviction_base_scores", default_value_to_return={"A_MSPI": 0.5, "NVP": 0.6, "SGDHP_Data": 0.8, "UGCH_Data": 0.7})
        self.conviction_confluence_bonus: float = float(self.config_manager.get_setting(*base_path, "conviction_confluence_bonus", default_value_to_return=0.25))
        self.max_conviction_score: float = float(self.config_manager.get_setting(*base_path, "max_conviction_score", default_value_to_return=1.0)) # Or 5.0 for stars

        # Column name mappings (from where to read metrics in df_strike_level_metrics)
        # These should align with output from MetricsCalculatorV2_5
        strike_metrics_cols_path = ["column_name_mappings", "strike_level_metric_cols"] # Example path
        self.col_strike: str = self.config_manager.get_setting(*strike_metrics_cols_path, "strike_col", default_value_to_return="strike")
        self.col_a_mspi: str = self.config_manager.get_setting(*strike_metrics_cols_path, "a_mspi_col", default_value_to_return="a_mspi_strike")
        self.col_nvp: str = self.config_manager.get_setting(*strike_metrics_cols_path, "nvp_col", default_value_to_return="nvp_strike")
        self.col_sgdhp_score: str = self.config_manager.get_setting(*strike_metrics_cols_path, "sgdhp_score_col", default_value_to_return="sgdhp_score_strike")
        self.col_ugch_score: str = self.config_manager.get_setting(*strike_metrics_cols_path, "ugch_score_col", default_value_to_return="ugch_score_strike")
        self.col_e_sdag_vf: str = self.config_manager.get_setting(*strike_metrics_cols_path, "e_sdag_vf_col", default_value_to_return="e_sdag_vf_strike_norm")
        self.col_d_tdpi: str = self.config_manager.get_setting(*strike_metrics_cols_path, "d_tdpi_col", default_value_to_return="d_tdpi_strike_norm")

        # Underlying data metric keys (for 0DTE context)
        und_metrics_cols_path = ["column_name_mappings", "underlying_metric_keys"] # Example path
        self.key_vci_0dte_agg = self.config_manager.get_setting(*und_metrics_cols_path, "vci_0dte_aggregate_key", default_value_to_return="vci_0dte_agg")

        self.logger.debug("KeyLevelIdentifierV2_5 configurations loaded.")

    def _find_peaks(self, series: pd.Series, threshold: float) -> pd.Index:
        '''Helper to find peaks (local maxima) in a series above a threshold.'''
        # Basic peak finding, can be made more robust (e.g. scipy.signal.find_peaks)
        series_abs = series.abs()
        peaks = series_abs[(series_abs.shift(1) < series_abs) & (series_abs.shift(-1) < series_abs) & (series_abs > threshold)]
        return peaks.index

    def _identify_levels_from_a_mspi(self, df_strike_metrics: pd.DataFrame) -> List[Dict[str, Any]]:
        levels = []
        if self.col_a_mspi not in df_strike_metrics.columns or df_strike_metrics.empty:
            return levels

        # Find significant positive (support) and negative (resistance) A-MSPI values/peaks
        # This is a simplified approach; peak finding or threshold crossing might be better.
        # For now, using a simple absolute threshold.
        potential_s_r = df_strike_metrics[df_strike_metrics[self.col_a_mspi].abs() >= self.a_mspi_threshold_abs]
        for idx, row in potential_s_r.iterrows():
            level_type = "Support" if row[self.col_a_mspi] > 0 else "Resistance"
            levels.append({
                "level_price": row[self.col_strike],
                "level_type": level_type,
                "initial_score": abs(row[self.col_a_mspi]), # Score based on magnitude
                "source": "A_MSPI"
            })
        self.logger.debug(f"Identified {len(levels)} potential levels from A-MSPI.")
        return levels

    def _identify_levels_from_nvp(self, df_strike_metrics: pd.DataFrame) -> List[Dict[str, Any]]:
        levels = []
        if self.col_nvp not in df_strike_metrics.columns or df_strike_metrics.empty:
            return levels

        # Consider top N NVP absolute peaks as S/R
        nvp_abs_sorted = df_strike_metrics.loc[df_strike_metrics[self.col_nvp].abs().sort_values(ascending=False).index]
        top_nvp_levels = nvp_abs_sorted.head(self.nvp_num_peaks_to_consider)

        for idx, row in top_nvp_levels.iterrows():
            # NVP sign: Positive NVP = net customer buying (dealers selling, so resistance if calls, support if puts)
            # This needs careful mapping based on call/put NVP or overall net NVP interpretation.
            # For simplicity here, assume positive NVP indicates strong interest, could be S or R.
            # A more detailed implementation would look at call NVP vs put NVP at the strike.
            # For now, just flagging as "NVP_Level" and relying on price proximity for S/R typing later.
            level_type = "NVP_Level_S" if row[self.col_nvp] > 0 else "NVP_Level_R" # Tentative based on sign
            levels.append({
                "level_price": row[self.col_strike],
                "level_type": level_type, # Will be refined
                "initial_score": abs(row[self.col_nvp]),
                "source": "NVP"
            })
        self.logger.debug(f"Identified {len(levels)} potential levels from NVP peaks.")
        return levels

    # ... Placeholder methods for _identify_levels_from_sgdhp, _identify_levels_from_ugch, etc. ...
    def _identify_levels_from_heatmap_data(self, df_strike_metrics: pd.DataFrame, metric_col: str, threshold: float, source_name: str, level_type_suffix: str) -> List[Dict[str, Any]]:
        levels = []
        if metric_col not in df_strike_metrics.columns or df_strike_metrics.empty:
            return levels

        potential_levels = df_strike_metrics[df_strike_metrics[metric_col].abs() >= threshold]
        for idx, row in potential_levels.iterrows():
            # Sign of score determines S (positive) or R (negative) for SGDHP/UGCH
            level_t = "Support" if row[metric_col] > 0 else "Resistance"
            levels.append({
                "level_price": row[self.col_strike],
                "level_type": f"{level_t}_{level_type_suffix}",
                "initial_score": abs(row[metric_col]),
                "source": source_name
            })
        self.logger.debug(f"Identified {len(levels)} potential levels from {source_name} (col: {metric_col}).")
        return levels


    def _identify_vol_triggers(self, df_strike_metrics: pd.DataFrame) -> List[Dict[str, Any]]:
        levels = []
        if self.col_e_sdag_vf not in df_strike_metrics.columns or df_strike_metrics.empty:
            return levels
        trigger_levels = df_strike_metrics[df_strike_metrics[self.col_e_sdag_vf] <= self.e_sdag_vf_trigger_threshold]
        for idx, row in trigger_levels.iterrows():
            levels.append({
                "level_price": row[self.col_strike],
                "level_type": "VolTrigger",
                "initial_score": abs(row[self.col_e_sdag_vf]), # Higher magnitude = stronger trigger potential
                "source": "E_SDAG_VF"
            })
        self.logger.debug(f"Identified {len(levels)} potential VolTriggers from E_SDAG_VF.")
        return levels

    def _identify_0dte_pin_zones(self, df_strike_metrics: pd.DataFrame, underlying_data: Dict[str, Any], current_price: float) -> List[Dict[str, Any]]:
        levels = []
        # This needs D-TDPI at strike, VCI_0DTE_Agg from underlying_data, and TickerContext for 0DTE status.
        # Placeholder logic
        is_0dte = underlying_data.get("ticker_context_dict_v2_5", {}).get("expiration_context", {}).get("is_0DTE", False)
        if not is_0dte or self.col_d_tdpi not in df_strike_metrics.columns or df_strike_metrics.empty:
            return levels

        # Example: find D-TDPI peaks near current price, check VCI_0DTE_Agg
        # This is highly simplified.
        # Look for high D-TDPI near ATM, especially if VCI_0DTE_Agg is high
        atm_strikes_d_tdpi = df_strike_metrics[
            (df_strike_metrics[self.col_strike] >= current_price * 0.98) &
            (df_strike_metrics[self.col_strike] <= current_price * 1.02) &
            (df_strike_metrics[self.col_d_tdpi].abs() > 0.5) # Arbitrary D-TDPI threshold for example
        ]
        vci_0dte_agg = underlying_data.get(self.key_vci_0dte_agg, 0)

        if vci_0dte_agg > 0.3: # Arbitrary VCI threshold
            for idx, row in atm_strikes_d_tdpi.iterrows():
                 levels.append({
                    "level_price": row[self.col_strike],
                    "level_type": "PinZone",
                    "initial_score": abs(row[self.col_d_tdpi]) * (1 + vci_0dte_agg), # Combine scores
                    "source": "0DTE_Pin_Zone"
                })
        self.logger.debug(f"Identified {len(levels)} potential 0DTE PinZones.")
        return levels


    def _apply_conviction_scoring_and_finalize(self, all_potential_levels: List[Dict[str, Any]], current_price: float) -> List[KeyLevelV2_5]:
        final_levels_dict: Dict[float, KeyLevelV2_5] = {} # Use price as key to merge

        if not all_potential_levels:
            return []

        # Group by level_price to handle confluence
        grouped_by_price = pd.DataFrame(all_potential_levels).groupby("level_price")

        for price_val, group_df in grouped_by_price:
            primary_source_info = group_df.sort_values(by="initial_score", ascending=False).iloc[0]

            final_score = self.conviction_base_score.get(primary_source_info["source"], 0.3) * (primary_source_info["initial_score"] / 100.0) # Normalize initial score roughly
            final_score = min(final_score, self.max_conviction_score * 0.8) # Cap base contribution

            contributing_metrics_list = list(group_df["source"].unique())

            if len(contributing_metrics_list) > 1:
                final_score += self.conviction_confluence_bonus * (len(contributing_metrics_list) -1)

            final_score = min(final_score, self.max_conviction_score)

            # Refine level_type (e.g. NVP_Level_S -> Support)
            level_type_final = primary_source_info["level_type"]
            if "NVP_Level" in level_type_final: # Basic refinement for NVP
                level_type_final = "Support" if price_val < current_price else "Resistance"
            elif "_S_" in level_type_final or level_type_final.endswith("_S"): level_type_final = "Support"
            elif "_R_" in level_type_final or level_type_final.endswith("_R"): level_type_final = "Resistance"
            # Further refinement for "MajorWall" based on SGDHP/UGCH strength could be added

            final_levels_dict[price_val] = KeyLevelV2_5(
                level_price=float(price_val),
                level_type=level_type_final,
                conviction_score=round(final_score, 3),
                contributing_metrics=contributing_metrics_list,
                source_component=primary_source_info["source"]
            )

        self.logger.info(f"Finalized {len(final_levels_dict)} key levels after conviction scoring.")
        return list(final_levels_dict.values())


    def identify_key_levels_v2_5(self,
                                 df_strike_level_metrics: pd.DataFrame,
                                 underlying_data_enriched_obj: Dict[str, Any],
                                 current_price: float
                                 ) -> List[KeyLevelV2_5]: # Returns a list of Pydantic KeyLevelV2_5 objects
        '''
        Main method to identify all key levels using various v2.5 metrics and context.
        '''
        self.logger.info(f"Starting Key Level Identification for {underlying_data_enriched_obj.get('symbol', 'UNKNOWN')} at price {current_price:.2f}")
        all_potential_levels: List[Dict[str, Any]] = []

        if df_strike_level_metrics.empty:
            self.logger.warning("Strike level metrics DataFrame is empty. Cannot identify key levels.")
            return []

        # 1. Identify from A-MSPI
        if "A_MSPI" in self.enabled_level_sources:
            all_potential_levels.extend(self._identify_levels_from_a_mspi(df_strike_level_metrics))

        # 2. Identify from NVP
        if "NVP" in self.enabled_level_sources:
            all_potential_levels.extend(self._identify_levels_from_nvp(df_strike_level_metrics))

        # 3. Identify from Enhanced Heatmap Data (SGDHP, UGCH)
        if "SGDHP_Data" in self.enabled_level_sources:
            all_potential_levels.extend(self._identify_levels_from_heatmap_data(df_strike_level_metrics, self.col_sgdhp_score, self.sgdhp_score_threshold_strong, "SGDHP_Data", "Wall"))
        if "UGCH_Data" in self.enabled_level_sources:
            all_potential_levels.extend(self._identify_levels_from_heatmap_data(df_strike_level_metrics, self.col_ugch_score, self.ugch_score_threshold_strong, "UGCH_Data", "Structure"))

        # 4. Identify Volatility Triggers from E-SDAG_VF
        if "E_SDAG_VF_Triggers" in self.enabled_level_sources:
            all_potential_levels.extend(self._identify_vol_triggers(df_strike_level_metrics))

        # 5. Identify 0DTE Pin Zones
        if "0DTE_Pin_Zones" in self.enabled_level_sources:
             all_potential_levels.extend(self._identify_0dte_pin_zones(df_strike_level_metrics, underlying_data_enriched_obj, current_price))

        # 6. Multi-Timeframe Analysis (Placeholder)
        # self.logger.debug("Multi-timeframe analysis placeholder.")

        # 7. Apply Conviction Scoring and Finalize
        final_levels = self._apply_conviction_scoring_and_finalize(all_potential_levels, current_price)

        # Sort by price for easier consumption
        final_levels.sort(key=lambda x: x.level_price)

        return final_levels

    def shutdown(self):
        self.logger.info(f"KeyLevelIdentifierV2_5 ({self.__class__.__name__}) shutdown called.")
