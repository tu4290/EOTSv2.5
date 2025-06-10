# elite_options_system_v2_5/tests/test_pydantic_raw_data_models_v2_5.py

print("Test script started") # Debug print

import pytest
from pydantic import ValidationError, BaseModel # Ensure BaseModel is imported for fallback if needed
from datetime import datetime, date

# Assuming pydantic_models_v2_5.py is in the parent directory (elite_options_system_v2_5)
# Adjust import if structure is different or if using package-style imports
# For subtask environment, direct import might work if PYTHONPATH is set up by the worker
try:
    # This assumes that the 'elite_options_system_v2_5' directory itself is in PYTHONPATH
    # or pytest is run from the parent of 'elite_options_system_v2_5'
    # For the subtask environment, running from repo root (/app), this should work if
    # pydantic_models_v2_5.py is in /app/elite_options_system_v2_5/
    from pydantic_models_v2_5 import (
        OptionContractRawV2_5,
        UnderlyingDataRawAPIV2_5,
        TradierQuoteV2_5,
        TradierOHLCVBarV2_5,
        UnderlyingDataCombinedV2_5,
        RawDataBundleV2_5,
        EOTSBaseModel # For testing base config if needed
    )
    print("Initial imports successful") # Debug print
except ImportError as e:
    print(f"Initial import failed: {e}") # Debug print
    # Fallback for local testing if path isn't set up.
    # The subtask should ideally handle the Python path correctly.
    # If this block is hit in the subtask, it means the primary import strategy failed.
    import sys, os
    # Construct the path to the 'elite_options_system_v2_5' directory
    # Assuming this test file is in 'elite_options_system_v2_5/tests/'
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir_eots_v2_5 = os.path.dirname(current_dir) # This should be 'elite_options_system_v2_5'

    # Add 'elite_options_system_v2_5' parent to sys.path to allow 'from pydantic_models_v2_5 import ...'
    # This is equivalent to 'elite_options_system_v2_5' being a top-level package.
    # For the test  to work, the directory containing
    #  (which is ) needs to be in sys.path.
    if project_dir_eots_v2_5 not in sys.path:
       sys.path.insert(0, project_dir_eots_v2_5)

    # Try importing again after path adjustment
    try:
        from pydantic_models_v2_5 import (
            OptionContractRawV2_5, UnderlyingDataRawAPIV2_5, TradierQuoteV2_5,
            TradierOHLCVBarV2_5, UnderlyingDataCombinedV2_5, RawDataBundleV2_5, EOTSBaseModel
        )
        print("Fallback imports successful") # Debug print
    except ImportError as e2:
        print(f"Fallback import failed: {e2}") # Debug print
        pytest.skip(f"Skipping Pydantic model tests: Could not import models even after path adjust. Primary error: {e}, Fallback error: {e2}", allow_module_level=True)


# --- Test OptionContractRawV2_5 ---

def test_option_contract_raw_valid_data():
    data = {
        "optionSymbolApiRawCv": "SPY241220C00500000",
        "expirationDaysFromEpochCalc": 19700.0,
        "strike": 500.0,
        "optKind": "call",
        "oi": 1200.0,
        "optionPrice": 10.50,
        "optionImpliedVol": 0.225,
        "multiplier": 100.0,
        "delta": 0.55,
        "gamma": 0.015,
        "theta": -0.08,
        "vega": 0.25,
        "charm": 0.005,
        "vanna": 0.03,
        "vomma": 0.002,
        "deltaTimesOi": 660.0,
        "gammaTimesOi": 18.0,
        "valueBuySell5m": 50000.0,
        "volumeBuySell5m": 250.0,
        "additionalCvFields": {"someKey": "someValue"}
    }
    contract = OptionContractRawV2_5(**data)
    assert contract.option_symbol_api_raw_cv == "SPY241220C00500000"
    assert contract.strike == 500.0
    assert contract.opt_kind == "call"
    assert contract.oi == 1200.0
    assert contract.price == 10.50
    assert contract.volatility == 0.225
    assert contract.delta == 0.55
    assert contract.dxoi == 660.0
    assert contract.valuebs_5m == 50000.0
    assert contract.additional_cv_fields["someKey"] == "someValue"
    assert contract.vomma == 0.002

def test_option_contract_raw_minimal_data():
    contract = OptionContractRawV2_5()
    assert contract.strike is None
    assert contract.oi is None
    assert contract.price is None
    assert contract.additional_cv_fields == {}


def test_option_contract_raw_invalid_type():
    data = {"strike": "not-a-float"}
    with pytest.raises(ValidationError):
        OptionContractRawV2_5(**data)

def test_option_contract_raw_extra_fields_ignored():
    data = {
        "strike": 500.0,
        "optKind": "put",
        "extraFieldNotInModel": "should_be_ignored"
    }
    contract = OptionContractRawV2_5(**data)
    assert contract.strike == 500.0
    assert not hasattr(contract, "extraFieldNotInModel")

def test_option_contract_raw_alias_population():
    data_with_aliases = {
        "optionSymbolApiRawCv": "XYZ",
        "optionPrice": 1.0,
        "optionImpliedVol": 0.30,
        "deltaTimesOi": 50.0,
        "valueBuySell5m": 1000.0
    }
    contract = OptionContractRawV2_5(**data_with_aliases)
    assert contract.price == 1.0
    assert contract.volatility == 0.30
    assert contract.dxoi == 50.0
    assert contract.valuebs_5m == 1000.0


# --- Test UnderlyingDataRawAPIV2_5 ---

def test_underlying_data_raw_api_valid():
    data = {
        "symbol": "SPY",
        "fetchTimestampParserCv": datetime.now(),
        "apiResponseSymbolUndCv": "SPY",
        "price": 450.75,
        "uVolatilityCv": 0.185,
        "additionalUndCvFields": {"gibActual": -100e9, "anotherKey": 123}
    }
    model = UnderlyingDataRawAPIV2_5(**data)
    assert model.symbol == "SPY"
    assert isinstance(model.fetch_timestamp_parser_cv, datetime)
    assert model.price == 450.75
    assert model.u_volatility_cv == 0.185 # Corrected attribute name
    assert model.additional_und_cv_fields["gibActual"] == -100e9

def test_underlying_data_raw_api_required_fields():
    with pytest.raises(ValidationError) as excinfo:
        UnderlyingDataRawAPIV2_5(price=450.0)
    assert "symbol" in str(excinfo.value).lower()

    model = UnderlyingDataRawAPIV2_5(symbol="QQQ")
    assert model.symbol == "QQQ"
    assert model.price is None
    assert model.additional_und_cv_fields == {}


# --- Test TradierQuoteV2_5 ---
def test_tradier_quote_valid():
    now = datetime.now()
    data = {
        "symbol": "AAPL",
        "description": "Apple Inc.",
        "last": 170.50,
        "changePercentage": 1.25,
        "volume": 50000000,
        "tradeDate": now,
        "rootSymbols": "AAPL,AAPL2"
    }
    quote = TradierQuoteV2_5(**data)
    assert quote.symbol == "AAPL"
    assert quote.last == 170.50
    assert quote.change_percentage == 1.25
    assert quote.trade_date == now
    assert quote.root_symbols == "AAPL,AAPL2"

def test_tradier_quote_invalid_type():
    with pytest.raises(ValidationError):
        TradierQuoteV2_5(symbol="MSFT", last="not-a-price")


# --- Test TradierOHLCVBarV2_5 ---
def test_tradier_ohlcv_bar_valid():
    data = {"date": "2023-10-20", "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0, "volume": 1234567}
    bar = TradierOHLCVBarV2_5(**data)
    assert bar.date == date(2023, 10, 20)
    assert bar.open == 150.0
    assert bar.volume == 1234567

def test_tradier_ohlcv_bar_invalid_date():
    with pytest.raises(ValidationError):
        TradierOHLCVBarV2_5(date="not-a-date", open=1, high=2, low=0, close=1, volume=100)

def test_tradier_ohlcv_bar_missing_required():
    with pytest.raises(ValidationError):
        TradierOHLCVBarV2_5(date="2023-10-20", high=2, low=0, close=1, volume=100)


# --- Test UnderlyingDataCombinedV2_5 ---
def test_underlying_data_combined_valid():
    cv_time = datetime.now()
    tradier_time = datetime.now()
    data = {
        "symbol": "SPY",
        "fetchTimestampPayloadCv": cv_time,
        "fetchTimestampPayloadTradier": tradier_time,
        "price": 4500.25,
        "uVolatilityCv": 0.15,
        "additionalUndCvFields": {"key1": "val1"},
        "tradierOpen": 4500.00,
        "tradierIv5ApproxSmvAvg": 0.145,
        "multiplier": 100.0
    }
    model = UnderlyingDataCombinedV2_5(**data)
    assert model.symbol == "SPY"
    assert model.price == 4500.25
    assert model.u_volatility_cv == 0.15
    assert model.tradier_iv5_approx_smv_avg == 0.145
    assert model.multiplier == 100.0
    assert model.additional_und_cv_fields["key1"] == "val1"


# --- Test RawDataBundleV2_5 ---
def test_raw_data_bundle_valid():
    now = datetime.now()
    option_dict1 = {"strike": 100.0, "optKind": "call", "optionPrice": 1.0}
    underlying_dict = {"symbol": "TEST", "price": 100.0}

    data = {
        "symbol": "TEST",
        "rawOptionsDfData": [option_dict1],
        "rawUnderlyingDictCombinedData": underlying_dict,
        "fetchTimestampBundleMaster": now,
        "errorDetailsCv": None,
        "errorDetailsTradier": "Some Tradier Error"
    }
    bundle = RawDataBundleV2_5(**data)
    assert bundle.symbol == "TEST"
    assert len(bundle.raw_options_df_data) == 1
    assert bundle.raw_options_df_data[0]["strike"] == 100.0
    assert bundle.raw_underlying_dict_combined_data["price"] == 100.0
    assert bundle.fetch_timestamp_bundle_master == now
    assert bundle.error_details_tradier == "Some Tradier Error"

def test_raw_data_bundle_empty_options():
    underlying_dict = {"symbol": "TEST", "price": 100.0}
    bundle = RawDataBundleV2_5(
        symbol="TEST",
        raw_options_df_data=[],
        raw_underlying_dict_combined_data=underlying_dict
    )
    assert bundle.symbol == "TEST"
    assert len(bundle.raw_options_df_data) == 0


# --- Test EOTSBaseModel Config ---
class _SampleModelForExtraFieldsTest(EOTSBaseModel): # Renamed to avoid pytest collection warning
    known_field: str

def test_eots_base_model_extra_fields_ignored():
    data = {"known_field": "value", "unknown_extra_field": "should_be_ignored"}
    model = _SampleModelForExtraFieldsTest(**data)
    assert model.known_field == "value"
    assert not hasattr(model, "unknown_extra_field")


def test_option_contract_raw_focused_explicit_alias():
    # Test with explicit aliases and without global alias_generator
    # Input keys here match the explicit Field(alias='...') in the model
    data = {
        'optionSymbolApiRawCv': 'SPY_C_450',
        'expirationDaysFromEpochCalc': 19800.0,
        'strike': 450.0,
        'optKind': 'call',
        'oi': 100.0,
        'optionPrice': 2.5,        # Alias for 'price'
        'optionImpliedVol': 0.20,  # Alias for 'volatility'
        'multiplier': 100.0,       # Alias for 'multiplier'
        'delta': 0.5,              # Alias for 'delta'
        'gamma': 0.02,             # Alias for 'gamma'
        'theta': -0.05,            # Alias for 'theta'
        'vega': 0.10,              # Alias for 'vega'
        'deltaTimesOi': 50.0,      # Alias for 'dxoi'
        'gammaTimesOi': 2.0,       # Alias for 'gxoi'
        'valueBuySell5m': 10000.0, # Alias for 'valuebs_5m'
        'volumeBuySell5m': 50.0    # Alias for 'volmbs_5m'
        # charm, vanna, vomma have Field(alias=...) so their camelCase versions would be expected here
        # For this test, we are providing keys that match the explicit aliases.
    }
    contract = OptionContractRawV2_5(**data)
    assert contract.option_symbol_api_raw_cv == 'SPY_C_450'
    assert contract.strike == 450.0
    assert contract.opt_kind == 'call'
    assert contract.oi == 100.0
    assert contract.price == 2.5, f'Price expected 2.5, got {contract.price}'
    assert contract.volatility == 0.20, f'Volatility expected 0.20, got {contract.volatility}'
    assert contract.multiplier == 100.0
    assert contract.delta == 0.5
    assert contract.gamma == 0.02
    assert contract.theta == -0.05
    assert contract.vega == 0.10
    assert contract.dxoi == 50.0, f'DXOI expected 50.0, got {contract.dxoi}'
    assert contract.gxoi == 2.0, f'GXOI expected 2.0, got {contract.gxoi}'
    assert contract.valuebs_5m == 10000.0, f'ValueBS5m expected 10000.0, got {contract.valuebs_5m}'
    assert contract.volmbs_5m == 50.0, f'VolBS5m expected 50.0, got {contract.volmbs_5m}'

    # Test with python field names as keys
    data_field_names = {
        'option_symbol_api_raw_cv': 'SPY_P_440',
        'expiration_days_from_epoch_calc': 19801.0,
        'strike': 440.0,
        'opt_kind': 'put',
        'oi': 200.0,
        'price': 3.5,
        'volatility': 0.22,
        'multiplier': 100.0,
        'delta': -0.4,
        'gamma': 0.025,
        'theta': -0.06,
        'vega': 0.12,
        'dxoi': -80.0,
        'gxoi': 5.0,
        'valuebs_5m': -5000.0,
        'volmbs_5m': -20.0
    }
    contract_fn = OptionContractRawV2_5(**data_field_names)
    assert contract_fn.option_symbol_api_raw_cv == 'SPY_P_440'
    assert contract_fn.strike == 440.0
    assert contract_fn.opt_kind == 'put'
    assert contract_fn.oi == 200.0
    assert contract_fn.price == 3.5, f'Price (field name) expected 3.5, got {contract_fn.price}'
    assert contract_fn.volatility == 0.22, f'Volatility (field name) expected 0.22, got {contract_fn.volatility}'
    assert contract_fn.multiplier == 100.0
    assert contract_fn.delta == -0.4
    assert contract_fn.gamma == 0.025
    assert contract_fn.theta == -0.06
    assert contract_fn.vega == 0.12
    assert contract_fn.dxoi == -80.0, f'DXOI (field name) expected -80.0, got {contract_fn.dxoi}'
    assert contract_fn.gxoi == 5.0, f'GXOI (field name) expected 5.0, got {contract_fn.gxoi}'
    assert contract_fn.valuebs_5m == -5000.0, f'ValueBS5m (field name) expected -5000.0, got {contract_fn.valuebs_5m}'
    assert contract_fn.volmbs_5m == -20.0, f'VolBS5m (field name) expected -20.0, got {contract_fn.volmbs_5m}'
