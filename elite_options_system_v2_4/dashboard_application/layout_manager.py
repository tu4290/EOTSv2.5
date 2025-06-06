# dashboard_application/layout_manager.py
import logging
from typing import Dict, Any, Optional, List, Callable
from dash import html, dcc # type: ignore
import dash_bootstrap_components as dbc # type: ignore
import importlib

# --- Corrected import for utilities ---
try:
    from . import utils_dashboard as utils 
    layout_logger = utils.utils_logger 
except ImportError:
    layout_logger = logging.getLogger(__name__)
    layout_logger.critical("LayoutManager: CRITICAL - Failed to import .utils_dashboard. Layout generation will likely fail or use severe fallbacks.", exc_info=True)
    class DummyUtilsLayoutManager: 
        def get_config_value(self, keys: Any, default_value_to_return: Any = None, config_dict_override: Optional[Dict[str,Any]] = None) -> Any:
            return default_value_to_return
    utils = DummyUtilsLayoutManager() # type: ignore

# --- Import IDs safely ---
try:
    from . import ids
    ID_URL_LOCATION = ids.ID_URL_LOCATION
    ID_MAIN_CONTENT_AREA = ids.ID_MAIN_CONTENT_AREA
    ID_CONTROL_PANEL_DIV = ids.ID_CONTROL_PANEL_DIV
    ID_STATUS_DISPLAY_AREA = ids.ID_STATUS_DISPLAY_AREA
    ID_MODE_SELECTOR_TABS = ids.ID_MODE_SELECTOR_TABS 
    ID_SYMBOL_INPUT = ids.ID_SYMBOL_INPUT
    ID_DTE_INPUT = ids.ID_DTE_INPUT
    ID_RANGE_SLIDER = ids.ID_RANGE_SLIDER
    ID_RANGE_SLIDER_OUTPUT_LABEL = ids.ID_RANGE_SLIDER_OUTPUT_LABEL
    ID_FETCH_DATA_BUTTON = ids.ID_FETCH_DATA_BUTTON
    ID_MAIN_DATA_STORE_MEMORY = ids.ID_MAIN_DATA_STORE_MEMORY
    ID_CURRENT_MODE_STORE = ids.ID_CURRENT_MODE_STORE
    ID_HIDDEN_INITIAL_LOAD_TRIGGER = ids.ID_HIDDEN_INITIAL_LOAD_TRIGGER
    ID_AUTO_REFRESH_INTERVAL_COMPONENT = ids.ID_AUTO_REFRESH_INTERVAL_COMPONENT
    ID_REFRESH_INTERVAL_DROPDOWN = ids.ID_REFRESH_INTERVAL_DROPDOWN
    ID_REFRESH_INTERVAL_STORE = ids.ID_REFRESH_INTERVAL_STORE
except ImportError:
    layout_logger.critical("LayoutManager: CRITICAL - Failed to import .ids module. Using placeholder IDs.", exc_info=True)
    ID_URL_LOCATION, ID_MAIN_CONTENT_AREA, ID_CONTROL_PANEL_DIV, ID_STATUS_DISPLAY_AREA, \
    ID_MODE_SELECTOR_TABS, ID_SYMBOL_INPUT, ID_DTE_INPUT, ID_RANGE_SLIDER, ID_RANGE_SLIDER_OUTPUT_LABEL, \
    ID_FETCH_DATA_BUTTON, ID_MAIN_DATA_STORE_MEMORY, ID_CURRENT_MODE_STORE, \
    ID_HIDDEN_INITIAL_LOAD_TRIGGER, ID_AUTO_REFRESH_INTERVAL_COMPONENT, ID_REFRESH_INTERVAL_DROPDOWN, \
    ID_REFRESH_INTERVAL_STORE = [f"fallback-id-{i}" for i in range(16)]


_REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE: Dict[str, Dict[str, Callable]] = {}
_ALL_REGISTERED_CHART_IDS: List[str] = []

def get_mode_details(mode_key: str, app_config_for_modes: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not mode_key: return None
    modes_config_path = ["visualization_settings", "dashboard", "modes_detail_config"]
    mode_specific_config = utils.get_config_value(keys=modes_config_path + [mode_key], default_value_to_return=None, config_dict_override=app_config_for_modes)
    if isinstance(mode_specific_config, dict): return mode_specific_config
    else: layout_logger.warning(f"LayoutManager: Configuration for mode '{mode_key}' not found or is not a dictionary."); return None

def _build_control_panel_v2_4(app_config: Optional[Dict[str, Any]] = None) -> dbc.Card:
    default_symbol = utils.get_config_value(keys=["visualization_settings", "dashboard", "defaults", "symbol"], default_value_to_return="SPY", config_dict_override=app_config)
    default_dte = utils.get_config_value(keys=["visualization_settings", "dashboard", "defaults", "dte"], default_value_to_return="0", config_dict_override=app_config)
    default_range_pct = utils.get_config_value(keys=["visualization_settings", "dashboard", "defaults", "range_pct"], default_value_to_return=5, config_dict_override=app_config)
    range_slider_marks_cfg = utils.get_config_value(keys=["visualization_settings", "dashboard", "range_slider_marks"], default_value_to_return={}, config_dict_override=app_config)
    range_slider_marks_processed = {}
    if isinstance(range_slider_marks_cfg, dict):
        for k, v_mark in range_slider_marks_cfg.items():
            try: range_slider_marks_processed[float(k)] = str(v_mark)
            except ValueError: layout_logger.warning(f"Could not convert range slider mark key '{k}' to float.")
    if not range_slider_marks_processed: range_slider_marks_processed = {i: str(i) for i in range(1, 11)}
    control_panel_styling = utils.get_config_value(keys=["visualization_settings", "dashboard", "styles", "control_panel"], default_value_to_return={}, config_dict_override=app_config)
    label_styling = utils.get_config_value(keys=["visualization_settings", "dashboard", "styles", "control_label"], default_value_to_return={}, config_dict_override=app_config)
    refresh_options_cfg = utils.get_config_value(keys=["visualization_settings", "dashboard", "refresh_options"], default_value_to_return=[], config_dict_override=app_config)
    control_panel_content = dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Div([dbc.Label("Symbol:", html_for=ID_SYMBOL_INPUT, style=label_styling), dbc.Input(id=ID_SYMBOL_INPUT, value=default_symbol, type="text", placeholder="e.g., SPY", className="mb-2 form-control-sm")]), width=6, sm=3, md=2),
            dbc.Col(html.Div([dbc.Label("DTE:", html_for=ID_DTE_INPUT, style=label_styling), dbc.Input(id=ID_DTE_INPUT, value=default_dte, type="text", placeholder="e.g., 0,1,7-10", className="mb-2 form-control-sm")]), width=6, sm=3, md=2),
            dbc.Col(html.Div([dbc.Label(f"Range:", id=ID_RANGE_SLIDER_OUTPUT_LABEL, style=label_styling), dcc.Slider(id=ID_RANGE_SLIDER, min=0.5, max=10, step=0.1, value=default_range_pct, marks=range_slider_marks_processed, tooltip={"placement": "bottom", "always_visible": False}, className="mb-3 custom-slider" )]), width=12, sm=6, md=3),
            dbc.Col(html.Div([dbc.Label("Refresh:", style=label_styling), dcc.Dropdown(id=ID_REFRESH_INTERVAL_DROPDOWN, options=refresh_options_cfg, value=0, clearable=False, searchable=False, className="form-select-sm")]), width=6, sm=4, md=2, className="mt-3 mt-sm-0"),
            dbc.Col(html.Div([dbc.Button("Fetch Data", id=ID_FETCH_DATA_BUTTON, color="primary", className="w-100 mt-3 mt-md-0", size="sm")]), width=6, sm=4, md=2, className="d-flex align-items-end pb-2 pb-md-0")
        ], className="align-items-start"),
    ], style=control_panel_styling)
    return dbc.Card(control_panel_content, className="mb-3 shadow-sm control-panel-card-class")

def _build_mode_selector_v2_4(app_config: Optional[Dict[str, Any]] = None) -> html.Div:
    modes_config = utils.get_config_value(keys=["visualization_settings", "dashboard", "modes_detail_config"], default_value_to_return={}, config_dict_override=app_config)
    tabs_children = []
    if isinstance(modes_config, dict):
        for mode_key, mode_details in modes_config.items():
            if isinstance(mode_details, dict) and "label" in mode_details:
                tabs_children.append(dbc.Tab(label=str(mode_details["label"]), tab_id=mode_key, className="custom-tab", active_tab_class_name="custom-active-tab"))
    if not tabs_children: return html.Div("Error: No display modes configured.", style={"color": "red", "textAlign": "center"})
    default_active_mode = utils.get_config_value(keys=["visualization_settings", "dashboard", "defaults", "mode"], default_value_to_return=list(modes_config.keys())[0] if modes_config else "main", config_dict_override=app_config)
    return html.Div(dbc.Tabs(id=ID_MODE_SELECTOR_TABS, active_tab=str(default_active_mode).lower(), children=tabs_children, className="mb-3 mode-selector-tabs-class nav-tabs-custom"))

def build_dynamic_mode_layout(active_mode_key: str, app_config_for_layout: Optional[Dict[str, Any]] = None) -> html.Div:
    layout_logger.info(f"LayoutManager: Building dynamic chart layout for mode: '{active_mode_key}'")
    mode_details = get_mode_details(active_mode_key, app_config_for_modes=app_config_for_layout)
    if not isinstance(mode_details, dict) or not isinstance(mode_details.get("charts"), list):
        layout_logger.error(f"LayoutManager: Invalid or missing chart configuration for mode '{active_mode_key}'. Returning empty layout.")
        return html.Div(f"Error: Chart configuration for mode '{active_mode_key}' is invalid or missing.")
    chart_ids_for_mode = mode_details["charts"]
    charts_per_row = int(utils.get_config_value(keys=["visualization_settings", "dashboard", "charts_per_row"], default_value_to_return=2, config_dict_override=app_config_for_layout))
    full_width_chart_ids = utils.get_config_value(keys=["visualization_settings", "dashboard", "full_width_chart_ids"], default_value_to_return=[], config_dict_override=app_config_for_layout)
    rows = []; current_row_charts: List[dbc.Col] = []
    for chart_id_str in chart_ids_for_mode:
        if not isinstance(chart_id_str, str): layout_logger.warning(f"LayoutManager: Invalid chart_id '{chart_id_str}' in mode '{active_mode_key}' config. Skipping."); continue
        chart_placeholder = dcc.Loading(type="default", children=[html.Div(id=chart_id_str, className="chart-placeholder-class")])
        col_width = 12 if chart_id_str in full_width_chart_ids else (12 // charts_per_row if charts_per_row > 0 else 12)
        current_row_charts.append(dbc.Col(dbc.Card(dbc.CardBody(chart_placeholder)), width=12, lg=col_width, className="mb-3 chart-col-class"))
        if len(current_row_charts) == charts_per_row or chart_id_str in full_width_chart_ids:
            rows.append(dbc.Row(current_row_charts, className="mb-2 chart-row-class")); current_row_charts = []
    if current_row_charts: rows.append(dbc.Row(current_row_charts, className="mb-2 chart-row-class"))
    layout_logger.info(f"LayoutManager: Dynamic layout for mode '{active_mode_key}' generated with {len(chart_ids_for_mode)} chart placeholders.")
    return html.Div(rows, className="dynamic-mode-layout-container-class")

def get_main_dashboard_layout_v2_4(app_config: Optional[Dict[str, Any]] = None, its_orch_ref_for_layout: Optional[Any] = None ) -> html.Div:
    layout_logger.info("LayoutManager: Generating V2.4 dashboard main layout structure...")
    dashboard_title = utils.get_config_value(keys=["visualization_settings", "dashboard", "title"], default_value_to_return="EOTS V2.4 Dashboard", config_dict_override=app_config)
    footer_text = utils.get_config_value(keys=["visualization_settings", "dashboard", "footer"], default_value_to_return="© 2025 EOTS Inc.", config_dict_override=app_config)
    main_container_style = utils.get_config_value(keys=["visualization_settings", "dashboard", "styles", "main_container"], default_value_to_return={}, config_dict_override=app_config)
    page_title_style = utils.get_config_value(keys=["visualization_settings", "dashboard", "styles", "page_title"], default_value_to_return={}, config_dict_override=app_config)
    main_footer_style = utils.get_config_value(keys=["visualization_settings", "dashboard", "styles", "main_footer"], default_value_to_return={}, config_dict_override=app_config)
    default_active_mode = utils.get_config_value(keys=["visualization_settings", "dashboard", "defaults", "mode"], default_value_to_return="main", config_dict_override=app_config)
    initial_dynamic_layout = build_dynamic_mode_layout(str(default_active_mode).lower(), app_config_for_layout=app_config)
    layout = html.Div([
        dcc.Location(id=ID_URL_LOCATION, refresh=False),
        dcc.Store(id=ID_MAIN_DATA_STORE_MEMORY, storage_type='memory'),
        dcc.Store(id=ID_CURRENT_MODE_STORE, storage_type='memory', data=str(default_active_mode).lower()),
        dcc.Store(id=ID_REFRESH_INTERVAL_STORE, storage_type='memory'), 
        dcc.Interval(id=ID_AUTO_REFRESH_INTERVAL_COMPONENT, interval=60*1000, n_intervals=0, disabled=True),
        html.Div(id=ID_HIDDEN_INITIAL_LOAD_TRIGGER, style={'display': 'none'}),
        dbc.Container(html.H1(dashboard_title, className="my-4 text-center page-title-class", style=page_title_style), fluid=True),
        dbc.Container(html.Div(id=ID_CONTROL_PANEL_DIV, children=[_build_control_panel_v2_4(app_config)]), fluid=True, className="control-panel-container-class"),
        dbc.Container(html.Div(id=ID_STATUS_DISPLAY_AREA, className="status-display-container-class"), fluid=True, className="mb-3"),
        dbc.Container(html.Div(id="mode-selector-container-id", children=[_build_mode_selector_v2_4(app_config)]), fluid=True, className="mode-selector-container-class"),
        dbc.Container(html.Div(id=ID_MAIN_CONTENT_AREA, children=[initial_dynamic_layout]), fluid=True, className="mt-3 main-content-area-class"),
        dbc.Container(html.Footer(dcc.Markdown(footer_text), className="text-center text-muted mt-5 main-footer-class", style=main_footer_style), fluid=True)
    ], style=main_container_style, className="main-dashboard-layout-class")
    layout_logger.info("Main dashboard layout V2.4 generated successfully.")
    return layout

def register_chart_generator(mode_name: str, chart_id: str, generator_function: Callable) -> None:
    global _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE, _ALL_REGISTERED_CHART_IDS
    if mode_name not in _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE: _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE[mode_name] = {}
    if chart_id in _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE[mode_name]: layout_logger.warning(f"Chart generator for mode '{mode_name}', ID '{chart_id}' is being overwritten.")
    _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE[mode_name][chart_id] = generator_function
    if chart_id not in _ALL_REGISTERED_CHART_IDS: _ALL_REGISTERED_CHART_IDS.append(chart_id)
    layout_logger.debug(f"Registered chart generator for Mode: '{mode_name}', Chart ID: '{chart_id}', Function: {generator_function.__name__}")

def get_chart_generator_function(mode_name: str, chart_id: str) -> Optional[Callable]:
    return _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE.get(mode_name, {}).get(chart_id)

def get_all_registered_chart_ids() -> List[str]: return list(set(_ALL_REGISTERED_CHART_IDS))

def populate_all_registered_chart_ids(config_manager_ref: Any) -> List[str]:
    global _ALL_REGISTERED_CHART_IDS, _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE
    _ALL_REGISTERED_CHART_IDS = []; _REGISTERED_CHART_GENERATOR_FUNCTIONS_BY_MODE = {}
    layout_logger.info("LayoutManager: Populating all registered chart IDs by dynamically importing mode modules...")
    raw_config_for_modes = None
    if config_manager_ref and hasattr(config_manager_ref, 'get_config'): raw_config_for_modes = config_manager_ref.get_config()
    modes_detail_config = utils.get_config_value(keys=["visualization_settings", "dashboard", "modes_detail_config"], default_value_to_return={}, config_dict_override=raw_config_for_modes )
    if not isinstance(modes_detail_config, dict) or not modes_detail_config:
        layout_logger.error("LayoutManager: 'modes_detail_config' is missing or invalid in configuration. Cannot populate chart IDs."); return []
    for mode_key, mode_details_cfg in modes_detail_config.items():
        if isinstance(mode_details_cfg, dict) and "module_name" in mode_details_cfg:
            module_name_str = mode_details_cfg["module_name"]
            try:
                full_module_path = f"dashboard_application.modes.{module_name_str}"
                mode_module = importlib.import_module(full_module_path)
                layout_logger.info(f"LayoutManager: Successfully imported mode module '{full_module_path}'.")
                if hasattr(mode_module, 'register_mode_charts') and callable(getattr(mode_module, 'register_mode_charts')):
                    getattr(mode_module, 'register_mode_charts')(); layout_logger.info(f"LayoutManager: Called 'register_mode_charts' for module '{module_name_str}'.")
            except ImportError as e_import_mode: layout_logger.error(f"LayoutManager: Failed to import mode module '{module_name_str}' (path: {full_module_path}): {e_import_mode}")
            except Exception as e_mode_load: layout_logger.error(f"LayoutManager: Error processing mode module '{module_name_str}': {e_mode_load}", exc_info=True)
        else: layout_logger.warning(f"LayoutManager: Invalid configuration for mode '{mode_key}'. Missing 'module_name' or not a dict.")
    layout_logger.info(f"LayoutManager: Chart ID population complete. Found {len(get_all_registered_chart_ids())} unique chart IDs across all modes. IDs: {get_all_registered_chart_ids()}")
    return get_all_registered_chart_ids()

def get_fallback_layout(error_message: str = "Error loading main dashboard layout.") -> html.Div:
    layout_logger.error(f"FALLBACK LAYOUT USED: {error_message}")
    return html.Div([html.H1("EOTS Dashboard - Error"), html.P("The dashboard could not be loaded due to an internal error."), html.P(f"Details: {error_message}", style={"color": "red", "fontFamily": "monospace"}), html.Hr(), html.Small("Please check the application logs for more information or contact support.")], style={"padding": "20px", "textAlign": "center"})

layout_logger.info("Dashboard Layout Manager (layout_manager.py) V2.4 Canonical Initialized.")
