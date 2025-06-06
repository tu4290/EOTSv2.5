# dashboard_application/modes/time_decay_mode_display.py
# (Elite Version 2.4 - Co-Pilot - Display Logic for Time Decay & Pinning Mode)

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
        PLOTLY_TEMPLATE_FOR_UTILS_MODULE as PLOTLY_TEMPLATE_TIMEDECAY_MODE
    )
    _utils_imported_successfully_td = True
except ImportError as e_util_td_disp:
    logging.getLogger(__name__).critical(f"CRITICAL Import Error in time_decay_mode_display.py for utils: {e_util_td_disp}. Visuals may fail.")
    _utils_imported_successfully_td = False
    def get_config_value(cfg, path, default): return default
    def create_empty_figure(title, height=None, reason="", config=None): return go.Figure().update_layout(title=title, height=height or 400)
    def add_timestamp_annotation(fig, ts, cfg=None): return fig
    def add_price_line(fig, price, orientation="v", cfg=None, **kwargs): return fig
    PLOTLY_TEMPLATE_TIMEDECAY_MODE = {"layout": go.Layout(template="plotly_dark")}

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__) # e.g., dashboard_application.modes.time_decay_mode_display

# --- Reusable Hover Text Logic (Simplified - Adapt or use utility) ---
def _create_timedecay_hover_text(
    row_data: Union[pd.Series, Dict[str,Any]], 
    config: Optional[Dict[str, Any]],
    strike_col_key: str,
    primary_metric_key: str, # e.g., "tdpi", "ctr_strike"
    opt_kind_for_hover: Optional[str] = None 
    ) -> str:
    parts = []
    strike_val = row_data.get(strike_col_key)
    parts.append(f"<b>Strike: {strike_val:.2f}</b>" if pd.notna(strike_val) else f"Strike: N/A")
    if opt_kind_for_hover: parts.append(f"Type: {opt_kind_for_hover}")

    metric_val = row_data.get(primary_metric_key)
    label = primary_metric_key.replace('_strike','').replace('_',' ').upper()
    parts.append(f"{label}: {metric_val:,.0f}" if pd.notna(metric_val) and abs(metric_val) > 1000 else \
                 f"{label}: {metric_val:.3f}" if pd.notna(metric_val) else f"{label}: N/A")
    
    # Add context for TDPI like charmxoi, txoi
    if primary_metric_key == get_config_value(config, ["visualization_settings", "mspi_visualizer", "column_names", "tdpi"], "tdpi"):
        charmxoi_key = get_config_value(config, ["strategy_settings", "charm_exposure_source_col"], "charmxoi")
        txoi_key = get_config_value(config, ["strategy_settings", "theta_exposure_source_col"], "txoi")
        if pd.notna(row_data.get(charmxoi_key)): parts.append(f"CharmxOI: {row_data.get(charmxoi_key):.0f}")
        if pd.notna(row_data.get(txoi_key)): parts.append(f"TxOI: {row_data.get(txoi_key):.0f}")
            
    return "<br>".join(parts) + "<extra></extra>"

# --- Chart Generation Functions for Time Decay & Pinning Mode ---

def generate_tdpi_strike_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    # This adapts the MSPIVisualizerV2.create_time_decay_visualization logic
    chart_name = "TDPI by Strike"
    logger.info(f"Generating: {chart_name}")

    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_opt_kind_col = get_config_value(app_config, ["strategy_settings", "option_kind_col_name"], "opt_kind")
    cfg_tdpi_col = "tdpi" # From MetricsCalculator output in df_strike_metrics, merged to chain
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")

    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 700)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"

    df_chain_metrics_list = analysis_bundle.get("df_chain_metrics", [])
    if not df_chain_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Chain metrics list empty", config=app_config)

    try:
        df_chain = pd.DataFrame.from_records(df_chain_metrics_list)
        required_cols = [cfg_strike_col, cfg_opt_kind_col, cfg_tdpi_col]
        if not all(col in df_chain.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_chain.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing for TDPI plot: {missing}", config=app_config)

        df_chain[cfg_strike_col] = pd.to_numeric(df_chain[cfg_strike_col], errors='coerce')
        df_chain[cfg_tdpi_col] = pd.to_numeric(df_chain[cfg_tdpi_col], errors='coerce')
        df_chain[cfg_opt_kind_col] = df_chain[cfg_opt_kind_col].astype(str).str.lower().fillna('?')
        df_plot = df_chain.dropna(subset=[cfg_strike_col, cfg_tdpi_col, cfg_opt_kind_col])
        df_plot = df_plot[df_plot[cfg_opt_kind_col].isin(['call', 'put'])]

        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Call/Put Data", height=fig_height, reason="No valid data for TDPI plot", config=app_config)
        
        pivot_df = df_plot.pivot_table(values=cfg_tdpi_col, index=cfg_strike_col, columns=cfg_opt_kind_col, aggfunc='first', fill_value=0.0)
        if 'put' not in pivot_df.columns: pivot_df['put'] = 0.0
        if 'call' not in pivot_df.columns: pivot_df['call'] = 0.0
        pivot_df = pivot_df[['put','call']].sort_index(ascending=True)

        if pivot_df.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: Pivot Table Empty", height=fig_height, reason="TDPI Pivot empty", config=app_config)

        fig = go.Figure()
        call_color = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "tdpi_call_color"], "mediumseagreen")
        put_color = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "tdpi_put_color"], "crimson")
        
        # To get context for hover, merge back if needed or ensure df_chain already has it
        # For simplicity, use the pivot data for primary value, and could enrich hover_text from original df_plot if needed.
        call_hovers = [_create_timedecay_hover_text(row_data={'strike':idx, cfg_tdpi_col:val}, config=app_config, strike_col_key=cfg_strike_col, primary_metric_key=cfg_tdpi_col, opt_kind_for_hover="Call") for idx, val in pivot_df['call'].items()]
        put_hovers = [_create_timedecay_hover_text(row_data={'strike':idx, cfg_tdpi_col:val}, config=app_config, strike_col_key=cfg_strike_col, primary_metric_key=cfg_tdpi_col, opt_kind_for_hover="Put") for idx, val in pivot_df['put'].items()]

        fig.add_trace(go.Bar(
            y=pivot_df.index.astype(str), x=pivot_df['call'], name='Calls TDPI', 
            orientation='h', marker_color=call_color, hovertext=call_hovers, hoverinfo="text"
        ))
        fig.add_trace(go.Bar(
            y=pivot_df.index.astype(str), x=pivot_df['put'], name='Puts TDPI', 
            orientation='h', marker_color=put_color, hovertext=put_hovers, hoverinfo="text"
        ))
        
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, yaxis_title='Strike', xaxis_title='Time Decay Pressure Index (TDPI)',
            barmode='relative', 
            template=PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, yaxis=dict(type='category', autorange='reversed'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="y unified",
            **PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='horizontal', y_col_for_line=pivot_df.index.astype(str), app_config=app_config)

    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig


def generate_vci_0dte_strike_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], # For trend line
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = "VCI 0DTE (Aggregate)"
    logger.info(f"Generating: {chart_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "gauge_height"], 250)
    symbol = analysis_bundle.get("symbol", "N/A")
    current_ts_iso = analysis_bundle.get("timestamp", datetime.now().isoformat())
    current_ts_dt = datetime.fromisoformat(current_ts_iso.replace("Z","+00:00")) if current_ts_iso else datetime.now()
    
    und_data = analysis_bundle.get("und_data_aggregates", {})
    times, vci_values = [], []
    
    metric_key_vci = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "column_names", "vci_0dte_agg"], "vci_0dte_agg")

    if chart_history:
        for ts_epoch, hist_bundle_data in chart_history:
            if isinstance(hist_bundle_data, dict): # Assuming history stores und_data part of bundle
                hist_val = hist_bundle_data.get(metric_key_vci)
                if hist_val is not None and pd.notna(hist_val):
                    times.append(datetime.fromtimestamp(ts_epoch))
                    vci_values.append(float(hist_val))
    
    current_vci_val = und_data.get(metric_key_vci)
    if current_vci_val is not None and pd.notna(current_vci_val):
        times.append(current_ts_dt)
        vci_values.append(float(current_vci_val))

    if not times or not vci_values:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="VCI 0DTE data missing", config=app_config)

    sorted_times_vcis = sorted(zip(times, vci_values)); plot_times, plot_vcis = zip(*sorted_times_vcis) if sorted_times_vcis else ([], [])
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(plot_times), y=list(plot_vcis), mode='lines+markers', name='VCI (0DTE)',
        line=dict(color='darkorange', width=2), marker=dict(size=5)
    ))
    
    # Add threshold lines from config
    vci_cascade_thresh = get_config_value(app_config, ["strategy_settings", "thresholds", "vci_cascade_thresh"], 0.35)
    if vci_cascade_thresh is not None:
        fig.add_hline(y=vci_cascade_thresh, line_dash="dot", line_color="red",
                      annotation_text=f"Cascade Thresh ({vci_cascade_thresh:.2f})", annotation_position="bottom right")

    current_val_str = f"Current: {plot_vcis[-1]:.3f}" if plot_vcis else "N/A"
    chart_title_full = f"<b>{symbol.upper()}</b> - {chart_name}<br><span style='font-size:0.8em;color:grey'>{current_val_str}</span>"

    fig.update_layout(
        title=chart_title_full, height=fig_height,
        template=PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {}).get("template", "plotly_dark"), 
        yaxis_title="VCI (0DTE) Value", hovermode="x unified",
        yaxis_range=[0, max(0.5, max(plot_vcis) * 1.1 if plot_vcis else 0.5)], # Dynamic upper bound, min 0.5
        **PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {})
    )
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig

def generate_ctr_strike_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = "CTR by Strike"
    logger.info(f"Generating: {chart_name}")

    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_ctr_col = "ctr_strike" # From MetricsCalculator output in df_strike_metrics
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")
    
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 450)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name} (Charm Decay Rate)"

    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Strike metrics list empty", config=app_config)
    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        required_cols = [cfg_strike_col, cfg_ctr_col]
        if not all(col in df_strikes.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_strikes.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing: {missing}", config=app_config)

        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        df_strikes[cfg_ctr_col] = pd.to_numeric(df_strikes[cfg_ctr_col], errors='coerce').replace([np.inf, -np.inf], np.nan) # Handle inf from division
        df_plot = df_strikes.dropna(subset=[cfg_strike_col, cfg_ctr_col]).sort_values(by=cfg_strike_col)
        
        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Data", height=fig_height, reason="No valid CTR data after cleaning", config=app_config)

        hover_texts = [_create_timedecay_hover_text(row, app_config, cfg_strike_col, cfg_ctr_col) for _, row in df_plot.iterrows()]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_plot[cfg_strike_col], y=df_plot[cfg_ctr_col], mode='lines+markers', name='CTR',
            line=dict(color='coral', width=2), marker=dict(size=5, symbol='cross'),
            hovertext=hover_texts, hoverinfo="text"
        ))
        
        ctr_cascade_thresh = get_config_value(app_config, ["strategy_settings", "thresholds", "charm_cascade_ctr_trigger"], 2.0)
        if ctr_cascade_thresh is not None:
            fig.add_hline(y=ctr_cascade_thresh, line_dash="dot", line_color="orange", annotation_text=f"Cascade Thresh ({ctr_cascade_thresh:.1f})")

        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, xaxis_title='Strike', yaxis_title='CTR Value',
            template=PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, hovermode="x unified",
            **PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='vertical', app_config=app_config)
    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig

def generate_tdfi_strike_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = "TDFI by Strike"
    logger.info(f"Generating: {chart_name}")

    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_tdfi_col = "tdfi_strike" # From MetricsCalculator output in df_strike_metrics
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")

    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 450)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name} (Time Decay Flow Imbalance)"

    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Strike metrics list empty", config=app_config)
    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        required_cols = [cfg_strike_col, cfg_tdfi_col]
        if not all(col in df_strikes.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_strikes.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing: {missing}", config=app_config)

        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        df_strikes[cfg_tdfi_col] = pd.to_numeric(df_strikes[cfg_tdfi_col], errors='coerce').replace([np.inf, -np.inf], np.nan)
        df_plot = df_strikes.dropna(subset=[cfg_strike_col, cfg_tdfi_col]).sort_values(by=cfg_strike_col)
        
        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Data", height=fig_height, reason="No valid TDFI data after cleaning", config=app_config)

        hover_texts = [_create_timedecay_hover_text(row, app_config, cfg_strike_col, cfg_tdfi_col) for _, row in df_plot.iterrows()]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_plot[cfg_strike_col], y=df_plot[cfg_tdfi_col], mode='lines+markers', name='TDFI',
            line=dict(color='gold', width=2), marker=dict(size=5, symbol='star-diamond'),
            hovertext=hover_texts, hoverinfo="text"
        ))
        
        tdfi_cascade_thresh = get_config_value(app_config, ["strategy_settings", "thresholds", "charm_cascade_tdfi_trigger"], 1.5)
        if tdfi_cascade_thresh is not None:
            fig.add_hline(y=tdfi_cascade_thresh, line_dash="dot", line_color="darkorange", annotation_text=f"Cascade Thresh ({tdfi_cascade_thresh:.1f})")

        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, xaxis_title='Strike', yaxis_title='TDFI Value',
            template=PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, hovermode="x unified",
            **PLOTLY_TEMPLATE_TIMEDECAY_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='vertical', app_config=app_config)
    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig

logger.info("time_decay_mode_display.py loaded and chart generation functions defined.")