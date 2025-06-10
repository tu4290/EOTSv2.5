import pytest
from pydantic import ValidationError
import logging
from datetime import datetime, date # Ensure date is imported for TradierOHLCVBarV2_5 if it were fully defined

# Setup logger for this test file
logger = logging.getLogger("TestDirectInstantiation")
logger.setLevel(logging.INFO)

try:
    from pydantic_models_v2_5 import OptionContractRawV2_5
except ImportError as e:
    logger.error(f"Failed to import OptionContractRawV2_5 for focused test: {e}")
    import sys, os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_eots = os.path.dirname(current_dir)
    if project_root_eots not in sys.path:
        sys.path.insert(0, project_root_eots)
    try:
        from pydantic_models_v2_5 import OptionContractRawV2_5
        logger.info("Successfully imported OptionContractRawV2_5 after sys.path adjustment.")
    except ImportError as e2:
        logger.error(f"Failed to import OptionContractRawV2_5 even after sys.path adjustment: {e2}")
        pytest.skip("Skipping direct instantiation test: Could not import OptionContractRawV2_5.", allow_module_level=True)


def test_direct_option_contract_instantiation_field_names():
    '''Test direct instantiation using Python field names as keys.'''
    data = {
        'strike': 450.0,
        'opt_kind': 'call',
        'price': 10.50,  # Key is 'price' (Python field name)
        'delta': 0.55    # Key is 'delta' (Python field name)
    }
    logger.info(f"Direct test input data (field names): {data}")
    try:
        model = OptionContractRawV2_5.model_validate(data)
        logger.info(f"Model after validation (field names): strike={model.strike}, opt_kind={model.opt_kind}, price={model.price}, delta={model.delta}")
        assert model.strike == 450.0
        assert model.opt_kind == 'call'
        assert model.price == 10.50, f"Expected model.price to be 10.50, got {model.price}"
        assert model.delta == 0.55, f"Expected model.delta to be 0.55, got {model.delta}"
    except ValidationError as e:
        pytest.fail(f"Direct instantiation with field names failed: {e}\nData: {data}")

def test_direct_option_contract_instantiation_alias_names():
    '''Test direct instantiation using alias names as keys for aliased fields.'''
    data = {
        'strike': 460.0,
        'opt_kind': 'put',
        'optionPrice': 12.50,    # Key is 'optionPrice' (alias for 'price')
        'delta': -0.45           # Key is 'delta' (model field name; also its own alias in simplified model)
    }
    logger.info(f"Direct test input data (alias names where applicable): {data}")
    try:
        model = OptionContractRawV2_5.model_validate(data)
        logger.info(f"Model after validation (alias names): strike={model.strike}, opt_kind={model.opt_kind}, price={model.price}, delta={model.delta}")
        assert model.strike == 460.0
        assert model.opt_kind == 'put'
        assert model.price == 12.50, f"Expected model.price to be 12.50 (from alias 'optionPrice'), got {model.price}"
        assert model.delta == -0.45, f"Expected model.delta to be -0.45, got {model.delta}"
    except ValidationError as e:
        pytest.fail(f"Direct instantiation with alias names failed: {e}\nData: {data}")
