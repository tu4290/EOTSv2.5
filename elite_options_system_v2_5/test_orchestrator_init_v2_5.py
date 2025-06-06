# elite_options_system_v2_5/test_orchestrator_init_v2_5.py
# Basic test to check initialization of Orchestrator and its components.

import logging
import sys
from datetime import datetime

# Configure basic logging for the test
logging.basicConfig(stream=sys.stdout, level=logging.INFO, # Changed to INFO for less verbose success
                    format='[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to sys.path to allow imports from elite_options_system_v2_5
# This assumes the test script is run from the root of the 'elite_options_system_v2_5' directory,
# or that the elite_options_system_v2_5 parent is in PYTHONPATH.
# For subtask environment, direct relative imports might work if path is set up.
try:
    from utils.config_manager_v2_5 import ConfigManagerV2_5
    from data_management.fetcher_convexvalue_v2_5 import ConvexValueDataFetcherV2_5
    from data_management.fetcher_tradier_v2_5 import TradierDataFetcherV2_5
    from data_management.historical_data_manager_v2_5 import HistoricalDataManagerV2_5
    # from data_management.performance_tracker_v2_5 import PerformanceTrackerV2_5 # Using Dummy
    from data_management.initial_processor_v2_5 import InitialDataProcessorV2_5
    from core_analytics_engine.metrics_calculator_v2_5 import MetricsCalculatorV2_5 # Actual one
    from core_analytics_engine.ticker_context_analyzer_v2_5 import TickerContextAnalyzerV2_5
    from core_analytics_engine.market_regime_engine_v2_5 import MarketRegimeEngineV2_5
    from core_analytics_engine.key_level_identifier_v2_5 import KeyLevelIdentifierV2_5
    from core_analytics_engine.signal_generator_v2_5 import SignalGeneratorV2_5
    from core_analytics_engine.adaptive_trade_idea_framework_v2_5 import AdaptiveTradeIdeaFrameworkV2_5
    from core_analytics_engine.trade_parameter_optimizer_v2_5 import TradeParameterOptimizerV2_5
    from core_analytics_engine.its_orchestrator_v2_5 import ITSOrchestratorV2_5
    import pandas as pd # For DummyPerformanceTracker
    # from pydantic_models_v2_5 import ... (not directly instantiated here but used by components)
except ImportError as e:
    logger.error(f"Failed to import necessary EOTS V2.5 modules: {e}")
    logger.error("Ensure this test script is run with 'elite_options_system_v2_5' in the Python path or from its root.")
    # Attempt to adjust sys.path for common local test scenario
    # This is often needed if the package structure is elite_options_system_v2_5.utils etc.
    # and the script is run from outside the parent of elite_options_system_v2_5
    import os
    # current_script_dir = os.path.dirname(os.path.abspath(__file__))
    # project_root_candidate = os.path.abspath(os.path.join(current_script_dir, '..')) # Parent of elite_options_system_v2_5
    # if project_root_candidate not in sys.path:
    #    sys.path.insert(0, project_root_candidate)
    # logger.info(f"Attempted to add {project_root_candidate} to sys.path. Current sys.path: {sys.path}")
    # Re-raising to make test fail clearly if imports are still broken
    raise



logger.info("Starting EOTS V2.5 Orchestrator Initialization Test...")

# --- DUMMY/STUB Components (if full ones are too complex for init test) ---
# MetricsCalculatorV2_5 is complex, so InitialProcessorV2_5 takes it.
# We'll use the actual MetricsCalculatorV2_5 but its methods are largely stubs.

class DummyPerformanceTracker: # If PerformanceTracker has complex init
    def __init__(self, cfg): logger.info("DummyPerformanceTracker initialized.")
    def record_recommendation_outcome(self, *args, **kwargs): pass
    def query_performance_data(self, *args, **kwargs): return pd.DataFrame()
    def get_signal_pattern_performance(self, *args, **kwargs): return {}
    def shutdown(self): logger.info("DummyPerformanceTracker shutdown.")


def run_initialization_test():
    config_manager = None
    orchestrator = None
    try:
        # 1. Config Manager
        # Assuming config_v2_5.json and schema are in the same directory or accessible
        # For subtask, assume they are in elite_options_system_v2_5/
        logger.info("Initializing ConfigManagerV2_5...")
        config_manager = ConfigManagerV2_5(
            config_path='config_v2_5.json',
            schema_path='config.schema.v2.5.json',
            project_root_marker='README.md'
        )
        logger.info("ConfigManagerV2_5 initialized successfully.")

        # 2. Initialize Components (Order can matter for dependencies if any beyond config)
        logger.info("Initializing Data Management components...")
        cv_fetcher = ConvexValueDataFetcherV2_5(config_manager)
        tradier_fetcher = TradierDataFetcherV2_5(config_manager)
        hist_data_mgr = HistoricalDataManagerV2_5(config_manager)
        perf_tracker = DummyPerformanceTracker(config_manager)

        logger.info("Initializing Core Analytics Engine components...")
        metrics_calc = MetricsCalculatorV2_5(config_manager, hist_data_mgr)
        init_processor = InitialDataProcessorV2_5(config_manager, metrics_calc)
        ticker_analyzer = TickerContextAnalyzerV2_5(config_manager)
        regime_engine = MarketRegimeEngineV2_5(config_manager)
        key_level_id = KeyLevelIdentifierV2_5(config_manager)
        signal_gen = SignalGeneratorV2_5(config_manager)
        atif_engine = AdaptiveTradeIdeaFrameworkV2_5(config_manager, perf_tracker)
        tpo_engine = TradeParameterOptimizerV2_5(config_manager)

        logger.info("All components initialized individually. Now initializing Orchestrator...")

        # 3. Orchestrator
        orchestrator = ITSOrchestratorV2_5(
            config_manager_v2_5=config_manager,
            convex_value_fetcher_v2_5=cv_fetcher,
            tradier_fetcher_v2_5=tradier_fetcher,
            initial_processor_v2_5=init_processor,
            historical_data_manager_v2_5=hist_data_mgr,
            performance_tracker_v2_5=perf_tracker,
            ticker_context_analyzer_v2_5=ticker_analyzer,
            market_regime_engine_v2_5=regime_engine,
            key_level_identifier_v2_5=key_level_id,
            signal_generator_v2_5=signal_gen,
            adaptive_trade_idea_framework_v2_5=atif_engine,
            trade_parameter_optimizer_v2_5=tpo_engine
        )
        logger.info("ITSOrchestratorV2_5 initialized successfully!")

    except ImportError:
        logger.critical("Failed due to ImportErrors already logged during module loading. Check paths and dependencies.")
        return False # Test fails
    except Exception as e:
        logger.error(f"An error occurred during the initialization test: {e}", exc_info=True)
        return False
    finally:
        if orchestrator and hasattr(orchestrator, 'shutdown'):
            logger.info("Shutting down orchestrator...")
            orchestrator.shutdown()
        # Individual components can also have shutdown methods if they manage resources
        logger.info("Initialization test finished.")
    return True

if __name__ == "__main__":
    logger.info("=====================================================================")
    logger.info("= Running EOTS V2.5 Orchestrator Initialization Test Script =")
    logger.info("=====================================================================")

    # This test assumes it's run from the repository root, and python can find
    # the elite_options_system_v2_5 package and its modules.
    # e.g., by having the parent of elite_options_system_v2_5 in PYTHONPATH,
    # or by running as: python -m elite_options_system_v2_5.test_orchestrator_init_v2_5
    # The subtask environment likely handles this by setting current working directory to repo root.
    # ConfigManagerV2_5 internally prepends "elite_options_system_v2_5/" to config/schema paths
    # when project_root_marker='README.md' is used from repo root.

    # Ensure required packages are installed (pydantic, pandas, numpy, jsonschema, requests)
    # This is usually handled by a requirements.txt in a real project.
    # For this subtask, assuming they are available in the environment.

    # Also ensure that a README.md exists at the project root for ConfigManagerV2_5 to find it.
    # And that elite_options_system_v2_5/config_v2_5.json and config.schema.v2.5.json exist.
    # These should have been created by previous subtasks.

    if run_initialization_test():
        logger.info("Orchestrator Initialization Test: PASSED")
        # sys.exit(0) # Explicitly exit with 0 for success
    else:
        logger.error("Orchestrator Initialization Test: FAILED")
        sys.exit(1) # Explicitly exit with 1 for failure
