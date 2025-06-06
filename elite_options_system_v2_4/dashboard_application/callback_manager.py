# dashboard_application/callback_manager.py
import logging
from typing import Dict, Any, Optional, List, Deque, Callable, Tuple 
from collections import deque 
from datetime import datetime
import importlib 

import dash
from dash import html, Input, Output, State, ctx, no_update, Patch
import plotly.graph_objects as go # type: ignore
import pandas as pd # type: ignore
import dash_bootstrap_components as dbc 
import dash_ag_grid as dag # type: ignore # Uncomment if used

# --- Module-Specific Logger ---
callback_logger = logging.getLogger(__name__)

# --- Global References (populated by app_main.initialize_dashboard_dependencies) ---
_APP_INSTANCE_REF_CB: Optional[dash.Dash] = None
_ITS_ORCHESTRATOR_REF_CB: Optional[Any] = None
_CONFIG_MANAGER_REF_CB: Optional[Any] = None
_RAW_APP_CONFIG_REF_CB: Optional[Dict[str, Any]] = None
_SERVER_SIDE_CACHE_REF_CB: Optional[Dict[str, Any]] = None 
_COMPONENT_HISTORY_CACHE_REF_CB: Optional[Dict[str, Deque[Any]]] = None

# --- Utility Function Imports ---
_utils_imported_ok_cb = False
utils_dashboard_module: Optional[Any] = None 
# Fallback definitions
get_config_value_util: Callable = lambda keys, default_value_to_return=None, **kwargs: default_value_to_return
create_empty_figure_util: Callable = lambda title, **kwargs: go.Figure() 
format_status_message_enhanced_util: Callable = lambda message, **kwargs: html.Div(message) # type: ignore
get_server_side_store_data_key_util: Callable = lambda *args, **kwargs: "fallback_key" 
get_chart_specific_height_util: Callable = lambda chart_id: 450 
add_timestamp_annotation_util: Callable = lambda fig, ts: fig 
add_price_line_util: Callable = lambda fig, px, **kwargs: fig 
store_in_server_side_cache_util: Callable = lambda key, data, cache_dict, **kwargs: None 
get_data_from_server_cache_util: Callable = lambda key, cache, **kwargs: None 
parse_dte_input_string_util: Callable = lambda dte_str: [] 
create_hover_text_from_dict_util: Callable = lambda data_dict, **kwargs: "" 

try:
    from . import utils_dashboard as utils 
    utils_dashboard_module = utils 
    get_config_value_util = utils.get_config_value
    create_empty_figure_util = utils.create_empty_figure
    format_status_message_enhanced_util = utils.format_status_message_enhanced
    get_server_side_store_data_key_util = utils.get_server_side_store_data_key
    get_chart_specific_height_util = utils.get_chart_specific_height
    add_timestamp_annotation_util = utils.add_timestamp_annotation
    add_price_line_util = utils.add_price_line
    store_in_server_side_cache_util = utils.store_in_server_side_cache
    get_data_from_server_cache_util = utils.get_data_from_server_cache
    parse_dte_input_string_util = utils.parse_dte_input_string
    create_hover_text_from_dict_util = utils.create_hover_text_from_dict
    _utils_imported_ok_cb = True
    callback_logger.info("CallbackManager: Successfully imported and assigned functions from .utils_dashboard.")
except ImportError as e_util_cb_final:
    callback_logger.critical(f"CallbackManager CRITICAL: Failed to import .utils_dashboard: {e_util_cb_final}. Essential utilities will use fallbacks.", exc_info=True)

# --- ID Imports ---
_ids_imported_ok_cb_flag = False 
try:
    from . import ids as ids_module_ref 
    
    ID_SYMBOL_INPUT = ids_module_ref.ID_SYMBOL_INPUT
    ID_DTE_INPUT = ids_module_ref.ID_DTE_INPUT
    ID_RANGE_SLIDER = ids_module_ref.ID_RANGE_SLIDER
    ID_FETCH_DATA_BUTTON = ids_module_ref.ID_FETCH_DATA_BUTTON
    ID_STATUS_DISPLAY_ALERT = ids_module_ref.ID_STATUS_DISPLAY_ALERT 
    ID_AUTO_REFRESH_INTERVAL_COMPONENT = ids_module_ref.ID_AUTO_REFRESH_INTERVAL_COMPONENT
    ID_REFRESH_INTERVAL_DROPDOWN = ids_module_ref.ID_REFRESH_INTERVAL_DROPDOWN
    ID_MAIN_DATA_STORE_MEMORY = ids_module_ref.ID_MAIN_DATA_STORE_MEMORY
    ID_CURRENT_MODE_STORE = ids_module_ref.ID_CURRENT_MODE_STORE
    ID_HIDDEN_INITIAL_LOAD_TRIGGER = ids_module_ref.ID_HIDDEN_INITIAL_LOAD_TRIGGER
    ID_MAIN_CONTENT_AREA = ids_module_ref.ID_MAIN_CONTENT_AREA
    ID_RANGE_SLIDER_OUTPUT_LABEL = ids_module_ref.ID_RANGE_SLIDER_OUTPUT_LABEL
    ID_REFRESH_INTERVAL_STORE = ids_module_ref.ID_REFRESH_INTERVAL_STORE
    ID_MODE_SELECTOR_TABS = ids_module_ref.ID_MODE_SELECTOR_TABS
    ID_STATUS_DISPLAY_AREA = ids_module_ref.ID_STATUS_DISPLAY_AREA # Added import
    
    ALL_DYNAMIC_CHART_IDS: List[str] = [] 
    _ids_imported_ok_cb_flag = True 
    callback_logger.info("CallbackManager: Successfully imported .ids module and assigned ID constants.")
except ImportError as e_ids_cb:
    callback_logger.critical(f"CallbackManager CRITICAL: Failed to import IDs from .ids: {e_ids_cb}. Using fallback ID constants.", exc_info=True)
    ID_SYMBOL_INPUT, ID_DTE_INPUT, ID_RANGE_SLIDER, ID_FETCH_DATA_BUTTON, \
    ID_STATUS_DISPLAY_ALERT, ID_AUTO_REFRESH_INTERVAL_COMPONENT, ID_REFRESH_INTERVAL_DROPDOWN, \
    ID_MAIN_DATA_STORE_MEMORY, ID_CURRENT_MODE_STORE, ID_HIDDEN_INITIAL_LOAD_TRIGGER, \
    ID_MAIN_CONTENT_AREA, ID_RANGE_SLIDER_OUTPUT_LABEL, ID_REFRESH_INTERVAL_STORE, \
    ID_MODE_SELECTOR_TABS, ID_STATUS_DISPLAY_AREA = [f"fallback-cb-id-{i}" for i in range(15)] # Added ID_STATUS_DISPLAY_AREA and incremented range
    ALL_DYNAMIC_CHART_IDS = []

# --- Layout Manager Function Imports ---
_layout_funcs_imported_ok_cb = False
build_dynamic_mode_layout_func_ref: Optional[Callable] = None
get_chart_generator_function_ref: Optional[Callable] = None 
get_all_registered_chart_ids_ref: Optional[Callable] = None

try:
    from . import layout_manager as layout_manager_imported_module 
    build_dynamic_mode_layout_func_ref = layout_manager_imported_module.build_dynamic_mode_layout
    get_chart_generator_function_ref = layout_manager_imported_module.get_chart_generator_function
    get_all_registered_chart_ids_ref = layout_manager_imported_module.get_all_registered_chart_ids
    _layout_funcs_imported_ok_cb = True
    callback_logger.info("CallbackManager: Successfully imported layout functions from .layout_manager.")
except ImportError as e_lm_cb: 
    callback_logger.critical(f"CallbackManager CRITICAL: Failed to import layout functions from .layout_manager: {e_lm_cb}. Layout building will use fallbacks.", exc_info=True)
    def fallback_build_dynamic_layout(*args, **kwargs): return html.Div("Error: Layout manager unavailable.") # html.Div used here, import is now correct.
    build_dynamic_mode_layout_func_ref = fallback_build_dynamic_layout
    get_all_registered_chart_ids_ref = lambda: []


# --- Styling Imports ---
PLOTLY_TEMPLATE_CB: Optional[go.layout.Template] = None 
try:
    from .styling import PLOTLY_TEMPLATE_FOR_STYLING_MODULE 
    PLOTLY_TEMPLATE_CB = PLOTLY_TEMPLATE_FOR_STYLING_MODULE
    callback_logger.info("CallbackManager: Successfully imported PLOTLY_TEMPLATE from .styling.")
except ImportError as e_style_cb:
    callback_logger.warning(f"CallbackManager: Failed to import PLOTLY_TEMPLATE from .styling: {e_style_cb}. Using fallback template if any.")
    PLOTLY_TEMPLATE_CB = go.layout.Template() 
    PLOTLY_TEMPLATE_CB.layout = go.Layout(template="plotly_dark") 

# --- Global Map for Chart Generators ---
CHART_GENERATOR_MAP_V2_4: Dict[str, Dict[str, Callable]] = {}

def _populate_chart_generator_map() -> None:
    global CHART_GENERATOR_MAP_V2_4
    CHART_GENERATOR_MAP_V2_4 = {} 
    pop_map_logger = callback_logger.getChild("PopulateChartGenMap")
    pop_map_logger.debug("Attempting to populate CHART_GENERATOR_MAP_V2_4...")
    if _CONFIG_MANAGER_REF_CB is None:
        pop_map_logger.error("ConfigManager reference not available. Cannot populate chart generator map.")
        return
    modes_config = get_config_value_util(keys=["visualization_settings", "dashboard", "modes_detail_config"], default_value_to_return={}, config_manager_instance=_CONFIG_MANAGER_REF_CB)
    if not isinstance(modes_config, dict) or not modes_config:
        pop_map_logger.warning("'modes_detail_config' not found or empty. Chart map will be empty.")
        return
    for mode_key, mode_details in modes_config.items():
        if isinstance(mode_details, dict) and "module_name" in mode_details and "charts" in mode_details:
            module_name_str = mode_details["module_name"]
            chart_ids_for_this_mode = mode_details["charts"]
            if not isinstance(chart_ids_for_this_mode, list): continue
            CHART_GENERATOR_MAP_V2_4[mode_key] = {}
            try:
                mode_module_path = f"dashboard_application.modes.{module_name_str}"
                mode_module_obj = importlib.import_module(mode_module_path)
                pop_map_logger.debug(f"Imported mode module: {mode_module_path}")
                for chart_id_str_from_config in chart_ids_for_this_mode:
                    if not isinstance(chart_id_str_from_config, str): continue
                    func_name_fig = f"generate_{chart_id_str_from_config}_figure"
                    func_name_comp = f"generate_{chart_id_str_from_config}_component"
                    generator_func_found: Optional[Callable] = None
                    if hasattr(mode_module_obj, func_name_fig) and callable(getattr(mode_module_obj, func_name_fig)):
                        generator_func_found = getattr(mode_module_obj, func_name_fig)
                    elif hasattr(mode_module_obj, func_name_comp) and callable(getattr(mode_module_obj, func_name_comp)):
                        generator_func_found = getattr(mode_module_obj, func_name_comp)
                    if generator_func_found:
                        CHART_GENERATOR_MAP_V2_4[mode_key][chart_id_str_from_config] = generator_func_found
                        pop_map_logger.debug(f"  Added generator for mode '{mode_key}', chart '{chart_id_str_from_config}': {generator_func_found.__name__}")
                    else:
                        pop_map_logger.debug(f"  No generator for '{chart_id_str_from_config}' in module '{module_name_str}'. Looked for '{func_name_fig}' or '{func_name_comp}'.")
            except ImportError: pop_map_logger.error(f"Failed to import mode module: {module_name_str}")
            except Exception as e_mod_load: pop_map_logger.error(f"Error processing mode module {module_name_str}: {e_mod_load}", exc_info=True)
    final_map_summary: Dict[str, List[str]] = {mode: list(charts.keys()) for mode, charts in CHART_GENERATOR_MAP_V2_4.items()}
    pop_map_logger.info(f"Final CHART_GENERATOR_MAP populated. Modes: {list(final_map_summary.keys())}")
    for mode_name_log, chart_list_log in final_map_summary.items():
         pop_map_logger.info(f"  Mode '{mode_name_log}': Loaded chart gens for {len(chart_list_log)} charts: {chart_list_log}")

def register_all_callbacks(
    app: dash.Dash, its_orchestrator_instance: Any, config_manager_instance: Any, 
    raw_app_config: Dict[str, Any], server_side_cache: Dict[str, Any], 
    component_history_cache: Dict[str, Deque[Any]]
) -> None:
    global _APP_INSTANCE_REF_CB, _ITS_ORCHESTRATOR_REF_CB, _CONFIG_MANAGER_REF_CB, \
           _RAW_APP_CONFIG_REF_CB, _SERVER_SIDE_CACHE_REF_CB, _COMPONENT_HISTORY_CACHE_REF_CB, \
           ALL_DYNAMIC_CHART_IDS
    _APP_INSTANCE_REF_CB = app; _ITS_ORCHESTRATOR_REF_CB = its_orchestrator_instance
    _CONFIG_MANAGER_REF_CB = config_manager_instance; _RAW_APP_CONFIG_REF_CB = raw_app_config 
    _SERVER_SIDE_CACHE_REF_CB = server_side_cache; _COMPONENT_HISTORY_CACHE_REF_CB = component_history_cache
    callback_logger.info("Registering V2.4 dashboard callbacks in callback_manager.py...")
    if not all([_APP_INSTANCE_REF_CB, _ITS_ORCHESTRATOR_REF_CB, _CONFIG_MANAGER_REF_CB, _RAW_APP_CONFIG_REF_CB is not None, _SERVER_SIDE_CACHE_REF_CB is not None, _COMPONENT_HISTORY_CACHE_REF_CB is not None]):
        callback_logger.critical("CallbackManager: Critical instances not properly set after assignment!")
    _populate_chart_generator_map()
    if get_all_registered_chart_ids_ref and callable(get_all_registered_chart_ids_ref):
        ALL_DYNAMIC_CHART_IDS = get_all_registered_chart_ids_ref()
        callback_logger.info(f"CallbackManager: Retrieved {len(ALL_DYNAMIC_CHART_IDS)} dynamic chart IDs from layout_manager: {ALL_DYNAMIC_CHART_IDS}")
    else:
        callback_logger.error("CallbackManager: get_all_registered_chart_ids_ref from layout_manager is not available.")
        ALL_DYNAMIC_CHART_IDS = []
    prerequisites_met = all([_APP_INSTANCE_REF_CB is not None, _ITS_ORCHESTRATOR_REF_CB is not None, _CONFIG_MANAGER_REF_CB is not None, _utils_imported_ok_cb, _ids_imported_ok_cb_flag, _layout_funcs_imported_ok_cb, build_dynamic_mode_layout_func_ref is not None, CHART_GENERATOR_MAP_V2_4 ])
    if not prerequisites_met: callback_logger.error("CallbackManager: Prerequisites for factory callbacks not met.")
    else: callback_logger.info("CallbackManager: All prerequisites for factory callbacks seem to be met.")

    @app.callback(Output(ID_REFRESH_INTERVAL_STORE, 'data'), Input(ID_REFRESH_INTERVAL_DROPDOWN, 'value'))
    def update_refresh_interval_store(selected_interval_value: Optional[int]) -> Dict[str, Optional[int]]:
        return {'interval_ms': selected_interval_value if selected_interval_value is not None else 0}

    @app.callback(Output(ID_AUTO_REFRESH_INTERVAL_COMPONENT, 'interval'), Output(ID_AUTO_REFRESH_INTERVAL_COMPONENT, 'disabled'), Input(ID_REFRESH_INTERVAL_STORE, 'data'))
    def set_auto_refresh_interval(store_data: Optional[Dict[str, Optional[int]]]) -> Tuple[int, bool]:
        if store_data and isinstance(store_data.get('interval_ms'), int) and store_data['interval_ms'] > 0:
            return store_data['interval_ms'], False
        return 60*60*1000, True

    @app.callback(Output(ID_RANGE_SLIDER_OUTPUT_LABEL, 'children'), Input(ID_RANGE_SLIDER, 'value'))
    def update_range_slider_label(value: Optional[float]) -> str:
        if value is None: return "Range % (+/-): N/A"
        return f"Range % (+/-): {value:.1f}%"

    @app.callback(Output(ID_MAIN_CONTENT_AREA, 'children', allow_duplicate=True), Output(ID_CURRENT_MODE_STORE, 'data'), Input(ID_MODE_SELECTOR_TABS, 'active_tab'), prevent_initial_call=True )
    def update_displayed_mode_content(active_mode_tab_id: Optional[str]) -> Tuple[Any, Dict[str, Optional[str]]]:
        callback_logger.debug(f"CALLBACK: update_displayed_mode_content triggered. Active Tab ID: {active_mode_tab_id}")
        
        if not active_mode_tab_id:
            callback_logger.debug("CALLBACK: update_displayed_mode_content returning no_update for layout and mode store due to no active_mode_tab_id.")
            return no_update, no_update
            
        if not build_dynamic_mode_layout_func_ref:
            error_msg = "Layout manager's build_dynamic_mode_layout function not available."
            callback_logger.error(f"CALLBACK ERROR in update_displayed_mode_content: {error_msg}")
            callback_logger.debug(f"CALLBACK: update_displayed_mode_content returning error layout: {error_msg}")
            return html.Div(error_msg, style={'color': 'red'}), {'active_mode': None}
            
        callback_logger.debug(f"CALLBACK: update_displayed_mode_content attempting to build layout for mode '{active_mode_tab_id}'.")
        new_mode_layout = build_dynamic_mode_layout_func_ref(active_mode_tab_id, app_config_for_layout=_RAW_APP_CONFIG_REF_CB)
        
        # Log type or a small part if it's a complex Dash component structure
        layout_log_info = f"Layout type: {type(new_mode_layout)}"
        if hasattr(new_mode_layout, 'id'): # Check if it has an id attribute
            layout_log_info += f", ID: {getattr(new_mode_layout, 'id', 'N/A')}"
        elif isinstance(new_mode_layout, (html.Div, dbc.Container)) and hasattr(new_mode_layout, 'children') and isinstance(new_mode_layout.children, list) and len(new_mode_layout.children) > 0:
             first_child_type = type(new_mode_layout.children[0])
             layout_log_info += f", First child type: {first_child_type}, Num children: {len(new_mode_layout.children)}"

        callback_logger.debug(f"CALLBACK: update_displayed_mode_content returning new layout for mode '{active_mode_tab_id}'. {layout_log_info}")
        return new_mode_layout, {'active_mode': active_mode_tab_id}

    @app.callback(
        Output(ID_MAIN_DATA_STORE_MEMORY, 'data'), Output(ID_STATUS_DISPLAY_AREA, 'children'), # Corrected ID
        # Output(ID_STATUS_DISPLAY_ALERT, 'is_open'), # Removed this Output
        Output(ID_MAIN_CONTENT_AREA, 'children', allow_duplicate=True),
        Input(ID_FETCH_DATA_BUTTON, 'n_clicks'), Input(ID_AUTO_REFRESH_INTERVAL_COMPONENT, 'n_intervals'),
        Input(ID_HIDDEN_INITIAL_LOAD_TRIGGER, 'children'),
        State(ID_SYMBOL_INPUT, 'value'), State(ID_DTE_INPUT, 'value'),
        State(ID_RANGE_SLIDER, 'value'), State(ID_CURRENT_MODE_STORE, 'data'),
        prevent_initial_call='initial_duplicate' # Changed line
    )
    def fetch_and_process_data_master_callback(
        n_clicks_fetch: Optional[int], n_intervals_refresh: Optional[int], _initial_load_trigger: Any,
        symbol_val: Optional[str], dte_str_val: Optional[str], range_pct_val: Optional[float],
        current_mode_store_data: Optional[Dict[str, Optional[str]]]
    ) -> Tuple[Optional[Dict[str, Any]], Any, Any]: # Corrected return tuple type hint
        callback_logger.debug(f"CALLBACK: MASTER_CB triggered by ID: {ctx.triggered_id}. Symbol: {symbol_val}, DTE: {dte_str_val}, Range: {range_pct_val}, Clicks: {n_clicks_fetch}, Intervals: {n_intervals_refresh}")
        
        triggered_id = ctx.triggered_id if ctx.triggered_id else "initial_load_via_hidden_div"
        
        if not symbol_val:
            callback_logger.debug("MASTER_CB: No symbol provided, returning no_update for data and layout.")
            # Returning 3 values now
            return no_update, format_status_message_enhanced_util("Symbol is required.", is_error=True), no_update
            
        dte_list_parsed = parse_dte_input_string_util(dte_str_val) if dte_str_val else None
        final_range_pct = float(range_pct_val) if range_pct_val is not None else get_config_value_util(["visualization_settings", "dashboard", "defaults", "range_pct"], 5.0)
        
        status_msg: Any = format_status_message_enhanced_util(f"Fetching data for {symbol_val}...", is_error=False)
        # status_open = True # Removed status_open
        main_data_output: Optional[Dict[str, Any]] = None
        layout_to_render: Any = no_update

        callback_logger.debug(f"MASTER_CB: Attempting to fetch and process data for symbol '{symbol_val}'. Trigger: {triggered_id}")
        try:
            if not _ITS_ORCHESTRATOR_REF_CB:
                raise RuntimeError("ITS Orchestrator reference not available for MASTER_CB.")
            
            current_time = datetime.now()
            callback_logger.debug(f"MASTER_CB: Calling fetch_data_for_analysis_cycle for {symbol_val} at {current_time.isoformat()}")
            raw_data_bundle = _ITS_ORCHESTRATOR_REF_CB.fetch_data_for_analysis_cycle(symbol=symbol_val, dte_list_for_api_call=dte_list_parsed, price_range_percentage_for_api=final_range_pct)
            
            raw_bundle_keys = list(raw_data_bundle.keys()) if isinstance(raw_data_bundle, dict) else None
            callback_logger.debug(f"MASTER_CB: raw_data_bundle type: {type(raw_data_bundle)}, Keys: {raw_bundle_keys}")
            if isinstance(raw_data_bundle, dict) and raw_data_bundle.get("error"):
                raise RuntimeError(f"Data Fetch Error from Orchestrator: {raw_data_bundle.get('error')}")

            callback_logger.debug(f"MASTER_CB: Calling run_analysis_cycle_v2_4 for {symbol_val}")
            analysis_bundle_from_its = _ITS_ORCHESTRATOR_REF_CB.run_analysis_cycle_v2_4(symbol=symbol_val, raw_options_df_from_fetcher=raw_data_bundle["raw_options_df"], raw_underlying_data_dict_from_fetcher=raw_data_bundle["raw_underlying_dict"], current_processing_datetime=current_time)
            
            analysis_bundle_keys = list(analysis_bundle_from_its.keys()) if isinstance(analysis_bundle_from_its, dict) else None
            callback_logger.debug(f"MASTER_CB: analysis_bundle_from_its type: {type(analysis_bundle_from_its)}, Keys: {analysis_bundle_keys}")
            if isinstance(analysis_bundle_from_its, dict) and analysis_bundle_from_its.get("cycle_error_summary"):
                raise RuntimeError(f"Analysis Cycle Error from Orchestrator: {analysis_bundle_from_its.get('cycle_error_summary')}")

            callback_logger.debug("MASTER_CB: Calling get_visualization_data_bundle")
            main_data_output = _ITS_ORCHESTRATOR_REF_CB.get_visualization_data_bundle(analysis_bundle_from_its)
            
            viz_bundle_keys = list(main_data_output.keys()) if isinstance(main_data_output, dict) else None
            callback_logger.debug(f"MASTER_CB: main_data_output (visualization bundle) type: {type(main_data_output)}, Keys: {viz_bundle_keys}")
            
            if isinstance(main_data_output, dict): # Ensure it's a dict before adding keys
                 main_data_output["last_updated_iso"] = current_time.isoformat()
            else: # Should not happen if orchestrator is correct, but good to be defensive
                 callback_logger.error("MASTER_CB: main_data_output from get_visualization_data_bundle was not a dict. This is unexpected.")
                 main_data_output = {"error": "Visualization bundle error", "last_updated_iso": current_time.isoformat()}


            status_msg = format_status_message_enhanced_util(f"Data for {symbol_val} processed successfully.", is_error=False, timestamp=current_time)
            
            if triggered_id == "initial_load_via_hidden_div" and build_dynamic_mode_layout_func_ref:
                active_mode = (current_mode_store_data.get('active_mode') if current_mode_store_data else None) or "main"
                callback_logger.debug(f"MASTER_CB (Initial Load): Attempting to build initial layout for mode '{active_mode}'.")
                layout_to_render = build_dynamic_mode_layout_func_ref(active_mode, app_config_for_layout=_RAW_APP_CONFIG_REF_CB)
                layout_render_log_info = f"Initial layout type: {type(layout_to_render)}"
                if hasattr(layout_to_render, 'id'): layout_render_log_info += f", ID: {getattr(layout_to_render, 'id', 'N/A')}"
                callback_logger.debug(f"MASTER_CB (Initial Load): {layout_render_log_info}")

        except Exception as e:
            callback_logger.error(f"MASTER_CB: Error processing data for {symbol_val} (Trigger: {triggered_id}): {e}", exc_info=True)
            status_msg = format_status_message_enhanced_util(f"Error processing data for {symbol_val}: {str(e)[:150]}", is_error=True, timestamp=datetime.now())
            main_data_output = {"error": str(e), "last_updated_iso": datetime.now().isoformat()}
        
        callback_logger.debug(f"MASTER_CB: Returning. main_data_output type: {type(main_data_output)}, status_msg type: {type(status_msg)}, layout_to_render type: {type(layout_to_render)}")
        return main_data_output, status_msg, layout_to_render # Removed status_open

    if prerequisites_met and ALL_DYNAMIC_CHART_IDS:
        for chart_id_for_factory in ALL_DYNAMIC_CHART_IDS:
            if not isinstance(chart_id_for_factory, str):
                callback_logger.warning(f"Skipping dynamic chart callback registration for non-string ID: {chart_id_for_factory}")
                continue
            @app.callback(Output(chart_id_for_factory, 'children'), Input(ID_MAIN_DATA_STORE_MEMORY, 'data'), Input(ID_CURRENT_MODE_STORE, 'data'))
            def generate_dynamic_chart_content_factory(main_store_data: Optional[Dict[str, Any]], mode_store_data: Optional[Dict[str, Optional[str]]], chart_id_closure: str = chart_id_for_factory) -> Any:
                active_mode = (mode_store_data.get('active_mode') if mode_store_data else None) or "main" # Get active_mode early for logging
                callback_logger.debug(f"CALLBACK: DYNAMIC_CHART_CB triggered for chart_id_closure: '{chart_id_closure}', current_mode: '{active_mode}'. Main store data is {'NOT ' if not main_store_data else ''}available.")

                if not main_store_data or main_store_data.get("error"):
                    error_reason = main_store_data.get('error', 'No data in store') if main_store_data else 'Main store data is None'
                    callback_logger.debug(f"DYNAMIC_CHART_CB ('{chart_id_closure}'): Main store has error or no data. Error: {error_reason}. Returning empty figure.")
                    return html.Div(create_empty_figure_util(title=f"{chart_id_closure.replace('_', ' ').title()}", reason=error_reason))
                
                generator_function: Optional[Callable] = None
                if active_mode in CHART_GENERATOR_MAP_V2_4 and chart_id_closure in CHART_GENERATOR_MAP_V2_4[active_mode]:
                    generator_function = CHART_GENERATOR_MAP_V2_4[active_mode][chart_id_closure]
                
                if generator_function and callable(generator_function):
                    callback_logger.debug(f"DYNAMIC_CHART_CB ('{chart_id_closure}'): Found generator {generator_function.__name__}. Attempting to generate chart content.")
                    try:
                        chart_content = generator_function(analysis_bundle=main_store_data, its_orch_ref=_ITS_ORCHESTRATOR_REF_CB, config_manager_ref=_CONFIG_MANAGER_REF_CB, raw_config_ref=_RAW_APP_CONFIG_REF_CB, chart_id=chart_id_closure)
                        callback_logger.debug(f"DYNAMIC_CHART_CB ('{chart_id_closure}'): Generator returned content of type: {type(chart_content)}. Returning this content.")
                        return chart_content
                    except Exception as e_chart_gen:
                        callback_logger.error(f"DYNAMIC_CHART_CB ('{chart_id_closure}'): Error generating chart for mode '{active_mode}': {e_chart_gen}", exc_info=True)
                        callback_logger.debug(f"DYNAMIC_CHART_CB ('{chart_id_closure}'): Returning empty/error figure due to exception.")
                        return html.Div(create_empty_figure_util(title=f"{chart_id_closure.replace('_', ' ').title()}", reason=f"Error: {str(e_chart_gen)[:100]}"))
                else:
                    callback_logger.warning(f"DYNAMIC_CHART_CB ('{chart_id_closure}'): No generator function found for mode '{active_mode}'. Returning empty Div.")
                    return html.Div() 
    else:
        callback_logger.warning("CallbackManager: ALL_DYNAMIC_CHART_IDS is empty or prerequisites not met. No dynamic chart update callbacks registered via factory.")
    callback_logger.info("V2.4 Callback registration process finalized.")
