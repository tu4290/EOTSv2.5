# dashboard_application/modes/volatility_mode_display.py
# (Elite Version 2.4 - Co-Pilot - Display Logic for Volatility Deep Dive Mode)

# Standard Library Imports
import logging
import time as pytime
import importlib
import sys
import inspect
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List, Union, Deque, Callable
import traceback
from collections import deque

# Third-Party Imports
import pandas as pd
import numpy as np
import dash
from dash import html, dcc, callback, Input, Output, State, no_update, ctx
import plotly.graph_objects as go
import dash_bootstrap_components as dbc

# EOTS V2.4 Dashboard Imports (from parent package)
try:
    from ..utils_dashboard import (
        get_config_value, create_empty_figure,
        add_timestamp_annotation, add_price_line,
        PLOTLY_TEMPLATE_FOR_UTILS_MODULE as PLOTLY_TEMPLATE_VOL_MODE # Use the resolved template
    )
    # For hover text, you might have a shared utility or adapt simplified versions
    # from ..utils_dashboard import create_custom_hover_text_utility 
    _utils_imported_successfully_vol = True
except ImportError as e_util_vol_disp:
    logging.getLogger(__name__).critical(f"CRITICAL Import Error in volatility_mode_display.py for utils: {e_util_vol_disp}. Visuals may fail.")
    _utils_imported_successfully_vol = False
    # Minimal fallbacks for functions if utils are missing
    def get_config_value(cfg, path, default): return default
    def create_empty_figure(title, height=None, reason="", config=None): return go.Figure().update_layout(title=title, height=height or 400)
    def add_timestamp_annotation(fig, ts, cfg=None): return fig
    def add_price_line(fig, price, orientation="v", cfg=None, **kwargs): return fig
    PLOTLY_TEMPLATE_VOL_MODE = {"layout": go.Layout(template="plotly_dark")}
    # def create_custom_hover_text_utility(row_data, config, chart_specific_rules): return "Hover N/A"


# --- Module-Specific Logger ---
logger = logging.getLogger(__name__) # e.g., dashboard_application.modes.volatility_mode_display


# --- Helper function for creating hover text (can be moved to utils if more complex) ---
def _create_vol_hover_text(row_data: Union[pd.Series, Dict[str,Any]], 
                           base_metric_key: str, # e.g., "vri_sensitivity", "vri_0dte"
                           config: Optional[Dict[str, Any]],
                           strike_col: str) -> str:
    parts = []
    strike_val = row_data.get(strike_col)
    parts.append(f"<b>Strike: {strike_val:.2f}</b>" if pd.notna(strike_val) else "Strike: N/A")
    
    metric_val = row_data.get(base_metric_key)
    parts.append(f"{base_metric_key.replace('_',' ').title()}: {metric_val:.3g}" if pd.notna(metric_val) else f"{base_metric_key.replace('_',' ').title()}: N/A")

    # Add other relevant context from row_data if needed for specific vol charts
    if base_metric_key == "vri_sensitivity":
        if pd.notna(row_data.get("vvr_sens_strike")): parts.append(f"VVR (Sens): {row_data.get('vvr_sens_strike'):.2f}")
        if pd.notna(row_data.get("vfi_sens_strike")): parts.append(f"VFI (Sens): {row_data.get('vfi_sens_strike'):.2f}")
    elif base_metric_key == "vri_0dte":
        if pd.notna(row_data.get("vvr_0dte")): parts.append(f"VVR (0DTE): {row_data.get('vvr_0dte'):.2f}")
        if pd.notna(row_data.get("vfi_0dte")): parts.append(f"VFI (0DTE): {row_data.get('vfi_0dte'):.2f}")
        if pd.notna(row_data.get("abs_vannaxoi_contract")): parts.append(f"AbsVannaOI: {row_data.get('abs_vannaxoi_contract'):.0f}")

    return "<br>".join(parts) + "<extra></extra>"


# --- Chart Generation Functions for Volatility Deep Dive Mode ---

def generate_vri_sensitivity_strike_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = "VRI Sensitivity by Strike"
    logger.info(f"Generating: {chart_name}")
    
    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    # Assuming vri_sensitivity is the key in df_strike_metrics
    cfg_vri_sens_col = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "column_names", "vri_sensitivity"], "vri_sensitivity") 
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")

    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 600)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"

    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Strike metrics list empty", config=app_config)
    
    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        required_cols = [cfg_strike_col, cfg_vri_sens_col]
        if not all(col in df_strikes.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_strikes.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing: {missing}", config=app_config)

        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        df_strikes[cfg_vri_sens_col] = pd.to_numeric(df_strikes[cfg_vri_sens_col], errors='coerce')
        df_plot = df_strikes.dropna(subset=[cfg_strike_col, cfg_vri_sens_col]).sort_values(by=cfg_strike_col)

        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Data", height=fig_height, reason="No valid data after cleaning", config=app_config)

        hover_texts = [_create_vol_hover_text(row, cfg_vri_sens_col, app_config, cfg_strike_col) for _, row in df_plot.iterrows()]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_plot[cfg_strike_col],
            y=df_plot[cfg_vri_sens_col],
            name="VRI Sensitivity",
            marker_color=['crimson' if v < 0 else 'mediumseagreen' for v in df_plot[cfg_vri_sens_col]],
            hovertext=hover_texts,
            hoverinfo="text"
        ))
        
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, xaxis_title='Strike', yaxis_title='VRI Sensitivity Value',
            template=PLOTLY_TEMPLATE_VOL_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, hovermode="x unified",
            **PLOTLY_TEMPLATE_VOL_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='vertical', app_config=app_config)
    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig


def generate_vri_0dte_strike_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    # This chart shows per-strike vri_0dte, which means it likely needs df_chain_metrics
    # if vri_0dte is calculated per-contract and then needs aggregation (e.g., sum or mean) per strike.
    # Or, if MetricsCalculator already produces a strike-level summary of vri_0dte in df_strike_metrics.
    # The orchestrator currently sums per-contract vri_0dte to df_strike_metrics.
    chart_name = "VRI 0DTE by Strike"
    logger.info(f"Generating: {chart_name}")

    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_vri_0dte_col = "vri_0dte" # This is the key in df_strike_metrics from orchestrator's aggregation
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")
    
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 600)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name} (0DTE Options)"

    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Strike metrics list empty", config=app_config)

    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        # Filter for 0DTE if not already done or if mixed DTEs could be in df_strike_metrics
        if 'dte_calc' in df_strikes.columns:
            df_strikes = df_strikes[pd.to_numeric(df_strikes['dte_calc'], errors='coerce') == 0]
        
        required_cols = [cfg_strike_col, cfg_vri_0dte_col]
        if not all(col in df_strikes.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_strikes.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing for 0DTE plot: {missing}", config=app_config)

        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        df_strikes[cfg_vri_0dte_col] = pd.to_numeric(df_strikes[cfg_vri_0dte_col], errors='coerce')
        df_plot = df_strikes.dropna(subset=[cfg_strike_col, cfg_vri_0dte_col]).sort_values(by=cfg_strike_col)
        
        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid 0DTE Data", height=fig_height, reason="No valid 0DTE data after cleaning", config=app_config)

        hover_texts = [_create_vol_hover_text(row, cfg_vri_0dte_col, app_config, cfg_strike_col) for _, row in df_plot.iterrows()]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_plot[cfg_strike_col],
            y=df_plot[cfg_vri_0dte_col],
            name="VRI (0DTE)",
            marker_color=['darkcyan' if v < 0 else 'goldenrod' for v in df_plot[cfg_vri_0dte_col]],
            hovertext=hover_texts,
            hoverinfo="text"
        ))
        
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, xaxis_title='Strike (0DTE)', yaxis_title='VRI (0DTE) Strike Aggregate',
            template=PLOTLY_TEMPLATE_VOL_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, hovermode="x unified",
            **PLOTLY_TEMPLATE_VOL_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='vertical', app_config=app_config)
    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig


def generate_vvr_0dte_agg_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], # For trend line
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = "VVR 0DTE Aggregate"
    logger.info(f"Generating: {chart_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "gauge_height"], 250)
    
    und_data = analysis_bundle.get("und_data_aggregates", {})
    # Orchestrator sums 'vvr_0dte' (per-contract) to 'vvr_0dte_und_sum' in und_data_aggregates.
    # A simple sum might not be ideal for a ratio. Average or a weighted average might be better.
    # For now, let's assume 'vvr_0dte_und_avg' or similar exists, or we calculate from history if available.
    # If using 'vvr_0dte_und_sum', the gauge scale needs to be appropriate.
    # Let's assume for a gauge we want an 'average' like value.
    # If 'chart_history' has DataFrames with 'vvr_0dte' per strike/contract, we could average it.
    # For simplicity of a single gauge, let's check if an aggregate like 'vvr_0dte_und_avg' is calculated.
    # If not, we'll use chart_history to plot a trend.
    
    # Let's plot a trend using chart_history
    symbol = analysis_bundle.get("symbol", "N/A")
    current_ts_iso = analysis_bundle.get("timestamp", datetime.now().isoformat())
    current_ts_dt = datetime.fromisoformat(current_ts_iso.replace("Z","+00:00")) if current_ts_iso else datetime.now()

    # Extracting average VVR 0DTE from history
    times = []
    vvr_values = []
    if chart_history:
        for ts_epoch, df_metrics_hist in chart_history:
            if 'vvr_0dte' in df_metrics_hist.columns and 'dte_calc' in df_metrics_hist.columns:
                df_0dte_hist = df_metrics_hist[pd.to_numeric(df_metrics_hist['dte_calc'], errors='coerce') == 0]
                if not df_0dte_hist.empty and pd.to_numeric(df_0dte_hist['vvr_0dte'], errors='coerce').notna().any():
                    # Avoid inf values in mean calculation
                    valid_vvr = df_0dte_hist['vvr_0dte'][np.isfinite(pd.to_numeric(df_0dte_hist['vvr_0dte'], errors='coerce'))]
                    if not valid_vvr.empty :
                        times.append(datetime.fromtimestamp(ts_epoch))
                        vvr_values.append(pd.to_numeric(valid_vvr, errors='coerce').mean())
    
    # Add current value if available from und_data_aggregates (e.g. if MetricsCalculator computes an avg)
    current_vvr_avg = und_data.get("vvr_0dte_und_avg") # Hypothetical key for aggregated average
    if current_vvr_avg is None and 'vvr_0dte_und_sum' in und_data and 'vvr_0dte_count' in und_data and und_data['vvr_0dte_count'] > 0:
        current_vvr_avg = und_data['vvr_0dte_und_sum'] / und_data['vvr_0dte_count'] # Calculate avg if sum and count available

    if current_vvr_avg is not None and pd.notna(current_vvr_avg):
        times.append(current_ts_dt)
        vvr_values.append(float(current_vvr_avg))

    if not times or not vvr_values:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="VVR 0DTE data missing", config=app_config)

    # Sort by time for plotting
    sorted_times_vvrs = sorted(zip(times, vvr_values))
    plot_times, plot_vvrs = zip(*sorted_times_vvrs) if sorted_times_vvrs else ([], [])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(plot_times), y=list(plot_vvrs), mode='lines+markers', name='Avg VVR 0DTE',
        line=dict(color=COLOR_PRIMARY, width=2), marker=dict(size=6)
    ))
    
    # Add threshold lines from config
    vvr_cascade_thresh = get_config_value(app_config, ["strategy_settings", "thresholds", "vvr_cascade_thresh"], 1.5)
    if vvr_cascade_thresh is not None:
        fig.add_hline(y=vvr_cascade_thresh, line_dash="dash", line_color=COLOR_DANGER,
                      annotation_text=f"Cascade Thresh ({vvr_cascade_thresh})", annotation_position="bottom right")

    current_val_str = f"Current Avg: {plot_vvrs[-1]:.2f}" if plot_vvrs else "N/A"
    chart_title_full = f"<b>{symbol.upper()}</b> - {chart_name}<br><span style='font-size:0.8em;color:grey'>{current_val_str}</span>"

    fig.update_layout(
        title=chart_title_full,
        height=fig_height,
        template=PLOTLY_TEMPLATE_VOL_MODE.get("layout", {}).get("template", "plotly_dark"),
        yaxis_title="Avg VVR (0DTE)",
        hovermode="x unified",
        **PLOTLY_TEMPLATE_VOL_MODE.get("layout", {})
    )
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig

# --- Placeholder for other Volatility Mode charts ---
def generate_vfi_0dte_agg_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    # Similar logic to vvr_0dte_agg_viz_figure, plotting a trend of average VFI 0DTE
    chart_name = "VFI 0DTE Aggregate Trend"
    logger.info(f"Generating: {chart_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "gauge_height"], 250)
    symbol = analysis_bundle.get("symbol", "N/A")
    current_ts_iso = analysis_bundle.get("timestamp", datetime.now().isoformat())
    current_ts_dt = datetime.fromisoformat(current_ts_iso.replace("Z","+00:00")) if current_ts_iso else datetime.now()
    
    und_data = analysis_bundle.get("und_data_aggregates", {})
    times, vfi_values = [], []
    if chart_history:
        for ts_epoch, df_metrics_hist in chart_history:
            if 'vfi_0dte' in df_metrics_hist.columns and 'dte_calc' in df_metrics_hist.columns:
                df_0dte_hist = df_metrics_hist[pd.to_numeric(df_metrics_hist['dte_calc'], errors='coerce') == 0]
                if not df_0dte_hist.empty and pd.to_numeric(df_0dte_hist['vfi_0dte'], errors='coerce').notna().any():
                    valid_vfi = df_0dte_hist['vfi_0dte'][np.isfinite(pd.to_numeric(df_0dte_hist['vfi_0dte'], errors='coerce'))]
                    if not valid_vfi.empty: times.append(datetime.fromtimestamp(ts_epoch)); vfi_values.append(pd.to_numeric(valid_vfi, errors='coerce').mean())
    
    current_vfi_avg = und_data.get("vfi_0dte_und_avg") # Hypothetical
    if current_vfi_avg is None and 'vfi_0dte_und_sum' in und_data and 'vfi_0dte_count' in und_data and und_data['vfi_0dte_count'] > 0:
        current_vfi_avg = und_data['vfi_0dte_und_sum'] / und_data['vfi_0dte_count']

    if current_vfi_avg is not None and pd.notna(current_vfi_avg): times.append(current_ts_dt); vfi_values.append(float(current_vfi_avg))
    if not times or not vfi_values: return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, config=app_config)
    sorted_times_vfis = sorted(zip(times, vfi_values)); plot_times, plot_vfis = zip(*sorted_times_vfis) if sorted_times_vfis else ([], [])
    fig = go.Figure(); fig.add_trace(go.Scatter(x=list(plot_times), y=list(plot_vfis), mode='lines+markers', name='Avg VFI 0DTE', line=dict(color=COLOR_SUCCESS, width=2)))
    vfi_high_thresh = get_config_value(app_config, ["strategy_settings", "thresholds", "vfi0dte_expansion_thresh"], 1.2)
    if vfi_high_thresh is not None: fig.add_hline(y=vfi_high_thresh, line_dash="dash", line_color=COLOR_WARNING, annotation_text=f"High Thresh ({vfi_high_thresh})")
    current_val_str = f"Current Avg: {plot_vfis[-1]:.2f}" if plot_vfis else "N/A"
    chart_title_full = f"<b>{symbol.upper()}</b> - {chart_name}<br><span style='font-size:0.8em;color:grey'>{current_val_str}</span>"
    fig.update_layout(title=chart_title_full, height=fig_height, template=PLOTLY_TEMPLATE_VOL_MODE.get("layout",{}).get("template"), yaxis_title="Avg VFI (0DTE)", hovermode="x unified", **PLOTLY_TEMPLATE_VOL_MODE.get("layout",{}))
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig


def generate_skew_factor_global_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    # This would plot the SkewFactor_Global from und_data_aggregates, likely as a trend line using chart_history
    chart_name = "Global Skew Factor Trend"
    logger.info(f"Generating: {chart_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "gauge_height"], 250)
    symbol = analysis_bundle.get("symbol", "N/A")
    current_ts_iso = analysis_bundle.get("timestamp", datetime.now().isoformat())
    current_ts_dt = datetime.fromisoformat(current_ts_iso.replace("Z","+00:00")) if current_ts_iso else datetime.now()
    
    und_data = analysis_bundle.get("und_data_aggregates", {})
    times, skew_values = [], []
    # Assuming 'SkewFactor_Global' might be a key in und_data if metrics_calculator adds it there or orchestrator.
    # Or, if it's part of a specific calculation that's stored, e.g., within VRI components.
    # For simplicity, let's assume it's available in und_data_aggregates from each history point.
    if chart_history:
        for ts_epoch, data_bundle_hist in chart_history: # Assuming history stores full bundle or und_data
            # If history stores df_strike_metrics, this logic needs to change
            # Assuming history stores dict like und_data_aggregates for each point
            if isinstance(data_bundle_hist, dict) and "SkewFactor_Global" in data_bundle_hist:
                skew_val_hist = data_bundle_hist.get("SkewFactor_Global")
                if skew_val_hist is not None and pd.notna(skew_val_hist):
                    times.append(datetime.fromtimestamp(ts_epoch))
                    skew_values.append(float(skew_val_hist))

    current_skew = und_data.get("SkewFactor_Global") # Expected from MetricsCalculator->VRI calculation context
    if current_skew is not None and pd.notna(current_skew):
        times.append(current_ts_dt)
        skew_values.append(float(current_skew))

    if not times or not skew_values:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, config=app_config)

    sorted_times_skews = sorted(zip(times, skew_values)); plot_times, plot_skews = zip(*sorted_times_skews) if sorted_times_skews else ([], [])
    fig = go.Figure(); fig.add_trace(go.Scatter(x=list(plot_times), y=list(plot_skews), mode='lines+markers', name='Global Skew Factor', line=dict(color=TEXT_SECONDARY_ON_DARK, width=2)))
    current_val_str = f"Current: {plot_skews[-1]:.3f}" if plot_skews else "N/A"
    chart_title_full = f"<b>{symbol.upper()}</b> - {chart_name}<br><span style='font-size:0.8em;color:grey'>{current_val_str}</span>"
    fig.update_layout(title=chart_title_full, height=fig_height, template=PLOTLY_TEMPLATE_VOL_MODE.get("layout",{}).get("template"), yaxis_title="Skew Factor", hovermode="x unified", yaxis_zeroline=True, **PLOTLY_TEMPLATE_VOL_MODE.get("layout",{}))
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig


def generate_iv_term_structure_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return create_empty_figure(title="IV Term Structure - Placeholder", height=get_config_value(app_config,["visualization_settings","dashboard","default_graph_height"]), config=app_config)

def generate_historical_iv_rank_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    # This would show current IV from und_data_aggregates vs its historical rank/percentile
    # (if HistoricalDataManager provides this rank, or if Orchestrator calculates it from history)
    chart_name = "IV Rank/Percentile"
    logger.info(f"Generating: {chart_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "gauge_height"], 250)
    symbol = analysis_bundle.get("symbol", "N/A")
    und_data = analysis_bundle.get("und_data_aggregates", {})
    
    # Fetch from app_config which column in und_data holds the IV Rank
    iv_rank_col_cfg = get_config_value(app_config, ["data_processor_settings", "iv_context_parameters", "iv_rank_col_from_und"], "u_iv_rank_30d") # default if not in config
    iv_rank_val = und_data.get(iv_rank_col_cfg) # This should be a percentile (0-100)
    current_iv_val = und_data.get(get_config_value(app_config, ["strategy_settings", "option_volatility_col_name"], "volatility"))


    if iv_rank_val is None or pd.isna(iv_rank_val):
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason=f"'{iv_rank_col_cfg}' missing", config=app_config)
    
    iv_rank = float(iv_rank_val)

    fig = go.Figure(go.Indicator(
        mode = "gauge+number", value = iv_rank,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': f"<b>IV Rank/Pctile</b><br><span style='font-size:0.7em;color:grey'>(Source: {iv_rank_col_cfg})</span><br><span style='font-size:0.8em;color:grey'>Curr IV: {current_iv_val:.2%}</span>", 'font': {'size': 14}},
        number = {'suffix': "%", 'font': {'size':30}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickvals': [0,25,50,75,100]},
            'bar': {'color': "darkblue"},
            'steps': [ {'range': [0, 25], 'color': "lightgreen"}, {'range': [25, 75], 'color': "lightyellow"}, {'range': [75, 100], 'color': "lightcoral"}],
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': iv_rank}}))
    fig.update_layout(height=fig_height, margin=dict(l=20,r=20,t=60,b=20), template=PLOTLY_TEMPLATE_VOL_MODE.get("layout",{}).get("template"), paper_bgcolor="rgba(0,0,0,0)", font={'color': TEXT_PRIMARY_ON_DARK})
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig


logger.info("volatility_mode_display.py loaded and chart generation functions defined.")