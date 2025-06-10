import pytest
import pandas as pd
from datetime import datetime, date # Added date
from unittest.mock import patch, MagicMock
from pydantic import ValidationError
import logging

test_logger = logging.getLogger("TestFetchIntegrationReRun") # Changed logger name
test_logger.setLevel(logging.INFO)
# handler = logging.StreamHandler() # For local debug
# test_logger.addHandler(handler)

try:
    from pydantic_models_v2_5 import (
        OptionContractRawV2_5,
        UnderlyingDataRawAPIV2_5,
        TradierQuoteV2_5,
        TradierOHLCVBarV2_5
    )
    from data_management.fetcher_convexvalue_v2_5 import ConvexValueDataFetcherV2_5
    from data_management.fetcher_tradier_v2_5 import TradierDataFetcherV2_5
except ImportError as e:
    test_logger.error(f"ImportError in test_fetcher_integration: {e}")
    # Attempt path adjustment for subtask environment
    import sys, os
    current_dir = os.path.dirname(os.path.abspath(__file__)) # .../tests
    project_root_eots = os.path.dirname(current_dir) # .../elite_options_system_v2_5
    if project_root_eots not in sys.path:
        sys.path.insert(0, project_root_eots)
    try:
        from pydantic_models_v2_5 import (
            OptionContractRawV2_5, UnderlyingDataRawAPIV2_5,
            TradierQuoteV2_5, TradierOHLCVBarV2_5
        )
        from data_management.fetcher_convexvalue_v2_5 import ConvexValueDataFetcherV2_5
        from data_management.fetcher_tradier_v2_5 import TradierDataFetcherV2_5
        test_logger.info("Successfully re-imported modules after sys.path adjustment.")
    except ImportError as e2:
        test_logger.error(f"Secondary ImportError in test_fetcher_integration: {e2}")
        pytest.skip("Skipping fetcher integration tests: Could not import necessary modules.", allow_module_level=True)


@pytest.fixture
def mock_config_manager_cv_fetcher_test_rerun(): # Changed fixture name
    class MockCM:
        def get_setting(self, *keys, default_value_to_return=None, symbol_context=None):
            cv_base_path = ("data_fetcher_settings", "convexvalue")
            cred_path = cv_base_path + ("api_credentials",)
            fetch_cfg_path = cv_base_path + ("fetch_config",)
            api_fields_path = ("metrics_io_params", "convexvalue_fields")
            col_map_base = ("column_name_mappings", "convexvalue_internal")

            if keys == cred_path + ("email_env_var",): return "CONVEX_EMAIL"
            if keys == cred_path + ("password_env_var",): return "CONVEX_PASSWORD"
            if keys == cred_path + ("environment",): return "dev"
            if keys == fetch_cfg_path + ("max_retries",): return 1
            if keys == fetch_cfg_path + ("base_retry_delay_seconds",): return 0.01
            if keys == fetch_cfg_path + ("max_retry_delay_seconds",): return 0.02
            if keys == fetch_cfg_path + ("inter_call_delay_seconds",): return 0.0
            if keys == fetch_cfg_path + ("default_dte_range",): return [0]
            if keys == fetch_cfg_path + ("default_price_range_pct",): return 0.05

            if keys == api_fields_path + ("get_und_params",):
                return ["price", "uVolatilityCv", "gibRawCv"]
            if keys == api_fields_path + ("get_chain_additional_params",):
                # This order is critical: 1st value in sample data list maps to 'optionPrice', 2nd to 'delta'
                return ["optionPrice", "delta"]
            if keys == api_fields_path + ("get_chain_prefix_params",):
                return ["option_symbol_api_raw_cv", "expiration_days_from_epoch_calc", "strike", "opt_kind"]

            if keys == col_map_base + ("expiration_col_name",): return "expiration_days_from_epoch_calc"
            if keys == col_map_base + ("strike_col_name",): return "strike"
            if keys == col_map_base + ("option_kind_col_name",): return "opt_kind"
            if keys == col_map_base + ("underlying_symbol_col_name",): return "underlying_symbol"
            if keys == col_map_base + ("underlying_price_col_name",): return "price"
            if keys == ("strategy_settings", "contract_multiplier_default_value"): return 100.0
            if keys == ("column_name_mappings", "input_chain_fields", "multiplier_col"): return "multiplier"
            return default_value_to_return
        def get_resolved_path_setting(self, *args, **kwargs): return None
    return MockCM()

sample_cv_underlying_api_data_rerun = {"data": [[["SPY", 450.10, 0.18, -500e9]]]}
# Values order: 10.50 for "optionPrice", 0.55 for "delta"
sample_cv_option_row_data_rerun = [
    "SPY241220C00450000", 19700.0, 450.0, "call",  # Prefix part
    10.50,  # This value for "optionPrice" (1st in additional_params)
    0.55    # This value for "delta" (2nd in additional_params)
]

@patch('data_management.fetcher_convexvalue_v2_5.ConvexApi')
def test_cv_fetcher_option_model_df_creation_and_validation_rerun(MockConvexApi, mock_config_manager_cv_fetcher_test_rerun): # Renamed test
    test_logger.info("Test Re-run: Validating DataFrame creation and OptionContractRawV2_5 from CV Fetcher output.")

    mock_api_instance = MockConvexApi.return_value
    mock_api_instance.get_und.return_value = sample_cv_underlying_api_data_rerun
    mock_api_instance.get_chain_as_rows.return_value = [sample_cv_option_row_data_rerun]

    fetcher = ConvexValueDataFetcherV2_5(mock_config_manager_cv_fetcher_test_rerun)
    fetcher.api = mock_api_instance

    df_opts, _ = fetcher.fetch_options_chain_and_underlying("SPY")
    assert not df_opts.empty, "Fetcher returned empty options DataFrame"

    test_logger.info("DEBUG_DF_CREATION_RERUN: Relevant columns from created DataFrame (df_opts):")
    if 'optionPrice' in df_opts.columns and 'delta' in df_opts.columns:
        print("\nDEBUG_DF_CREATION_OUTPUT:") # Ensure this print happens
        print(df_opts[['optionPrice', 'delta']].head(1).to_string())
        print("---------------------------\n")
    else:
        test_logger.warning("DEBUG_DF_CREATION_RERUN: 'optionPrice' or 'delta' column not found in df_opts!")
        print("\nDEBUG_DF_CREATION_OUTPUT (all columns):") # Ensure this print happens
        print(df_opts.head(1).to_string())
        print("---------------------------\n")

    first_option_row_dict = df_opts.iloc[0].to_dict()
    test_logger.info(f"DEBUG_DF_ROW_DICT_RERUN: DataFrame row to dict: {first_option_row_dict}")

    assert first_option_row_dict.get('optionPrice') == 10.50, f"DataFrame column 'optionPrice' should be 10.50, got {first_option_row_dict.get('optionPrice')}"
    assert first_option_row_dict.get('delta') == 0.55, f"DataFrame column 'delta' should be 0.55, got {first_option_row_dict.get('delta')}"

    option_pydantic_input = {
        'strike': first_option_row_dict.get('strike'),
        'opt_kind': first_option_row_dict.get('opt_kind'),
        'price': first_option_row_dict.get('optionPrice'),
        'delta': first_option_row_dict.get('delta')
    }

    full_model_field_names = [
        'option_symbol_api_raw_cv', 'expiration_days_from_epoch_calc', 'oi',
        'volatility', 'multiplier', 'gamma', 'theta', 'vega', 'charm',
        'vanna', 'vomma', 'dxoi', 'gxoi', 'vxoi', 'txoi', 'charmxoi', 'vannaxoi',
        'vommaxoi', 'dxvolm', 'gxvolm', 'vxvolm', 'txvolm', 'charmxvolm', 'vannaxvolm', 'vommaxvolm',
        'valuebs_5m', 'volmbs_5m', 'valuebs_15m', 'volmbs_15m',
        'bid', 'ask', 'total_volume', 'smv_vol', 'additional_cv_fields'
    ]
    for f_name in full_model_field_names:
        df_col_name = f_name
        if f_name == 'volatility': df_col_name = 'optionImpliedVol' # Map Pydantic field to expected DF column if different
        elif f_name == 'dxoi': df_col_name = 'deltaTimesOi'
        elif f_name == 'gxoi': df_col_name = 'gammaTimesOi'
        # Add other explicit alias mappings if the DF column name is different from Pydantic field name
        # For this test, we are primarily concerned with 'price' and 'delta' which are handled above.
        # Other fields will be None if their corresponding DF columns (e.g. 'oi', 'optionImpliedVol') are not in first_option_row_dict
        # because the simplified sample_cv_option_row_data_rerun only provides data for optionPrice and delta.

        if df_col_name in first_option_row_dict: # Check if the source DF column exists
            option_pydantic_input[f_name] = first_option_row_dict.get(df_col_name)
        elif f_name not in option_pydantic_input:
             option_pydantic_input[f_name] = None

    option_pydantic_input_cleaned = {k:v for k,v in option_pydantic_input.items() if k in OptionContractRawV2_5.model_fields}
    if 'additional_cv_fields' not in option_pydantic_input_cleaned: # Ensure default_factory field is present
        option_pydantic_input_cleaned['additional_cv_fields'] = {}


    test_logger.info(f"DEBUG_PYDANTIC_INPUT_RERUN: Input dict for OptionContractRawV2_5 validation: {option_pydantic_input_cleaned}")

    try:
        option_model = OptionContractRawV2_5.model_validate(option_pydantic_input_cleaned)
        assert option_model.strike == 450.0, f"Strike expected 450.0, got {option_model.strike}"
        assert option_model.opt_kind == "call", f"OptKind expected call, got {option_model.opt_kind}"
        assert option_model.price == 10.50, f"Price expected 10.50, got {option_model.price}"
        assert option_model.delta == 0.55, f"Delta expected 0.55, got {option_model.delta}"

        assert option_model.oi is None, f"Expected oi to be None, got {option_model.oi}" # Was not in simplified data
        assert option_model.gamma is None, f"Expected gamma to be None, got {option_model.gamma}" # Not in simplified
        assert option_model.volatility is None # Not in simplified
        test_logger.info("CV Fetcher Re-run: FULL OptionContractRawV2_5 from SUBSET DataFrame row validated successfully.")
    except ValidationError as e:
        pytest.fail(f"CV Fetcher Re-run: FULL OptionContractRawV2_5 validation failed. Error: {e}\nInput Dict: {option_pydantic_input_cleaned}\nOriginal DF Row: {first_option_row_dict}")
