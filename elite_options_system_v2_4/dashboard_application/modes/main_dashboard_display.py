# dashboard_application/modes/main_dashboard_display.py
# (Elite Version 2.4 - Co-Pilot - Display Logic for Main Dashboard Mode - Enhanced & Adherent)

import logging
from typing import Dict, Any, List, Optional, Union, Tuple # Added List, Optional, Union, Tuple
import pandas as pd # type: ignore
import numpy as np # type: ignore
import plotly.graph_objects as go # type: ignore
from plotly.subplots import make_subplots # Ensuring this is present
from dash import html # type: ignore
import dash_bootstrap_components as dbc # type: ignore

# --- Local Module Imports ---
try:
    from .. import layout_manager # For chart registration
    from .. import utils_dashboard as utils # For common utilities like create_empty_figure
    from ..ids import (
        ID_MARKET_REGIME_INDICATOR_DISPLAY, # Corrected name
        ID_GIB_OI_BASED_GAUGE_VIZ,
        ID_MSPI_HEATMAP_VIZ,
        ID_NVP_STRIKE_VIZ,
        ID_COMBINED_ROLLING_FLOW_CHART_VIZ,
        ID_VRI_0DTE_AGGREGATED_VIZ,
        ID_KEY_LEVELS_SUMMARY_VIZ,
        ID_STRATEGY_RECOMMENDATIONS_TABLE_DISPLAY
    )
except ImportError as e_import_mode:
    # Fallback for direct execution or import issues (less likely in integrated system)
    logging.getLogger(__name__).critical(f"MDD_Display: CRITICAL - Failed to import parent/sibling modules: {e_import_mode}. This module may not function correctly.", exc_info=True)
    # Define dummy/fallback versions if necessary for basic loading, though functionality will be impaired.
    class DummyLayoutManager:
        def register_chart_generator(self, mode_name: str, chart_id: str, generator_function: Any): pass
    layout_manager = DummyLayoutManager()
    
    class DummyUtils:
        def create_empty_figure(self, title: str, reason: str = "Data not available.") -> go.Figure:
            fig = go.Figure()
            fig.update_layout(title_text=title, annotations=[dict(text=reason, showarrow=False)])
            return fig
        def get_config_value(self, *args, **kwargs) -> Any: return None
        def add_timestamp_annotation(self, fig: go.Figure, ts: Any) -> go.Figure: return fig # Added
        def add_price_line(self, fig: go.Figure, price: Any, orientation: str, label: str) -> go.Figure: return fig # Added
        utils_logger = logging.getLogger(__name__) # Added

    utils = DummyUtils()
    # Define fallback IDs if ids.py is not available (ensure all used IDs are listed)
    # These must match the names being imported in the try block
    ID_MARKET_REGIME_INDICATOR_DISPLAY = "fallback-market-regime-indicator-display" # Corrected name and value
    ID_GIB_OI_BASED_GAUGE_VIZ = "fallback-gib-oi-based-gauge-viz"
    ID_MSPI_HEATMAP_VIZ = "fallback-mspi-heatmap-viz"
    ID_NVP_STRIKE_VIZ = "fallback-nvp-strike-viz"
    ID_COMBINED_ROLLING_FLOW_CHART_VIZ = "fallback-combined-rolling-flow-chart-viz"
    ID_VRI_0DTE_AGGREGATED_VIZ = "fallback-vri-0dte-aggregated-viz"
    ID_KEY_LEVELS_SUMMARY_VIZ = "fallback-key-levels-summary-viz"
    ID_STRATEGY_RECOMMENDATIONS_TABLE_DISPLAY = "fallback-strategy-recommendations-table-display"


# --- Module-Specific Logger ---
# Use the logger from utils if available and configured, otherwise create a new one.
if hasattr(utils, 'utils_logger') and utils.utils_logger:
    logger = utils.utils_logger.getChild("MainDashDisplay")
else:
    logger = logging.getLogger(__name__)
    if not logger.handlers: # Basic config if no handlers are set up by utils/app_main
        logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')

# Type alias for the data bundle for clarity (actual structure depends on orchestrator output)
DashboardDataBundle = Dict[str, Any] 


# --- Chart Generator Functions for 'main' mode ---

def generate_market_regime_indicator_display_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating Market Regime Indicator. Data type: {type(its_data)}")
    if not its_data or not isinstance(its_data.get("und_data_aggregates_CANONICAL_OBJ"), dict):
        return utils.create_empty_figure(title="Market Regime Indicator", reason="Underlying data aggregates missing.")
    
    und_data = its_data["und_data_aggregates_CANONICAL_OBJ"]
    regime = und_data.get("current_market_regime", "REGIME_UNKNOWN")
    fig = go.Figure()
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=0, # Placeholder, actual value mapping needed
        title={'text': f"<b>Market Regime:</b><br>{regime.replace('REGIME_', '').replace('_', ' ')}", 'font': {'size': 18}},
        gauge={
            'axis': {'visible': False, 'range': [None, 100]},
            'bar': {'color': "rgba(0,0,0,0)"}, # Invisible bar
        }
    ))
    fig.update_layout(
        height=utils.get_chart_specific_height(ID_MARKET_REGIME_INDICATOR_DISPLAY) or 200, # Corrected name
        template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE,
        title_text="" # Title handled by indicator
    )
    utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
    logger.debug(f"MDD_Display: Market Regime Indicator generated for regime: {regime}")
    return fig

def generate_gib_oi_based_gauge_viz_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating GIB OI Based Gauge. Data type: {type(its_data)}")
    if not its_data or not isinstance(its_data.get("und_data_aggregates_CANONICAL_OBJ"), dict):
        return utils.create_empty_figure(title="GIB OI Gauge", reason="Underlying data aggregates missing.")

    und_data = its_data["und_data_aggregates_CANONICAL_OBJ"]
    gib_oi_val_raw = und_data.get("GIB_OI_based_Und") 
    
    gib_oi_val = 0.0
    if isinstance(gib_oi_val_raw, (int, float)) and not np.isnan(gib_oi_val_raw):
        gib_oi_val = float(gib_oi_val_raw)
    elif gib_oi_val_raw is not None:
         logger.warning(f"MDD_Display: GIB_OI_based_Und value is not a valid number: {gib_oi_val_raw}. Using 0.")
    
    threshold_key = "gib_oi_conviction_threshold" 
    gib_threshold = float(utils.get_config_value(
        keys=["strategy_settings", "thresholds", threshold_key, "value"], 
        default_value_to_return=0.6  # Default if not found
    ))
    
    max_val_gauge = max(abs(gib_oi_val), gib_threshold * 1.5, 1.0) # Ensure gauge has reasonable max

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=gib_oi_val,
        title={'text': "<b>GIB OI Based Und Flow</b><br>(Gamma Imbalance Flow)", 'font': {'size': 16}},
        gauge={
            'axis': {'range': [-max_val_gauge, max_val_gauge], 'tickwidth': 1, 'tickcolor': "darkblue"},
            'bar': {'color': "rgba(0,0,0,0.1)"}, # Light bar color
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "#cccccc",
            'steps': [
                {'range': [-max_val_gauge, -gib_threshold], 'color': 'rgba(255, 100, 100, 0.5)'}, # Bearish
                {'range': [gib_threshold, max_val_gauge], 'color': 'rgba(100, 255, 100, 0.5)'}   # Bullish
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.90,
                'value': gib_threshold 
            } # This threshold line is for positive side
        },
        number={'valueformat': '.2f', 'font': {'size': 36}}
    ))
    fig.update_layout(
        height=utils.get_chart_specific_height(ID_GIB_OI_BASED_GAUGE_VIZ) or 300, 
        template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE,
        title_text="" # Title handled by indicator
    )
    utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
    logger.debug(f"MDD_Display: GIB OI Gauge generated. Value: {gib_oi_val}, Threshold: {gib_threshold}")
    return fig

def generate_mspi_heatmap_viz_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating MSPI Heatmap. Data type: {type(its_data)}")
    df_strike_metrics = its_data.get("df_strike_metrics_CANONICAL_OBJ") if its_data else None
    
    if not isinstance(df_strike_metrics, pd.DataFrame) or df_strike_metrics.empty:
        return utils.create_empty_figure(title="MSPI Heatmap", reason="Strike metrics data missing or empty.")

    required_cols = ['strike', 'dte_calc', 'mspi']
    df_strike_metrics, cols_ok = utils.ensure_columns_and_numeric_key_levels(df_strike_metrics, required_cols, "MSPI_Heatmap")
    if not cols_ok:
        return utils.create_empty_figure(title="MSPI Heatmap", reason="Required columns missing or invalid in strike data for MSPI.")

    try:
        # Ensure DTEs are integers and strikes are numeric for pivoting
        df_strike_metrics['dte_calc'] = df_strike_metrics['dte_calc'].astype(int)
        df_strike_metrics['strike'] = pd.to_numeric(df_strike_metrics['strike'], errors='coerce')
        df_strike_metrics = df_strike_metrics.dropna(subset=['strike', 'mspi'])


        pivot_df = df_strike_metrics.pivot_table(index='strike', columns='dte_calc', values='mspi', aggfunc='mean')
        if pivot_df.empty:
             return utils.create_empty_figure(title="MSPI Heatmap", reason="Could not pivot MSPI data (empty after pivot).")

        fig = go.Figure(data=go.Heatmap(
            z=pivot_df.values,
            x=pivot_df.columns,
            y=pivot_df.index,
            colorscale='RdYlGn', # Red-Yellow-Green
            zmid=0, # Center color scale at 0 for MSPI
            xgap=1, ygap=1
        ))
        fig.update_layout(
            title_text="<b>MSPI (Market Sentiment Pressure Index) Heatmap</b>",
            xaxis_title="Days to Expiration (DTE)",
            yaxis_title="Strike Price",
            height=utils.get_chart_specific_height(ID_MSPI_HEATMAP_VIZ) or 450, # Default height
            template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE
        )
        # Add current underlying price line if available
        if isinstance(its_data.get("und_data_aggregates_CANONICAL_OBJ"), dict):
            und_price = its_data["und_data_aggregates_CANONICAL_OBJ"].get(utils.get_config_value(["strategy_settings", "underlying_price_col_name"], "price"))
            if und_price is not None:
                fig = utils.add_price_line(fig, und_price, orientation='horizontal', line_label="Und. Price")
        
        utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
        logger.debug("MDD_Display: MSPI Heatmap generated.")
        return fig
    except Exception as e:
        logger.error(f"MDD_Display: Error generating MSPI Heatmap: {e}", exc_info=True)
        return utils.create_empty_figure(title="MSPI Heatmap", reason=f"Error: {str(e)[:100]}")


def generate_nvp_strike_viz_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating NVP Strike Profile. Data type: {type(its_data)}")
    df_strike_metrics = its_data.get("df_strike_metrics_CANONICAL_OBJ") if its_data else None

    if not isinstance(df_strike_metrics, pd.DataFrame) or df_strike_metrics.empty:
        return utils.create_empty_figure(title="NVP Strike Profile", reason="Strike metrics data missing or empty.")

    required_cols = ['strike', 'nvp_strike', 'arfi_strike'] # NVP and ARFI
    df_strike_metrics, cols_ok = utils.ensure_columns_and_numeric_key_levels(df_strike_metrics, required_cols, "NVP_ARFI_Strike_Profile")
    if not cols_ok:
        return utils.create_empty_figure(title="NVP Strike Profile", reason="Required columns (strike, nvp_strike, arfi_strike) missing or invalid.")
    
    df_strike_metrics['strike'] = pd.to_numeric(df_strike_metrics['strike'], errors='coerce').dropna()
    df_agg = df_strike_metrics.groupby('strike').agg({'nvp_strike': 'sum', 'arfi_strike': 'sum'}).reset_index()
    df_agg = df_agg.sort_values(by='strike')

    if df_agg.empty:
        return utils.create_empty_figure(title="NVP Strike Profile", reason="No valid aggregated NVP/ARFI data.")

    fig = make_subplots(specs=[[{"secondary_y": True}]]) # make_subplots is used here
    fig.add_trace(go.Bar(x=df_agg['strike'], y=df_agg['nvp_strike'], name='NVP (Net Value Pressure)', marker_color='rgba(0, 128, 255, 0.7)'), secondary_y=False)
    fig.add_trace(go.Scatter(x=df_agg['strike'], y=df_agg['arfi_strike'], name='ARFI (Agg. Risk Flow Imb.)', mode='lines+markers', line=dict(color='rgba(255, 165, 0, 0.9)')), secondary_y=True)
    
    fig.update_layout(
        title_text="<b>NVP & ARFI Strike Profile</b>",
        xaxis_title="Strike Price",
        height=utils.get_chart_specific_height(ID_NVP_STRIKE_VIZ) or 450,
        template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_yaxes(title_text="NVP (Net Value Pressure)", secondary_y=False)
    fig.update_yaxes(title_text="ARFI (Risk Flow Imbalance)", secondary_y=True, showgrid=False) # Hide grid for secondary y-axis
    
    if isinstance(its_data.get("und_data_aggregates_CANONICAL_OBJ"), dict):
        und_price = its_data["und_data_aggregates_CANONICAL_OBJ"].get(utils.get_config_value(["strategy_settings", "underlying_price_col_name"], "price"))
        if und_price is not None:
            fig = utils.add_price_line(fig, und_price, orientation='vertical', line_label="Und. Price")

    utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
    logger.debug("MDD_Display: NVP Strike Profile generated.")
    return fig

def generate_combined_rolling_flow_chart_viz_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating Combined Rolling Flow Chart. Data type: {type(its_data)}")
    und_data = its_data.get("und_data_aggregates_CANONICAL_OBJ") if its_data else None
    
    if not isinstance(und_data, dict):
        return utils.create_empty_figure(title="Combined Rolling Flows", reason="Underlying aggregate data missing.")

    # Assuming these keys exist in und_data after metrics calculation
    flow_metrics = {
        "NetValueFlow_15m_Und": "Net Value Flow (15m)",
        "GIB_OI_based_Und": "GIB OI Based Flow", # This is a snapshot, not rolling, but can be plotted
        # Add more rolling flow metrics here as they become available
        # "SomeOtherFlow_30m_Und": "Some Other Flow (30m)" 
    }
    
    fig = make_subplots() # make_subplots is used here
    
    plot_data_found = False
    for key, name in flow_metrics.items():
        value = und_data.get(key)
        if isinstance(value, (int, float)) and not np.isnan(value):
            # For single values, we plot them as horizontal lines for now, or consider a bar chart if more appropriate contextually
            # For a true "rolling flow" this would usually be a time series.
            # Here, we adapt to show current snapshot values if that's what's in und_data.
            # If these are *actually* series in und_data (e.g. last N points), the chart needs to be different.
            # Assuming they are single current values for this placeholder:
            fig.add_trace(go.Bar(x=[name], y=[value], name=name))
            plot_data_found = True
        elif value is not None:
             logger.warning(f"MDD_Display: Flow metric '{key}' has non-numeric value: {value}")


    if not plot_data_found:
        return utils.create_empty_figure(title="Combined Rolling Flows", reason="No valid flow metric data found.")

    fig.update_layout(
        title_text="<b>Combined Rolling Flow Metrics (Snapshot)</b>",
        xaxis_title="Metric",
        yaxis_title="Value",
        height=utils.get_chart_specific_height(ID_COMBINED_ROLLING_FLOW_CHART_VIZ) or 400,
        template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE,
        showlegend=len(flow_metrics) > 1 # Show legend if multiple metrics
    )
    utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
    logger.debug("MDD_Display: Combined Rolling Flow Chart generated.")
    return fig

def generate_vri_0dte_aggregated_viz_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating VRI 0DTE Aggregated Viz. Data type: {type(its_data)}")
    und_data = its_data.get("und_data_aggregates_CANONICAL_OBJ") if its_data else None

    if not isinstance(und_data, dict):
        return utils.create_empty_figure(title="VRI 0DTE Aggregated", reason="Underlying aggregate data missing.")

    vri_val_raw = und_data.get("vri_0dte_und_sum") # Key from ITS Orchestrator
    vri_val = 0.0
    if isinstance(vri_val_raw, (int, float)) and not np.isnan(vri_val_raw):
        vri_val = float(vri_val_raw)
    elif vri_val_raw is not None:
        logger.warning(f"MDD_Display: vri_0dte_und_sum value is not a valid number: {vri_val_raw}. Using 0.")
        
    # Example: Simple bar for VRI
    fig = go.Figure(go.Bar(
        x=['VRI 0DTE Sum'], 
        y=[vri_val],
        name='VRI 0DTE Sum',
        marker_color='teal'
    ))
    fig.update_layout(
        title_text="<b>VRI (Volatility Risk Index) 0DTE Aggregated</b>",
        height=utils.get_chart_specific_height(ID_VRI_0DTE_AGGREGATED_VIZ) or 350,
        template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE,
        yaxis_title="VRI Sum Value"
    )
    utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
    logger.debug(f"MDD_Display: VRI 0DTE Aggregated Viz generated. Value: {vri_val}")
    return fig


def generate_key_levels_summary_viz_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating Key Levels Summary. Data type: {type(its_data)}")
    und_data = its_data.get("und_data_aggregates_CANONICAL_OBJ") if its_data else None

    if not isinstance(und_data, dict):
        return utils.create_empty_figure(title="Key Levels Summary", reason="Underlying aggregate data missing.")

    levels_to_display = {
        "HP_EOD_Und": "High Perf. EOD Level", # Key from ITS Orchestrator
        # Add other key levels from und_data as they become available
        # e.g. "vwap_daily": "VWAP Daily"
    }
    
    level_names = []
    level_values = []
    plot_data_found = False

    for key, name in levels_to_display.items():
        value = und_data.get(key)
        if isinstance(value, (int, float)) and not np.isnan(value):
            level_names.append(name)
            level_values.append(value)
            plot_data_found = True
        elif value is not None:
            logger.warning(f"MDD_Display: Key Level '{key}' has non-numeric value: {value}")
            
    if not plot_data_found:
        return utils.create_empty_figure(title="Key Levels Summary", reason="No valid key level data found.")

    fig = go.Figure(data=[go.Bar(x=level_names, y=level_values, text=level_values, textposition='auto', marker_color='skyblue')])
    fig.update_layout(
        title_text="<b>Key Levels Summary</b>",
        height=utils.get_chart_specific_height(ID_KEY_LEVELS_SUMMARY_VIZ) or 400,
        template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE,
        xaxis_title="Level Type",
        yaxis_title="Price Level"
    )
    utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
    logger.debug("MDD_Display: Key Levels Summary generated.")
    return fig

def generate_strategy_recommendations_table_display_figure(its_data: Optional[DashboardDataBundle], app_config: Dict[str, Any]) -> go.Figure:
    logger.info(f"MDD_Display: Generating Strategy Recommendations Table. Data type: {type(its_data)}")
    active_recos = its_data.get("active_recommendations_managed") if its_data else None

    if not isinstance(active_recos, list) or not active_recos:
        return utils.create_empty_figure(title="Strategy Recommendations", reason="No active recommendations available.")

    # Define columns for the table - adjust based on actual recommendation dict keys
    header_values = ['ID', 'Symbol', 'Type', 'Bias', 'Entry', 'SL', 'T1', 'T2', 'Status', 'Conviction']
    # Map recommendation keys to header values - this needs careful alignment
    reco_key_map = {
        'ID': 'id', 'Symbol': 'underlying_symbol', 'Type': 'category', 'Bias': 'bias',
        'Entry': 'entry_price_at_signal', 'SL': 'stop_loss', 'T1': 'target_1', 'T2': 'target_2',
        'Status': 'status', 'Conviction': 'overall_conviction_score'
    }
    
    cells_values = [[] for _ in header_values] # Initialize list of lists for cells

    for reco in active_recos:
        if not isinstance(reco, dict): continue
        for i, header_name in enumerate(header_values):
            key_in_reco = reco_key_map.get(header_name)
            val = reco.get(key_in_reco, "N/A")
            if isinstance(val, float): val = f"{val:.2f}" # Format floats
            cells_values[i].append(str(val))

    if not any(cells_values): # Check if any data was actually added
         return utils.create_empty_figure(title="Strategy Recommendations", reason="No valid recommendation data to display.")

    fig = go.Figure(data=[go.Table(
        header=dict(values=header_values, fill_color='paleturquoise', align='left'),
        cells=dict(values=cells_values, fill_color='lavender', align='left')
    )])
    fig.update_layout(
        title_text="<b>Active Strategy Recommendations</b>",
        height=utils.get_chart_specific_height(ID_STRATEGY_RECOMMENDATIONS_TABLE_DISPLAY) or 400,
        template=utils.PLOTLY_TEMPLATE_FOR_UTILS_MODULE
    )
    utils.add_timestamp_annotation(fig, its_data.get("timestamp"))
    logger.debug("MDD_Display: Strategy Recommendations Table generated.")
    return fig


# --- Chart Registration Function for 'main' mode ---
def register_mode_charts():
    """Registers all chart generator functions for the 'main' display mode."""
    logger.info("MDD_Display: Registering chart generators for 'main' mode...")

    # Ensure these IDs match exactly what's imported via `from ..ids import ...`
    # and what's defined as fallback IDs in the except ImportError block.
    charts_to_register = [
        (ID_MARKET_REGIME_INDICATOR_DISPLAY, generate_market_regime_indicator_display_figure), # Corrected name
        (ID_GIB_OI_BASED_GAUGE_VIZ, generate_gib_oi_based_gauge_viz_figure),
        (ID_MSPI_HEATMAP_VIZ, generate_mspi_heatmap_viz_figure),
        (ID_NVP_STRIKE_VIZ, generate_nvp_strike_viz_figure),
        (ID_COMBINED_ROLLING_FLOW_CHART_VIZ, generate_combined_rolling_flow_chart_viz_figure),
        (ID_VRI_0DTE_AGGREGATED_VIZ, generate_vri_0dte_aggregated_viz_figure),
        (ID_KEY_LEVELS_SUMMARY_VIZ, generate_key_levels_summary_viz_figure),
        (ID_STRATEGY_RECOMMENDATIONS_TABLE_DISPLAY, generate_strategy_recommendations_table_display_figure),
    ]

    for chart_id, generator_function in charts_to_register:
        # Ensure layout_manager is not None and has the method (especially if dummy was used)
        if hasattr(layout_manager, 'register_chart_generator') and callable(layout_manager.register_chart_generator):
            layout_manager.register_chart_generator(
                mode_name="main", # Mode name should be lowercase as per convention
                chart_id=chart_id,
                generator_function=generator_function
            )
            logger.debug(f"MDD_Display: Registered chart '{chart_id}' for 'main' mode.")
        else:
            logger.error(f"MDD_Display: layout_manager or register_chart_generator not available. Cannot register chart '{chart_id}'.")
            
    logger.info("MDD_Display: Completed registration of chart generators for 'main' mode.")

# This ensures that if the module is imported, registration happens if layout_manager is available.
# The actual call from populate_all_registered_chart_ids in layout_manager is the primary mechanism.
if hasattr(layout_manager, 'register_chart_generator'): # Basic check
    pass # register_mode_charts() # Decided against auto-calling here to let layout_manager control it.
else:
    logger.warning("MDD_Display: layout_manager not fully available at module load time for potential pre-registration.")

logger.info("MDD_Display: Main Dashboard Display Mode Module (main_dashboard_display.py) V2.4 Initialized.")
