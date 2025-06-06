# dashboard_application/app_main.py
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc 
import os
import logging
from typing import Dict, Any, Optional, Deque, Callable 
from collections import deque

# --- EOTS System Runner and ConfigManager (Global Singleton) ---
try:
    from run_system_dashboard import config_manager as global_config_manager_from_runner
except ImportError:
    logging.getLogger(__name__).critical(
        "APP_MAIN: Could not import global_config_manager_from_runner. "
        "ConfigManager might not be properly shared. Using a new instance, which is NOT ideal."
    )
    try:
        from run_system_dashboard import ConfigManager 
        global_config_manager_from_runner = ConfigManager()
        if not global_config_manager_from_runner._config: 
            if global_config_manager_from_runner.load_config("config_v2_4.json", "config.schema.json"):
                logging.getLogger(__name__).info("APP_MAIN: Fallback ConfigManager loaded default config.")
            else:
                logging.getLogger(__name__).error("APP_MAIN: Fallback ConfigManager FAILED to load default config.")
    except ImportError:
        logging.getLogger(__name__).critical("APP_MAIN: CRITICAL - Cannot import ConfigManager class from run_system_dashboard.")
        global_config_manager_from_runner = None


# --- Module-Specific Logger ---
logger_app_main = logging.getLogger(__name__)

# --- Global Shared References (populated by initialize_dashboard_dependencies) ---
_APP_INSTANCE_REF_APPMAIN: Optional[dash.Dash] = None
_ITS_ORCHESTRATOR_SHARED: Optional[Any] = None
_CONFIG_MANAGER_SHARED: Optional[Any] = global_config_manager_from_runner
_RAW_APP_CONFIG_SHARED: Optional[Dict[str, Any]] = None
_SERVER_SIDE_CACHE_SHARED: Dict[str, Any] = {} 
_COMPONENT_HISTORY_CACHE_SHARED: Dict[str, Deque[Any]] = {}

# --- Fallback Layout Function (if layout_manager fails to import) ---
def _fallback_get_main_layout_v2_4(app_config: Optional[Dict[str,Any]] = None) -> html.Div:
    error_msg = "APP_MAIN FALLBACK: Main layout_manager module failed to import or its layout function is unavailable. Displaying minimal fallback content."
    logger_app_main.error(error_msg) 
    title_text = "EOTS Dashboard - Error"
    if app_config and isinstance(app_config.get("visualization_settings"), dict):
        title_text = app_config["visualization_settings"].get("dashboard", {}).get("title", title_text)
    return html.Div([ 
        html.H1(title_text, style={'textAlign': 'center', 'color': 'red'}),
        html.P("The dashboard experienced a critical error during layout generation.", style={'textAlign': 'center'}),
        html.P("Please check the application logs for detailed error messages from 'layout_manager.py' or 'app_main.py'.", style={'textAlign': 'center'}),
        html.Hr(),
        html.Div(id="fallback-main-content-area-id"), 
        html.Div(id="fallback-status-display-area-id")
    ], style={'padding': '20px'})

# --- Dynamic Imports for Dashboard Components ---
utils_appmain_module: Optional[Any] = None 
try:
    from . import utils_dashboard as utils_appmain_module 
    logger_app_main.info("APP_MAIN: Successfully imported .utils_dashboard.")
except ImportError as e_util_am:
    logger_app_main.critical(f"APP_MAIN CRITICAL: Failed to import .utils_dashboard: {e_util_am}. Core utilities unavailable.", exc_info=True)

styling_module_appmain: Optional[Any] = None
APP_THEME_APPMAIN: Any = dbc.themes.CYBORG 
initialize_styling_config_func_ref: Optional[Callable] = None
cleanup_styling_resources_func_ref: Optional[Callable] = None
try:
    from . import styling as styling_module_appmain
    APP_THEME_APPMAIN = styling_module_appmain.APP_THEME
    initialize_styling_config_func_ref = styling_module_appmain.initialize_styling_config
    cleanup_styling_resources_func_ref = styling_module_appmain.cleanup_styling_resources
    logger_app_main.info("APP_MAIN: Successfully imported APP_THEME and initializers from .styling.")
except ImportError as e_style_am:
    logger_app_main.critical(f"APP_MAIN CRITICAL: Failed to import .styling module: {e_style_am}. Styling will be broken.", exc_info=True)

imported_layout_manager_module: Optional[Any] = None
get_dashboard_layout_func_ref: Callable = _fallback_get_main_layout_v2_4
try:
    from . import layout_manager as imported_layout_manager_module
    if hasattr(imported_layout_manager_module, 'get_main_dashboard_layout_v2_4'): 
        get_dashboard_layout_func_ref = imported_layout_manager_module.get_main_dashboard_layout_v2_4
        logger_app_main.info("APP_MAIN: Successfully imported get_main_dashboard_layout_v2_4 from .layout_manager.")
    else:
        logger_app_main.error("APP_MAIN ERROR: Function 'get_main_dashboard_layout_v2_4' not found in .layout_manager. Using fallback layout.")
except ImportError as e_lm_appmain: 
    logger_app_main.critical(f"APP_MAIN CRITICAL: Failed to import .layout_manager module: {e_lm_appmain}. Using fallback layout.", exc_info=True)

imported_callback_manager_module: Optional[Any] = None
register_all_callbacks_func_ref: Optional[Callable] = None
try:
    from . import callback_manager as imported_callback_manager_module
    register_all_callbacks_func_ref = imported_callback_manager_module.register_all_callbacks
    logger_app_main.info("APP_MAIN: Successfully imported register_all_callbacks from .callback_manager.")
except ImportError as e_cb_man_am: 
    logger_app_main.critical(f"APP_MAIN CRITICAL: Failed to import .callback_manager: {e_cb_man_am}. Callbacks will not be registered.", exc_info=True)

logger_app_main.info("Initializing Dash application instance in app_main.py...")
assets_folder_config_key = ["runner_settings", "paths", "assets_folder_dashboard"]
assets_folder_default_rel_path = "dashboard_application/assets"
assets_path: Optional[str] = None
if _CONFIG_MANAGER_SHARED and hasattr(_CONFIG_MANAGER_SHARED, 'get_resolved_path'):
    assets_path = _CONFIG_MANAGER_SHARED.get_resolved_path(assets_folder_config_key, default_relative_path=assets_folder_default_rel_path)
if assets_path is None:
    current_script_dir = os.path.dirname(os.path.abspath(__file__)) 
    assets_path = os.path.join(current_script_dir, 'assets') 
    logger_app_main.warning(f"APP_MAIN: Assets path not resolved via ConfigManager. Using default relative to app_main.py: {assets_path}")
else:
    logger_app_main.info(f"Determined assets folder path for Dash app: '{assets_path}'")

app = dash.Dash(
    __name__,
    external_stylesheets=[APP_THEME_APPMAIN, dbc.icons.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
    assets_folder=str(assets_path), 
    title="EOTS V2.4 Dashboard (Loading...)" 
)
server = app.server 
_APP_INSTANCE_REF_APPMAIN = app 
logger_app_main.info(f"Dash application instance created. Initial Title: '{app.title}'. Assets Folder: '{assets_path}'")

def initialize_dashboard_dependencies(
    its_orchestrator_instance: Any,
    config_manager_instance: Any 
) -> None:
    global _ITS_ORCHESTRATOR_SHARED, _CONFIG_MANAGER_SHARED, _RAW_APP_CONFIG_SHARED
    global _SERVER_SIDE_CACHE_SHARED, _COMPONENT_HISTORY_CACHE_SHARED, _APP_INSTANCE_REF_APPMAIN
    
    logger_app_main.info("app_main.initialize_dashboard_dependencies called from runner...")
    _ITS_ORCHESTRATOR_SHARED = its_orchestrator_instance
    _CONFIG_MANAGER_SHARED = config_manager_instance
    logger_app_main.info("Step 1: Setting global shared references (ITS Orchestrator, ConfigManager)...")
    if _CONFIG_MANAGER_SHARED and hasattr(_CONFIG_MANAGER_SHARED, 'get_config'):
        _RAW_APP_CONFIG_SHARED = _CONFIG_MANAGER_SHARED.get_config()
        if not isinstance(_RAW_APP_CONFIG_SHARED, dict):
            logger_app_main.error("APP_MAIN: _CONFIG_MANAGER_SHARED.get_config() did not return a dict. Raw app config will be empty.")
            _RAW_APP_CONFIG_SHARED = {}
        else:
            logger_app_main.info("Raw application configuration loaded from ConfigManager.")
    else:
        logger_app_main.error("APP_MAIN: _CONFIG_MANAGER_SHARED is invalid or has no get_config method. Raw app config will be empty.")
        _RAW_APP_CONFIG_SHARED = {}
    logger_app_main.info("Step 1 complete: Global shared references set.")

    logger_app_main.info("Step 2: Initializing styling configuration...")
    if initialize_styling_config_func_ref and callable(initialize_styling_config_func_ref):
        try:
            initialize_styling_config_func_ref(app_config_dict=_RAW_APP_CONFIG_SHARED, config_manager_instance=_CONFIG_MANAGER_SHARED)
            logger_app_main.info("Step 2 complete: Styling module (styling.py) initialized/updated successfully.")
        except Exception as e_style_init_call:
            logger_app_main.error(f"APP_MAIN: Error calling styling.initialize_styling_config: {e_style_init_call}", exc_info=True)
            logger_app_main.warning("Step 2 FAILED: Styling module initialization error.")
    else:
        logger_app_main.warning("APP_MAIN: Styling module initializer not available. Step 2 SKIPPED.")

    logger_app_main.info("Step 3: Setting application configuration for dashboard utilities...")
    if utils_appmain_module and hasattr(utils_appmain_module, 'set_app_config_for_utils'):
        try:
            utils_appmain_module.set_app_config_for_utils(_CONFIG_MANAGER_SHARED)
            logger_app_main.info("Step 3 complete: utils_dashboard.set_app_config_for_utils called successfully.")
        except Exception as e_utils_set_cfg:
            logger_app_main.error(f"APP_MAIN: Error calling utils_dashboard.set_app_config_for_utils: {e_utils_set_cfg}", exc_info=True)
            logger_app_main.warning("Step 3 FAILED: utils_dashboard configuration error.")
    else:
        logger_app_main.warning("APP_MAIN: utils_dashboard or its set_app_config_for_utils function not available. Step 3 SKIPPED.")
        
    logger_app_main.info("Step 4: Populating registered chart IDs from layout_manager...")
    if imported_layout_manager_module and hasattr(imported_layout_manager_module, 'populate_all_registered_chart_ids'):
        try:
            chart_ids_found = imported_layout_manager_module.populate_all_registered_chart_ids(_CONFIG_MANAGER_SHARED)
            num_chart_ids = len(chart_ids_found) if chart_ids_found is not None else 0
            logger_app_main.info(f"Step 4 complete: layout_manager.populate_all_registered_chart_ids called. Found {num_chart_ids} chart IDs.")
        except Exception as e_pop_ids:
            logger_app_main.error(f"APP_MAIN: Error calling layout_manager.populate_all_registered_chart_ids: {e_pop_ids}", exc_info=True)
            logger_app_main.warning("Step 4 FAILED: Chart ID population error.")
    else:
        logger_app_main.warning("APP_MAIN: Layout Manager or its chart ID populator not loaded. Step 4 SKIPPED.")

    _RAW_APP_CONFIG_FOR_LAYOUT_STYLING = _RAW_APP_CONFIG_SHARED if _RAW_APP_CONFIG_SHARED is not None else {}
    logger_app_main.info("Step 5: Setting main application layout and title...")
    if app and get_dashboard_layout_func_ref:
        try:
            app.layout = get_dashboard_layout_func_ref(app_config=_RAW_APP_CONFIG_FOR_LAYOUT_STYLING)
            logger_app_main.info("Main application layout structure set using get_dashboard_layout_func_ref.")
            
            title_to_set = "EOTS V2.4 Dashboard"
            if utils_appmain_module and hasattr(utils_appmain_module, 'get_config_value'):
                title_to_set = utils_appmain_module.get_config_value(
                    keys=["visualization_settings", "dashboard", "title"],
                    default_value_to_return="EOTS V2.4 Dashboard (UtilFail)", # Default if util fails
                    config_manager_instance=_CONFIG_MANAGER_SHARED
                )
            app.title = title_to_set
            logger_app_main.info(f"Dashboard application title updated to: '{app.title}'.")
            logger_app_main.info("Step 5 complete: Main application layout and title set successfully.")
        except Exception as e_set_layout:
            logger_app_main.critical(f"APP_MAIN CRITICAL: Error setting main application layout: {e_set_layout}", exc_info=True)
            try:
                app.layout = _fallback_get_main_layout_v2_4(_RAW_APP_CONFIG_FOR_LAYOUT_STYLING)
                logger_app_main.warning("APP_MAIN: Successfully set FALLBACK layout after primary layout error.")
                logger_app_main.warning("Step 5 PARTIALLY FAILED: Using fallback layout.")
            except Exception as e_set_fallback_layout:
                logger_app_main.critical(f"APP_MAIN CRITICAL: Error setting even the FALLBACK layout: {e_set_fallback_layout}", exc_info=True)
                logger_app_main.error("Step 5 FAILED: Could not set any layout.")
    else:
        logger_app_main.error("APP_MAIN: Dash app instance or layout function not available. Cannot set layout. Step 5 FAILED.")

    logger_app_main.info("Step 6: Registering all application callbacks...")
    if app and register_all_callbacks_func_ref and callable(register_all_callbacks_func_ref):
        try:
            register_all_callbacks_func_ref(
                app, _ITS_ORCHESTRATOR_SHARED, _CONFIG_MANAGER_SHARED,
                _RAW_APP_CONFIG_SHARED if _RAW_APP_CONFIG_SHARED is not None else {},
                _SERVER_SIDE_CACHE_SHARED, _COMPONENT_HISTORY_CACHE_SHARED
            )
            logger_app_main.info("Step 6 complete: Application callbacks registration initiated successfully.")
        except Exception as e_reg_cb:
            logger_app_main.critical(f"APP_MAIN CRITICAL ERROR registering application callbacks: {e_reg_cb}", exc_info=True)
            logger_app_main.error("Step 6 FAILED: Callback registration error.")
    else:
        logger_app_main.error("APP_MAIN: Cannot register callbacks. App instance or callback registration function is missing. Step 6 FAILED.")
    
    logger_app_main.info("Function initialize_dashboard_dependencies finished processing all steps.")

def cleanup_app_resources():
    global _APP_INSTANCE_REF_APPMAIN, _ITS_ORCHESTRATOR_SHARED, _CONFIG_MANAGER_SHARED, \
           _RAW_APP_CONFIG_SHARED, _SERVER_SIDE_CACHE_SHARED, _COMPONENT_HISTORY_CACHE_SHARED
    logger_app_main.info("Executing dashboard_application.app_main.cleanup_app_resources for dashboard application...")
    if cleanup_styling_resources_func_ref and callable(cleanup_styling_resources_func_ref):
        try:
            cleanup_styling_resources_func_ref()
            logger_app_main.info("Styling module cleanup_styling_resources executed.")
        except Exception as e_style_cleanup:
            logger_app_main.warning(f"Error during styling module cleanup: {e_style_cleanup}")
    if utils_appmain_module and hasattr(utils_appmain_module, 'cleanup_utils_resources') and callable(getattr(utils_appmain_module, 'cleanup_utils_resources')): 
        try:
            getattr(utils_appmain_module, 'cleanup_utils_resources')() 
            logger_app_main.info("utils_dashboard cleanup_utils_resources executed.")
        except Exception as e_utils_cleanup:
            logger_app_main.warning(f"Error during utils_dashboard cleanup: {e_utils_cleanup}")
    _APP_INSTANCE_REF_APPMAIN = None; _ITS_ORCHESTRATOR_SHARED = None; _CONFIG_MANAGER_SHARED = None
    _RAW_APP_CONFIG_SHARED = None
    if isinstance(_SERVER_SIDE_CACHE_SHARED, dict): _SERVER_SIDE_CACHE_SHARED.clear()
    if isinstance(_COMPONENT_HISTORY_CACHE_SHARED, dict): _COMPONENT_HISTORY_CACHE_SHARED.clear()
    logger_app_main.info("Global references (ITS, ConfigManager, RawConfig, Caches) in app_main.py have been cleared.")
    logger_app_main.info("Dashboard app_main.py resources cleanup process completed.")

if __name__ == '__main__': 
    logger_app_main.warning("app_main.py executed directly. This is for testing purposes.")
    logger_app_main.warning("Full system functionality requires running via run_system_dashboard.py.")
    class MockITS: pass
    class MockCM: 
        _config = {}
        def __init__(self): self._project_root = os.path.dirname(os.path.abspath(__file__)) 
        def get_config(self): return self._config if self._config else {"version": "MockConfigForAppMainTest"}
        def get_setting(self, keys, default_value_to_return=None, quiet=False): 
            val = self.get_config()
            path_list = keys if isinstance(keys, list) else keys.split('.')
            try:
                for k in path_list: val = val[k]
                return val
            except (KeyError, TypeError): return default_value_to_return
        def get_resolved_path(self, keys, default_relative_path=None, quiet=False):
            if keys == ["runner_settings", "paths", "assets_folder_dashboard"]:
                return os.path.join(self._project_root, 'assets') 
            path_from_setting = self.get_setting(keys, default_value_to_return=default_relative_path, quiet=quiet)
            if path_from_setting:
                return os.path.join(self._project_root, path_from_setting) if not os.path.isabs(path_from_setting) else path_from_setting
            return None
        def load_config(self, c_path, s_path=None): 
            self._config = {"version": "MockLoadedViaAppMainTest", 
                            "visualization_settings": {"dashboard": {"title": "AppMain Test Dashboard"}}}
            return True

    mock_cm_instance = MockCM()
    if not _CONFIG_MANAGER_SHARED : 
        _CONFIG_MANAGER_SHARED = mock_cm_instance
        if not _CONFIG_MANAGER_SHARED._config: 
            _CONFIG_MANAGER_SHARED.load_config("dummy_cfg.json") 
        _RAW_APP_CONFIG_SHARED = _CONFIG_MANAGER_SHARED.get_config()

    initialize_dashboard_dependencies(its_orchestrator_instance=MockITS(), config_manager_instance=_CONFIG_MANAGER_SHARED)
    
    if _APP_INSTANCE_REF_APPMAIN:
        _APP_INSTANCE_REF_APPMAIN.run(debug=True, host='0.0.0.0', port=8051) 
    else:
        logger_app_main.error("APP_MAIN (standalone test): Dash app instance not created. Cannot run server.")
