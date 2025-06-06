# dashboard_application/styling.py
import copy
import logging
from typing import Dict, Any, Optional, List, Union # Added Union, List
import plotly.graph_objects as go 

# --- Module-Specific Logger ---
styling_logger = logging.getLogger(__name__)

_STYLING_CONSTANTS_CONFIG_KEY_PATH: List[str] = ["visualization_settings", "dashboard", "styling_constants"]

# --- Global Variables for Styling ---
_CONFIG_MANAGER_STYLING_REF: Optional[Any] = None
_RAW_APP_CONFIG_STYLING_CACHE: Optional[Dict[str, Any]] = None
_STYLING_CONFIG_INITIALIZED: bool = False

APP_THEME: str = "https://cdn.jsdelivr.net/npm/bootswatch@5.3.5/dist/cyborg/bootstrap.min.css"
PLOTLY_TEMPLATE_FOR_STYLING_MODULE: go.layout.Template = go.layout.Template()
PLOTLY_TEMPLATE_FOR_STYLING_MODULE.layout = go.Layout(template="plotly_dark") # Basic fallback

COLOR_PRIMARY_STYLING: str = "#0d6efd" 
TEXT_PRIMARY_ON_DARK_STYLING: str = "#E9ECEF"
BACKGROUND_COLOR_CARD_STYLING: str = "#212529" 

def _get_styling_config_value(keys: Union[str, List[str]], default: Any = None) -> Any:
    """Internal helper to get config values for styling module."""
    if _CONFIG_MANAGER_STYLING_REF and hasattr(_CONFIG_MANAGER_STYLING_REF, 'get_setting'):
        return _CONFIG_MANAGER_STYLING_REF.get_setting(keys, default_value_to_return=default, quiet=True)
    elif _RAW_APP_CONFIG_STYLING_CACHE:
        current = _RAW_APP_CONFIG_STYLING_CACHE
        path_list = keys if isinstance(keys, list) else keys.split('.')
        try:
            for k in path_list: current = current[k]
            return current
        except (KeyError, TypeError): return default
    return default

def initialize_styling_config(app_config_dict: Optional[Dict[str, Any]] = None, 
                              config_manager_instance: Optional[Any] = None) -> None:
    global _CONFIG_MANAGER_STYLING_REF, _RAW_APP_CONFIG_STYLING_CACHE, _STYLING_CONFIG_INITIALIZED
    global APP_THEME, PLOTLY_TEMPLATE_FOR_STYLING_MODULE
    global COLOR_PRIMARY_STYLING, TEXT_PRIMARY_ON_DARK_STYLING, BACKGROUND_COLOR_CARD_STYLING

    if config_manager_instance and hasattr(config_manager_instance, 'get_setting') and hasattr(config_manager_instance, 'get_config'):
        _CONFIG_MANAGER_STYLING_REF = config_manager_instance
        _RAW_APP_CONFIG_STYLING_CACHE = _CONFIG_MANAGER_STYLING_REF.get_config()
        styling_logger.info("STYLING: Application configuration received and set successfully for styling module.")
    elif app_config_dict is not None:
        _RAW_APP_CONFIG_STYLING_CACHE = app_config_dict
        _CONFIG_MANAGER_STYLING_REF = None
        styling_logger.info("STYLING: Using provided raw app_config_dict for styling module.")
    else:
        styling_logger.warning("STYLING: initialize_styling_config called with None or empty app_config. Using existing/fallback config for re-initialization.")

    configured_theme_url = _get_styling_config_value(keys=["visualization_settings", "dashboard", "dbc_theme_name"], default=APP_THEME)
    if isinstance(configured_theme_url, str) and configured_theme_url.startswith("https://"):
        APP_THEME = configured_theme_url
    elif isinstance(configured_theme_url, str) and configured_theme_url:
        if configured_theme_url.upper() == "CYBORG":
            APP_THEME = "https://cdn.jsdelivr.net/npm/bootswatch@5.3.5/dist/cyborg/bootstrap.min.css"
    
    plotly_defaults_cfg = _get_styling_config_value(keys=["visualization_settings", "dashboard", "plotly_defaults"], default={})
    
    base_template_name = "plotly_dark"
    if isinstance(plotly_defaults_cfg, dict) and isinstance(plotly_defaults_cfg.get("template"), str):
        base_template_name = plotly_defaults_cfg.get("template", "plotly_dark")
    
    current_plotly_template = go.layout.Template()
    try:
        base_template_obj = go.layout.Template(layout=go.Layout(template=base_template_name))
        current_plotly_template.layout = copy.deepcopy(base_template_obj.layout)
        current_plotly_template.data = copy.deepcopy(base_template_obj.data)
    except Exception as e_base_template:
        styling_logger.warning(f"STYLING: Could not apply base Plotly template '{base_template_name}': {e_base_template}. Using empty layout.")
        current_plotly_template.layout = go.Layout()

    if isinstance(plotly_defaults_cfg, dict) and isinstance(plotly_defaults_cfg.get("layout"), dict):
        config_layout_settings = plotly_defaults_cfg["layout"]
        for key, value_from_config in config_layout_settings.items():
            if hasattr(current_plotly_template.layout, key) and isinstance(getattr(current_plotly_template.layout, key), dict) and isinstance(value_from_config, dict):
                new_nested_dict = getattr(current_plotly_template.layout, key).copy() if getattr(current_plotly_template.layout, key) else {}
                new_nested_dict.update(value_from_config)
                setattr(current_plotly_template.layout, key, new_nested_dict)
            else:
                setattr(current_plotly_template.layout, key, value_from_config)
    
    if isinstance(plotly_defaults_cfg, dict) and isinstance(plotly_defaults_cfg.get("data"), dict):
        config_data_settings = plotly_defaults_cfg["data"]
        for trace_type, trace_defaults_list in config_data_settings.items():
            if isinstance(trace_defaults_list, list) and trace_defaults_list and isinstance(trace_defaults_list[0], dict):
                trace_constructor = getattr(go, trace_type.capitalize(), None)
                if trace_constructor:
                    try: setattr(current_plotly_template.data, trace_type, [trace_constructor(**trace_defaults_list[0])])
                    except Exception as e_trace_constr_style: styling_logger.warning(f"STYLING: Error constructing trace type '{trace_type}' with defaults {trace_defaults_list[0]} in styling: {e_trace_constr_style}")

    PLOTLY_TEMPLATE_FOR_STYLING_MODULE = current_plotly_template
    styling_logger.info("STYLING: Plotly template constructed/updated from 'plotly_defaults' in configuration, merged with fallback.")

    styling_constants_cfg = _get_styling_config_value(_STYLING_CONSTANTS_CONFIG_KEY_PATH, {})
    if isinstance(styling_constants_cfg, dict):
        COLOR_PRIMARY_STYLING = str(styling_constants_cfg.get("COLOR_PRIMARY", COLOR_PRIMARY_STYLING))
        TEXT_PRIMARY_ON_DARK_STYLING = str(styling_constants_cfg.get("TEXT_PRIMARY_ON_DARK", TEXT_PRIMARY_ON_DARK_STYLING))
        BACKGROUND_COLOR_CARD_STYLING = str(styling_constants_cfg.get("BACKGROUND_COLOR_CARD", BACKGROUND_COLOR_CARD_STYLING))
    
    _STYLING_CONFIG_INITIALIZED = True
    styling_logger.info(f"Styling constants and Plotly template re-initialized. App Theme: {APP_THEME}")

def cleanup_styling_resources() -> None:
    global _CONFIG_MANAGER_STYLING_REF, _RAW_APP_CONFIG_STYLING_CACHE, _STYLING_CONFIG_INITIALIZED
    _CONFIG_MANAGER_STYLING_REF = None; _RAW_APP_CONFIG_STYLING_CACHE = None
    _STYLING_CONFIG_INITIALIZED = False
    styling_logger.info("Styling module resources (config reference and loaded flag) have been cleared.")

if not _STYLING_CONFIG_INITIALIZED:
    styling_logger.debug("Styling module self-initialized with default/fallback values on first import.")
    initialize_styling_config(None, None)

styling_logger.info("Styling module V2.4 (Canonical with Robust Init) fully initialized and ready.")
