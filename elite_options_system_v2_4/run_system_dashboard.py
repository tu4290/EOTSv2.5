#!/usr/bin/env python3
import re
"""
Elite Options System Dashboard Runner (V2.4 - "Co-Pilot")

Primary launcher for the EOTS V2.4 Dashboard. Initializes configuration,
checks dependencies, dynamically loads core analytics and the Dash application,
and starts the web server.
"""

# Standard Library Imports
import os
import sys
import argparse
import logging
import traceback
import importlib
import json
from typing import Optional, List, Dict, Any, Tuple, Callable, Union
from collections import deque # For type hinting cache passed to dashboard
import pandas as pd # For type hinting cache passed to dashboard
import re # <--- ADD THIS LINE

# --- Initial Configuration ---
# Basic Logging Setup - will be reconfigured based on args and then config file
logging.basicConfig(
    level=logging.INFO, # Default, will be overridden by --log-level-runner
    format='%(asctime)s [%(levelname)-8s] %(name)-25s L%(lineno)d: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
runner_logger = logging.getLogger("EOTS_SystemRunnerV2.4") # Main logger for THIS runner script

DEFAULT_CONFIG_FILENAME_V2_4 = "config_v2_4.json"
DEFAULT_SCHEMA_FILENAME_V2_4 = "config.schema.json"

# Python package dependencies to check (ensure this list matches requirements.txt)
PYTHON_PACKAGES_V2_4 = [
    "dash",
    "pandas",
    "numpy",
    "plotly",
    "requests",
    "python-dotenv",
    "python-dateutil",
    "convexlib", # Assuming this is your primary data provider's library
    "dash_bootstrap_components",
    "jsonschema" # For config validation
]

# --- Helper Function for Path Management (Ensures utils can be found) ---
def _ensure_project_root_in_path_early():
    """Ensures the project root directory is in sys.path for relative imports."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"[RunnerPreSetup] Added project root to sys.path: {project_root}", flush=True)

_ensure_project_root_in_path_early()

# Now that path is set, we can import Dash safely for type hints and our ConfigManager
import dash # type: ignore
from jsonschema import validate, ValidationError # type: ignore

# --- ConfigManager Class (as provided by user) ---
class ConfigManager:
    _instance = None
    _config: Dict[str, Any] = {}
    _abs_config_path: Optional[str] = None
    _project_root: Optional[str] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            if __name__ == '__main__' and sys.argv and sys.argv[0]:
                 cls._project_root = os.path.dirname(os.path.abspath(sys.argv[0]))
            else:
                 cls._project_root = os.path.dirname(os.path.abspath(__file__))

            global runner_logger # Ensure it uses the globally defined runner_logger
            if 'runner_logger' in globals() and runner_logger is not None:
                runner_logger.debug(f"ConfigManager project root initialized to: {cls._project_root}")
            else: # Fallback if runner_logger somehow not available (should not happen)
                print(f"[ConfigManagerDebugInit] Project root initialized to: {cls._project_root}", flush=True)
        return cls._instance

    def load_config(self, config_path: str, schema_path: Optional[str] = None) -> bool:
        global runner_logger # Ensure it uses the globally defined runner_logger

        current_abs_config_path = os.path.abspath(config_path if os.path.isabs(config_path) else os.path.join(self._project_root or os.getcwd(), config_path))

        # Check if this exact config was already loaded and validated
        if self._config and self._abs_config_path == current_abs_config_path and self._config.get("_validated_schema_path") == (os.path.abspath(schema_path) if schema_path else None):
            runner_logger.debug(f"Configuration already loaded and validated from {self._abs_config_path}.")
            return True
        # If config is loaded but from a different path or schema, log a warning but don't reload (singleton behavior)
        elif self._config:
             runner_logger.warning(f"ConfigManager already initialized with {self._abs_config_path}. "
                                   f"Current request to load {current_abs_config_path} (original input: {config_path}) will use existing loaded config.")
             return True # Return true as a config is loaded, though it might not be the one requested now.

        runner_logger.info(f"Attempting to load configuration from: {config_path}")

        if not os.path.isabs(config_path):
            if self._project_root is None:
                runner_logger.error("Project root not set in ConfigManager. Cannot resolve relative config path.")
                return False
            resolved_config_path_for_load = os.path.join(self._project_root, config_path)
        else:
            resolved_config_path_for_load = config_path

        self._abs_config_path = os.path.abspath(resolved_config_path_for_load)
        runner_logger.debug(f"Absolute config path for loading resolved to: {self._abs_config_path}")

        try:
            with open(self._abs_config_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            current_abs_schema_path: Optional[str] = None
            if schema_path:
                if not os.path.isabs(schema_path):
                    if self._project_root is None:
                        runner_logger.error("Project root not set. Cannot resolve relative schema path.")
                        current_abs_schema_path = os.path.abspath(schema_path) # Best effort
                    else:
                        current_abs_schema_path = os.path.join(self._project_root, schema_path)
                else:
                    current_abs_schema_path = schema_path
                
                if current_abs_schema_path:
                    current_abs_schema_path = os.path.abspath(current_abs_schema_path)

                if current_abs_schema_path and os.path.exists(current_abs_schema_path):
                    runner_logger.info(f"Attempting to validate config against schema: {current_abs_schema_path}")
                    with open(current_abs_schema_path, 'r', encoding='utf-8') as sf:
                        schema_data_to_validate = json.load(sf)
                    validate(instance=loaded_data, schema=schema_data_to_validate)
                    runner_logger.info(f"Configuration validated successfully against schema: {schema_path}")
                    loaded_data["_validated_schema_path"] = current_abs_schema_path # Mark as validated
                elif schema_path: # Schema path provided but not found
                    runner_logger.warning(f"Schema file not found at resolved path '{current_abs_schema_path}' (from input '{schema_path}'). Skipping schema validation.")
                    loaded_data["_validated_schema_path"] = None # Mark as not validated
                else: # No schema path provided initially
                    runner_logger.info("No schema path explicitly provided. Skipping schema validation.")
                    loaded_data["_validated_schema_path"] = None

            self._config = loaded_data
            # Store project root in the config dict itself for other modules to potentially access
            if self._project_root:
                self._config["_project_root_path"] = self._project_root
            self._config["_config_file_absolute_path"] = self._abs_config_path


            runner_logger.info(f"Successfully loaded configuration from {self._abs_config_path}.")
            return True

        except FileNotFoundError:
            runner_logger.error(f"FATAL ERROR: Configuration file not found at {config_path} (resolved to {self._abs_config_path}).")
        except NameError: # For jsonschema if not imported
             runner_logger.error(f"FATAL ERROR: 'jsonschema' library likely not installed. Cannot validate configuration. Please install 'jsonschema'.")
        except ImportError: # If jsonschema import fails
            runner_logger.error(f"FATAL ERROR: 'jsonschema' library failed to import. Cannot validate configuration. Please install 'jsonschema'.")
        except ValidationError as ve:
            path_str = " -> ".join(map(str, ve.path)) if ve.path else "N/A"
            schema_path_str_log = " -> ".join(map(str, ve.schema_path)) if ve.schema_path else "N/A"
            runner_logger.error(f"FATAL ERROR: Configuration validation failed for {self._abs_config_path} "
                                f"against schema {schema_path if schema_path else 'N/A'}:")
            runner_logger.error(f"  Message: {ve.message}")
            runner_logger.error(f"  Path in JSON: {path_str}")
            runner_logger.error(f"  Offending Instance (first 200 chars): {str(ve.instance)[:200]}...")
            runner_logger.error(f"  Validator: {ve.validator} = {ve.validator_value}")
            runner_logger.error(f"  Schema Path: {schema_path_str_log}")
            if runner_logger.getEffectiveLevel() <= logging.DEBUG and hasattr(ve, 'context') and ve.context:
                 runner_logger.debug(f"  Validation Context: {ve.context}")
        except json.JSONDecodeError as e_json_decode:
            runner_logger.error(f"FATAL ERROR: Could not parse JSON configuration file {self._abs_config_path}: {e_json_decode}")
        except Exception as e_load_general:
            runner_logger.error(f"FATAL ERROR: An unexpected error occurred while loading {self._abs_config_path}: {e_load_general}", exc_info=True)

        self._config = {} # Clear config on any load error
        self._abs_config_path = None
        return False

    def get_config(self) -> Dict[str, Any]:
        if not self._config:
            runner_logger.error("ConfigManager: Configuration not loaded. Call load_config() first or check for loading errors.")
            raise RuntimeError("Configuration has not been loaded or loading failed.")
        return self._config

    def get_setting(self, key_path: Union[str, List[str]], default_value_to_return: Any = None, quiet: bool = False) -> Any:
        if not self._config:
            if not quiet:
                runner_logger.warning(f"ConfigManager: Attempted to get setting '{key_path}' but config not loaded. Returning default: {default_value_to_return}")
            return default_value_to_return

        # Process key_path into a list of keys
        if isinstance(key_path, str):
            keys = key_path.split('.') if key_path else [] # Handle empty string key_path
        elif isinstance(key_path, list):
            keys = key_path
        else:
            if not quiet:
                runner_logger.warning(f"ConfigManager: Invalid key_path type '{type(key_path)}'. Returning default: {default_value_to_return}")
            return default_value_to_return

        # --- Integrated Fix for empty keys list ---
        if not keys: # If keys list is empty (e.g., from an empty string key_path or passed as empty list)
            if not quiet:
                # The original key_path might be more informative here if it was an empty string
                original_path_for_log = "''" if isinstance(key_path, str) and not key_path.strip() else str(key_path)
                runner_logger.debug(f"ConfigManager: Empty keys list derived from path '{original_path_for_log}'. Returning default: {default_value_to_return}")
            return default_value_to_return
        # --- End of Integrated Fix ---

        # Start search from the root of the config
        current_config_node = self._config
        
        # Traverse for the parent of the final key
        parent_of_final_key = current_config_node
        path_traversed_log = []
        
        # This loop will not run if len(keys) is 1, which is correct.
        # It also correctly handles len(keys) > 1.
        # The 'if not keys:' check above handles len(keys) == 0.
        if len(keys) > 1:
            for key_segment in keys[:-1]: # Iterate through all but the last key segment
                path_traversed_log.append(key_segment)
                if isinstance(parent_of_final_key, dict) and key_segment in parent_of_final_key:
                    parent_of_final_key = parent_of_final_key[key_segment]
                else: # Path segment not found before reaching the end
                    if not quiet:
                        runner_logger.debug(f"ConfigManager: Path segment '{key_segment}' in '{'.'.join(keys)}' not found. Path traversed: '{'.'.join(path_traversed_log)}'. Returning default: {default_value_to_return}")
                    return default_value_to_return
        
        final_key_segment = keys[-1]

        # Now, at parent_of_final_key, try to get the final_key_segment, considering schema structure
        if isinstance(parent_of_final_key, dict):
            # Priority 1: Direct value if it's not a schema definition node
            if final_key_segment in parent_of_final_key:
                direct_value = parent_of_final_key[final_key_segment]
                # Check if the direct value itself looks like a schema node with "properties" or "default"
                is_schema_definition_node = isinstance(direct_value, dict) and \
                                          ("properties" in direct_value or \
                                           "default" in direct_value or \
                                           ("type" in direct_value and "enum" in direct_value)) # [cite: 1]
                if not is_schema_definition_node:
                    return direct_value

            # Priority 2: Schema structure: parent -> "properties" -> key -> "default"
            # This handles cases where the config value might be missing, so we look at the schema's default for that property.
            if isinstance(parent_of_final_key, dict) and "properties" in parent_of_final_key:
                properties_node = parent_of_final_key.get("properties")
                if isinstance(properties_node, dict) and final_key_segment in properties_node:
                    final_key_node = properties_node.get(final_key_segment)
                    if isinstance(final_key_node, dict) and "default" in final_key_node:
                        value = final_key_node["default"]
                        return value

            # Priority 3: Schema structure (simpler): parent -> key -> "default" (if key itself IS a schema node)
            # This handles cases where the 'final_key_segment' points to a schema node that has its own "default".
            if final_key_segment in parent_of_final_key and \
               isinstance(parent_of_final_key.get(final_key_segment), dict) and \
               "default" in parent_of_final_key[final_key_segment]: # [cite: 1]
                value = parent_of_final_key[final_key_segment]["default"] # [cite: 1]
                return value
        
        # If not found in any structure after all checks
        if not quiet:
            full_path_str = '.'.join(keys)
            traversed_path_str = '.'.join(path_traversed_log) if path_traversed_log else "(root)"
            runner_logger.debug(f"ConfigManager: Setting '{full_path_str}' not found. Parent traversed to: '{traversed_path_str}', final key: '{final_key_segment}'. Returning default: {default_value_to_return}")
        return default_value_to_return

    def resolve_path(self, relative_or_absolute_path: str) -> str:
        if self._project_root is None:
            runner_logger.error("ConfigManager: Project root is not set, cannot resolve relative paths robustly. Using CWD as base.")
            # Fallback to CWD if project_root is somehow None
            base_path_for_resolve = os.getcwd()
        else:
            base_path_for_resolve = self._project_root

        if os.path.isabs(relative_or_absolute_path):
            return os.path.normpath(relative_or_absolute_path)
        return os.path.normpath(os.path.join(base_path_for_resolve, relative_or_absolute_path))

    def get_resolved_path(self, key_path: Union[str, List[str]], default_relative_path: Optional[str] = None, quiet: bool = False) -> Optional[str]:
        # Get the path string from config, using default_relative_path if config key is not found
        path_val_from_config = self.get_setting(key_path, default_value_to_return=None, quiet=quiet)

        final_path_to_resolve = None
        if isinstance(path_val_from_config, str) and path_val_from_config.strip():
            final_path_to_resolve = path_val_from_config
        elif default_relative_path is not None: # Only use default_relative_path if config returned None or empty string
            final_path_to_resolve = default_relative_path
        
        if final_path_to_resolve:
            return self.resolve_path(final_path_to_resolve)

        # Logging for cases where path cannot be resolved
        keys_str_log = key_path if isinstance(key_path, str) else ".".join(key_path)
        if path_val_from_config is not None and not isinstance(path_val_from_config, str): # Config had a value, but it wasn't a string
            if not quiet:
                runner_logger.warning(f"ConfigManager: Path setting at '{keys_str_log}' is not a string: {path_val_from_config}. Cannot resolve.")
        elif path_val_from_config is None and default_relative_path is None and not quiet: # Config key not found AND no default provided
            runner_logger.debug(f"ConfigManager: Path setting at '{keys_str_log}' not found and no default relative path provided. Returning None.")
        return None

    def get_project_root_instance(self) -> Optional[str]:
        return self._project_root

    def get_abs_config_path_instance(self) -> Optional[str]:
        return self._abs_config_path

    @classmethod
    def get_project_root(cls) -> Optional[str]:
        return cls._project_root

    @classmethod
    def get_abs_config_path(cls) -> Optional[str]:
        return cls._abs_config_path

# --- Global ConfigManager Instance ---
config_manager = ConfigManager() # Instantiated once

# --- Runner Helper Functions (using ConfigManager) ---
# (get_required_directories_from_config_v2_4, check_python_packages_v2_4, 
#  check_api_credentials_v2_4, ensure_directories_v2_4 remain largely the same,
#  as they already use the config_manager instance)

def get_required_directories_from_config_v2_4() -> List[str]:
    # This function now relies on ConfigManager instance being correctly populated.
    runner_logger.debug(f"Project root for resolving relative directories (from ConfigManager instance): {config_manager.get_project_root_instance()}")
    dirs_to_check: set[str] = set()

    # Example: "runner_settings.paths.raw_data_cache"
    dirs_to_check.add(config_manager.get_resolved_path(["runner_settings", "paths", "raw_data_cache"], default_relative_path="data_output/raw_data_cache"))
    dirs_to_check.add(config_manager.get_resolved_path(["runner_settings", "paths", "processed_data_cache"], default_relative_path="data_output/processed_data_cache"))
    dirs_to_check.add(config_manager.get_resolved_path(["runner_settings", "paths", "historical_ohlc_store"], default_relative_path="data_output/historical_ohlc_data"))
    dirs_to_check.add(config_manager.get_resolved_path(["runner_settings", "paths", "historical_metric_store"], default_relative_path="data_output/historical_metric_data"))
    
    # data_directory is under system_settings.properties.data_directory.default
    dirs_to_check.add(config_manager.get_resolved_path(["system_settings", "data_directory"]))

    dashboard_pkg_name = config_manager.get_setting(["runner_settings", "dashboard_package_name"], default_value_to_return="dashboard_application")
    assets_rel_path = os.path.join(str(dashboard_pkg_name), "assets") # Ensure dashboard_pkg_name is string
    dirs_to_check.add(config_manager.resolve_path(assets_rel_path)) # Use resolve_path directly if base is known

    viz_output_dir = config_manager.get_resolved_path(["visualization_settings", "mspi_visualizer", "output_dir"], default_relative_path="output_visualizations_v2_4")
    dirs_to_check.add(viz_output_dir)

    # Filter out None values that might result if a path couldn't be resolved
    final_dirs = sorted([d for d in list(dirs_to_check) if d is not None])
    runner_logger.info(f"Required directories identified for V2.4 structure (via ConfigManager): {final_dirs}")
    return final_dirs

def check_python_packages_v2_4(packages_to_check: List[str]) -> bool:
    runner_logger.info("Checking required Python package imports for V2.4...")
    missing_packages_list = []
    for package_name_from_reqs in packages_to_check:
        try:
            # Simplified import name derivation
            import_name_candidate = re.split(r'[=<>~\[@!]', package_name_from_reqs)[0].strip()
            if import_name_candidate == "python-dotenv": import_name_candidate = "dotenv"
            elif import_name_candidate == "python-dateutil": import_name_candidate = "dateutil"
            elif import_name_candidate == "dash-bootstrap-components": import_name_candidate = "dash_bootstrap_components"
            elif import_name_candidate == "MarkupSafe": import_name_candidate = "markupsafe"
            
            importlib.import_module(import_name_candidate)
            runner_logger.debug(f"  - Package '{package_name_from_reqs}' (checked as '{import_name_candidate}') found.")
        except ImportError:
            runner_logger.error(f"  - CRITICAL: Required package '{package_name_from_reqs}' (tried importing '{import_name_candidate}') is NOT installed.")
            missing_packages_list.append(package_name_from_reqs)
        except Exception as e_pkg_check:
             runner_logger.error(f"  - Error checking package '{package_name_from_reqs}' (import name '{import_name_candidate}'): {e_pkg_check}", exc_info=False)
             missing_packages_list.append(package_name_from_reqs) # Add to missing if check fails for other reasons

    if missing_packages_list:
        runner_logger.error("-" * 70 + "\nFATAL ERROR: Missing required Python packages or error during check.\n" +
                            "Please install them, e.g., 'pip install -r requirements.txt' or individually:\n" +
                            "\n".join([f"  pip install \"{pkg}\"" for pkg in missing_packages_list]) + "\n" + "-" * 70)
        return False
    runner_logger.info("All required Python packages for V2.4 seem to be installed and importable.")
    return True

def check_api_credentials_v2_4() -> Tuple[bool, Optional[str], Optional[str]]:
    # This function checks for ConvexValue credentials by default.
    # For Tradier, the TradierDataFetcher will check its own specific token.
    # This function can remain as is for ConvexValue, or be generalized if needed.
    runner_logger.info("Checking for ConvexValue API credentials (V2.4)...")
    project_r = config_manager.get_project_root_instance()
    
    env_file_path_default = ".env"
    env_file_path = config_manager.resolve_path(env_file_path_default) if project_r else os.path.join(os.getcwd(), env_file_path_default)
        
    try:
        from dotenv import load_dotenv # type: ignore
        loaded_from_env_file = load_dotenv(dotenv_path=env_file_path, verbose=True, override=True)
        if os.path.exists(env_file_path):
            runner_logger.info(f".env file {'loaded' if loaded_from_env_file else 'found but no new vars loaded/overridden'} from: {env_file_path}")
        else:
             runner_logger.info(f"No .env file found at {env_file_path}. Will check system environment variables only.")
    except ImportError:
        runner_logger.warning("'python-dotenv' not found. Cannot load .env file. Checking system environment variables only.")
    except Exception as dotenv_err: # Catch more general errors from dotenv
         runner_logger.warning(f"Error loading .env file from '{env_file_path}': {dotenv_err}")

    # Get ConvexValue specific env var names from config
    email_env_var = config_manager.get_setting(["api_credentials", "email_env_var"], "CONVEX_EMAIL")
    pass_env_var = config_manager.get_setting(["api_credentials", "password_env_var"], "CONVEX_PASSWORD")
    
    api_email = os.getenv(str(email_env_var))
    api_pass = os.getenv(str(pass_env_var))

    if api_email and api_pass:
        runner_logger.info(f"ConvexValue API credentials ('{email_env_var}', password for '{pass_env_var}' redacted) found in environment.")
        return True, api_email, api_pass # Return them for potential direct use if needed, though components usually get from env themselves
    else:
        # This error message is specific to ConvexValue. Tradier token check will be separate.
        runner_logger.error("\n" + "="*70 + "\n!! WARNING: ConvexValue API Credentials Not Found !!\n" + "-"*70 +
                            (f"\n  - Environment variable '{email_env_var}' for ConvexValue is missing or empty." if not api_email else "") +
                            (f"\n  - Environment variable '{pass_env_var}' for ConvexValue is missing or empty." if not api_pass else "") +
                            f"\nEnsure these are set if you intend to use ConvexValue. System might proceed if other data sources are primary.\n" + "="*70 + "\n")
        return False, None, None # Return False for ConvexValue creds

def ensure_directories_v2_4(dir_list: List[str]) -> bool:
    # This function remains the same.
    if not dir_list:
        runner_logger.info("No specific directories configured to check/create via get_required_directories.")
        return True # No dirs to check means success in this context
    runner_logger.info(f"Ensuring required directories exist: {dir_list}")
    all_ok = True
    for dir_path in dir_list:
        if not dir_path: # Skip if a path resolved to None
            runner_logger.debug("Skipping None directory path in ensure_directories_v2_4.")
            continue
        try:
            os.makedirs(dir_path, exist_ok=True)
            runner_logger.debug(f"  - Directory '{dir_path}' ensured.")
        except Exception as e:
            runner_logger.error(f"  - FAILED to create/ensure directory '{dir_path}': {e}", exc_info=True)
            all_ok = False # Mark failure but continue checking other dirs
    if not all_ok:
        runner_logger.error("FATAL ERROR: Failed to create/ensure one or more required directories.")
        return False
    runner_logger.info("All required directories verified/created successfully.")
    return True


def initialize_its_and_dashboard_app() -> Optional[Tuple[Any, dash.Dash, Any, Optional[Callable[[], None]]]]:
    """
    Dynamically loads and initializes the ITS Orchestrator and the Dash application.
    The ITS Orchestrator will internally load its components (including DataFetchers)
    based on the global config_manager.
    """
    runner_logger.info("Initializing Core Analytics Engine (ITS Orchestrator) and Dashboard App for V2.4...")
    
    # Get module and class names from the (already loaded) config_manager
    its_mod_p = config_manager.get_setting(["runner_settings", "its_orchestrator_module_path"], "core_analytics_engine.its_orchestrator")
    its_cls_n = config_manager.get_setting(["runner_settings", "its_orchestrator_class_name"], "IntegratedTradingSystemV2_4")
    
    dash_mod_p = config_manager.get_setting(["runner_settings", "dashboard_module_path"], "dashboard_application.app_main")
    dash_app_obj_n = config_manager.get_setting(["runner_settings", "dashboard_app_object_name"], "app")
    dash_serv_obj_n = config_manager.get_setting(["runner_settings", "dashboard_server_object_name"], "server") # For Gunicorn/WSGI
    dash_init_deps_n = config_manager.get_setting(["runner_settings", "dashboard_init_deps_function_name"], "initialize_dashboard_dependencies")
    dash_cleanup_n = config_manager.get_setting(["runner_settings", "dashboard_cleanup_function_name"], "cleanup_app_resources")

    its_orch_instance: Optional[Any] = None
    dash_app_instance: Optional[dash.Dash] = None
    dash_server_instance: Optional[Any] = None # For WSGI server
    dashboard_cleanup_function: Optional[Callable[[], None]] = None

    try:
        runner_logger.debug(f"Attempting to import ITS Orchestrator: {its_mod_p}.{its_cls_n}")
        ITSOrchestratorClass = getattr(importlib.import_module(str(its_mod_p)), str(its_cls_n))
        # The ITS Orchestrator's __init__ should take the config_manager instance.
        # It will then use this config_manager to load its own components,
        # including the ConvexValue fetcher AND the new TradierDataFetcher.
        its_orch_instance = ITSOrchestratorClass(loaded_config_manager_instance=config_manager)
        runner_logger.info(f"ITS Orchestrator '{its_cls_n}' initialized successfully.")
        
        # Check if ITS Orchestrator itself reported an initialization failure
        if hasattr(its_orch_instance, 'initialization_failed') and its_orch_instance.initialization_failed:
            runner_logger.critical("ITS Orchestrator reported its own initialization failure. Aborting.")
            return None # Critical failure of a core component

        runner_logger.debug(f"Attempting to import Dashboard application: {dash_mod_p} (app object: {dash_app_obj_n})")
        dashboard_module = importlib.import_module(str(dash_mod_p))
        dash_app_instance_candidate = getattr(dashboard_module, str(dash_app_obj_n))
        
        # Check if it's already a Dash app instance or a factory function
        if isinstance(dash_app_instance_candidate, dash.Dash):
            dash_app_instance = dash_app_instance_candidate
        elif callable(dash_app_instance_candidate):
            runner_logger.info(f"Dashboard app object '{dash_app_obj_n}' appears to be a factory. Calling it.")
            dash_app_instance = dash_app_instance_candidate() # Assuming factory takes no args or gets them from globals
            if not isinstance(dash_app_instance, dash.Dash):
                 raise TypeError(f"Dashboard factory '{dash_app_obj_n}' did not return a Dash app instance.")
        else:
            raise AttributeError(f"Dashboard app object '{dash_app_obj_n}' in '{dash_mod_p}' is not a Dash app instance or a factory.")

        # Get server object if defined separately (for Gunicorn etc.)
        if hasattr(dash_app_instance, 'server'): # Standard for Dash apps
             dash_server_instance = dash_app_instance.server
        elif hasattr(dashboard_module, str(dash_serv_obj_n)): # Fallback to module attribute
             dash_server_instance = getattr(dashboard_module, str(dash_serv_obj_n))
        
        runner_logger.info(f"Dash app '{dash_app_obj_n}' (and server if applicable) imported/instantiated.")

        # Initialize dashboard dependencies (passing ITS orchestrator and ConfigManager)
        if dash_init_deps_n and hasattr(dashboard_module, str(dash_init_deps_n)):
            initialize_dependencies_func = getattr(dashboard_module, str(dash_init_deps_n))
            if callable(initialize_dependencies_func):
                runner_logger.debug(f"Calling dashboard dependency initializer: '{dash_init_deps_n}'")
                initialize_dependencies_func(
                    its_orchestrator_instance=its_orch_instance,
                    config_manager_instance=config_manager # Corrected keyword argument
                )
                runner_logger.info(f"Dashboard dependency initializer '{dash_init_deps_n}' called successfully.")
            else:
                runner_logger.warning(f"Configured dashboard initializer '{dash_init_deps_n}' in '{dash_mod_p}' is not callable.")
        else:
            runner_logger.info(f"No dashboard dependency initializer function ('{dash_init_deps_n}') configured or found in '{dash_mod_p}'.")
        
        # Get cleanup function if defined
        if dash_cleanup_n and hasattr(dashboard_module, str(dash_cleanup_n)):
            cleanup_func_candidate = getattr(dashboard_module, str(dash_cleanup_n))
            if callable(cleanup_func_candidate):
                dashboard_cleanup_function = cleanup_func_candidate
                runner_logger.info(f"Registered dashboard cleanup function: '{dash_cleanup_n}'.")
        
        if its_orch_instance and dash_app_instance:
            return its_orch_instance, dash_app_instance, dash_server_instance, dashboard_cleanup_function
            
    except ModuleNotFoundError as mnfe:
        runner_logger.critical(f"FATAL ERROR: Module not found during ITS/Dashboard initialization: {mnfe.name}. Check PYTHONPATH and module paths in config ('runner_settings').", exc_info=True)
    except AttributeError as ae:
        runner_logger.critical(f"FATAL ERROR: Attribute (class/function/object name) not found during ITS/Dashboard initialization: {ae}. Check names in config ('runner_settings').", exc_info=True)
    except Exception as e_init_all:
        runner_logger.critical(f"FATAL ERROR during ITS/Dashboard initialization: {e_init_all}", exc_info=True)
        runner_logger.error(f"Details - ITS Module: {its_mod_p}, Class: {its_cls_n}. Dash Module: {dash_mod_p}, App Obj: {dash_app_obj_n}, Server Obj: {dash_serv_obj_n}")
    
    return None # Return None on any critical failure

# --- Main Application Logic ---
def main_v2_4():
    global runner_logger # Allow modification of the global runner_logger

    runner_logger.info("=" * 70 + f"\n====== Starting Elite Options System Dashboard Runner (V2.4 Co-Pilot) | PID: {os.getpid()} ======\n" + "=" * 70)

    parser = argparse.ArgumentParser(description="Run EOTS V2.4 Dashboard")
    parser.add_argument("--config-path", type=str, default=DEFAULT_CONFIG_FILENAME_V2_4, help=f"Path to V2.4 config file (default: ./{DEFAULT_CONFIG_FILENAME_V2_4})")
    parser.add_argument("--schema-path", type=str, default=DEFAULT_SCHEMA_FILENAME_V2_4, help=f"Path to V2.4 config schema file for validation (default: ./{DEFAULT_SCHEMA_FILENAME_V2_4})")
    parser.add_argument("--production", action="store_true", help="Run Dash in production mode (debug=False, use_reloader typically True for prod with Gunicorn).")
    parser.add_argument("--host", type=str, help="Server host IP (overrides config)")
    parser.add_argument("--port", type=int, help="Server port (overrides config)")
    parser.add_argument("--skip-api-check", action="store_true", help="Skip ConvexValue API credential validation (USE WITH CAUTION)")
    parser.add_argument("--skip-package-check", action="store_true", help="Skip Python package validation check.")
    parser.add_argument("--log-level-runner", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Logging level for this runner script.")
    args = parser.parse_args()

    # Set runner's own log level first
    try:
        runner_logger.setLevel(getattr(logging, args.log_level_runner.upper()))
    except AttributeError: # Should not happen with choices
        runner_logger.warning(f"Invalid runner log level '{args.log_level_runner}'. Using INFO.")
    runner_logger.info(f"SystemRunnerV2.4 log level set to: {logging.getLevelName(runner_logger.getEffectiveLevel())}")

    # Load configuration using the global ConfigManager instance
    if not config_manager.load_config(args.config_path, schema_path=args.schema_path):
        runner_logger.critical("Config loading and/or validation failed. Exiting.")
        sys.exit(1)

    # Set global log level for other modules based on loaded config
    # Note: Individual modules might override this with their own specific config settings
    global_log_level_from_config = config_manager.get_setting(["system_settings", "log_level"], "INFO")
    try:
        root_logger_level = getattr(logging, str(global_log_level_from_config).upper())
        logging.getLogger().setLevel(root_logger_level) # Set for root logger
        runner_logger.info(f"Global log level for other modules (from config 'system_settings.log_level') set to: '{global_log_level_from_config}'. Individual modules may have specific overrides.")
    except (AttributeError, ValueError):
        runner_logger.warning(f"Invalid global log level '{global_log_level_from_config}' in config. Root logger level not changed from runner's default.")
        logging.getLogger().setLevel(logging.INFO) # Fallback for root

    # Determine final host and port, allowing CLI args to override config
    final_host = args.host or config_manager.get_setting(["system_settings", "dashboard_host"], "0.0.0.0")
    final_port = args.port or config_manager.get_setting(["system_settings", "dashboard_port"], 8050) # Ensure int

    runner_logger.info(f"Config Path Used: {config_manager.get_abs_config_path_instance()}")
    schema_file_for_log = config_manager.resolve_path(args.schema_path) if args.schema_path else None
    runner_logger.info(f"Schema Path Used for Validation: {schema_file_for_log if schema_file_for_log and os.path.exists(schema_file_for_log) else 'N/A (default, not found, or skipped)'}")
    runner_logger.info(f"Dashboard Run Mode: {'PRODUCTION' if args.production else 'DEVELOPMENT'}")
    runner_logger.info(f"Dashboard Server Target: http://{final_host}:{final_port}")

    # Perform pre-run checks
    if not args.skip_package_check and not check_python_packages_v2_4(PYTHON_PACKAGES_V2_4):
        sys.exit(1) # Critical failure
    if not args.skip_api_check:
        # Check for ConvexValue creds; Tradier creds will be checked by TradierDataFetcher itself
        _cv_creds_ok, _, _ = check_api_credentials_v2_4()
        if not _cv_creds_ok:
            runner_logger.warning("ConvexValue API credentials check failed or not found. System might rely on other data sources like Tradier if configured.")
            # Not exiting here, as the system might be configured to use Tradier primarily.
            # The individual fetchers will log errors if they cannot connect.
    
    required_dirs = get_required_directories_from_config_v2_4()
    if not ensure_directories_v2_4(required_dirs):
        sys.exit(1) # Critical failure

    # Initialize ITS and Dashboard App
    init_results = initialize_its_and_dashboard_app()
    if not init_results:
        runner_logger.critical("Core system components (ITS Orchestrator or Dashboard App) failed to initialize. Exiting.")
        sys.exit(1)

    its_orchestrator_main, dash_app_main, _dash_server_obj_main_unused, dashboard_cleanup_function_main = init_results

    # Determine Dash debug mode
    if args.production:
        dash_debug_mode_final = False
        # For production with Gunicorn, use_reloader is typically False and handled by Gunicorn.
        # If running directly with `python run_system_dashboard.py --production`, reloader might still be useful.
        dash_use_reloader_final = True # Or False if Gunicorn is the standard
        runner_logger.info("Production mode: Dash debug=False.")
    else: # Development mode
        dash_debug_mode_final = config_manager.get_setting(["system_settings", "dashboard_debug_mode"], True)
        dash_use_reloader_final = dash_debug_mode_final # Usually reloader is on if debug is on
        runner_logger.info(f"Development mode: Dash debug={dash_debug_mode_final}, Reloader={dash_use_reloader_final} (from config).")


    runner_logger.info(f"Starting Dash server (Dash Internal Debug Mode: {dash_debug_mode_final}, Use Reloader: {dash_use_reloader_final})...")
    print("-" * 70 + f"\n Elite Options System Dashboard V2.4 ('Co-Pilot') running on http://{final_host}:{final_port} \n" +
          (f"(Also try: http://127.0.0.1:{final_port} or http://localhost:{final_port})\n" if str(final_host) in ['0.0.0.0', '0'] else "") +
          "-" * 70 + "\nPress CTRL+C to stop the server.", flush=True)

    try:
        dash_app_main.run( # Changed from app.run to dash_app_main.run_server
            debug=dash_debug_mode_final,
            host=str(final_host),
            port=int(final_port), # Ensure port is int
            use_reloader=dash_use_reloader_final
        )
    except (KeyboardInterrupt, SystemExit):
        runner_logger.info("Shutdown signal received (KeyboardInterrupt/SystemExit).")
    except ValueError as e_val_run: # Catch common errors like port in use
        runner_logger.critical(f"ValueError during Dash server run (often port issue or invalid config for run_server): {e_val_run}", exc_info=True)
        sys.exit(1)
    except Exception as e_run_general:
        runner_logger.critical(f"FATAL Dash Server Run Error: {e_run_general}", exc_info=True)
        sys.exit(1)
    finally:
        runner_logger.info("Server stopped. Executing cleanup...")
        if dashboard_cleanup_function_main and callable(dashboard_cleanup_function_main):
            try:
                dashboard_cleanup_function_main()
                runner_logger.info("Dashboard cleanup function executed successfully.")
            except Exception as e_cleanup_dash_main:
                runner_logger.warning(f"Error during dashboard cleanup: {e_cleanup_dash_main}", exc_info=True)
        
        # Orchestrator cleanup
        if its_orchestrator_main and hasattr(its_orchestrator_main, 'shutdown_cleanup') and callable(getattr(its_orchestrator_main, 'shutdown_cleanup')):
            try:
                getattr(its_orchestrator_main, 'shutdown_cleanup')() # Call the method
                runner_logger.info("ITS orchestrator cleanup executed successfully.")
            except Exception as e_cleanup_its_main:
                runner_logger.warning(f"Error during ITS orchestrator cleanup: {e_cleanup_its_main}", exc_info=True)
        else:
            runner_logger.debug("ITS orchestrator cleanup skipped (instance not available or method missing).")

        runner_logger.info("EOTS V2.4 Dashboard shutdown complete.\n" + "=" * 70)

# --- Script Entry Point ---
if __name__ == '__main__':
    main_v2_4()
