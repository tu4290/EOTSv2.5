#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elite Options System - V2.4 Co-Pilot Dashboard Utilities
File: elite_options_system_v2_4/dashboard_application/utils_dashboard.py
"""

import logging
import time as pytime 
import json
import copy
import os
import re
import sys
from datetime import datetime, date, time as dt_time, timedelta 
from typing import Dict, Any, Optional, Tuple, List, Union, Deque, Callable

import pandas as pd # type: ignore
import numpy as np # type: ignore
import plotly.graph_objects as go # type: ignore
from dateutil import parser as date_parser # type: ignore
from dash import html # type: ignore 
import dash_bootstrap_components as dbc # type: ignore

utils_logger = logging.getLogger(__name__)

_CONFIG_MANAGER_UTILS_REF: Optional[Any] = None
_RAW_CONFIG_CACHE_FOR_UTILS: Optional[Dict[str, Any]] = None
_UTILS_CONFIG_INITIALIZED_FLAG: bool = False

_PLOTLY_DEFAULTS_CONFIG_KEY_PATH: List[str] = ["visualization_settings", "dashboard", "plotly_defaults"]
_STYLING_CONSTANTS_CONFIG_KEY_PATH: List[str] = ["visualization_settings", "dashboard", "styling_constants"]
_CHART_SPECIFIC_HEIGHTS_CONFIG_KEY_PATH: List[str] = ["visualization_settings", "dashboard", "chart_specific_heights"]
_DEFAULT_CHART_HEIGHT_CONFIG_KEY_PATH: List[str] = ["visualization_settings", "dashboard", "default_graph_height"]
_CACHE_TIMEOUT_CONFIG_KEY_PATH: List[str] = ["system_settings", "dashboard_cache_timeout_seconds"]
_CACHE_MAX_ITEMS_CONFIG_KEY_PATH: List[str] = ["system_settings", "dashboard_max_cache_items"]
_STATUS_MESSAGE_ERROR_DURATION_KEY_PATH: List[str] = ["visualization_settings", "dashboard", "status_message_error_duration_ms"]
_STATUS_MESSAGE_DEFAULT_DURATION_KEY_PATH: List[str] = ["visualization_settings", "dashboard", "status_message_default_duration_ms"]

_FALLBACK_PLOTLY_TEMPLATE_LAYOUT_CONFIG_UTILS_CANONICAL: Dict[str, Any] = {
    "template": "plotly_dark",
    "font": dict(family="Roboto, 'Helvetica Neue', Helvetica, Arial, sans-serif", size=11, color="#bdc3c7"),
    "title": dict(font_size=15, font_color="#ecf0f1", x=0.03, xanchor='left', pad=dict(t=25, b=10)),
    "paper_bgcolor": "rgba(30, 33, 38, 1)",
    "plot_bgcolor": "rgba(39, 43, 50, 1)",
    "xaxis": dict(gridcolor="rgba(70, 80, 100, 0.4)", linecolor="rgba(100, 110, 130, 0.8)", zerolinecolor="rgba(100, 110, 130, 0.9)", zerolinewidth=1, showgrid=True, gridwidth=0.5, tickfont=dict(color="#bdc3c7", size=10), title_font=dict(color="#bdc3c7", size=11), zeroline=False, mirror=True, ticks='outside', showline=True),
    "yaxis": dict(gridcolor="rgba(70, 80, 100, 0.4)", linecolor="rgba(100, 110, 130, 0.8)", zerolinecolor="rgba(100, 110, 130, 0.9)", zerolinewidth=1, showgrid=True, gridwidth=0.5, tickfont=dict(color="#bdc3c7", size=10), title_font=dict(color="#bdc3c7", size=11), zeroline=True, mirror=True, ticks='outside', showline=True),
    "legend": dict(bgcolor="rgba(42, 48, 62, 0.85)", bordercolor="rgba(70, 80, 100, 0.7)", borderwidth=1, font=dict(color="#ecf0f1", size=10), orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1.0),
    "margin": dict(l=60, r=30, t=70, b=50),
    "modebar": dict(bgcolor="rgba(42, 48, 62, 0.9)", color="#bdc3c7", activecolor="#17a2b8")
}

PLOTLY_TEMPLATE_FOR_UTILS_MODULE: go.layout.Template = go.layout.Template()
PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout = go.Layout(**_FALLBACK_PLOTLY_TEMPLATE_LAYOUT_CONFIG_UTILS_CANONICAL)

def set_app_config_for_utils(config_manager_instance: Optional[Any]) -> None:
    global _CONFIG_MANAGER_UTILS_REF, _RAW_CONFIG_CACHE_FOR_UTILS, _UTILS_CONFIG_INITIALIZED_FLAG
    global PLOTLY_TEMPLATE_FOR_UTILS_MODULE, _FALLBACK_PLOTLY_TEMPLATE_LAYOUT_CONFIG_UTILS_CANONICAL
    utils_logger.debug(f"UTILS_DASHBOARD: set_app_config_for_utils called. Received cm_instance type: {type(config_manager_instance)}")
    if config_manager_instance and hasattr(config_manager_instance, 'get_config') and callable(getattr(config_manager_instance, 'get_config')) and hasattr(config_manager_instance, 'get_setting') and callable(getattr(config_manager_instance, 'get_setting')):
        _CONFIG_MANAGER_UTILS_REF = config_manager_instance
        try:
            _RAW_CONFIG_CACHE_FOR_UTILS = _CONFIG_MANAGER_UTILS_REF.get_config()
            if not isinstance(_RAW_CONFIG_CACHE_FOR_UTILS, dict):
                utils_logger.error(f"UTILS_DASHBOARD: ConfigManager.get_config() did not return a dict. Type: {type(_RAW_CONFIG_CACHE_FOR_UTILS)}. Using empty raw config cache.")
                _RAW_CONFIG_CACHE_FOR_UTILS = {}
            utils_logger.info("UTILS_DASHBOARD: ConfigManager reference and raw config cache successfully set.")
        except Exception as e_get_raw_cfg:
            utils_logger.error(f"UTILS_DASHBOARD: Error getting raw config from ConfigManager: {e_get_raw_cfg}. Using empty raw config cache.", exc_info=True)
            _RAW_CONFIG_CACHE_FOR_UTILS = {}
    else:
        utils_logger.warning("UTILS_DASHBOARD: Invalid or None ConfigManager instance passed. Config access will use fallbacks. Raw config cache set to empty.")
        _CONFIG_MANAGER_UTILS_REF = None
        _RAW_CONFIG_CACHE_FOR_UTILS = {}
    utils_logger.debug("UTILS_DASHBOARD: Initializing Plotly template from configuration.")
    plotly_defaults_cfg = get_config_value(keys=_PLOTLY_DEFAULTS_CONFIG_KEY_PATH, default_value_to_return={})
    new_template_for_update = go.layout.Template()
    merged_layout_dict = copy.deepcopy(_FALLBACK_PLOTLY_TEMPLATE_LAYOUT_CONFIG_UTILS_CANONICAL)
    if isinstance(plotly_defaults_cfg, dict) and plotly_defaults_cfg:
        config_layout_settings = plotly_defaults_cfg.get('layout', {})
        if isinstance(config_layout_settings, dict):
            for key, value_from_config in config_layout_settings.items():
                if isinstance(merged_layout_dict.get(key), dict) and isinstance(value_from_config, dict):
                    merged_layout_dict[key] = {**merged_layout_dict[key], **value_from_config}
                else:
                    merged_layout_dict[key] = value_from_config
        new_template_for_update.layout = go.Layout(**merged_layout_dict)
        config_data_settings = plotly_defaults_cfg.get('data', {})
        if isinstance(config_data_settings, dict):
            for trace_type, trace_defaults_list in config_data_settings.items():
                if isinstance(trace_defaults_list, list) and trace_defaults_list and isinstance(trace_defaults_list[0], dict):
                    trace_constructor = getattr(go, trace_type.capitalize(), None)
                    if trace_constructor:
                        try: 
                            setattr(new_template_for_update.data, trace_type, [trace_constructor(**trace_defaults_list[0])])
                        except Exception as e_trace_constr:
                            utils_logger.warning(f"UTILS_DASHBOARD: Error constructing trace type '{trace_type}' with defaults {trace_defaults_list[0]}: {e_trace_constr}")
                    else:
                        utils_logger.warning(f"UTILS_DASHBOARD: Unknown trace type '{trace_type}' in plotly_defaults data config.")
        utils_logger.info("UTILS_DASHBOARD: Plotly template initialized/updated from 'plotly_defaults' in configuration, merged with fallback.")
    else:
        utils_logger.info("UTILS_DASHBOARD: 'plotly_defaults' not found/empty or not a dict in configuration. Using internal fallback Plotly template dictionary to construct layout.")
        new_template_for_update.layout = go.Layout(**merged_layout_dict) 
        if not isinstance(plotly_defaults_cfg, dict):
             utils_logger.warning(f"UTILS_DASHBOARD: 'plotly_defaults' in config was of type {type(plotly_defaults_cfg)}, expected dict.")
    PLOTLY_TEMPLATE_FOR_UTILS_MODULE = new_template_for_update
    _UTILS_CONFIG_INITIALIZED_FLAG = True
    utils_logger.debug(f"UTILS_DASHBOARD: Configuration initialization process complete. Flag: {_UTILS_CONFIG_INITIALIZED_FLAG}")

def get_config_value(keys: Union[str, List[str]], default_value_to_return: Any = None, config_manager_instance: Optional[Any] = None, config_dict_override: Optional[Dict[str, Any]] = None) -> Any:
    key_path_str_for_logging = '.'.join(keys) if isinstance(keys, list) else str(keys)

    if config_dict_override and isinstance(config_dict_override, dict):
        current_level = config_dict_override
        path_list = keys if isinstance(keys, list) else keys.split('.')
        try:
            for key_segment in path_list:
                if isinstance(current_level, dict):
                    current_level = current_level[key_segment]
                else:
                    # Path segment not found or current_level is not a dict
                    utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' segment '{key_segment}' not found or not dict in config_dict_override. Falling through.")
                    break # Break to allow fall-through
            else: # Successfully traversed the path in override
                # Check if the direct value itself looks like a schema node with "properties" or "default"
                if isinstance(current_level, dict) and \
                   ("properties" in current_level or \
                    "default" in current_level or \
                    ("type" in current_level and "enum" in current_level)):
                    # It's a schema node, try to return its "default" value
                    utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' found in config_dict_override, appears to be schema node. Returning its 'default'.")
                    return current_level.get("default", default_value_to_return)
                utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' found and returned from config_dict_override.")
                return current_level
        except (KeyError, TypeError):
            # Key not found in override dict
            utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' not found in config_dict_override (KeyError/TypeError). Falling through.")
            pass # Let it fall through to other methods

    cm_to_use = config_manager_instance if config_manager_instance else _CONFIG_MANAGER_UTILS_REF
    if cm_to_use and hasattr(cm_to_use, 'get_setting') and callable(getattr(cm_to_use, 'get_setting')):
        try:
            # Assuming cm_to_use.get_setting already handles schema-like "default" extraction if necessary
            # and is quiet by default or has a quiet param.
            val_from_cm = cm_to_use.get_setting(keys, default_value_to_return=None, quiet=True) # Use None to differentiate not found from actual None
            if val_from_cm is not None: # If CM found something (even if it's False, 0, or empty string)
                utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' found and returned by ConfigManager instance.")
                return val_from_cm
            # If val_from_cm is None, it means CM didn't find it (assuming get_setting returns the default on not found)
            # So we fall through to _RAW_CONFIG_CACHE_FOR_UTILS or the final default
        except Exception as e_cm_get_setting:
            utils_logger.debug(f"UTILS_DASHBOARD: Error calling ConfigManager.get_setting for '{key_path_str_for_logging}': {e_cm_get_setting}. Falling back to raw cache if available.")

    if _RAW_CONFIG_CACHE_FOR_UTILS and isinstance(_RAW_CONFIG_CACHE_FOR_UTILS, dict):
        current_level = _RAW_CONFIG_CACHE_FOR_UTILS
        path_list = keys if isinstance(keys, list) else keys.split('.') # Re-split if not already list
        try:
            for key_segment in path_list:
                if isinstance(current_level, dict): current_level = current_level[key_segment]
                else:
                    utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' segment '{key_segment}' not found or not dict in _RAW_CONFIG_CACHE_FOR_UTILS. Returning default.")
                    return default_value_to_return
            # Successfully traversed path in raw cache
            # Check for schema-like "default" if the node itself is a schema definition
            if isinstance(current_level, dict) and \
               ("properties" in current_level or \
                "default" in current_level or \
                ("type" in current_level and "enum" in current_level)):
                utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' found in _RAW_CONFIG_CACHE_FOR_UTILS, appears to be schema node. Returning its 'default'.")
                return current_level.get("default", default_value_to_return)
            utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' found and returned from _RAW_CONFIG_CACHE_FOR_UTILS.")
            return current_level
        except (KeyError, TypeError):
            utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' not found in _RAW_CONFIG_CACHE_FOR_UTILS (KeyError/TypeError). Returning default.")
            return default_value_to_return
            
    utils_logger.debug(f"UTILS_DASHBOARD: Key '{key_path_str_for_logging}' not found in any source. Returning default value: {default_value_to_return}")
    return default_value_to_return

def create_empty_figure(title: str, height: Optional[int] = None, reason: str = "No data available.") -> go.Figure:
    fig_height_to_use: int
    if height is not None: fig_height_to_use = height
    else:
        specific_empty_height = get_config_value(keys=_CHART_SPECIFIC_HEIGHTS_CONFIG_KEY_PATH + ["default_empty_chart"], default_value_to_return=None)
        if isinstance(specific_empty_height, (int, float)) and specific_empty_height > 0: fig_height_to_use = int(specific_empty_height)
        else:
            general_default_height = get_config_value(keys=_DEFAULT_CHART_HEIGHT_CONFIG_KEY_PATH, default_value_to_return=450)
            fig_height_to_use = int(general_default_height) if isinstance(general_default_height, (int,float)) and general_default_height > 50 else 450
    fig = go.Figure(); fig.update_layout(template=PLOTLY_TEMPLATE_FOR_UTILS_MODULE)
    font_color_from_template = "#888"
    if PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout and PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.font:
        font_color_from_template = PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.font.color or font_color_from_template
    fig.update_layout(title_text=f"<b>{title}</b>", height=fig_height_to_use, xaxis={'visible': False, 'showgrid': False, 'zeroline': False}, yaxis={'visible': False, 'showgrid': False, 'zeroline': False}, annotations=[{'text': reason, 'xref': 'paper', 'yref': 'paper', 'x': 0.5, 'y': 0.5, 'showarrow': False, 'font': {'size': 16, 'color': font_color_from_template}}])
    return fig

def add_timestamp_annotation(fig: go.Figure, timestamp_data: Optional[Union[str, datetime, float, int]]) -> go.Figure:
    if timestamp_data is None: return fig
    ts_str: str = ""
    try:
        if isinstance(timestamp_data, (float, int)): 
            ts_val = timestamp_data / 1000.0 if timestamp_data > 1e12 else timestamp_data
            ts_dt = datetime.fromtimestamp(ts_val)
        elif isinstance(timestamp_data, str): ts_dt = date_parser.parse(timestamp_data)
        elif isinstance(timestamp_data, datetime): ts_dt = timestamp_data
        else: ts_dt = None
        if ts_dt: ts_str = ts_dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip() if ts_dt.tzinfo else ts_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception: ts_str = str(timestamp_data)
    if not ts_str: return fig
    show_ts = get_config_value(keys=["visualization_settings", "dashboard", "show_chart_timestamps"], default_value_to_return=True)
    if not show_ts: return fig
    ts_annotation_cfg = get_config_value(keys=_PLOTLY_DEFAULTS_CONFIG_KEY_PATH + ["timestamp_annotation"], default_value_to_return={})
    x_pos = float(ts_annotation_cfg.get("x_pos", 0.99))
    y_pos = float(ts_annotation_cfg.get("y_pos", -0.12 if fig.layout and fig.layout.margin and fig.layout.margin.b and fig.layout.margin.b > 40 else 0.01)) # type: ignore
    font_cfg = ts_annotation_cfg.get("font", {"size": 9, "color": "#7f8c8d"})
    fig.add_annotation(text=f"Data as of: {ts_str}", align='right', xref='paper', yref='paper', x=x_pos, y=y_pos, showarrow=False, font=font_cfg, xanchor='right', yanchor='top' if y_pos > 0.5 else 'bottom')
    return fig

def add_price_line(fig: go.Figure, price_value: Optional[Union[float, int]], orientation: str = 'horizontal', line_label: str = "Current Price") -> go.Figure:
    if price_value is None or not isinstance(price_value, (int, float)) or np.isnan(price_value): return fig
    line_style_cfg = get_config_value(keys=_PLOTLY_DEFAULTS_CONFIG_KEY_PATH + ["price_line_style"], default_value_to_return={})
    line_color = str(line_style_cfg.get("color", "rgba(220,220,220,0.6)"))
    line_width = int(line_style_cfg.get("width", 1)); line_dash = str(line_style_cfg.get("dash", "dot"))
    annotation_font_cfg = get_config_value(keys=_PLOTLY_DEFAULTS_CONFIG_KEY_PATH + ["price_line_annotation_font"], default_value_to_return={"size":10})
    annotation_bgcolor = str(get_config_value(keys=_PLOTLY_DEFAULTS_CONFIG_KEY_PATH + ["price_line_annotation_bgcolor"], default_value_to_return="rgba(0,0,0,0.6)"))
    func_to_call = fig.add_hline if orientation == 'horizontal' else fig.add_vline
    price_axis_arg_name = 'y' if orientation == 'horizontal' else 'x'
    func_to_call_args = {price_axis_arg_name: price_value, "line_width": line_width, "line_dash": line_dash, "line_color": line_color, "annotation_text": f"{line_label}: {price_value:.2f}", "annotation_position": "bottom right" if orientation == 'horizontal' else "top left", "annotation_font": annotation_font_cfg, "annotation_bgcolor": annotation_bgcolor, "annotation_borderpad": 2, "annotation_borderwidth": 1, "annotation_bordercolor": line_color}
    func_to_call(**func_to_call_args); return fig

def get_server_side_store_data_key(symbol: str, dte_list: Optional[List[int]], range_pct: Optional[float], timestamp_dt: Optional[datetime] = None, is_snapshot_key: bool = True) -> str:
    symbol_safe = re.sub(r'[^a-zA-Z0-9_-]', '', str(symbol).upper()) if symbol else "NOSYMBOL"; dte_str: str
    if isinstance(dte_list, list):
        unique_sorted_dtes = sorted(list(set(filter(lambda d: isinstance(d, int) and d >= 0, dte_list))))
        dte_str = "_".join(map(str, unique_sorted_dtes)) if unique_sorted_dtes else "ALLDTE"
    elif dte_list is None: dte_str = "DEFAULTDTE"
    else: dte_str = "INVALIDDTE"
    range_str = f"{float(range_pct):.1f}" if isinstance(range_pct, (float, int)) and pd.notna(range_pct) else "DEFRANGE"
    if is_snapshot_key:
        ts_to_use = timestamp_dt if isinstance(timestamp_dt, datetime) else datetime.utcnow()
        time_key_part = ts_to_use.strftime("%Y%m%d%H%M%S%f")[:-3]
        return f"{symbol_safe}_{dte_str}_{range_str}_{time_key_part}"
    else: return f"{symbol_safe}_{dte_str}_{range_str}_GENERAL"

def store_in_server_side_cache(key: str, data_bundle: Dict[str, Any], cache_dict: Dict[str, Any], symbol_for_log: str = "N/A") -> None:
    max_cache_size_val = get_config_value(keys=_CACHE_MAX_ITEMS_CONFIG_KEY_PATH, default_value_to_return=50)
    max_cache_size = int(max_cache_size_val) if isinstance(max_cache_size_val, (int,float)) and max_cache_size_val > 0 else 50
    if not isinstance(cache_dict, dict): utils_logger.error(f"UTILS_DASHBOARD: Cache_dict is not a dictionary. Cannot store item for key '{key}'."); return
    keys_to_evict = []
    if len(cache_dict) >= max_cache_size and max_cache_size > 0:
        num_to_evict = len(cache_dict) - max_cache_size + 1
        temp_keys_list = list(cache_dict.keys()) 
        for i in range(min(num_to_evict, len(temp_keys_list))): 
            keys_to_evict.append(temp_keys_list[i])
    for old_key in keys_to_evict:
        try:
            cache_dict.pop(old_key)
            utils_logger.debug(f"UTILS_DASHBOARD: Cache full (max {max_cache_size}). Evicted oldest key: '{old_key}' (for symbol: {symbol_for_log}).")
        except KeyError: utils_logger.warning(f"UTILS_DASHBOARD: Tried to evict key '{old_key}' which was already removed (race condition?).")
        except Exception as e_evict_pop: utils_logger.warning(f"UTILS_DASHBOARD: Error during cache eviction for key '{old_key}': {e_evict_pop}"); break
    if max_cache_size > 0: cache_dict[key] = (pytime.time(), data_bundle); utils_logger.debug(f"UTILS_DASHBOARD: Stored in cache with key '{key}' for symbol {symbol_for_log}. Cache size: {len(cache_dict)}/{max_cache_size}.")
    elif max_cache_size <= 0 : utils_logger.info(f"UTILS_DASHBOARD: Max cache size is {max_cache_size}. Item for key '{key}' not stored.")

def get_data_from_server_cache(key: str, cache: Optional[Dict[str, Tuple[float, Dict[str, Any]]]], app_config_for_timeout: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if cache is None or not isinstance(cache, dict) or key not in cache: return None
    cache_timeout_default = 120.0
    timeout_val_from_config = get_config_value(keys=_CACHE_TIMEOUT_CONFIG_KEY_PATH, default_value_to_return=cache_timeout_default)
    try:
        timeout_seconds = float(timeout_val_from_config)
        if timeout_seconds <=0: timeout_seconds = cache_timeout_default
    except (ValueError, TypeError): timeout_seconds = cache_timeout_default; utils_logger.warning(f"UTILS_DASHBOARD: Invalid cache timeout value '{timeout_val_from_config}'. Using default {timeout_seconds}s.")
    timestamp_cached, data_cached = cache[key]
    if (pytime.time() - timestamp_cached) < timeout_seconds: return data_cached
    else:
        utils_logger.info(f"UTILS_DASHBOARD: Cache expired for key '{key}'. Removing from cache.")
        try: del cache[key]
        except KeyError: utils_logger.warning(f"UTILS_DASHBOARD: Tried to delete already removed key '{key}' from cache (race condition?).")
        return None

def format_status_message_enhanced(message: str, is_error: bool = False, timestamp: Optional[datetime] = None, symbol: Optional[str] = None, duration_ms: Optional[int] = None) -> dbc.Alert:
    status_type = "error" if is_error else "info"
    icon_map_raw = get_config_value(keys=_STYLING_CONSTANTS_CONFIG_KEY_PATH + ["status_icon_map"], default_value_to_return={})
    icon_map = icon_map_raw if isinstance(icon_map_raw, dict) else {}
    color_type_key = f"STATUS_{status_type.upper()}_COLOR"; default_color_val = "danger" if status_type == "error" else "info"
    alert_color = get_config_value(keys=_STYLING_CONSTANTS_CONFIG_KEY_PATH + [color_type_key], default_value_to_return=default_color_val)
    icon_class = icon_map.get(status_type, icon_map.get("default", "bi bi-bell-fill"))
    effective_duration_ms = duration_ms
    if effective_duration_ms is None:
        duration_key_path = _STATUS_MESSAGE_ERROR_DURATION_KEY_PATH if is_error else _STATUS_MESSAGE_DEFAULT_DURATION_KEY_PATH
        default_duration_val = None if is_error else 7000
        duration_from_config_raw = get_config_value(keys=duration_key_path, default_value_to_return=default_duration_val)
        if isinstance(duration_from_config_raw, (int, float)) and duration_from_config_raw > 0: effective_duration_ms = int(duration_from_config_raw)
        elif duration_from_config_raw is None and is_error: effective_duration_ms = None 
        else: effective_duration_ms = default_duration_val if default_duration_val is not None else (None if is_error else 7000)
    ts_str = f" ({timestamp.strftime('%H:%M:%S')})" if isinstance(timestamp, datetime) else ""
    symbol_str = f"[{str(symbol).upper()}] " if symbol and isinstance(symbol, str) else ""
    formatted_message_content = html.Span([html.I(className=f"{icon_class} me-2"), f"{symbol_str}{message}{ts_str}"])
    return dbc.Alert(formatted_message_content, color=str(alert_color), duration=effective_duration_ms, dismissable=True, className="mb-2 p-2 small status-alert-global")

def get_chart_specific_height(chart_id: str) -> int:
    specific_height = get_config_value(keys=_CHART_SPECIFIC_HEIGHTS_CONFIG_KEY_PATH + [chart_id], default_value_to_return=None)
    if isinstance(specific_height, (int, float)) and specific_height > 50 : return int(specific_height)
    general_default_height = get_config_value(keys=_DEFAULT_CHART_HEIGHT_CONFIG_KEY_PATH, default_value_to_return=450)
    return int(general_default_height) if isinstance(general_default_height, (int,float)) and general_default_height > 50 else 450

def create_hover_text_from_dict(data_dict: Dict[str, Any], hover_config_list: Optional[List[Dict[str, Any]]] = None, title: Optional[str] = None, excluded_keys: Optional[List[str]] = None) -> str:
    if not isinstance(data_dict, dict): return "<extra></extra>"
    default_excluded = ['symbol', 'timestamp', 'timestamp_issued', 'last_updated', 'last_adjusted_ts', 'error', 'raw_df', 'strike_df', 'plot_df', 'current_processing_datetime_iso', 'id', 'target_rationale', 'exit_reason', 'rationale_full', 'current_market_regime_at_signal_time', 'current_market_regime_at_issuance', 'key_metrics_at_issuance', 'status_update']
    final_excluded_keys = set(excluded_keys) if excluded_keys is not None else set(); final_excluded_keys.update(default_excluded)
    lines: List[str] = [f"<b>{html.escape(str(title))}</b>"] if title and isinstance(title, str) else []
    items_to_process: List[Tuple[str, Any, Optional[Dict[str, Any]]]] = [] 
    if isinstance(hover_config_list, list) and hover_config_list:
        for item_cfg in hover_config_list:
            if isinstance(item_cfg, dict) and isinstance(item_cfg.get("key"), str):
                key = item_cfg["key"]
                if key not in final_excluded_keys and not key.startswith('_') and key in data_dict: items_to_process.append((key, data_dict.get(key), item_cfg))
    else: items_to_process = [(k, v, None) for k, v in data_dict.items() if k not in final_excluded_keys and not k.startswith('_')]
    
    for key, value, item_config_dict_nullable in items_to_process:
        item_cfg = item_config_dict_nullable or {} 
        label = str(item_cfg.get("label", key.replace('_', ' ').title()))
        if value is None or (isinstance(value, float) and np.isnan(value)): formatted_value = str(item_cfg.get("na_format", "N/A"))
        else:
            precision = item_cfg.get("precision")
            multiplier_val = float(item_cfg.get("multiplier", 1.0)) 
            prefix = str(item_cfg.get("prefix", "")); suffix = str(item_cfg.get("suffix", ""))
            is_currency_val = bool(item_cfg.get("is_currency", False))
            
            if isinstance(value, (float, int, np.number)):
                num_value = float(value) * multiplier_val # Apply multiplier
                if is_currency_val: # Check before modifying prefix
                    prefix = "$" + prefix.lstrip('$') # Ensure single '$'
                
                # CORRECTED SYNTAX: Split statements
                if isinstance(precision, int) and precision >= 0:
                    format_str = f"{prefix}{{val:,.{precision}f}}{suffix}"
                    try: formatted_value = format_str.format(val=num_value)
                    except: formatted_value = f"{prefix}{num_value}{suffix}" 
                else: 
                    if abs(num_value) >= 1e7 or (abs(num_value) < 1e-3 and num_value != 0): formatted_value = f"{prefix}{num_value:.2e}{suffix}"
                    elif isinstance(num_value, float) and abs(num_value - round(num_value)) < 1e-9 : formatted_value = f"{prefix}{num_value:,.0f}{suffix}"
                    else: formatted_value = f"{prefix}{num_value:,.2f}{suffix}"
            elif isinstance(value, (datetime, date)):
                try: formatted_value = value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime) else value.strftime("%Y-%m-%d")
                except: formatted_value = str(value)
            else: 
                formatted_value = f"{prefix}{html.escape(str(value))}{suffix}"
        lines.append(f"<b>{html.escape(label)}:</b> {formatted_value}")
    return "<br>".join(lines) + "<extra></extra>" if lines else "<extra></extra>"

def parse_timestamp_to_datetime(timestamp: Optional[Union[str, float, int, datetime]], default_tz: Optional[Any] = None) -> Optional[datetime]:
    if timestamp is None: return None
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None and default_tz: return timestamp.replace(tzinfo=default_tz)
        return timestamp
    try:
        dt_obj: Optional[datetime] = None
        if isinstance(timestamp, (float, int)):
            if timestamp > 1e12: timestamp /= 1000
            dt_obj = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str): 
            dt_obj = date_parser.parse(timestamp)
        if dt_obj and dt_obj.tzinfo is None and default_tz: 
            dt_obj = dt_obj.replace(tzinfo=default_tz)
        return dt_obj
    except (ValueError, TypeError, OverflowError, date_parser.ParserError) as e_parse_ts_robust:
        utils_logger.debug(f"UTILS_DASHBOARD: Could not parse robust timestamp '{timestamp}' (type: {type(timestamp)}): {e_parse_ts_robust}")
    return None

def parse_dte_input_string(dte_input_str: Optional[str]) -> List[int]:
    if not dte_input_str or not isinstance(dte_input_str, str): return []
    processed_dtes: set[int] = set()
    parts = [part.strip() for part in dte_input_str.split(',') if part.strip()]
    for part_str in parts:
        if part_str.isdigit():
            try: 
                dte_val = int(part_str)
                if dte_val >= 0: processed_dtes.add(dte_val)
                else: utils_logger.debug(f"UTILS_DASHBOARD: Invalid negative DTE value: '{part_str}'")
            except ValueError: utils_logger.debug(f"UTILS_DASHBOARD: Invalid DTE part (int): '{part_str}'")
        elif '-' in part_str:
            range_parts = part_str.split('-')
            if len(range_parts) == 2 and range_parts[0].strip().isdigit() and range_parts[1].strip().isdigit():
                try:
                    start_dte, end_dte = int(range_parts[0].strip()), int(range_parts[1].strip())
                    if 0 <= start_dte <= end_dte: processed_dtes.update(range(start_dte, end_dte + 1))
                    else: utils_logger.debug(f"UTILS_DASHBOARD: Invalid DTE range (start>end or negative): '{part_str}'")
                except ValueError: utils_logger.debug(f"UTILS_DASHBOARD: Invalid DTE range part (int conv): '{part_str}'")
            else: utils_logger.debug(f"UTILS_DASHBOARD: Invalid DTE range format: '{part_str}'")
        else: utils_logger.debug(f"UTILS_DASHBOARD: Unrecognized DTE part: '{part_str}'")
    return sorted(list(processed_dtes))

def ensure_columns_and_numeric_key_levels(df: pd.DataFrame, required_cols: List[str], calculation_name_for_log: str, fill_numeric_with: Any = 0.0, fill_object_with: str = "UNKNOWN_UTIL") -> Tuple[pd.DataFrame, bool]:
    if not isinstance(df, pd.DataFrame): 
        utils_logger.error(f"UTILS ({calculation_name_for_log}): Input not DataFrame. Returning empty DF with required columns."); 
        return pd.DataFrame(columns=required_cols), False
    df_copy = df.copy(); all_present_and_valid = True; missing_logs: List[str] = []; type_issue_logs: List[str] = []
    num_keywords = ['oi','vol','price','value','strike','delta','gamma','theta','vega','flow','rate','pct','ratio','num','count','id','level','score','avg','sum','min','max','std','mult','exp','sens','calc','days','dte','gex','dex','iv']
    num_suffixes = ['_val','_amt','_qty','_pct','_idx','_id','_lvl','_num','_cnt','_rt','_sc','_avg','_sum','_min','_max','_std','_mult','_exp','_sens','_calc','_days','_dte','xoi','xvolm','_bs','_5m','_15m','_30m','_60m','_buy','_sell','_norm']
    for col in required_cols:
        is_num_expect = any(k in col.lower() for k in num_keywords) or any(col.lower().endswith(s) for s in num_suffixes)
        if col not in df_copy.columns:
            missing_logs.append(col); all_present_and_valid = False
            df_copy[col] = fill_numeric_with if is_num_expect else fill_object_with
        else:
            if is_num_expect and not pd.api.types.is_numeric_dtype(df_copy[col]):
                orig_nans = df_copy[col].isnull().sum()
                try:
                    df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
                    if df_copy[col].isnull().sum() > orig_nans:
                        type_issue_logs.append(col); all_present_and_valid = False
                except Exception as e_to_num:
                    utils_logger.warning(f"UTILS ({calculation_name_for_log}): Error converting column '{col}' to numeric: {e_to_num}. Filling with default.")
                    df_copy[col] = fill_numeric_with
                    type_issue_logs.append(f"{col} (conversion_error)"); all_present_and_valid = False
            if pd.api.types.is_numeric_dtype(df_copy[col]): 
                df_copy[col] = df_copy[col].fillna(fill_numeric_with)
            elif df_copy[col].dtype == 'object': 
                df_copy[col] = df_copy[col].fillna(fill_object_with)
    if missing_logs: utils_logger.debug(f"UTILS ({calculation_name_for_log}): Added missing columns: {missing_logs}.")
    if type_issue_logs: utils_logger.warning(f"UTILS ({calculation_name_for_log}): Type conversion issues (new NaNs created or conversion error) in: {type_issue_logs}.")
    return df_copy, all_present_and_valid

if not _UTILS_CONFIG_INITIALIZED_FLAG:
    utils_logger.debug("UTILS_DASHBOARD: Module level init: _UTILS_CONFIG_INITIALIZED_FLAG is False. Calling set_app_config_for_utils(None) for fallbacks.")
    set_app_config_for_utils(None)
utils_logger.info("Dashboard Utilities Module (utils_dashboard.py) V2.4 Canonical Robust Initialized.")

if __name__ == '__main__': 
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)-8s] %(name)-45s L%(lineno)-4d: %(message)s', datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)
    utils_logger.info("--- Running utils_dashboard.py Standalone Test (Canonical Robust Version) ---")
    class MockCMForUtilsStandaloneTestRobust:
        _test_cfg_data: Dict[str, Any]
        def __init__(self, test_config_dict: Dict[str, Any]): 
            self._test_cfg_data = test_config_dict
            utils_logger.info(f"MockCM (Standalone Test) initialized. Config version: {self._test_cfg_data.get('version','N/A')}")
        def get_config(self) -> Dict[str, Any]: return self._test_cfg_data
        def get_setting(self, keys: Union[str, List[str]], default_value_to_return: Any = None, quiet: bool = False) -> Any:
            path_list = keys if isinstance(keys, list) else keys.split('.'); val = self._test_cfg_data
            try:
                for k_seg in path_list: val = val[k_seg] # type: ignore
                return val if val is not None else default_value_to_return
            except (KeyError, TypeError): return default_value_to_return
    sample_test_config_utils_standalone_robust = {
        "version": "UtilsStandaloneTestConfig_v2.4_CanonRobust",
        "system_settings": { "dashboard_cache_max_items": 3, "dashboard_cache_timeout_seconds": 60 },
        "visualization_settings": { "dashboard": {
            "plotly_defaults": { 
                "template": "plotly_dark",
                "layout": { 
                    "paper_bgcolor": "rgb(20,20,20)", 
                    "font": {"family": "Arial Black", "size": 13, "color": "#FFFFFF"},
                    "xaxis": {"gridcolor": "blue"}
                },
                "data": { 
                    "scatter": [{"marker": {"symbol": "star", "color": "yellow"}}]
                }
            },
            "styling_constants": { "status_icon_map": {"success":"bi-hand-thumbs-up", "error":"bi-emoji-dizzy", "default": "bi-info-circle"}, "STATUS_INFO_COLOR": "royalblue", "STATUS_ERROR_COLOR": "firebrick"},
            "chart_specific_heights": { "default_empty_chart": 220, "specific_test_chart": 520 },
            "default_graph_height": 380,
            "show_chart_timestamps": False,
            "status_message_default_duration_ms": 5000,
            "status_message_error_duration_ms": None
        }}
    }
    mock_cm_standalone_robust = MockCMForUtilsStandaloneTestRobust(sample_test_config_utils_standalone_robust)
    set_app_config_for_utils(mock_cm_standalone_robust)
    utils_logger.info(f"Test Plotly Template after mock CM init: Paper BgColor = {PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.paper_bgcolor}, Font Family = {PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.font.family}, Xaxis Gridcolor = {PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.xaxis.gridcolor}") # type: ignore
    assert PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.paper_bgcolor == "rgb(20,20,20)" # type: ignore
    assert PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.font.family == "Arial Black" # type: ignore
    assert PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.font.size == 13 # type: ignore
    assert PLOTLY_TEMPLATE_FOR_UTILS_MODULE.layout.xaxis.gridcolor == "blue" # type: ignore
    if PLOTLY_TEMPLATE_FOR_UTILS_MODULE.data.scatter: # type: ignore
        assert PLOTLY_TEMPLATE_FOR_UTILS_MODULE.data.scatter[0].marker.symbol == "star" # type: ignore
    assert get_chart_specific_height('specific_test_chart') == 520
    assert get_chart_specific_height('unknown_chart') == 380 
    status_msg_test_info = format_status_message_enhanced_util("Utils Test Info Message", is_error=False)
    utils_logger.info(f"Test Info Status Message Color: {status_msg_test_info.color}, Icon: {status_msg_test_info.children[0].children[0].className}") # type: ignore
    assert status_msg_test_info.color == "royalblue" # type: ignore
    assert "bi-info-circle" in status_msg_test_info.children[0].children[0].className # type: ignore
    status_msg_test_err = format_status_message_enhanced_util("Utils Test Error Message", is_error=True)
    utils_logger.info(f"Test Error Status Message Color: {status_msg_test_err.color}, Icon: {status_msg_test_err.children[0].children[0].className}") # type: ignore
    assert status_msg_test_err.color == "firebrick" # type: ignore
    assert "bi-emoji-dizzy" in status_msg_test_err.children[0].children[0].className # type: ignore
    utils_logger.info(f"Empty figure test title: {create_empty_figure(title='Test Empty').layout.title.text}") # type: ignore
    assert create_empty_figure(title='Test Empty').layout.title.text == "<b>Test Empty</b>" # type: ignore
    utils_logger.info("--- utils_dashboard.py Standalone Test (Canonical Robust Version) Complete ---")
