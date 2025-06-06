# dashboard_application/modes/flow_mode_display.py
# (Elite Version 2.4 - Co-Pilot - Display Logic for Flow Breakdown Mode)

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
        PLOTLY_TEMPLATE_FOR_UTILS_MODULE as PLOTLY_TEMPLATE_FLOW_MODE
    )
    # from ..utils_dashboard import create_custom_hover_text_utility # If you create a shared one
    _utils_imported_successfully_flow = True
except ImportError as e_util_flow_disp:
    logging.getLogger(__name__).critical(f"CRITICAL Import Error in flow_mode_display.py for utils: {e_util_flow_disp}. Visuals may fail.")
    _utils_imported_successfully_flow = False
    def get_config_value(cfg, path, default): return default
    def create_empty_figure(title, height=None, reason="", config=None): return go.Figure().update_layout(title=title, height=height or 400)
    def add_timestamp_annotation(fig, ts, cfg=None): return fig
    def add_price_line(fig, price, orientation="v", cfg=None, **kwargs): return fig
    PLOTLY_TEMPLATE_FLOW_MODE = {"layout": go.Layout(template="plotly_dark")}

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__) # e.g., dashboard_application.modes.flow_mode_display

# --- Chart Generation Functions for Flow Breakdown Mode ---

def generate_net_value_heatmap_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = "Net Value Pressure Heatmap (Flow Mode)" # Can be different from main NVP bar chart
    logger.info(f"Generating: {chart_name}")
    
    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_opt_kind_col = get_config_value(app_config, ["strategy_settings", "option_kind_col_name"], "opt_kind")
    # NVP is typically strike-level. If we want a heatmap by C/P, we need per-contract net value.
    # The per-contract net value is `col_c_value_bs` (e.g., "value_bs" or "c_value_bs") in df_chain_metrics
    cfg_nvp_contract_col = get_config_value(app_config, ["strategy_settings", "net_flow_cols_chain", "value_bs"], "value_bs")
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")
    
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 600)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"

    df_chain_metrics_list = analysis_bundle.get("df_chain_metrics", [])
    if not df_chain_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Chain metrics list empty", config=app_config)
    
    try:
        df_chain = pd.DataFrame.from_records(df_chain_metrics_list)
        required_cols = [cfg_strike_col, cfg_opt_kind_col, cfg_nvp_contract_col]
        if not all(col in df_chain.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_chain.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing for pivot: {missing}", config=app_config)

        df_chain[cfg_strike_col] = pd.to_numeric(df_chain[cfg_strike_col], errors='coerce')
        df_chain[cfg_nvp_contract_col] = pd.to_numeric(df_chain[cfg_nvp_contract_col], errors='coerce')
        df_chain[cfg_opt_kind_col] = df_chain[cfg_opt_kind_col].astype(str).str.lower().fillna('?')
        df_plot = df_chain.dropna(subset=[cfg_strike_col, cfg_nvp_contract_col, cfg_opt_kind_col])
        df_plot = df_plot[df_plot[cfg_opt_kind_col].isin(['call', 'put'])]

        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Call/Put Data", height=fig_height, reason="No valid call/put for pivot", config=app_config)

        # Pivot sums the per-contract net value at each strike/kind intersection
        pivot_df = df_plot.pivot_table(values=cfg_nvp_contract_col, index=cfg_strike_col, columns=cfg_opt_kind_col, aggfunc='sum', fill_value=0)
        if 'put' not in pivot_df.columns: pivot_df['put'] = 0
        if 'call' not in pivot_df.columns: pivot_df['call'] = 0
        pivot_df = pivot_df[['put','call']].sort_index(ascending=False)

        if pivot_df.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: Pivot Table Empty", height=fig_height, reason="Pivot operation resulted in empty table", config=app_config)

        hover_matrix = [[f"Strike: {strike}<br>Type: {col_type}<br>Net Value: ${pivot_df.loc[strike, col_type]:,.0f}<extra></extra>"
                         for col_type in pivot_df.columns] for strike in pivot_df.index]

        cs_cfg_path = ["visualization_settings", "mspi_visualizer", "colorscales", "net_value_heatmap"]
        colorscale = get_config_value(app_config, cs_cfg_path, "RdYlGn")
        
        fig = go.Figure(data=[go.Heatmap(
            z=pivot_df.values, x=pivot_df.columns.str.capitalize(), y=pivot_df.index.astype(str),
            colorscale=colorscale, zmid=0, colorbar=dict(title='Net Value ($)'),
            hovertext=hover_matrix, hoverinfo='text'
        )])
        
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, xaxis_title='Option Type', yaxis_title='Strike',
            yaxis=dict(type='category', autorange='reversed', tickfont=dict(size=10)),
            template=PLOTLY_TEMPLATE_FLOW_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height,
            **PLOTLY_TEMPLATE_FLOW_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='horizontal', app_config=app_config)
    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig


def generate_arfi_strike_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = "ARFI by Strike"
    logger.info(f"Generating: {chart_name}")

    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_arfi_col = "arfi_strike" # From MetricsCalculator output in df_strike_metrics
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")

    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 450)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"

    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Strike metrics list empty", config=app_config)

    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        required_cols = [cfg_strike_col, cfg_arfi_col]
        if not all(col in df_strikes.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_strikes.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing for ARFI plot: {missing}", config=app_config)

        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        df_strikes[cfg_arfi_col] = pd.to_numeric(df_strikes[cfg_arfi_col], errors='coerce')
        df_plot = df_strikes.dropna(subset=[cfg_strike_col, cfg_arfi_col]).sort_values(by=cfg_strike_col)
        
        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Data", height=fig_height, reason="No valid ARFI data after cleaning", config=app_config)

        hover_texts = [f"Strike: {row[cfg_strike_col]:.2f}<br>ARFI: {row[cfg_arfi_col]:.3f}<extra></extra>" for _, row in df_plot.iterrows()]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_plot[cfg_strike_col],
            y=df_plot[cfg_arfi_col],
            name="ARFI",
            marker_color='cornflowerblue',
            hovertext=hover_texts,
            hoverinfo="text"
        ))
        
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, xaxis_title='Strike', yaxis_title='ARFI Value',
            template=PLOTLY_TEMPLATE_FLOW_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, hovermode="x unified",
            **PLOTLY_TEMPLATE_FLOW_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='vertical', app_config=app_config)
    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig


def _generate_net_cust_greek_flow_chart(
    greek_name: str, # "Delta", "Gamma", "Vega", "Theta"
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], # Used for plotting trend
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    metric_key = f"NetCust{greek_name}Flow_Und"
    chart_title_name = f"Net Customer {greek_name} Flow (Daily)"
    logger.info(f"Generating: {chart_title_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "gauge_height"], 250) # Smaller chart for single value trend
    
    symbol = analysis_bundle.get("symbol", "N/A")
    current_ts_iso = analysis_bundle.get("timestamp", datetime.now().isoformat())
    current_ts_dt = datetime.fromisoformat(current_ts_iso.replace("Z","+00:00")) if current_ts_iso else datetime.now()
    
    und_data = analysis_bundle.get("und_data_aggregates", {})
    times, flow_values = [], []

    if chart_history:
        for ts_epoch, hist_bundle_data in chart_history: # Assuming history stores und_data_aggregates part of bundle
            if isinstance(hist_bundle_data, dict):
                hist_val = hist_bundle_data.get(metric_key)
                if hist_val is not None and pd.notna(hist_val):
                    times.append(datetime.fromtimestamp(ts_epoch))
                    flow_values.append(float(hist_val))
    
    current_flow_val = und_data.get(metric_key)
    if current_flow_val is not None and pd.notna(current_flow_val):
        times.append(current_ts_dt)
        flow_values.append(float(current_flow_val))

    if not times or not flow_values:
        return create_empty_figure(title=f"{symbol}-{chart_title_name}: No Data", height=fig_height, reason=f"{metric_key} data missing", config=app_config)

    sorted_times_flows = sorted(zip(times, flow_values)); plot_times, plot_flows = zip(*sorted_times_flows) if sorted_times_flows else ([], [])
    
    fig = go.Figure()
    line_color = 'lightseagreen' if greek_name in ["Delta", "Gamma"] else 'mediumpurple'
    fig.add_trace(go.Scatter(
        x=list(plot_times), y=list(plot_flows), mode='lines+markers', name=f'Net Cust {greek_name} Flow',
        line=dict(color=line_color, width=2), marker=dict(size=5)
    ))
    
    current_val_str = f"Current: {plot_flows[-1]:.2e}" if plot_flows else "N/A" # Scientific notation for large Greek values
    chart_title_full = f"<b>{symbol.upper()}</b> - {chart_title_name}<br><span style='font-size:0.8em;color:grey'>{current_val_str}</span>"

    fig.update_layout(
        title=chart_title_full, height=fig_height,
        template=PLOTLY_TEMPLATE_FLOW_MODE.get("layout", {}).get("template", "plotly_dark"), 
        yaxis_title=f"Net {greek_name} Flow", hovermode="x unified", yaxis_zeroline=True,
        **PLOTLY_TEMPLATE_FLOW_MODE.get("layout", {})
    )
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig

def generate_net_cust_delta_flow_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return _generate_net_cust_greek_flow_chart("Delta", analysis_bundle, app_config, chart_history, its_orchestrator_ref)

def generate_net_cust_gamma_flow_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return _generate_net_cust_greek_flow_chart("Gamma", analysis_bundle, app_config, chart_history, its_orchestrator_ref)

def generate_net_cust_vega_flow_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return _generate_net_cust_greek_flow_chart("Vega", analysis_bundle, app_config, chart_history, its_orchestrator_ref)
    # Note: Theta flow chart would be similar, add if needed in FLOW_MODE_CHART_IDS_V2_4


def generate_vflowratio_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    # Plots vflowratio (from und_data_aggregates) as a trend line using chart_history
    chart_name = "Vflowratio Trend"
    logger.info(f"Generating: {chart_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "gauge_height"], 250)
    symbol = analysis_bundle.get("symbol", "N/A")
    current_ts_iso = analysis_bundle.get("timestamp", datetime.now().isoformat())
    current_ts_dt = datetime.fromisoformat(current_ts_iso.replace("Z","+00:00")) if current_ts_iso else datetime.now()
    
    und_data = analysis_bundle.get("und_data_aggregates", {})
    times, vflow_values = [], []

    # Get the API key for vflowratio from config (as initialized in MetricsCalculator)
    cfg_vflow_key = get_config_value(app_config, ["strategy_settings", "greeks_from_und", "vflowratio_api_field"], "vflowratio")
    
    if chart_history:
        for ts_epoch, hist_bundle_data in chart_history:
            if isinstance(hist_bundle_data, dict):
                hist_val = hist_bundle_data.get(cfg_vflow_key) # Use configured key
                if hist_val is not None and pd.notna(hist_val):
                    times.append(datetime.fromtimestamp(ts_epoch))
                    vflow_values.append(float(hist_val))
    
    current_vflow_val = und_data.get(cfg_vflow_key) # Use configured key
    if current_vflow_val is not None and pd.notna(current_vflow_val):
        times.append(current_ts_dt)
        vflow_values.append(float(current_vflow_val))

    if not times or not vflow_values:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="vflowratio data missing", config=app_config)

    sorted_times_vflows = sorted(zip(times, vflow_values)); plot_times, plot_vflows = zip(*sorted_times_vflows) if sorted_times_vflows else ([], [])
    
    fig = go.Figure(); fig.add_trace(go.Scatter(x=list(plot_times), y=list(plot_vflows), mode='lines+markers', name='Vflowratio', line=dict(color='orange', width=2)))
    fig.add_hline(y=1.0, line_dash="dash", line_color="grey", annotation_text="Balance (1.0)")
    
    current_val_str = f"Current: {plot_vflows[-1]:.2f}" if plot_vflows else "N/A"
    chart_title_full = f"<b>{symbol.upper()}</b> - {chart_name}<br><span style='font-size:0.8em;color:grey'>{current_val_str}</span>"
    fig.update_layout(title=chart_title_full, height=fig_height, template=PLOTLY_TEMPLATE_FLOW_MODE.get("layout",{}).get("template"), yaxis_title="Vflowratio", hovermode="x unified", **PLOTLY_TEMPLATE_FLOW_MODE.get("layout",{}))
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig


def generate_granular_pcrs_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    # Plots the 4 granular PCRs (CustBuy Val, CustSell Val, CustBuy Vol, CustSell Vol) as trend lines
    chart_name = "Granular PCRs Trend"
    logger.info(f"Generating: {chart_name}")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 500)
    symbol = analysis_bundle.get("symbol", "N/A")
    current_ts_iso = analysis_bundle.get("timestamp", datetime.now().isoformat())
    current_ts_dt = datetime.fromisoformat(current_ts_iso.replace("Z","+00:00")) if current_ts_iso else datetime.now()

    und_data = analysis_bundle.get("und_data_aggregates", {})
    pcr_keys = [
        "PCR_CustBuy_Val_Daily_calc", "PCR_CustSell_Val_Daily_calc",
        "PCR_CustBuy_Vol_Daily_calc", "PCR_CustSell_Vol_Daily_calc"
    ]
    pcr_data_trends: Dict[str, Tuple[List[datetime], List[float]]] = {key: ([], []) for key in pcr_keys}

    if chart_history:
        for ts_epoch, hist_bundle_data in chart_history:
            if isinstance(hist_bundle_data, dict):
                for key in pcr_keys:
                    hist_val = hist_bundle_data.get(key)
                    if hist_val is not None and pd.notna(hist_val) and np.isfinite(hist_val): # Check for inf
                        pcr_data_trends[key][0].append(datetime.fromtimestamp(ts_epoch))
                        pcr_data_trends[key][1].append(float(hist_val))
    
    for key in pcr_keys:
        current_val = und_data.get(key)
        if current_val is not None and pd.notna(current_val) and np.isfinite(current_val):
            pcr_data_trends[key][0].append(current_ts_dt)
            pcr_data_trends[key][1].append(float(current_val))

    fig = go.Figure()
    pcr_labels_colors = {
        "PCR_CustBuy_Val_Daily_calc": ("PCR Buy Val", "lightcoral"),
        "PCR_CustSell_Val_Daily_calc": ("PCR Sell Val", "indianred"),
        "PCR_CustBuy_Vol_Daily_calc": ("PCR Buy Vol", "lightskyblue"),
        "PCR_CustSell_Vol_Daily_calc": ("PCR Sell Vol", "steelblue")
    }

    has_data = False
    for key, (label, color) in pcr_labels_colors.items():
        if key in pcr_data_trends and pcr_data_trends[key][0]:
            has_data = True
            times, values = pcr_data_trends[key]
            # Sort by time before plotting
            sorted_data = sorted(zip(times, values))
            plot_times, plot_values = zip(*sorted_data) if sorted_data else ([], [])
            fig.add_trace(go.Scatter(x=list(plot_times), y=list(plot_values), mode='lines+markers', name=label, line=dict(color=color)))
    
    if not has_data:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Granular PCR data missing", config=app_config)

    chart_title_full = f"<b>{symbol.upper()}</b> - {chart_name}"
    fig.update_layout(title=chart_title_full, height=fig_height, template=PLOTLY_TEMPLATE_FLOW_MODE.get("layout",{}).get("template"), yaxis_title="Put/Call Ratio", hovermode="x unified", yaxis_type="log", **PLOTLY_TEMPLATE_FLOW_MODE.get("layout",{}))
    fig.add_hline(y=1.0, line_dash="dash", line_color="grey", annotation_text="Balance (1.0)")
    fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config)
    return fig


logger.info("flow_mode_display.py loaded and chart generation functions defined.")