# elite_options_system_v2_5/utils/config_manager_v2_5.py

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from ..data_models.eots_schemas_v2_5 import EOTSConfigV2_5
    from pydantic import ValidationError as PydanticValidationError
    PYDANTIC_SCHEMAS_AVAILABLE = True
except ImportError as e: # Catching the specific error
    # Fallback for PYDANTIC_SCHEMAS_AVAILABLE, and define dummy classes
    PYDANTIC_SCHEMAS_AVAILABLE = False
    class EOTSConfigV2_5: # type: ignore
        # Add dummy attributes that might be checked by `hasattr` if absolutely necessary
        # Or ensure no code relies on attributes of a non-existent model.
        pass
    class PydanticValidationError(Exception): # type: ignore
        pass
    # Log this specific import error clearly
    # Cannot use self.logger here as it's not initialized yet.
    # Use a temporary logger or print for this critical bootstrap phase.
    temp_logger = logging.getLogger(f"{__name__}_bootstrap_error")
    temp_logger.critical(f"CRITICAL IMPORT ERROR: EOTSConfigV2_5 or PydanticValidationError from pydantic could not be imported. Pydantic config parsing will be SKIPPED. Error: {e}")


from jsonschema import validate, RefResolver, Draft7Validator # Keep for fallback

logger = logging.getLogger(__name__)

class ConfigManagerV2_5:
    def __init__(self,
                 config_filename: str = 'config_v2_5.json',
                 schema_filename: str = 'config.schema.v2.5.json',
                 project_root_marker: str = 'README.md'):

        self.project_root = self._find_project_root(start_path=Path(__file__).parent, marker=project_root_marker)
        if not self.project_root:
            self.project_root = Path.cwd()
            logger.warning(f"Project root marker '{project_root_marker}' not found. Using CWD: {self.project_root} for ConfigManagerV2_5.")

        # Correctly use project_root for config/schema paths
        # Assuming elite_options_system_v2_5 is a direct child of project_root
        self.config_file_path = self.project_root / 'elite_options_system_v2_5' / config_filename
        self.schema_file_path = self.project_root / 'elite_options_system_v2_5' / schema_filename

        self.raw_config: Dict[str, Any] = {}
        self.eots_config_model: Optional[EOTSConfigV2_5] = None

        self._load_and_parse_config()

        if not self.eots_config_model and self.raw_config:
            logger.warning("Pydantic model parsing failed or was skipped. Attempting jsonschema validation on raw config as a fallback.")
            self._validate_config_with_jsonschema()
        elif not self.raw_config:
             logger.error("No raw configuration was loaded. Cannot perform Pydantic parsing or JSONSchema validation.")


    def _find_project_root(self, start_path: Path, marker: str) -> Optional[Path]:
        current_path = start_path.resolve()
        # Iterate up a limited number of times to avoid scanning the entire filesystem
        for _ in range(len(current_path.parts) - 1): # Max depth based on parts
            if (current_path / marker).exists():
                return current_path
            if current_path == current_path.parent: # Reached filesystem root
                break
            current_path = current_path.parent

        # Final check if marker is in the last path checked (e.g. filesystem root)
        if (current_path / marker).exists():
            return current_path

        logger.warning(f"Project root marker '{marker}' not found starting from {start_path}.")
        return None

    def _load_and_parse_config(self):
        logger.info(f"Loading configuration from: {self.config_file_path}")
        try:
            with open(self.config_file_path, 'r') as f: self.raw_config = json.load(f)
            logger.info("Raw configuration JSON loaded successfully.")
        except FileNotFoundError:
            logger.error(f"CRITICAL: Configuration file not found at {self.config_file_path}.")
            self.raw_config = {}
            return # Cannot proceed if file not found
        except json.JSONDecodeError as e:
            logger.error(f"CRITICAL: Invalid JSON in configuration file: {self.config_file_path}. Error: {e}")
            self.raw_config = {}
            return # Cannot proceed if JSON is invalid

        if PYDANTIC_SCHEMAS_AVAILABLE and self.raw_config:
            logger.info("Attempting Pydantic parsing of raw config into EOTSConfigV2_5...")
            try:
                self.eots_config_model = EOTSConfigV2_5(**self.raw_config)
                logger.info("Config successfully parsed and validated by EOTSConfigV2_5 Pydantic model.")
            except PydanticValidationError as e_pydantic:
                logger.error(f"CRITICAL: Pydantic validation error for config {self.config_file_path}:\n{e_pydantic}")
                self.eots_config_model = None
            except Exception as e_other_parse:
                logger.error(f"CRITICAL: Unexpected error parsing config with Pydantic: {e_other_parse}", exc_info=True)
                self.eots_config_model = None
        elif not self.raw_config: # This case is now handled by early returns above
             pass
        elif not PYDANTIC_SCHEMAS_AVAILABLE:
             logger.warning("Pydantic EOTSConfigV2_5 model not available due to import errors. Skipping Pydantic parsing and validation.")


    def _validate_config_with_jsonschema(self):
        # This is a fallback if Pydantic parsing fails or is unavailable
        if not self.raw_config:
            logger.warning("JSONSchema validation: Raw config is empty, skipping.")
            return

        logger.info("Attempting JSONSchema validation as fallback/secondary check...")
        try:
            with open(self.schema_file_path, 'r') as f: schema = json.load(f)

            # Resolve local references like file:///path/to/schemas_dir/config.schema.json#definitions/subSchema
            # Correct base_uri should point to the directory containing the schema file.
            base_uri = 'file://' + str(self.schema_file_path.parent.resolve()) + '/'
            resolver = RefResolver(base_uri=base_uri, referrer=schema)

            Draft7Validator.check_schema(schema) # Check if schema itself is valid
            validate(instance=self.raw_config, schema=schema, resolver=resolver)
            logger.info("JSONSchema validation successful (raw_config against schema file).")

        except FileNotFoundError:
            logger.warning(f"JSONSchema file not found at {self.schema_file_path}. JSONSchema validation skipped.")
        except Exception as e: # Catches jsonschema.exceptions.SchemaError, jsonschema.exceptions.ValidationError
            logger.error(f"JSONSchema validation error: {e}")


    def get_setting(self, *keys: str, symbol_context: Optional[str] = None, default_value_to_return: Any = None) -> Any:
        # Kept as original for now, operating on self.raw_config
        # Future: This method will be updated to primarily use self.eots_config_model
        # and perhaps fallback to raw_config or provide a specific method for raw access.

        config_source = self.raw_config

        # Try symbol-specific override first
        if symbol_context:
            symbol_overrides = config_source.get("symbol_specific_overrides", {}).get(symbol_context)
            if symbol_overrides:
                current_level = symbol_overrides
                found_in_symbol = True
                try:
                    for key_part in keys: current_level = current_level[key_part]
                    return current_level
                except (KeyError, TypeError): found_in_symbol = False

            # Try "DEFAULT" symbol profile if specific symbol override not found or parameter missing
            default_symbol_profile = config_source.get("symbol_specific_overrides", {}).get("DEFAULT")
            if default_symbol_profile:
                current_level = default_symbol_profile
                try:
                    for key_part in keys: current_level = current_level[key_part]
                    return current_level
                except (KeyError, TypeError): pass

        # Fallback to global setting
        current_level = config_source
        try:
            for key_part in keys: current_level = current_level[key_part]
            return current_level
        except (KeyError, TypeError):
            # Schema default lookup was part of old get_setting, but Pydantic handles defaults at model load.
            # If Pydantic model is not used, this raw get_setting won't automatically fill schema defaults.
            # For now, just return the provided default_value_to_return.
            return default_value_to_return

    def get_resolved_path_setting(self, *keys: str, symbol_context: Optional[str] = None, default_value_to_return: Optional[str] = None) -> Optional[Path]:
        relative_path_str = self.get_setting(*keys, symbol_context=symbol_context, default_value_to_return=default_value_to_return)

        if relative_path_str is None or not isinstance(relative_path_str, str):
            return None

        if not self.project_root:
            logger.error("Project root not determined. Cannot resolve path accurately. Returning relative path.")
            return Path(relative_path_str)

        # Paths in config are assumed to be relative to 'elite_options_system_v2_5' directory
        # which is a child of the project_root.
        base_path_for_config_paths = self.project_root / 'elite_options_system_v2_5'

        # Check if path is already absolute
        path_obj = Path(relative_path_str)
        if path_obj.is_absolute():
            return path_obj.resolve()
        else:
            return (base_path_for_config_paths / relative_path_str).resolve()

    def get_project_root(self) -> Optional[Path]: return self.project_root
    def get_config_file_path(self) -> Path: return self.config_file_path
    def get_eots_config_model(self) -> Optional[EOTSConfigV2_5]:
        if not PYDANTIC_SCHEMAS_AVAILABLE:
            logger.warning("Cannot return EOTSConfigV2_5 model: Pydantic schemas were not available or failed to import.")
            return None
        return self.eots_config_model
