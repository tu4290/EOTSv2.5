# dashboard_application/modes/structure_mode_display.py
# (Elite Version 2.4 - Co-Pilot - Display Logic for Structure & Dealer Pos. Mode)

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
        PLOTLY_TEMPLATE_FOR_UTILS_MODULE as PLOTLY_TEMPLATE_STRUCTURE_MODE
    )
    # from ..utils_dashboard import create_custom_hover_text_utility # If you create a shared one
    _utils_imported_successfully_struct = True
except ImportError as e_util_struct_disp:
    logging.getLogger(__name__).critical(f"CRITICAL Import Error in structure_mode_display.py for utils: {e_util_struct_disp}. Visuals may fail.")
    _utils_imported_successfully_struct = False
    # Minimal fallbacks for functions if utils are missing
    def get_config_value(cfg, path, default): return default
    def create_empty_figure(title, height=None, reason="", config=None): return go.Figure().update_layout(title=title, height=height or 400)
    def add_timestamp_annotation(fig, ts, cfg=None): return fig
    def add_price_line(fig, price, orientation="v", cfg=None, **kwargs): return fig
    PLOTLY_TEMPLATE_STRUCTURE_MODE = {"layout": go.Layout(template="plotly_dark")}

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__) # e.g., dashboard_application.modes.structure_mode_display

# --- Reusable Hover Text Logic (Simplified - Adapt from mspi_visualizer_v2.py or utils) ---
def _create_structure_hover_text(
    row_data: Union[pd.Series, Dict[str,Any]], 
    config: Optional[Dict[str, Any]],
    strike_col_key: str,
    primary_metric_key: str, # e.g., "mspi", "sdag_multiplicative"
    opt_kind_for_hover: Optional[str] = None # "Call" or "Put" if applicable
    ) -> str:
    parts = []
    strike_val = row_data.get(strike_col_key)
    parts.append(f"<b>Strike: {strike_val:.2f}</b>" if pd.notna(strike_val) else f"Strike: N/A")
    if opt_kind_for_hover: parts.append(f"Type: {opt_kind_for_hover}")

    metric_val = row_data.get(primary_metric_key)
    parts.append(f"{primary_metric_key.replace('_norm',' (N)').replace('_',' ').title()}: {metric_val:.3g}" if pd.notna(metric_val) else f"{primary_metric_key.replace('_',' ').title()}: N/A")
    
    # Add other context if needed, e.g., GEX/DEX for SDAGs
    if primary_metric_key.startswith("sdag_"):
        gex_source_col = get_config_value(config, ["strategy_settings", "gamma_col_for_sdag_calc"], "gxoi") # Or sgxoi_calc
        dex_col = get_config_value(config, ["strategy_settings", "delta_exposure_source_col"], "dxoi")
        if gex_source_col in row_data and pd.notna(row_data.get(gex_source_col)):
            parts.append(f"{gex_source_col.upper()}: {row_data.get(gex_source_col):.2e}")
        if dex_col in row_data and pd.notna(row_data.get(dex_col)):
            parts.append(f"{dex_col.upper()}: {row_data.get(dex_col):.2e}")
            
    return "<br>".join(parts) + "<extra></extra>"


# --- Chart Generation Functions for Structure & Dealer Pos. Mode ---

def generate_mspi_components_viz_figure(
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    # This adapts the MSPIVisualizerV2.create_component_comparison logic
    chart_name = "MSPI Components by Strike"
    logger.info(f"Generating: {chart_name}")

    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_mspi_col = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "column_names", "mspi"], "mspi")
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")
    
    fig_height = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "component_comparison_height"], 600)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"

    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Strike metrics list empty", config=app_config)

    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        
        # Determine which MSPI components are active based on weights from _get_mspi_weights (passed via analysis_bundle or re-fetched)
        # For simplicity, assume all _norm columns that might be MSPI components are present if calculated.
        # The MSPI orchestrator should have already normalized them.
        potential_norm_components = [
            'dag_custom_norm', 'tdpi_norm', 'vri_sensitivity_norm', 
            'vri_0dte_norm', 'vfi_0dte_norm', 'arfi_strike_norm'
        ]
        enabled_sdags_cfg = get_config_value(app_config, ["strategy_settings", "dag_methodologies", "enabled"], [])
        for sdag_method in enabled_sdags_cfg:
            potential_norm_components.append(f"sdag_{sdag_method}_norm")
        
        present_components = [cfg_mspi_col] + [col for col in potential_norm_components if col in df_strikes.columns]
        
        required_cols = [cfg_strike_col] + present_components
        if not all(col in df_strikes.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_strikes.columns and col != cfg_mspi_col] # MSPI itself is primary
            if cfg_mspi_col not in df_strikes.columns: missing.append(cfg_mspi_col)
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Component Cols ({missing})", height=fig_height, reason=f"Missing: {missing}", config=app_config)

        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        for comp_col in present_components:
            df_strikes[comp_col] = pd.to_numeric(df_strikes[comp_col], errors='coerce')
        
        df_plot = df_strikes.dropna(subset=[cfg_strike_col] + present_components).sort_values(by=cfg_strike_col)

        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Data", height=fig_height, reason="No valid data after cleaning for components", config=app_config)

        fig = go.Figure()
        component_colors_cfg = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "mspi_components_bar_colors"], {})

        # Plot MSPI first, then other components
        plot_order = [cfg_mspi_col] + [c for c in present_components if c != cfg_mspi_col]

        for y_col in plot_order:
            series_data = df_plot[y_col].fillna(0)
            hover_texts = [_create_structure_hover_text(row, app_config, cfg_strike_col, y_col) for _, row in df_plot.iterrows()]
            
            trace_name = y_col.replace('_norm', ' (N)').replace('sdag_', 'SDAG ').replace('_', ' ').title()
            
            color_map = component_colors_cfg.get(y_col, {"pos": "grey", "neg": "darkgrey"})
            bar_colors = [color_map.get('pos') if v >= 0 else color_map.get('neg') for v in series_data]

            fig.add_trace(go.Bar(
                x=df_plot[cfg_strike_col],
                y=series_data,
                name=trace_name,
                marker_color=bar_colors,
                hovertext=hover_texts,
                hoverinfo="text"
            ))
        
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        y_range_val = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "mspi_components_y_range"], [-1.1, 1.1])

        fig.update_layout(
            title=chart_title, xaxis_title='Strike', yaxis_title='MSPI / Normalized Component Value',
            barmode='overlay', # Or 'group' if preferred
            template=PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, hovermode="x unified",
            yaxis_range=y_range_val,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            **PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        fig = add_price_line(fig, current_price, orientation='vertical', app_config=app_config)

    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig

def _generate_sdag_chart_base(
    sdag_method_key: str, # e.g., "sdag_multiplicative"
    chart_display_name_suffix: str, # e.g., "(Multiplicative)"
    analysis_bundle: Dict[str, Any], 
    app_config: Optional[Dict[str, Any]], 
    chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]],
    its_orchestrator_ref: Optional[Any]
) -> go.Figure:
    chart_name = f"SDAG {chart_display_name_suffix}"
    logger.info(f"Generating: {chart_name}")

    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_opt_kind_col = get_config_value(app_config, ["strategy_settings", "option_kind_col_name"], "opt_kind") # Needed for C/P split
    cfg_sdag_col = sdag_method_key # This is the direct column name from MetricsCalculator
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")

    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 700) # SDAG charts can be tall
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"

    # SDAGs are strike-level metrics, merged back to df_chain. So, source from df_chain_metrics.
    df_chain_metrics_list = analysis_bundle.get("df_chain_metrics", [])
    if not df_chain_metrics_list:
        return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, reason="Chain metrics list empty", config=app_config)

    try:
        df_chain = pd.DataFrame.from_records(df_chain_metrics_list)
        required_cols = [cfg_strike_col, cfg_opt_kind_col, cfg_sdag_col]
        if not all(col in df_chain.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df_chain.columns]
            return create_empty_figure(f"{symbol}-{chart_name}: Missing Cols ({missing})", height=fig_height, reason=f"Missing for SDAG plot: {missing}", config=app_config)

        df_chain[cfg_strike_col] = pd.to_numeric(df_chain[cfg_strike_col], errors='coerce')
        df_chain[cfg_sdag_col] = pd.to_numeric(df_chain[cfg_sdag_col], errors='coerce')
        df_chain[cfg_opt_kind_col] = df_chain[cfg_opt_kind_col].astype(str).str.lower().fillna('?')
        df_plot = df_chain.dropna(subset=[cfg_strike_col, cfg_sdag_col, cfg_opt_kind_col])
        df_plot = df_plot[df_plot[cfg_opt_kind_col].isin(['call', 'put'])]

        if df_plot.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: No Valid Call/Put Data", height=fig_height, reason="No valid data for SDAG plot", config=app_config)
        
        # Pivot for separate call/put traces if needed, or aggregate for net.
        # Your _create_raw_greek_chart from mspi_visualizer_v2 adapted this well.
        # We'll replicate a similar horizontal bar chart structure.
        pivot_df = df_plot.pivot_table(values=cfg_sdag_col, index=cfg_strike_col, columns=cfg_opt_kind_col, aggfunc='first', fill_value=0.0) # 'first' because SDAG is strike-level
        if 'put' not in pivot_df.columns: pivot_df['put'] = 0.0
        if 'call' not in pivot_df.columns: pivot_df['call'] = 0.0
        pivot_df = pivot_df[['put','call']].sort_index(ascending=True) # Ascending for y-axis mapping

        if pivot_df.empty:
            return create_empty_figure(f"{symbol}-{chart_name}: Pivot Table Empty", height=fig_height, reason="SDAG Pivot empty", config=app_config)

        fig = go.Figure()
        
        # Colors can be configured per SDAG method
        colors_cfg = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "mspi_components_bar_colors"], {})
        norm_col_for_color = f"{cfg_sdag_col}_norm" # SDAG method key in colors_cfg often ends with _norm
        color_map = colors_cfg.get(norm_col_for_color, {"pos": "lightgreen", "neg": "lightcoral"}) # Default colors
        
        call_values = pivot_df['call']
        put_values = pivot_df['put'] 
        
        # Create hover text for each bar
        call_hovers = [_create_structure_hover_text(row_data={'strike':idx, cfg_sdag_col:val}, config=app_config, strike_col_key=cfg_strike_col, primary_metric_key=cfg_sdag_col, opt_kind_for_hover="Call") for idx, val in call_values.items()]
        put_hovers = [_create_structure_hover_text(row_data={'strike':idx, cfg_sdag_col:val}, config=app_config, strike_col_key=cfg_strike_col, primary_metric_key=cfg_sdag_col, opt_kind_for_hover="Put") for idx, val in put_values.items()]

        fig.add_trace(go.Bar(
            y=pivot_df.index.astype(str), x=call_values, name=f'Calls {chart_display_name_suffix}', 
            orientation='h', marker_color=color_map.get('pos'), hovertext=call_hovers, hoverinfo="text"
        ))
        fig.add_trace(go.Bar(
            y=pivot_df.index.astype(str), x=put_values, name=f'Puts {chart_display_name_suffix}', 
            orientation='h', marker_color=color_map.get('neg'), hovertext=put_hovers, hoverinfo="text"
        ))
        
        # Optional Net SDAG trace
        show_net_trace = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "show_net_sdag_trace"], True)
        if show_net_trace:
            net_sdag_values = call_values + put_values # Element-wise sum
            net_hovers = [_create_structure_hover_text(row_data={'strike':idx, cfg_sdag_col:val}, config=app_config, strike_col_key=cfg_strike_col, primary_metric_key=cfg_sdag_col, opt_kind_for_hover="Net") for idx, val in net_sdag_values.items()]
            net_style = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "net_sdag_marker_style"], {})
            net_visibility = get_config_value(app_config, ["visualization_settings", "mspi_visualizer", "chart_specific_params", "net_sdag_trace_default_visibility"], 'legendonly')
            fig.add_trace(go.Scatter(
                y=pivot_df.index.astype(str), x=net_sdag_values, mode='markers', name=f'Net {chart_display_name_suffix}',
                marker=dict(symbol=net_style.get('symbol','diamond'), color=net_style.get('color','white'), size=net_style.get('size',8)),
                hovertext=net_hovers, hoverinfo="text", visible=net_visibility
            ))

        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(
            title=chart_title, yaxis_title='Strike', xaxis_title=f'SDAG Value {chart_display_name_suffix}',
            barmode='relative', # Stack negative and positive parts relative to zero
            template=PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout", {}).get("template", "plotly_dark"), 
            height=fig_height, yaxis=dict(type='category', autorange='reversed'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="y unified",
            **PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout", {})
        )
        fig = add_timestamp_annotation(fig, analysis_bundle.get("fetch_timestamp_original_data") or analysis_bundle.get("timestamp"), app_config)
        # For horizontal bar chart, price line is on y-axis (strike)
        fig = add_price_line(fig, current_price, orientation='horizontal', y_col_for_line=pivot_df.index.astype(str), app_config=app_config)

    except Exception as e:
        logger.error(f"Error creating {chart_name} for {symbol}: {e}", exc_info=True)
        return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig

# Generate functions for each SDAG type
def generate_sdag_multiplicative_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return _generate_sdag_chart_base("sdag_multiplicative", "(Multiplicative)", analysis_bundle, app_config, chart_history, its_orchestrator_ref)

def generate_sdag_directional_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return _generate_sdag_chart_base("sdag_directional", "(Directional)", analysis_bundle, app_config, chart_history, its_orchestrator_ref)

def generate_sdag_weighted_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return _generate_sdag_chart_base("sdag_weighted", "(Weighted)", analysis_bundle, app_config, chart_history, its_orchestrator_ref)

def generate_sdag_volatility_focused_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    return _generate_sdag_chart_base("sdag_volatility_focused", "(Volatility Focused)", analysis_bundle, app_config, chart_history, its_orchestrator_ref)


# Placeholder for SAI and SSI per-strike charts
def generate_sai_strike_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    # Similar to ARFI chart, plotting 'sai' from df_strike_metrics
    chart_name = "SAI by Strike"
    logger.info(f"Generating: {chart_name}")
    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_sai_col = "sai" 
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 450)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"
    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list: return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, config=app_config)
    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        # ... (similar data prep as ARFI chart) ...
        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        df_strikes[cfg_sai_col] = pd.to_numeric(df_strikes[cfg_sai_col], errors='coerce')
        df_plot = df_strikes.dropna(subset=[cfg_strike_col, cfg_sai_col]).sort_values(by=cfg_strike_col)
        if df_plot.empty: return create_empty_figure(f"{symbol}-{chart_name}: No Valid Data", height=fig_height, config=app_config)
        hover_texts = [f"Strike: {row[cfg_strike_col]:.2f}<br>SAI: {row[cfg_sai_col]:.3f}<extra></extra>" for _, row in df_plot.iterrows()]
        fig = go.Figure(); fig.add_trace(go.Bar(x=df_plot[cfg_strike_col], y=df_plot[cfg_sai_col], name="SAI", marker_color='teal', hovertext=hover_texts, hoverinfo="text"))
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(title=chart_title, xaxis_title='Strike', yaxis_title='SAI Value', template=PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout",{}).get("template"), height=fig_height, hovermode="x unified", yaxis_range=[-1.1,1.1], **PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout",{}))
        fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config); fig = add_price_line(fig, current_price, app_config=app_config)
    except Exception as e: return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig

def generate_ssi_strike_viz_figure(analysis_bundle: Dict[str, Any], app_config: Optional[Dict[str, Any]], chart_history: Optional[Deque[Tuple[float, pd.DataFrame]]], its_orchestrator_ref: Optional[Any]) -> go.Figure:
    # Similar to ARFI/SAI chart, plotting 'ssi_agg' from df_strike_metrics
    chart_name = "SSI by Strike"
    logger.info(f"Generating: {chart_name}")
    cfg_strike_col = get_config_value(app_config, ["strategy_settings", "strike_col_name"], "strike")
    cfg_ssi_col = "ssi_agg" 
    cfg_und_price_col = get_config_value(app_config, ["strategy_settings", "underlying_price_col_name"], "price")
    fig_height = get_config_value(app_config, ["visualization_settings", "dashboard", "default_graph_height"], 450)
    symbol = analysis_bundle.get("symbol", "N/A")
    chart_title = f"<b>{symbol.upper()}</b> - {chart_name}"
    df_strike_metrics_list = analysis_bundle.get("df_strike_metrics", [])
    if not df_strike_metrics_list: return create_empty_figure(title=f"{symbol}-{chart_name}: No Data", height=fig_height, config=app_config)
    try:
        df_strikes = pd.DataFrame.from_records(df_strike_metrics_list)
        # ... (similar data prep as ARFI chart) ...
        df_strikes[cfg_strike_col] = pd.to_numeric(df_strikes[cfg_strike_col], errors='coerce')
        df_strikes[cfg_ssi_col] = pd.to_numeric(df_strikes[cfg_ssi_col], errors='coerce')
        df_plot = df_strikes.dropna(subset=[cfg_strike_col, cfg_ssi_col]).sort_values(by=cfg_strike_col)
        if df_plot.empty: return create_empty_figure(f"{symbol}-{chart_name}: No Valid Data", height=fig_height, config=app_config)
        hover_texts = [f"Strike: {row[cfg_strike_col]:.2f}<br>SSI: {row[cfg_ssi_col]:.3f}<extra></extra>" for _, row in df_plot.iterrows()]
        fig = go.Figure(); fig.add_trace(go.Bar(x=df_plot[cfg_strike_col], y=df_plot[cfg_ssi_col], name="SSI", marker_color='slateblue', hovertext=hover_texts, hoverinfo="text"))
        current_price = analysis_bundle.get("und_data_aggregates", {}).get(cfg_und_price_col)
        fig.update_layout(title=chart_title, xaxis_title='Strike', yaxis_title='SSI Value', template=PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout",{}).get("template"), height=fig_height, hovermode="x unified", yaxis_range=[0,1.05], **PLOTLY_TEMPLATE_STRUCTURE_MODE.get("layout",{}))
        fig = add_timestamp_annotation(fig, analysis_bundle.get("timestamp"), app_config); fig = add_price_line(fig, current_price, app_config=app_config)
    except Exception as e: return create_empty_figure(f"{symbol}-{chart_name}: Plot Error", height=fig_height, reason=str(e), config=app_config)
    return fig


logger.info("structure_mode_display.py loaded and chart generation functions defined.")