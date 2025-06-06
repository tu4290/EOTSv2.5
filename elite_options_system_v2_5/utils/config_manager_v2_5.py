import json
import os
from jsonschema import validate, RefResolver, Draft7Validator
from pathlib import Path

class ConfigManagerV2_5:
    def __init__(self, config_path='config_v2_5.json', schema_path='config.schema.v2.5.json', project_root_marker='README.md'):
        self.project_root = self._find_project_root(start_path=Path(__file__).parent, marker=project_root_marker)
        if not self.project_root:
            # Fallback if marker not found, assuming script is run from within project structure
            # Adjust this fallback as necessary for your specific project structure
            self.project_root = Path(__file__).resolve().parent.parent
            print(f"Warning: Project root marker '{project_root_marker}' not found. Using fallback root: {self.project_root}")
            # Attempt to find it from the elite_options_system_v2_5 directory if possible
            if 'elite_options_system_v2_5' in str(Path(__file__)):
                 self.project_root = Path(str(Path(__file__).resolve()).split('elite_options_system_v2_5')[0])
                 print(f"Adjusted project root based on 'elite_options_system_v2_5' in path: {self.project_root}")


        self.config_file_path = self.project_root / 'elite_options_system_v2_5' / config_path
        self.schema_file_path = self.project_root / 'elite_options_system_v2_5' / schema_path

        self.config = self._load_config()
        self._validate_config()

    def _find_project_root(self, start_path: Path, marker: str) -> Path | None:
        current_path = start_path.resolve()
        while current_path != current_path.parent: # Stop at the root of the filesystem
            if (current_path / marker).exists():
                return current_path
            if 'elite_options_system_v2_5' in str(current_path) and not (current_path.parent / marker).exists():
                 # Specific EOTS case: if we are inside and can't find marker, go to parent of eots_v2_5
                 # This is a heuristic for the specific project structure.
                 parts = current_path.parts
                 if 'elite_options_system_v2_5' in parts:
                     eots_index = parts.index('elite_options_system_v2_5')
                     if eots_index > 0:
                         # project_root should be the parent of elite_options_system_v2_5
                         # but if marker is not there, this logic is a fallback.
                         # For now, let it return None if marker isn't found at higher levels.
                         pass
            current_path = current_path.parent
        # Check filesystem root as well if marker not found
        if (current_path / marker).exists():
            return current_path
        return None


    def _load_config(self):
        try:
            with open(self.config_file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: Configuration file not found at {self.config_file_path}")
            # Create a minimal default config if not found
            # This should ideally be based on the schema's defaults
            return {"system_settings": {"default_symbol": "SPY"}}
        except json.JSONDecodeError:
            raise ValueError(f"Error: Invalid JSON in configuration file: {self.config_file_path}")

    def _validate_config(self):
        try:
            with open(self.schema_file_path, 'r') as f:
                schema = json.load(f)

            # For resolving local $ref in schema if any (e.g., to definitions)
            # Assumes schema and references are in the same directory or use resolvable paths
            resolver_path = 'file://' + str(self.schema_file_path.parent.resolve()) + '/'
            resolver = RefResolver(base_uri=resolver_path, referrer=schema)

            Draft7Validator.check_schema(schema) # Check if schema itself is valid
            validate(instance=self.config, schema=schema, resolver=resolver)
            print("Configuration is valid against the schema.")

        except FileNotFoundError:
            # Allow to proceed if schema is not found, but warn.
            print(f"Warning: Schema file not found at {self.schema_file_path}. Configuration validation skipped.")
        except Exception as e:
            # Catch jsonschema.exceptions.SchemaError for invalid schema or other validation errors
            raise ValueError(f"Configuration validation error: {e}")


    def get_setting(self, *keys, symbol_context=None):
        # Start with global config
        current_level_config = self.config

        # Try symbol-specific override first
        if symbol_context and 'symbol_specific_overrides' in current_level_config:
            symbol_overrides = current_level_config.get('symbol_specific_overrides', {}).get(symbol_context)
            if symbol_overrides:
                try:
                    value = symbol_overrides
                    for key in keys:
                        value = value[key]
                    # print(f"Retrieved '{'.'.join(keys)}' for symbol '{symbol_context}': {value}")
                    return value
                except KeyError:
                    pass # Setting not found in symbol-specific, will try DEFAULT or global

        # Try "DEFAULT" symbol profile if specific symbol override not found or parameter missing
        if 'symbol_specific_overrides' in current_level_config:
            default_symbol_profile = current_level_config.get('symbol_specific_overrides', {}).get("DEFAULT")
            if default_symbol_profile:
                try:
                    value = default_symbol_profile
                    for key in keys:
                        value = value[key]
                    # print(f"Retrieved '{'.'.join(keys)}' from 'DEFAULT' symbol profile: {value}")
                    return value
                except KeyError:
                    pass # Setting not found in DEFAULT profile, will try global

        # Fallback to global setting
        try:
            value = current_level_config
            for key in keys:
                value = value[key]
            # print(f"Retrieved '{'.'.join(keys)}' from global settings: {value}")
            return value
        except KeyError:
            # print(f"Warning: Setting '{'.'.join(keys)}' not found in global, DEFAULT, or symbol-specific ('{symbol_context}') configuration.")
            # Optionally, you could raise an error or return a specific default value here.
            # For now, consistent with schema providing defaults, this path might indicate missing mandatory field if schema not used properly
            # or an optional field that is truly absent.
            # Check if the schema has a default for this path - this is complex to implement here directly.
            # The jsonschema validation with default filling happens at load time if schema is well-defined.
            # So, if a key is missing here, it means it wasn't in config and had no schema default, or it's a typo.

            # Try to retrieve default from schema (simplified example, real impl is harder)
            # This is a basic attempt and might not cover all cases or nested defaults well.
            # The `jsonschema.validate` with a `Draft7Validator` that fills defaults is the proper way,
            # meaning `self.config` should already be populated with defaults if they existed in the schema.
            temp_schema = self.config # This should be self.schema if loaded
            current_schema_level = self.get_schema() # Assuming get_schema() returns the loaded schema

            path_to_default = []
            final_key_default = None

            current_s_level = current_schema_level
            try:
                for key_part in keys:
                    if 'properties' in current_s_level and key_part in current_s_level['properties']:
                        current_s_level = current_s_level['properties'][key_part]
                    elif 'patternProperties' in current_s_level: # Handle patternProperties if used for symbol overrides etc.
                        # This is a simplified handling. Real patternProperties logic is more complex.
                        # Assuming the key might match one of the patterns.
                        found_in_pattern = False
                        for pattern, schema_prop in current_s_level['patternProperties'].items():
                            # This check is very basic, regex matching needed for real patterns
                            if key_part in pattern: # Simplistic check
                                current_s_level = schema_prop
                                found_in_pattern = True
                                break
                        if not found_in_pattern:
                             raise KeyError
                    else:
                        raise KeyError # Key not in schema properties path

                if 'default' in current_s_level:
                    # print(f"Retrieved schema default for '{'.'.join(keys)}': {current_s_level['default']}")
                    return current_s_level['default']
            except KeyError:
                # print(f"No schema default found for '{'.'.join(keys)}'.")
                pass

            # print(f"Warning: Setting '{'.'.join(keys)}' not found.") # Final warning if no default either
            raise KeyError(f"Setting '{'.'.join(keys)}' not found in any configuration layer and no schema default applicable/found.")


    def get_resolved_path_setting(self, *keys, symbol_context=None):
        relative_path_str = self.get_setting(*keys, symbol_context=symbol_context)
        # Ensure the path is resolved relative to the project root's sub-directory for the v2.5 system
        # This assumes paths in config are relative to the 'elite_options_system_v2_5' directory itself.
        base_path_for_relative_paths = self.project_root / 'elite_options_system_v2_5'
        return (base_path_for_relative_paths / relative_path_str).resolve()

    def get_project_root(self) -> Path:
        return self.project_root

    def get_config_file_path(self) -> Path:
        return self.config_file_path

    def get_schema(self):
        try:
            with open(self.schema_file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Schema file not found at {self.schema_file_path}")
            return {} # Return empty schema if not found
        except json.JSONDecodeError:
            raise ValueError(f"Error: Invalid JSON in schema file: {self.schema_file_path}")

# Example usage:
if __name__ == '__main__':
    # This assumes config_v2_5.json and config.schema.v2.5.json are in the same directory as this script
    # For proper usage, they should be in the root of the elite_options_system_v2_5 project folder.
    # Adjust paths in ConfigManagerV2_5 constructor if running this example elsewhere.

    # Create dummy config and schema for testing if they don't exist
    # In a real scenario, these files would be properly defined.

    # Determine project root for example (assuming this script is in utils)
    example_project_root = Path(__file__).resolve().parent.parent.parent
    example_config_dir = example_project_root / 'elite_options_system_v2_5'

    example_config_dir.mkdir(parents=True, exist_ok=True)

    example_config_path = example_config_dir / 'config_v2_5.json'
    example_schema_path = example_config_dir / 'config.schema.v2.5.json'

    if not example_config_path.exists():
        with open(example_config_path, 'w') as f:
            json.dump({
                "system_settings": {"default_symbol": "SPY", "log_level": "INFO"},
                "data_fetcher_settings": {
                    "convexvalue_api_key": "YOUR_DUMMY_CV_KEY",
                    "tradier_api_key": "YOUR_DUMMY_TRADIER_KEY"
                },
                "symbol_specific_overrides": {
                    "SPY": {"log_level": "DEBUG"},
                    "AAPL": {"data_fetcher_settings": {
                        "convexvalue_api_key": "AAPL_DUMMY_CV_KEY",
                        "tradier_api_key": "AAPL_DUMMY_TRADIER_KEY"
                    }},
                    "DEFAULT": {"log_level": "WARNING", "some_other_default": 123}
                },
                "paths": {"data_cache_root_dir": "data_cache"} # Ensure this matches later tests
            }, f, indent=4)

    if not example_schema_path.exists():
        with open(example_schema_path, 'w') as f:
            json.dump({
                "type": "object",
                "properties": {
                    "system_settings": {
                        "type": "object",
                        "properties": {
                            "default_symbol": {"type": "string", "default": "QQQ"},
                            "log_level": {"type": "string", "enum": ["INFO", "DEBUG", "WARNING", "ERROR"], "default": "INFO"},
                            "new_setting_with_default": {"type": "integer", "default": 100}
                        },
                        "required": ["default_symbol"]
                    },
                    "data_fetcher_settings": {
                        "type": "object",
                        "properties": {
                            "convexvalue_api_key": {"type": "string"},
                            "tradier_api_key": {"type": "string"}
                        },
                        "required": ["convexvalue_api_key", "tradier_api_key"]
                    },
                    "symbol_specific_overrides": {
                        "type": "object",
                        "patternProperties": {
                            "^[A-Z]+$": {
                                "type": "object",
                                "properties": {
                                    "log_level": {"type": "string", "enum": ["INFO", "DEBUG", "WARNING", "ERROR"]},
                                    "data_fetcher_settings": {
                                        "type": "object",
                                        "properties": {
                                            "convexvalue_api_key": {"type": "string"},
                                            "tradier_api_key": {"type": "string"}
                                        }
                                        # Not requiring keys here, as overrides might be partial
                                    },
                                    "some_other_default": {"type": "integer"}
                                }
                            }
                        }
                    },
                    "paths": {
                        "type": "object",
                        "properties": {
                            "data_cache_root_dir": {"type": "string", "default": "cache_default"} # Ensure this matches
                        }
                    }
                },
                "required": ["system_settings", "data_fetcher_settings"] # Not requiring paths, as it might have all defaults
            }, f, indent=4)

    # When instantiating ConfigManagerV2_5, ensure it can find the project root correctly.
    # If this script is in elite_options_system_v2_5/utils, project_root_marker='README.md'
    # should be in the parent directory of elite_options_system_v2_5.
    # We need to ensure a README.md exists at the intended project root for _find_project_root to work.
    # For this example, let's assume the marker is in the parent of elite_options_system_v2_5
    readme_marker_path = example_project_root / 'README.md'
    if not readme_marker_path.exists():
        with open(readme_marker_path, 'w') as f:
            f.write("# Project README\n")

    config_manager = ConfigManagerV2_5(project_root_marker='README.md') # This will use the files created above

    print(f"Project Root: {config_manager.get_project_root()}")
    print(f"Config File Path: {config_manager.get_config_file_path()}")
    print(f"Schema File Path: {config_manager.schema_file_path}")

    print("\n--- Testing get_setting ---")
    print(f"Global log_level: {config_manager.get_setting('system_settings', 'log_level')}") # Should be INFO
    print(f"SPY log_level: {config_manager.get_setting('system_settings', 'log_level', symbol_context='SPY')}") # Should be DEBUG
    print(f"MSFT log_level (uses DEFAULT): {config_manager.get_setting('system_settings', 'log_level', symbol_context='MSFT')}") # Should be WARNING
    print(f"AAPL tradier_api_key (fallback to global): {config_manager.get_setting('data_fetcher_settings', 'tradier_api_key', symbol_context='AAPL')}")
    print(f"SPY tradier_api_key (fallback to global): {config_manager.get_setting('data_fetcher_settings', 'tradier_api_key', symbol_context='SPY')}")

    # Test retrieving a setting that only exists in DEFAULT
    print(f"MSFT some_other_default: {config_manager.get_setting('some_other_default', symbol_context='MSFT')}") # 123
    # Test retrieving a setting with a schema default but not in config
    print(f"Global new_setting_with_default: {config_manager.get_setting('system_settings', 'new_setting_with_default')}") # Should be 100 (from schema default)

    print("\n--- Testing get_resolved_path_setting ---")
    # This assumes 'data_cache' is relative to 'elite_options_system_v2_5'
    expected_cache_path = (config_manager.get_project_root() / 'elite_options_system_v2_5' / 'data_cache').resolve()
    print(f"Resolved data_cache_root_dir: {config_manager.get_resolved_path_setting('paths', 'data_cache_root_dir')}")
    print(f"Expected data_cache_root_dir: {expected_cache_path}")

    # Test missing key
    try:
        config_manager.get_setting('non_existent_key')
    except KeyError as e:
        print(f"Correctly caught missing key: {e}")

    print("\n--- Testing schema defaults more explicitly ---")
    # The validation process should fill defaults if schema is correctly set up.
    # Let's check a value that should come from schema default directly from the loaded config
    # if it wasn't present in the config file itself.
    # This requires the jsonschema library to be used with default filling,
    # which `validate` does if the schema defines defaults.
    # The current _load_config doesn't explicitly fill defaults if the key is missing.
    # The validation step is where defaults are normally applied by the library.
    # Our get_setting has a fallback to check schema if key is missing after initial load.

    # Re-create a minimal config file that's missing 'new_setting_with_default'
    minimal_config_data = {
        "system_settings": {"default_symbol": "SPY"}, # Missing log_level and new_setting_with_default
        "data_fetcher_settings": {
            "convexvalue_api_key": "YOUR_MINIMAL_CV_KEY",
            "tradier_api_key": "YOUR_MINIMAL_TRADIER_KEY"
        },
         "paths": {} # missing data_cache_root_dir
    }
    with open(example_config_path, 'w') as f:
        json.dump(minimal_config_data, f, indent=4)

    print("Reloading ConfigManager with minimal config to test schema defaults...")
    config_manager_reloaded = ConfigManagerV2_5(project_root_marker='README.md')
    print(f"Reloaded log_level (schema default): {config_manager_reloaded.get_setting('system_settings', 'log_level')}") # INFO from schema
    print(f"Reloaded new_setting_with_default (schema default): {config_manager_reloaded.get_setting('system_settings', 'new_setting_with_default')}") # 100 from schema
    print(f"Reloaded paths.data_cache_root_dir (schema default): {config_manager_reloaded.get_setting('paths', 'data_cache_root_dir')}") # cache_default from schema

    print("\nExample ConfigManagerV2_5 setup complete.")
