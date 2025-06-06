# core_analytics_engine/its_orchestrator.py
# (Elite Version 2.4 - Co-Pilot - Canonical Orchestrator - Phase 10 Full Integration with Tradier)

# --- Standard & Third-Party Imports ---
import json
import traceback
import logging
import os
import sys
from datetime import datetime, time, date, timedelta
from typing import Dict, Optional, Tuple, Any, List, Union, Deque, Callable 
from collections import deque, OrderedDict 
import math
import importlib # For dynamic module loading
import re # For parsing MRE dynamic threshold strings

# Third-Party Imports
try:
    import pandas as pd # type: ignore
    import numpy as np # type: ignore
except ImportError as e_dep: # pragma: no cover
    print(f"CRITICAL ERROR: ITSOrchestrator: Essential third-party libraries (pandas, numpy) not found: {e_dep}. Please install them.", file=sys.stderr)
    pass 

# --- Module-Specific Logger ---
logger = logging.getLogger(__name__) 

# --- Placeholder for Dynamic EOTS V2.4 Module Imports (Class References) ---
DataFetcherV2_4_ClassRef: Optional[type] = None # For ConvexValue
TradierDataFetcher_ClassRef: Optional[type] = None # ADDED for Tradier
InitialDataProcessorV2_4_ClassRef: Optional[type] = None
MetricsCalculatorV2_4_ClassRef: Optional[type] = None
HistoricalDataManager_V2_4_ClassRef: Optional[type] = None 
MarketRegimeEngineV2_4_Superior_ClassRef: Optional[type] = None 
SignalGeneratorV2_4_ClassRef: Optional[type] = None
RecommendationGeneratorV2_4_ClassRef: Optional[type] = None
TradeParameterOptimizerV2_4_ClassRef: Optional[type] = None


# --- Helper Constants ---
EPSILON_ORCH: float = 1e-9 
DEFAULT_ATR_FALLBACK_PERCENTAGE_ORCH: float = 0.015 
DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH: float = 0.05  


class IntegratedTradingSystemV2_4:
    """
    Main orchestrator for the Elite Options Trading System V2.4.
    Coordinates data fetching, processing, metric calculation, regime analysis,
    signal generation, recommendation formulation, and stateful management.
    """
    # --- Core Methods ---
    def __init__(self, loaded_config_manager_instance: Any): # Expecting ConfigManager
        self.logger = logging.getLogger(__name__).getChild(self.__class__.__name__)
        self.logger.info("Initializing IntegratedTradingSystemV2_4 (Co-Pilot Core Orchestrator - Phase 10 with Tradier)...")

        if not hasattr(loaded_config_manager_instance, 'get_setting') or not hasattr(loaded_config_manager_instance, 'get_config'):
            self.logger.critical("ITS_Orchestrator FATAL: Invalid ConfigManager instance provided. Aborting initialization.")
            self.initialization_failed = True
            # Set all component attributes to None or Dummy versions to prevent AttributeError
            class DummyCM: 
                def get_setting(self, *args, **kwargs): return kwargs.get('default_value_to_return')
                def get_config(self, *args, **kwargs): return {}
                def get_resolved_path(self, *args, **kwargs): return None 
            self.config_manager: Any = DummyCM() 
            self.data_fetcher: Optional[Any] = None # For ConvexValue
            self.tradier_data_fetcher: Optional[Any] = None # ADDED for Tradier
            self.historical_data_manager: Optional[Any] = None
            self.metrics_calculator: Optional[Any] = None
            self.initial_data_processor: Optional[Any] = None
            self.market_regime_engine: Optional[Any] = None
            self.signal_generator: Optional[Any] = None
            self.recommendation_generator: Optional[Any] = None
            self.trade_parameter_optimizer: Optional[Any] = None
            # Class references
            self.DataFetcherClass: Optional[type] = None
            self.TradierDataFetcherClass: Optional[type] = None # ADDED
            self.HistoricalDataManagerClass: Optional[type] = None
            self.MetricsCalculatorClass: Optional[type] = None
            self.InitialDataProcessorClass: Optional[type] = None
            self.MarketRegimeEngineClass: Optional[type] = None
            self.SignalGeneratorClass: Optional[type] = None
            self.RecommendationGeneratorClass: Optional[type] = None
            self.TradeParameterOptimizerClass: Optional[type] = None
            # Initialize other attributes
            self.current_symbol_being_managed: Optional[str] = None
            self.last_analysis_timestamp: Optional[datetime] = None
            self.active_recommendations: List[Dict[str, Any]] = []
            self.processed_strike_df_history: deque = deque(maxlen=1) 
            self.processed_und_data_history: deque = deque(maxlen=1)
            self.metric_history_series_for_thresholds: Dict[str, pd.Series] = {}
            self.resolved_dynamic_thresholds_cache: Dict[str, Any] = {}
            self.min_hist_for_dyn_thresh: int = 1 
            self.mre_config_orch: Dict[str, Any] = {}
            self.threshold_configs_orch: Dict[str, Any] = {}
            self.metrics_for_dyn_thresh_keys: List[str] = []
            self.col_und_price_orch: str = "price"
            self.col_strike_orch: str = "strike"
            self.exit_config: Dict[str, Any] = {}
            self.target_config: Dict[str, Any] = {}
            self.reco_config: Dict[str, Any] = {}
            self.default_multiplier_val: float = 100.0 
            self.col_u_day_open_price: Optional[str] = "day_open_price" 
            self.col_u_day_high_price_orch: Optional[str] = "day_high_price"
            self.col_u_day_low_price_orch: Optional[str] = "day_low_price"
            self.col_u_day_volume_orch: Optional[str] = "day_volume"
            self.mspi_col: str = "mspi"
            self.sai_col: str = "sai"
            self.ssi_col: str = "ssi_agg"
            self.arfi_strike_col: str = "arfi_strike"
            self.nvp_strike_col: str = "nvp_strike"
            self.tdpi_strike_col: str = "tdpi" 
            self.gib_oi_und_col: str = "GIB_OI_based_Und"
            self.rolling_net_value_flow_15m_col: str = "NetValueFlow_15m_Und" 
            self.vri_0dte_agg_col: str = "vri_0dte_und_sum"
            self.vfi_0dte_agg_col: str = "vfi_0dte_und_sum"
            self.vci_0dte_agg_col: str = "vci_0dte_agg" 
            self.hp_eod_und_col: str = "HP_EOD_Und"
            return

        self.config_manager: Any = loaded_config_manager_instance 
        self.initialization_failed: bool = False

        self._configure_orchestrator_logging() 
        
        self.logger.info("ITS Orchestrator: Initializing core components...")
        
        # ConvexValue Data Fetcher (Primary)
        fetcher_module_path = self.config_manager.get_setting(["runner_settings", "data_fetcher_module_path"], "data_management.fetcher")
        fetcher_class_name = self.config_manager.get_setting(["runner_settings", "data_fetcher_class_name"], "DataFetcherV2_4")
        self.data_fetcher, self.DataFetcherClass = self._try_init_module_instance(
            "DataFetcher (ConvexValue)", str(fetcher_module_path), str(fetcher_class_name)
        )

        # --- START: Tradier Data Fetcher Initialization ---
        tradier_fetcher_module_path_cfg = self.config_manager.get_setting(
            ["runner_settings", "tradier_data_fetcher_module_path"], 
            default_value_to_return="data_management.tradier_data_fetcher"
        )
        tradier_fetcher_class_name_cfg = self.config_manager.get_setting(
            ["runner_settings", "tradier_data_fetcher_class_name"], 
            default_value_to_return="TradierDataFetcher"
        )
        # The _try_init_module_instance already passes config_manager_instance by default now
        self.tradier_data_fetcher, self.TradierDataFetcherClass = self._try_init_module_instance(
            module_key_name="TradierDataFetcher",
            module_path_str=str(tradier_fetcher_module_path_cfg),
            class_name_str=str(tradier_fetcher_class_name_cfg)
            # constructor_kwargs={'config_manager_instance': self.config_manager} # No longer needed if _try_init handles it
        )
        # Per subtask: If a critical sub-component (TradierDataFetcher is now considered one) fails,
        # set self.initialization_failed = True.
        # _try_init_module_instance returns None if the component itself failed init or couldn't be loaded.
        if self.tradier_data_fetcher is None: # This implies it failed to initialize
            self.logger.critical("ITS Orchestrator: CRITICAL SUB-COMPONENT FAILURE: TradierDataFetcher failed to initialize.")
            # self.initialization_failed = True # This will be caught by the critical_components_check
        else:
            self.logger.info("ITS Orchestrator: TradierDataFetcher initialized successfully.")
        # --- END: Tradier Data Fetcher Initialization ---

        # Historical Data Manager
        hdm_module_path = self.config_manager.get_setting(["runner_settings", "historical_manager_module_path"], "data_management.historical_data_manager")
        hdm_class_name = self.config_manager.get_setting(["runner_settings", "historical_manager_class_name"], "HistoricalDataManagerV2_4")
        self.historical_data_manager, self.HistoricalDataManagerClass = self._try_init_module_instance(
            "HistoricalDataManager", str(hdm_module_path), str(hdm_class_name)
        )

        # Metrics Calculator
        mc_module_path = self.config_manager.get_setting(["runner_settings", "metrics_calculator_module_path"], "core_analytics_engine.metrics_calculator")
        mc_class_name = self.config_manager.get_setting(["runner_settings", "metrics_calculator_class_name"], "MetricsCalculatorV2_4")
        mc_constructor_kwargs = {'historical_data_manager_instance': self.historical_data_manager}
        self.metrics_calculator, self.MetricsCalculatorClass = self._try_init_module_instance(
            "MetricsCalculator", str(mc_module_path), str(mc_class_name),
            constructor_kwargs=mc_constructor_kwargs
        )

        # Initial Data Processor
        idp_module_path = self.config_manager.get_setting(["runner_settings", "initial_processor_module_path"], "data_management.initial_processor")
        idp_class_name = self.config_manager.get_setting(["runner_settings", "initial_processor_class_name"], "InitialDataProcessorV2_4")
        idp_constructor_kwargs = {'metrics_calculator_instance': self.metrics_calculator}
        self.initial_data_processor, self.InitialDataProcessorClass = self._try_init_module_instance(
            "InitialDataProcessor", str(idp_module_path), str(idp_class_name),
            constructor_kwargs=idp_constructor_kwargs
        )

        # Market Regime Engine
        mre_module_path = self.config_manager.get_setting(["runner_settings", "market_regime_engine_module_path"], "core_analytics_engine.market_regime_engine")
        mre_class_name = self.config_manager.get_setting(["runner_settings", "market_regime_engine_class_name"], "MarketRegimeEngineV2_4_Superior")
        self.market_regime_engine, self.MarketRegimeEngineClass = self._try_init_module_instance(
            "MarketRegimeEngine", str(mre_module_path), str(mre_class_name)
        )
        # Per subtask: If MarketRegimeEngine (now considered critical) fails, this should lead to orchestrator failure.
        # _try_init_module_instance returns None if the component itself failed init or couldn't be loaded.
        if self.market_regime_engine is None:
            self.logger.critical("ITS Orchestrator: CRITICAL SUB-COMPONENT FAILURE: MarketRegimeEngine failed to initialize.")
            # self.initialization_failed = True # This will be caught by the critical_components_check
            self._use_dummy_market_regime_engine() # Still use dummy to prevent NoneErrors if check is bypassed
        elif hasattr(self.market_regime_engine, 'initialization_failed') and self.market_regime_engine.initialization_failed:
            # This case is when the instance was created but it internally failed.
            self.logger.critical("ITS Orchestrator: CRITICAL SUB-COMPONENT FAILURE: MarketRegimeEngine reported its own initialization failure.")
            # self.initialization_failed = True # This will be caught by the critical_components_check
            self._use_dummy_market_regime_engine() # Still use dummy
        else:
            self.logger.info("ITS Orchestrator: MarketRegimeEngine initialized successfully.")

        # Signal Generator
        sg_module_path = self.config_manager.get_setting(["runner_settings", "signal_generator_module_path"], "core_analytics_engine.signal_generator")
        sg_class_name = self.config_manager.get_setting(["runner_settings", "signal_generator_class_name"], "SignalGeneratorV2_4")
        self.signal_generator, self.SignalGeneratorClass = self._try_init_module_instance(
            "SignalGenerator", str(sg_module_path), str(sg_class_name)
        )

        # Recommendation Generator
        rg_module_path = self.config_manager.get_setting(["runner_settings", "recommendation_logic_module_path"], "core_analytics_engine.recommendation_logic")
        rg_class_name = self.config_manager.get_setting(["runner_settings", "recommendation_logic_class_name"], "RecommendationGeneratorV2_4")
        rg_constructor_kwargs = {'orchestrator_ref': self}
        self.recommendation_generator, self.RecommendationGeneratorClass = self._try_init_module_instance(
            "RecommendationGenerator", str(rg_module_path), str(rg_class_name),
            constructor_kwargs=rg_constructor_kwargs
        )

        # Trade Parameter Optimizer
        tpo_module_path = self.config_manager.get_setting(["runner_settings", "trade_parameter_optimizer_module_path"], "core_analytics_engine.trade_parameter_optimizer")
        tpo_class_name = self.config_manager.get_setting(["runner_settings", "trade_parameter_optimizer_class_name"], "TradeParameterOptimizerV2_4")
        tpo_constructor_kwargs = {'orchestrator_ref': self} 
        self.trade_parameter_optimizer, self.TradeParameterOptimizerClass = self._try_init_module_instance(
            "TradeParameterOptimizer", str(tpo_module_path), str(tpo_class_name),
            constructor_kwargs=tpo_constructor_kwargs
        )
        # Per subtask: If TradeParameterOptimizer (now considered critical) fails, this should lead to orchestrator failure.
        if self.trade_parameter_optimizer is None:
            self.logger.critical("ITS Orchestrator: CRITICAL SUB-COMPONENT FAILURE: TradeParameterOptimizer failed to initialize.")
            # self.initialization_failed = True # This will be caught by the critical_components_check
            self._use_dummy_trade_parameter_optimizer() # Still use dummy
        elif hasattr(self.trade_parameter_optimizer, 'initialization_failed_tpo') and self.trade_parameter_optimizer.initialization_failed_tpo:
            self.logger.critical("ITS Orchestrator: CRITICAL SUB-COMPONENT FAILURE: TradeParameterOptimizer reported its own initialization failure.")
            # self.initialization_failed = True # This will be caught by the critical_components_check
            self._use_dummy_trade_parameter_optimizer() # Still use dummy
        else:
            self.logger.info("ITS Orchestrator: TradeParameterOptimizer initialized successfully.")

        # Consolidate all components that are considered critical for the orchestrator's core functionality.
        # If any of these failed to initialize (instance is None, or its own init_failed flag is True),
        # the orchestrator's self.initialization_failed will be set to True.
        critical_components_check = {
            "DataFetcher (ConvexValue)": (self.data_fetcher, 'initialization_failed'),
            "TradierDataFetcher": (self.tradier_data_fetcher, 'initialization_failed'), # Added as critical
            "HistoricalDataManager": (self.historical_data_manager, 'initialization_failed'),
            "MetricsCalculator": (self.metrics_calculator, 'initialization_failed'),
            "InitialDataProcessor": (self.initial_data_processor, 'initialization_failed'),
            "MarketRegimeEngine": (self.market_regime_engine, 'initialization_failed'), # Added as critical
            "SignalGenerator": (self.signal_generator, 'initialization_failed'),
            "RecommendationGenerator": (self.recommendation_generator, 'initialization_failed'),
            "TradeParameterOptimizer": (self.trade_parameter_optimizer, 'initialization_failed_tpo') # Added as critical
        }

        for name, (component_instance, init_flag_name) in critical_components_check.items():
            component_failed = False
            if component_instance is None:
                component_failed = True
                # Log specific message if instance is None, as _try_init_module_instance would have logged details already
                self.logger.debug(f"ITS Orchestrator: Critical component '{name}' instance is None (presumed failed initialization).")
            elif hasattr(component_instance, init_flag_name) and getattr(component_instance, init_flag_name):
                component_failed = True
                # This log is slightly redundant if _try_init_module_instance already logged it,
                # but good for a clear summary here.
                self.logger.debug(f"ITS Orchestrator: Critical component '{name}' reported its own initialization failure via attribute '{init_flag_name}'.")
            
            if component_failed:
                # Check if not already True to avoid redundant critical logs for multiple failures
                if not self.initialization_failed: 
                    self.logger.critical(f"ITS Orchestrator: Critical component '{name}' did not initialize successfully. Orchestrator initialization marked as failed.")
                self.initialization_failed = True
        
        if self.initialization_failed:
            self.logger.critical("ITS V2.4 Orchestrator FAILED to initialize one or more CRITICAL components. System may not function correctly and will likely operate with dummies or halt.")
            # Ensure dummy versions are used if any critical component failed,
            # even if the dummy was already set (e.g. MRE, TPO).
            # This also handles cases where a component in critical_components_check might not have a _use_dummy_* method.
            if self.data_fetcher is None: self._use_dummy_data_fetcher()
            # No dummy for TradierDataFetcher, its absence is handled by checks in operational methods.
            if self.historical_data_manager is None: self._use_dummy_historical_data_manager()
            if self.metrics_calculator is None: self._use_dummy_metrics_calculator()
            if self.initial_data_processor is None: self._use_dummy_initial_processor()
            if self.market_regime_engine is None : self._use_dummy_market_regime_engine() # Ensure dummy if it became None
            if self.signal_generator is None: self._use_dummy_signal_generator()
            if self.recommendation_generator is None: self._use_dummy_recommendation_generator()
            if self.trade_parameter_optimizer is None : self._use_dummy_trade_parameter_optimizer() # Ensure dummy if it became None
        else:
            self.logger.info("ITS V2.4 Orchestrator and all CRITICAL components initialized successfully.")
        
        df_history_maxlen_config_key = ["system_settings", "df_history_maxlen"]
        df_history_maxlen_default = 20
        df_history_maxlen = int(self.config_manager.get_setting(df_history_maxlen_config_key, default_value_to_return=df_history_maxlen_default))
        
        self.processed_strike_df_history: deque = deque(maxlen=df_history_maxlen)
        self.processed_und_data_history: deque = deque(maxlen=df_history_maxlen)
        self.metric_history_series_for_thresholds: Dict[str, pd.Series] = {} 
        self.resolved_dynamic_thresholds_cache: Dict[str, Any] = {}
        self.min_hist_for_dyn_thresh: int = int(self._get_config_value_its(["system_settings", "min_days_for_dynamic_threshold_activation"], 10))

        self.active_recommendations: List[Dict[str, Any]] = [] 
        self.current_market_regime: str = self.config_manager.get_setting(["market_regime_engine_settings", "default_regime"], "REGIME_UNCLEAR_LOW_CONVICTION")
        self.current_symbol_being_managed: Optional[str] = None 
        self.last_analysis_timestamp: Optional[datetime] = None
        self.default_multiplier_val = float(self._get_config_value_its(["strategy_settings", "contract_multiplier_default_value"], 100.0))
        
        self._initialize_critical_configs_and_columns() 
        self.logger.info(f"ITS Orchestrator fully configured. Processed data history maxlen: {df_history_maxlen}.")

    def _try_init_module_instance(self, module_key_name: str, module_path_str: str, class_name_str: str,
                                 constructor_kwargs: Optional[Dict[str, Any]] = None
                                ) -> Tuple[Optional[Any], Optional[type]]:
        instance: Optional[Any] = None
        ClassReference: Optional[type] = None
        
        try:
            self.logger.debug(f"ITS Orchestrator: Attempting to load class '{class_name_str}' from module '{module_path_str}' for '{module_key_name}'.")
            module_obj = importlib.import_module(module_path_str)
            if hasattr(module_obj, class_name_str):
                ClassReference = getattr(module_obj, class_name_str)
                
                # Ensure config_manager_instance is always passed if not already in kwargs
                final_constructor_kwargs: Dict[str, Any] = {'config_manager_instance': self.config_manager}
                if constructor_kwargs:
                    final_constructor_kwargs.update(constructor_kwargs) # constructor_kwargs can override if needed
                
                self.logger.debug(f"Instantiating '{class_name_str}' with kwargs: {list(final_constructor_kwargs.keys())}")
                instance = ClassReference(**final_constructor_kwargs)
                
                # Check for component-specific initialization failure flags
                init_failed_attr_name = 'initialization_failed' # Default attribute name
                if module_key_name == "TradeParameterOptimizer": # Specific case for TPO
                    init_failed_attr_name = 'initialization_failed_tpo'

                if hasattr(instance, init_failed_attr_name) and getattr(instance, init_failed_attr_name):
                    self.logger.error(f"ITS Orchestrator: Instance of '{class_name_str}' for '{module_key_name}' reported its own initialization failure (attr: {init_failed_attr_name}).")
                    return None, ClassReference # Return class ref but None instance

                self.logger.info(f"ITS Orchestrator: Successfully instantiated '{class_name_str}' for '{module_key_name}'.")
            else:
                self.logger.error(f"ITS Orchestrator: Class '{class_name_str}' not found in module '{module_path_str}'.")
        except ImportError as ie:
            self.logger.error(f"ITS Orchestrator: Failed to import module '{module_path_str}' for '{module_key_name}': {ie}", exc_info=False)
        except TypeError as te: 
            # Log the specific TypeError, which often happens if constructor signature is wrong
            self.logger.error(f"ITS Orchestrator: TypeError instantiating {module_key_name} ('{class_name_str if ClassReference else 'UnknownClass'}'): {te}", exc_info=True)
        except Exception as e: # Catch-all for other unexpected errors during dynamic load/init
            self.logger.error(f"ITS Orchestrator: Failed to dynamically load/init class '{class_name_str}' from '{module_path_str}' for {module_key_name}: {e}", exc_info=True)
        
        if instance is None and ClassReference is not None: 
             self.logger.error(f"ITS Orchestrator: Instantiation of {class_name_str} failed but class was found. Check constructor or previous errors.")
        elif instance is None and ClassReference is None: 
            self.logger.error(f"ITS Orchestrator: ClassReference for {module_key_name} is None (module/class load likely failed). Cannot instantiate.")
            
        return instance, ClassReference

    def _validate_config_structure(self) -> None:
        """
        Validates that essential top-level sections are present in the loaded configuration.
        Raises ValueError if critical sections are missing.
        """
        val_logger = self.logger.getChild("ConfigValidatorOrch")
        required_sections_cfg = self.config_manager.get_setting(
            "validation.required_top_level_sections", 
            default_value_to_return=[] # Use default from config if present
        )
        # Fallback to a hardcoded list if config doesn't specify or is empty
        if not required_sections_cfg: 
            required_sections_cfg = [
                "system_settings", "runner_settings", "api_credentials", 
                "data_fetcher_settings", "data_processor_settings", 
                "strategy_settings", "market_regime_engine_settings", "visualization_settings"
            ]
        
        config_dict = self.config_manager.get_config() # Get the raw config dictionary
        if not isinstance(config_dict, dict):
            self.initialization_failed = True
            val_logger.critical("Orchestrator: Loaded configuration is not a dictionary. Cannot validate structure.")
            raise ValueError("Orchestrator: Loaded configuration is not a dictionary.")

        missing_critical = [section for section in required_sections_cfg if section not in config_dict]
        if missing_critical:
            self.initialization_failed = True # Mark as failed
            val_logger.critical(f"Orchestrator: Critical configuration sections missing: {', '.join(missing_critical)}")
            raise ValueError(f"Orchestrator: Critical configuration sections missing from loaded config: {', '.join(missing_critical)}")
        
        val_logger.info("Orchestrator: Basic configuration structure appears valid (required top-level sections present).")

    def _configure_orchestrator_logging(self):
        """
        Sets the logging level for the ITS Orchestrator's instance logger based on configuration.
        Prioritizes 'log_level_orchestrator', falls back to global 'log_level', then to INFO.
        """
        # Note: self.logger is already initialized in __init__ before this method is called.
        orchestrator_log_level_cfg_key = ["system_settings", "log_level_orchestrator"]
        system_log_level_cfg_key = ["system_settings", "log_level"]
        default_log_level_str = "INFO" # Hardcoded fallback if all config lookups fail
        
        # Attempt to get orchestrator-specific log level
        log_level_str_orch = self.config_manager.get_setting(
            orchestrator_log_level_cfg_key, 
            default_value_to_return=None # Important: return None if not found to trigger next fallback
        )
        
        # If orchestrator-specific is not set, try global log level
        if log_level_str_orch is None:
            log_level_str_orch = self.config_manager.get_setting(
                system_log_level_cfg_key, 
                default_value_to_return=default_log_level_str # Use hardcoded default if global also not found
            )
        
        # If still None (e.g., config was missing both), ensure it's the hardcoded default
        if log_level_str_orch is None:
            log_level_str_orch = default_log_level_str

        try:
            # Ensure log_level_str_orch is a string before .upper()
            final_log_level_str = str(log_level_str_orch).upper()
            self.logger.setLevel(getattr(logging, final_log_level_str))
            self.logger.info(f"Orchestrator logger level set to: {logging.getLevelName(self.logger.getEffectiveLevel())} (derived from config value: '{log_level_str_orch}').")
        except (AttributeError, ValueError):
            self.logger.setLevel(logging.INFO) # Fallback to INFO on any error
            self.logger.warning(f"Invalid log level '{log_level_str_orch}' in config. Orchestrator logger defaulting to INFO.")
        
    def _get_config_value_its(self, key_path: Union[str, List[str]], default_val_param: Any = None, quiet: bool = False) -> Any: 
        """
        Convenience wrapper for self.config_manager.get_setting.
        Ensures the correct parameter name `default_value_to_return` is used.
        """
        if not hasattr(self, 'config_manager') or not hasattr(self.config_manager, 'get_setting'):
            self.logger.error(f"_get_config_value_its: ConfigManager not available. Returning default: {default_val_param} for key: {key_path}")
            return default_val_param
        return self.config_manager.get_setting(key_path, default_value_to_return=default_val_param, quiet=quiet) 

    def _initialize_critical_configs_and_columns(self) -> None:
        """
        Loads and stores frequently used configurations and column name mappings
        from the ConfigManager into instance attributes for efficient access.
        This method assumes self.config_manager is valid and initialized.
        """
        self.logger.debug("ITSOrch: Initializing critical config attributes and column name mappings...")
        
        # Config Dictionaries (these will be used frequently by other methods)
        self.reco_config = self._get_config_value_its("strategy_settings.recommendations", {})
        self.exit_config = self._get_config_value_its("strategy_settings.exits", {})
        self.target_config = self._get_config_value_its("strategy_settings.targets", {})
        self.mre_config_orch = self._get_config_value_its("market_regime_engine_settings", {}) 
        self.threshold_configs_orch = self._get_config_value_its("strategy_settings.thresholds", {})
        
        # Metrics for Dynamic Thresholds
        self.metrics_for_dyn_thresh_keys = self._get_config_value_its(
            "system_settings.metrics_for_dynamic_threshold_distribution_tracking", 
            [] # Default to empty list
        )
        
        # Key Column Names from strategy_settings
        s_cfg = "strategy_settings" # Common base path
        self.col_strike_orch = self._get_config_value_its(f"{s_cfg}.strike_col_name", "strike")
        self.col_und_price_orch = self._get_config_value_its(f"{s_cfg}.underlying_price_col_name", "price")
        
        # Underlying column names from "greeks_from_und" mapping (used for OHLCV storage & some calcs)
        greeks_from_und_map = self._get_config_value_its(f"{s_cfg}.greeks_from_und", {})
        if not isinstance(greeks_from_und_map, dict): greeks_from_und_map = {} # Ensure it's a dict

        self.col_u_day_open_price = greeks_from_und_map.get("day_open_price_und") # Can be None if not mapped
        self.col_u_day_high_price_orch = greeks_from_und_map.get("day_high_price_und")
        self.col_u_day_low_price_orch = greeks_from_und_map.get("day_low_price_und")
        self.col_u_day_volume_orch = greeks_from_und_map.get("day_volume_und")

        # Standardized metric names used internally by the orchestrator (derived from analysis)
        self.mspi_col = "mspi" 
        self.sai_col = "sai"
        self.ssi_col = "ssi_agg"
        self.arfi_strike_col = "arfi_strike"
        self.nvp_strike_col = "nvp_strike"
        self.tdpi_strike_col = "tdpi" 
        self.gib_oi_und_col = "GIB_OI_based_Und" # Output key from MetricsCalculator
        self.rolling_net_value_flow_15m_col = "NetValueFlow_15m_Und" # Example, could be configurable
        self.vri_0dte_agg_col = "vri_0dte_und_sum" # Output key from MetricsCalculator
        self.vfi_0dte_agg_col = "vfi_0dte_und_sum" # Output key from MetricsCalculator
        self.vci_0dte_agg_col = "vci_0dte_agg"     # Output key from MetricsCalculator
        self.hp_eod_und_col = "HP_EOD_Und"         # Output key from MetricsCalculator
        
        self.logger.debug("ITSOrch: Critical config attributes and column names initialized.")


    # ----------------------- Dummy Initializers for Fallback --------------------------------
    def _use_dummy_data_fetcher(self):
        """Instantiates a dummy DataFetcher if the real one fails."""
        class DummyDataFetcher:
            def __init__(self, config_manager_instance: Any): 
                self.logger = logging.getLogger("DummyDataFetcher_Orch")
                self.config_manager = config_manager_instance # Store for potential use
                self.logger.warning("Initialized DUMMY DataFetcher.")

            def fetch_options_chain_and_underlying(self, symbol_to_fetch: str, # Matched kwarg from main call
                                                   dte_list_override: Optional[List[int]] = None, 
                                                   price_range_pct_override: Optional[float] = None
                                                   ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
                self.logger.warning(f"DUMMY DataFetcher: fetch_options_chain_and_underlying called for {symbol_to_fetch}. Returning empty data with error.")
                return pd.DataFrame(), {"error": "Dummy DataFetcher in use", "symbol": symbol_to_fetch}

            def shutdown(self): 
                self.logger.info("DUMMY DataFetcher shutdown called.")
        
        self.data_fetcher = DummyDataFetcher(self.config_manager) 
        self.logger.warning("ITS Orchestrator is using a DUMMY DataFetcher due to earlier initialization failure.")

    def _use_dummy_initial_processor(self):
        """Instantiates a dummy InitialDataProcessor."""
        class DummyInitialProcessor:
            def __init__(self, config_manager_instance: Any, metrics_calculator_instance: Optional[Any]): 
                self.logger = logging.getLogger("DummyInitialProcessor_Orch")
                self.config_manager = config_manager_instance
                self.metrics_calculator = metrics_calculator_instance # Store for potential use
                self.logger.warning("Initialized DUMMY InitialDataProcessor.")

            def process_option_chain_snapshot_v2_4(self, options_df_raw: pd.DataFrame, 
                                                   underlying_data_raw: Dict[str, Any], 
                                                   current_time_dt: datetime, 
                                                   symbol: str) -> Dict[str, Any]:
                self.logger.warning(f"DUMMY InitialProcessor: process_option_chain_snapshot_v2_4 called for {symbol}. Returning minimal bundle with error status.")
                return {
                    "symbol": symbol, 
                    "status": "ERROR_DUMMY_PROCESSOR", 
                    "error_message": "Dummy InitialDataProcessor in use.",
                    "options_df_input_to_metrics_calc_obj": options_df_raw if isinstance(options_df_raw, pd.DataFrame) else pd.DataFrame(),
                    "underlying_data_input_to_metrics_calc_obj": underlying_data_raw if isinstance(underlying_data_raw, dict) else {},
                    "options_df_with_metrics_obj": pd.DataFrame(), # No metrics calculated
                    "df_strike_level_metrics_obj": pd.DataFrame(), # No metrics calculated
                    "underlying_data_enriched_obj": underlying_data_raw if isinstance(underlying_data_raw, dict) else {}, # Pass through raw
                    "json_safe_data": {"error": "Dummy InitialDataProcessor"}
                }
        self.initial_data_processor = DummyInitialProcessor(self.config_manager, self.metrics_calculator)
        self.logger.warning("ITS Orchestrator is using a DUMMY InitialDataProcessor.")

    def _use_dummy_historical_data_manager(self):
        """Instantiates a dummy HistoricalDataManager."""
        class DummyHDM:
            def __init__(self, config_manager_instance: Any): 
                self.logger = logging.getLogger("DummyHDM_Orch")
                self.config_manager = config_manager_instance
                self.logger.warning("Initialized DUMMY HistoricalDataManager.")

            def get_ohlc_history_for_atr(self, symbol: str, num_days: int, current_trading_date: date) -> pd.DataFrame: 
                self.logger.warning(f"DUMMY HDM: get_ohlc_history_for_atr for {symbol}. Returning empty DataFrame.")
                return pd.DataFrame() 
            
            def get_average_iv(self, symbol: str, period_days: int, current_date: date) -> Optional[float]: 
                self.logger.warning(f"DUMMY HDM: get_average_iv for {symbol}. Returning default 0.20.")
                return 0.20 # Default IV
            
            def get_metric_distribution_for_threshold(self, symbol: str, metric_key: str, days_history: int, current_trading_date: date) -> pd.Series: 
                self.logger.warning(f"DUMMY HDM: get_metric_distribution for {metric_key} of {symbol}. Returning empty Series.")
                return pd.Series(dtype=float)
            
            def store_daily_metric_value(self, *args, **kwargs): 
                self.logger.debug("DUMMY HDM: store_daily_metric_value called. No action.")
            
            def store_daily_ohlcv(self, *args, **kwargs): 
                self.logger.debug("DUMMY HDM: store_daily_ohlcv called. No action.")
            
            def shutdown(self): 
                self.logger.info("DUMMY HDM shutdown called.")
        
        self.historical_data_manager = DummyHDM(self.config_manager)
        self.logger.warning("ITS Orchestrator is using a DUMMY HistoricalDataManager.")

    def _use_dummy_metrics_calculator(self):
        """Instantiates a dummy MetricsCalculator."""
        class DummyMC:
            def __init__(self, config_manager_instance: Any, historical_data_manager_instance: Optional[Any]): 
                self.logger = logging.getLogger("DummyMC_Orch")
                self.config_manager = config_manager_instance
                self.historical_data_manager = historical_data_manager_instance
                self.logger.warning("Initialized DUMMY MetricsCalculator.")

            def orchestrate_all_metric_calculations(self, options_df_raw: pd.DataFrame, 
                                                   und_data_api_raw: Dict[str, Any], 
                                                   current_time_dt: datetime, 
                                                   symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]: 
                self.logger.warning(f"DUMMY MetricsCalculator: orchestrate_all_metric_calculations for {symbol}. Returning empty/passthrough data.")
                # Pass through raw underlying data, return empty DataFrames for metrics
                und_enriched = und_data_api_raw.copy() if isinstance(und_data_api_raw, dict) else {}
                und_enriched["error_metrics_calc"] = "Dummy MetricsCalculator in use"
                return pd.DataFrame(), pd.DataFrame(), und_enriched
            
            def _get_atr_internal(self, symbol: str, current_price: float, period: int, current_trading_date: date) -> float:
                self.logger.warning(f"DUMMY MetricsCalculator: _get_atr_internal for {symbol}. Returning fallback ATR.")
                return max(current_price * DEFAULT_ATR_FALLBACK_PERCENTAGE_ORCH, DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH) if current_price > 0 else DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH

        self.metrics_calculator = DummyMC(self.config_manager, self.historical_data_manager)
        self.logger.warning("ITS Orchestrator is using a DUMMY MetricsCalculator.")

    def _use_dummy_market_regime_engine(self):
        """Instantiates a dummy MarketRegimeEngine."""
        class DummyMRE:
            def __init__(self, config_manager_instance: Any): 
                self.logger = logging.getLogger("DummyMRE_Orch")
                self.config_manager = config_manager_instance
                self.default_regime = self.config_manager.get_setting(
                    ["market_regime_engine_settings", "default_regime"], 
                    default_value_to_return="REGIME_DUMMY_MRE_IN_USE"
                )
                self.logger.warning(f"Initialized DUMMY MarketRegimeEngine. Will always return '{self.default_regime}'.")
            
            def determine_market_regime_v2_4(self, *args, **kwargs) -> str: 
                self.logger.warning(f"DUMMY MRE: determine_market_regime_v2_4 called. Returning default: {self.default_regime}")
                return self.default_regime
        
        self.market_regime_engine = DummyMRE(self.config_manager)
        self.logger.warning("ITS Orchestrator is using a DUMMY MarketRegimeEngine.")

    def _use_dummy_signal_generator(self):
        """Instantiates a dummy SignalGenerator."""
        class DummySG:
            def __init__(self, config_manager_instance: Any): 
                self.logger = logging.getLogger("DummySG_Orch")
                self.config_manager = config_manager_instance
                self.logger.warning("Initialized DUMMY SignalGenerator.")

            def generate_all_signals_v2_4(self, *args, **kwargs) -> Dict[str, Dict[str, List[Dict[str,Any]]]]: 
                self.logger.warning("DUMMY SignalGenerator: generate_all_signals_v2_4 called. Returning empty signals dict.")
                # Return the expected empty structure
                return {
                    'directional': {'bullish': [], 'bearish': []}, 
                    'volatility': {'expansion': [], 'contraction': []}, 
                    'time_decay': {'pin_risk': [], 'charm_cascade': []}, 
                    'complex': {'structure_change': [], 'flow_divergence': [], 'sdag_conviction': []},
                    'v2_4_new': {
                        'vanna_cascade_alert': [], 'volatility_skew_shift_alert': [],
                        'eod_hedging_pressure': [], 'bubble_warning_signal': [],
                        'rolling_flow_momentum_signal': [], 'unusual_customer_greek_flow_signal': []
                    }
                }
        self.signal_generator = DummySG(self.config_manager)
        self.logger.warning("ITS Orchestrator is using a DUMMY SignalGenerator.")
        
    def _use_dummy_recommendation_generator(self):
        """Instantiates a dummy RecommendationGenerator."""
        class DummyRG:
            def __init__(self, config_manager_instance: Any, orchestrator_ref: Any): 
                self.logger = logging.getLogger("DummyRG_Orch")
                self.config_manager = config_manager_instance
                self.orchestrator_ref = orchestrator_ref # Store for potential use
                self.logger.warning("Initialized DUMMY RecommendationGenerator.")

            def formulate_recommendations_v2_4(self, *args, **kwargs) -> List[Dict[str, Any]]: 
                self.logger.warning("DUMMY RecommendationGenerator: formulate_recommendations_v2_4 called. Returning empty list.")
                return []
        self.recommendation_generator = DummyRG(self.config_manager, self)
        self.logger.warning("ITS Orchestrator is using a DUMMY RecommendationGenerator.")

    def _use_dummy_trade_parameter_optimizer(self):
        """Instantiates a dummy TradeParameterOptimizer."""
        class DummyTPO:
            def __init__(self, config_manager_instance: Any, orchestrator_ref: Any): # Added config_manager_instance
                 self.logger = logging.getLogger("DummyTPO_Orch")
                 self.config_manager = config_manager_instance # Store it
                 self.orchestrator_ref = orchestrator_ref
                 self.logger.warning("Initialized DUMMY TradeParameterOptimizer.")

            def optimize_parameters_for_recommendation(self, recommendation_payload: Dict[str, Any], 
                                                       *args, **kwargs) -> Dict[str, Any]:
                self.logger.warning(f"DUMMY TPO: optimize_parameters_for_recommendation called for reco ID {recommendation_payload.get('id','N/A')}. Returning payload with default params and error status.")
                updated_payload = recommendation_payload.copy()
                updated_payload.update({
                    "target_1": None, "target_2": None, "stop_loss": None, 
                    "target_rationale": "Dummy TPO - Parameters not optimized.", 
                    "status": "ERROR_PARAMETERS" # Indicate parameters could not be set
                })
                return updated_payload
        # Pass config_manager to the dummy TPO constructor as well
        self.trade_parameter_optimizer = DummyTPO(self.config_manager, self) 
        self.logger.warning("ITS Orchestrator is using a DUMMY TradeParameterOptimizer.")
    

    # --------------------------------- Main Operational Methods ---------------------------------------
    def fetch_data_for_analysis_cycle(self, 
                                      symbol: str, 
                                      dte_list_for_api_call: Optional[List[int]], 
                                      price_range_percentage_for_api: Optional[float] 
                                      ) -> Dict[str, Any]:
        """
        Orchestrates fetching raw options chain and underlying data using the DataFetcher component.
        Handles potential errors from the fetcher and ensures a standardized output format.
        """
        fetch_logger_orch = self.logger.getChild("FetchDataCycle_Orch")
        fetch_logger_orch.info(f"Orchestrator fetching data for {symbol} (DTEs: {dte_list_for_api_call}, RangePct: {price_range_percentage_for_api})")

        if self.initialization_failed or not self.data_fetcher or not hasattr(self.data_fetcher, 'fetch_options_chain_and_underlying'):
            err_msg = "DataFetcher not available or lacks 'fetch_options_chain_and_underlying' method in Orchestrator."
            fetch_logger_orch.error(err_msg)
            return {"raw_options_df": pd.DataFrame(), "raw_underlying_dict": {"error": err_msg, "symbol": symbol}, "error": err_msg, "symbol": symbol}
        
        try:
            # The DataFetcher is expected to handle the conversion of price_range_percentage_for_api if needed.
            # Orchestrator passes it as received.
            options_df, und_data = self.data_fetcher.fetch_options_chain_and_underlying(
                symbol,  # Pass 'symbol' as the first positional argument
                dte_list_override=dte_list_for_api_call,
                price_range_pct_override=price_range_percentage_for_api
            )
            fetch_logger_orch.info(f"Data fetched for {symbol}. Options DF shape: {options_df.shape if isinstance(options_df, pd.DataFrame) else 'N/A'}, Und Data error: {und_data.get('error') if isinstance(und_data, dict) else 'N/A'}")
            
            # Ensure 'symbol' is in und_data for consistency, even if fetcher had an error
            if isinstance(und_data, dict) and "symbol" not in und_data: 
                und_data["symbol"] = symbol 
            elif not isinstance(und_data, dict): # If und_data is not a dict (e.g. None due to severe error)
                und_data = {"error": "Invalid underlying data structure from fetcher.", "symbol": symbol}

            return {
                "raw_options_df": options_df if isinstance(options_df, pd.DataFrame) else pd.DataFrame(), # Ensure DataFrame
                "raw_underlying_dict": und_data,
                "error": und_data.get("error"), # Propagate error if present
                "symbol": symbol
            }
        except Exception as e_fetch_orch:
            err_msg = f"Exception during orchestrator's data fetch call for {symbol}: {type(e_fetch_orch).__name__} - {e_fetch_orch}"
            fetch_logger_orch.error(err_msg, exc_info=True)
            return {"raw_options_df": pd.DataFrame(), "raw_underlying_dict": {"error": err_msg, "symbol": symbol}, "error": err_msg, "symbol": symbol}

    # --- START: Tradier Data Fetching and Processing Methods ---
    def _fetch_and_store_tradier_ohlcv(self, symbol: str, current_processing_datetime: datetime) -> bool:
        """
        Fetches historical OHLCV data from Tradier for the given symbol for a defined lookback
        (e.g., last 60-90 days to ensure enough data for ATR and other historical calcs)
        and stores it via the HistoricalDataManager.
        Returns True if successful and data was stored, False otherwise.
        """
        tradier_fetch_logger = self.logger.getChild(f"TradierOHLCVFetch.{symbol}")
        if not self.tradier_data_fetcher or not hasattr(self.tradier_data_fetcher, 'get_ohlcv_data'):
            tradier_fetch_logger.warning("TradierDataFetcher not available or 'get_ohlcv_data' method missing. Skipping Tradier OHLCV fetch.")
            return False
        if not self.historical_data_manager or not hasattr(self.historical_data_manager, 'store_daily_ohlcv'):
            tradier_fetch_logger.warning("HistoricalDataManager not available or 'store_daily_ohlcv' method missing. Cannot store Tradier OHLCV.")
            return False

        # Determine date range for fetching OHLCV from Tradier
        # Fetch enough history for ATR calculations (e.g., 60-90 trading days which is ~90-130 calendar days)
        # This can be made configurable.
        days_lookback_ohlcv = int(self._get_config_value_its(["tradier_api_settings", "ohlcv_historical_lookback_days"], default_val_param=90))
        end_date_dt = current_processing_datetime.date() # Fetch up to (and including) yesterday if market is open, or today if market closed
        start_date_dt = end_date_dt - timedelta(days=days_lookback_ohlcv)
        start_date_str = start_date_dt.strftime('%Y-%m-%d')
        end_date_str = end_date_dt.strftime('%Y-%m-%d')

        tradier_fetch_logger.info(f"Requesting Tradier OHLCV for {symbol} from {start_date_str} to {end_date_str}.")
        
        try:
            ohlcv_list_from_tradier = self.tradier_data_fetcher.get_ohlcv_data(
                symbol, 
                interval="daily", 
                start_date_str=start_date_str, 
                end_date_str=end_date_str
            )

            if not ohlcv_list_from_tradier: # Empty list or None
                tradier_fetch_logger.info(f"No OHLCV data returned from Tradier for {symbol} for the period.")
                return False

            bars_stored_count = 0
            for bar_data in ohlcv_list_from_tradier:
                if not isinstance(bar_data, dict) or 'date' not in bar_data:
                    tradier_fetch_logger.warning(f"Skipping invalid OHLCV bar data from Tradier: {bar_data}")
                    continue
                
                date_str = bar_data.get('date')
                try:
                    data_date_object = datetime.strptime(str(date_str), '%Y-%m-%d').date()
                except (ValueError, TypeError) as e:
                    tradier_fetch_logger.error(f"Could not parse date string '{date_str}' from Tradier OHLCV: {e}")
                    continue

                ohlcv_payload = {
                    'open': bar_data.get('open'),
                    'high': bar_data.get('high'),
                    'low': bar_data.get('low'),
                    'close': bar_data.get('close'),
                    'volume': bar_data.get('volume')
                }
                
                # Validate payload before storing
                if all(ohlcv_payload.get(k) is not None and pd.notna(ohlcv_payload.get(k)) for k in ['open', 'high', 'low', 'close', 'volume']):
                    if self.historical_data_manager.store_daily_ohlcv(symbol, data_date_object, ohlcv_payload):
                        bars_stored_count += 1
                else:
                    tradier_fetch_logger.warning(f"Skipping storage for {symbol} on {data_date_object} due to incomplete OHLCV data from Tradier: {ohlcv_payload}")
            
            tradier_fetch_logger.info(f"Successfully fetched and attempted to store {bars_stored_count}/{len(ohlcv_list_from_tradier)} OHLCV bars from Tradier for {symbol}.")
            return bars_stored_count > 0
        except Exception as e:
            tradier_fetch_logger.error(f"Exception during Tradier OHLCV fetch/store for {symbol}: {e}", exc_info=True)
            return False

    def _fetch_and_integrate_tradier_iv_metrics(self, symbol: str, und_data_aggregates_to_update: Dict[str, Any]) -> None:
        """
        Fetches IV5 approximation and potentially other IV metrics from Tradier
        and integrates them into the und_data_aggregates dictionary.
        """
        tradier_iv_logger = self.logger.getChild(f"TradierIVFetch.{symbol}")
        if not self.tradier_data_fetcher or not hasattr(self.tradier_data_fetcher, 'get_iv_approximation'):
            tradier_iv_logger.warning("TradierDataFetcher not available or 'get_iv_approximation' method missing. Skipping Tradier IV fetch.")
            return

        tradier_iv_logger.info(f"Requesting Tradier IV5 approximation for {symbol}.")
        try:
            # Fetch IV5 approximation
            target_dte_for_iv5 = int(self._get_config_value_its(["tradier_api_settings", "iv_approximation_target_dte"], default_val_param=5))
            iv5_data = self.tradier_data_fetcher.get_iv_approximation(symbol, target_dte=target_dte_for_iv5)

            if iv5_data and not iv5_data.get("error"):
                iv5_approx_value = iv5_data.get(f'iv{target_dte_for_iv5}_approx_smv_avg')
                if iv5_approx_value is not None:
                    und_data_aggregates_to_update[f'tradier_iv{target_dte_for_iv5}_approx_smv_avg'] = float(iv5_approx_value)
                    tradier_iv_logger.info(f"Successfully fetched and integrated Tradier IV{target_dte_for_iv5} approx for {symbol}: {iv5_approx_value:.4f}")
                
                # Store other potentially useful IV details from the iv5_data bundle
                und_data_aggregates_to_update['tradier_iv_approx_selected_exp'] = iv5_data.get('selected_expiration')
                und_data_aggregates_to_update['tradier_iv_approx_actual_dte'] = iv5_data.get('actual_dte')
                und_data_aggregates_to_update['tradier_atm_call_smv_vol'] = iv5_data.get('atm_call_smv_vol')
                und_data_aggregates_to_update['tradier_atm_put_smv_vol'] = iv5_data.get('atm_put_smv_vol')

            elif iv5_data and iv5_data.get("error"):
                tradier_iv_logger.warning(f"Tradier returned an error for IV{target_dte_for_iv5} approximation for {symbol}: {iv5_data.get('error')}")
            else:
                tradier_iv_logger.warning(f"No IV{target_dte_for_iv5} approximation data returned from Tradier for {symbol}.")

            # Placeholder: Fetch other specific IVs if needed in the future
            # For example, you might want to fetch the full option chain for the nearest expiration
            # and extract bid_iv, mid_iv, ask_iv, smv_vol for specific ATM/OTM options.
            # This would require more logic to select strikes and parse the chain.
            # Example:
            # nearest_exp = self.tradier_data_fetcher.get_option_expirations(symbol)
            # if nearest_exp:
            #     chain = self.tradier_data_fetcher.get_option_chain(symbol, nearest_exp[0])
            #     # ... logic to find ATM option and extract greeks.bid_iv etc. ...
            #     # und_data_aggregates_to_update['tradier_atm_call_bid_iv'] = ...

        except Exception as e:
            tradier_iv_logger.error(f"Exception during Tradier IV metrics fetch/integration for {symbol}: {e}", exc_info=True)
    # --- END OF ADDED METHODS ---

    def map_score_to_stars(self, score: Optional[Union[float, int]], category: Optional[str] = None) -> int:
        """
        Maps a numerical conviction score to a star rating (0-5) based on configured thresholds.
        """
        score_val = 0.0
        if isinstance(score, (int, float)) and pd.notna(score) and np.isfinite(score): # Check for NaN and Inf
            score_val = float(score)
        
        # Ensure reco_config is loaded, use defaults if not.
        # These defaults should match what might be in a typical config.
        conv_map_5star = float(self.reco_config.get("conviction_map_high", 4.0)) 
        conv_map_4star = float(self.reco_config.get("conviction_map_high_medium", 3.0))
        conv_map_3star = float(self.reco_config.get("conviction_map_medium", 2.0))
        conv_map_2star = float(self.reco_config.get("conviction_map_medium_low", 1.0))
        conv_map_1star = float(self.reco_config.get("conviction_map_low", 0.5))
        
        if score_val >= conv_map_5star: return 5
        if score_val >= conv_map_4star: return 4
        if score_val >= conv_map_3star: return 3
        if score_val >= conv_map_2star: return 2
        if score_val >= conv_map_1star: return 1
        return 0

    def _get_atr(self, symbol: str, current_price: float, period: Optional[int] = None, current_trading_date: Optional[date] = None) -> float:
        """
        Retrieves ATR for a symbol. Delegates to MetricsCalculator, with robust fallbacks.
        """
        atr_logger_orch = self.logger.getChild(f"GetATR_Orch.{symbol}")
        
        if self.initialization_failed or not self.metrics_calculator or not hasattr(self.metrics_calculator, '_get_atr_internal'):
            atr_logger_orch.error(f"MetricsCalculator not available or lacks '_get_atr_internal'. Using default fallback ATR.")
            return max(current_price * DEFAULT_ATR_FALLBACK_PERCENTAGE_ORCH, DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH) if current_price > 0 else DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH
        
        date_for_hist_lookup = current_trading_date
        if date_for_hist_lookup is None:
            if self.last_analysis_timestamp: # Use timestamp from the current cycle if available
                date_for_hist_lookup = self.last_analysis_timestamp.date()
            else: 
                date_for_hist_lookup = date.today() # Absolute fallback
                atr_logger_orch.warning(f"No current_trading_date or last_analysis_timestamp for ATR. Using today ({date_for_hist_lookup}). This might affect historical data accuracy.")

        # Get default ATR period from config if not provided
        default_atr_period_orch = int(self._get_config_value_its(["data_processor_settings", "approximations", "generic_atr_period"], 14))
        atr_period_to_use = period if period is not None and period > 0 else default_atr_period_orch
        
        try:
            # Delegate to MetricsCalculator's internal ATR method
            calculated_atr = self.metrics_calculator._get_atr_internal(
                symbol=symbol, 
                current_price=current_price, 
                period=atr_period_to_use, 
                current_trading_date=date_for_hist_lookup
            )
            if pd.isna(calculated_atr) or not np.isfinite(calculated_atr) or calculated_atr <= EPSILON_ORCH:
                 atr_logger_orch.warning(f"MetricsCalculator returned invalid ATR ({calculated_atr}). Using fallback.") # Corrected logger name
                 return max(current_price * DEFAULT_ATR_FALLBACK_PERCENTAGE_ORCH, DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH) if current_price > 0 else DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH
            return calculated_atr
        except Exception as e_atr_mc_call:
            atr_logger_orch.error(f"Error calling MetricsCalculator._get_atr_internal: {e_atr_mc_call}. Using fallback ATR.", exc_info=True)
            return max(current_price * DEFAULT_ATR_FALLBACK_PERCENTAGE_ORCH, DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH) if current_price > 0 else DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH
            
    def _get_threshold_its(self, threshold_name_in_config: str, 
                           default_static_value_override: Optional[Union[float, List[float]]] = None
                           ) -> Optional[Union[float, List[float]]]:
        """
        Retrieves a threshold value for use within the orchestrator or its components.
        Priority:
        1. Dynamically resolved value from self.resolved_dynamic_thresholds_cache.
        2. Static 'value' from self.threshold_configs_orch[threshold_name_in_config] (if type is 'fixed').
        3. Static 'fallback_value' from self.threshold_configs_orch[threshold_name_in_config] (if type is dynamic but not resolved).
        4. Programmer-provided default_static_value_override.
        5. None if not found.
        """
        # Check pre-resolved dynamic thresholds cache first
        if threshold_name_in_config in self.resolved_dynamic_thresholds_cache:
            val = self.resolved_dynamic_thresholds_cache[threshold_name_in_config]
            if val is not None: # Ensure it's not None from a failed dynamic resolution
                self.logger.debug(f"ITSOrch: Using cached dynamic/resolved threshold '{threshold_name_in_config}' = {val}")
                return val 
            # If it was None in cache, it means dynamic resolution failed, proceed to static fallbacks.
        
        # Fallback to static configuration from self.threshold_configs_orch (loaded from strategy_settings.thresholds)
        threshold_definition_dict = self.threshold_configs_orch.get(threshold_name_in_config) 
        
        if isinstance(threshold_definition_dict, dict):
            # If it's a "fixed" type, use its "value"
            if threshold_definition_dict.get("type") == "fixed":
                fixed_val = threshold_definition_dict.get("value")
                if fixed_val is not None:
                    self.logger.debug(f"ITSOrch: Using static fixed threshold '{threshold_name_in_config}' = {fixed_val}")
                    try: return float(fixed_val)
                    except (ValueError, TypeError): self.logger.warning(f"ITSOrch: Invalid 'value' for static fixed threshold '{threshold_name_in_config}'.")
            
            # For any type (fixed or dynamic), if "value" wasn't used/applicable, try "fallback_value"
            # This is the primary fallback if dynamic resolution failed or if it's a fixed threshold without a "value" key
            fallback_val = threshold_definition_dict.get("fallback_value")
            if fallback_val is not None:
                 self.logger.debug(f"ITSOrch: Using 'fallback_value' for threshold '{threshold_name_in_config}' = {fallback_val}.")
                 try: return float(fallback_val)
                 except (ValueError, TypeError): self.logger.warning(f"ITSOrch: Invalid 'fallback_value' for threshold '{threshold_name_in_config}'.")

        # Fallback to programmer's default if provided to this function
        if default_static_value_override is not None:
            self.logger.debug(f"ITSOrch: Using programmer default for '{threshold_name_in_config}' = {default_static_value_override}")
            return default_static_value_override 
            
        self.logger.warning(f"ITSOrch: Threshold '{threshold_name_in_config}' not found in cache or static config (value/fallback_value), and no programmer default. Returning None.")
        return None

    def _calculate_dynamic_threshold_core_logic(self, 
                                               threshold_params_dict: Dict[str, Any], 
                                               historical_metric_series: pd.Series,
                                               comparison_mode_hint: str = "value" # From strategy_settings.thresholds.X.comparison_mode
                                               ) -> Optional[Union[float, List[float]]]:
        """
        Core logic for calculating a single dynamic threshold value from a historical series.
        Handles percentile and mean_factor types, and applies abs/abs_neg modifiers.
        """
        calc_logger_dyn = self.logger.getChild("DynamicThresholdCore_ITS")
        threshold_type = threshold_params_dict.get("type")
        metric_hist_key = threshold_params_dict.get("history_key", "UnknownMetric_ITS") # For logging
        
        if not isinstance(historical_metric_series, pd.Series) or historical_metric_series.empty:
            calc_logger_dyn.debug(f"Cannot calculate dynamic threshold for '{metric_hist_key}' (type '{threshold_type}'), historical series is empty or not a Series.")
            return None
        
        # Ensure series is numeric and drop NaNs for calculations
        series_for_calc_numeric = pd.to_numeric(historical_metric_series, errors='coerce').dropna()
        if series_for_calc_numeric.empty:
            calc_logger_dyn.debug(f"Historical series for '{metric_hist_key}' became empty after numeric conversion and NaN drop. Cannot calculate dynamic threshold.")
            return None

        try:
            # Apply absolute value modifications based on comparison_mode_hint
            # This hint comes from the threshold definition (e.g., strategy_settings.thresholds.X.comparison_mode)
            # or is parsed from MRE dynamic_threshold_references (e.g., [PERCENTILE=85_ABS])
            is_abs_modifier = "_ABS" in comparison_mode_hint.upper() and not "_ABS_NEG" in comparison_mode_hint.upper()
            is_abs_neg_modifier = "_ABS_NEG" in comparison_mode_hint.upper()
            
            series_to_use_for_calc = series_for_calc_numeric.copy()
            if is_abs_modifier or is_abs_neg_modifier:
                series_to_use_for_calc = series_to_use_for_calc.abs()

            calculated_value: Optional[Union[float, List[float]]] = None # Type hint for clarity
            if threshold_type == "relative_percentile":
                percentile_val_cfg = threshold_params_dict.get("percentile")
                if percentile_val_cfg is None: 
                    calc_logger_dyn.warning(f"Missing 'percentile' in config for '{metric_hist_key}'."); return None
                percentile = float(percentile_val_cfg)
                percentile = max(0.0, min(100.0, percentile)) # Ensure valid percentile range
                calculated_value = np.percentile(series_to_use_for_calc, percentile)
            
            elif threshold_type == "relative_mean_factor":
                # This type can use either 'factor' or 'num_std_devs'
                factor_val_cfg = threshold_params_dict.get("factor")
                num_std_devs_cfg = threshold_params_dict.get("num_std_devs")
                
                if num_std_devs_cfg is not None: # Prioritize num_std_devs if present
                    num_std_devs = float(num_std_devs_cfg)
                    mean_val = series_to_use_for_calc.mean()
                    std_dev_val = series_to_use_for_calc.std()
                    if pd.isna(mean_val) or pd.isna(std_dev_val): calc_logger_dyn.warning(f"Mean/StdDev NaN for '{metric_hist_key}'."); return None
                    calculated_value = mean_val + (num_std_devs * std_dev_val)
                elif factor_val_cfg is not None:
                    factor = float(factor_val_cfg)
                    mean_val = series_to_use_for_calc.mean()
                    if pd.isna(mean_val): calc_logger_dyn.warning(f"Mean NaN for '{metric_hist_key}'."); return None
                    calculated_value = mean_val * factor
                else:
                    calc_logger_dyn.warning(f"Missing 'factor' or 'num_std_devs' for relative_mean_factor type for '{metric_hist_key}'."); return None
            else:
                calc_logger_dyn.warning(f"Unsupported dynamic threshold type: '{threshold_type}' for metric '{metric_hist_key}'."); return None
            
            # Final checks and application of negative sign if needed
            if pd.notna(calculated_value) and np.isfinite(calculated_value): # Check for NaN/Inf
                final_val = float(calculated_value) # Ensure it's a standard float
                if is_abs_neg_modifier: 
                    final_val = -abs(final_val) # Apply negation after calculation on absolute series
                return final_val
            else: 
                calc_logger_dyn.warning(f"Calculated dynamic threshold for '{metric_hist_key}' is invalid (NaN/Inf): {calculated_value}"); return None
        
        except Exception as e:
            calc_logger_dyn.error(f"Error calculating dynamic threshold for '{metric_hist_key}' (type '{threshold_type}'): {e}", exc_info=True); return None

    def _resolve_all_dynamic_thresholds_for_cycle(self, symbol_context_for_hist: Optional[str], current_date_for_hist_lookup: date) -> None:
        """
        Resolves all dynamic thresholds defined in the configuration for the current analysis cycle.
        Populates self.resolved_dynamic_thresholds_cache.
        Uses self.historical_data_manager to fetch historical metric series.
        """
        dyn_res_logger = self.logger.getChild(f"ResolveAllDynThresh.{symbol_context_for_hist or 'GENERAL'}")
        self.resolved_dynamic_thresholds_cache.clear() # Clear cache for the new cycle
        
        if self.initialization_failed or not self.historical_data_manager or not hasattr(self.historical_data_manager, 'get_metric_distribution_for_threshold'):
            dyn_res_logger.warning("HistoricalDataManager not available/valid. ALL dynamic thresholds will use their static fallbacks from config.")
            # Populate cache with fallbacks for all known dynamic threshold keys
            for thresh_key, thresh_def in self.threshold_configs_orch.items(): 
                if isinstance(thresh_def, dict) and thresh_def.get("type", "fixed") != "fixed":
                    self.resolved_dynamic_thresholds_cache[thresh_key] = thresh_def.get("fallback_value")
            
            mre_dyn_refs_for_fallback = self.mre_config_orch.get("dynamic_threshold_references_for_mre", {})
            if isinstance(mre_dyn_refs_for_fallback, dict):
                for mre_var_name in mre_dyn_refs_for_fallback.keys():
                    if mre_var_name not in self.resolved_dynamic_thresholds_cache: 
                        self.resolved_dynamic_thresholds_cache[mre_var_name] = None # Default to None if no specific fallback
            dyn_res_logger.debug(f"Dynamic threshold cache populated with fallbacks only due to HDM issue. Size: {len(self.resolved_dynamic_thresholds_cache)}")
            return

        min_hist_len_for_calc = self.min_hist_for_dyn_thresh 
        days_history_to_fetch_val = int(self._get_config_value_its(["system_settings", "metric_history_days_for_dynamic_thresholds"], 60))

        # --- Part 1: Resolve dynamic thresholds defined in 'strategy_settings.thresholds' ---
        dyn_res_logger.debug(f"Resolving dynamic thresholds from 'strategy_settings.thresholds' (count: {len(self.threshold_configs_orch)})...")
        for thresh_key_from_config, thresh_params_from_config in self.threshold_configs_orch.items():
            if not isinstance(thresh_params_from_config, dict) or thresh_params_from_config.get("type", "fixed") == "fixed":
                # This is a static threshold, its value is directly in the config or will be handled by _get_threshold_its
                # No dynamic resolution needed here, but ensure it's in cache if it's a fixed value for MRE to use.
                if isinstance(thresh_params_from_config, dict) and "value" in thresh_params_from_config:
                     self.resolved_dynamic_thresholds_cache[thresh_key_from_config] = thresh_params_from_config.get("value")
                continue # Skip to next if not a dynamic type

            metric_history_key_name = thresh_params_from_config.get("history_key")
            if not metric_history_key_name:
                self.resolved_dynamic_thresholds_cache[thresh_key_from_config] = thresh_params_from_config.get("fallback_value")
                dyn_res_logger.warning(f"Dynamic threshold '{thresh_key_from_config}' (strat_settings) missing 'history_key'. Using its fallback: {self.resolved_dynamic_thresholds_cache[thresh_key_from_config]}.")
                continue
            
            # Fetch or use cached historical series
            if metric_history_key_name not in self.metric_history_series_for_thresholds or \
               self.metric_history_series_for_thresholds[metric_history_key_name] is None or \
               len(self.metric_history_series_for_thresholds[metric_history_key_name]) < min_hist_len_for_calc: 
                
                fetched_hist_series = self.historical_data_manager.get_metric_distribution_for_threshold(
                    symbol=symbol_context_for_hist, metric_key=metric_history_key_name, 
                    days_history=days_history_to_fetch_val, current_trading_date=current_date_for_hist_lookup
                )
                self.metric_history_series_for_thresholds[metric_history_key_name] = fetched_hist_series if fetched_hist_series is not None else pd.Series(dtype=float)
            
            hist_series_for_calc = self.metric_history_series_for_thresholds[metric_history_key_name]
            cleaned_hist_series_for_calc = pd.to_numeric(hist_series_for_calc, errors='coerce').dropna() if hist_series_for_calc is not None else pd.Series(dtype=float)
            
            if len(cleaned_hist_series_for_calc) < min_hist_len_for_calc:
                self.resolved_dynamic_thresholds_cache[thresh_key_from_config] = thresh_params_from_config.get("fallback_value")
                dyn_res_logger.debug(f"Insufficient/empty history for '{metric_history_key_name}' ({len(cleaned_hist_series_for_calc) if cleaned_hist_series_for_calc is not None else 0 }<{min_hist_len_for_calc}). Using fallback for '{thresh_key_from_config}': {self.resolved_dynamic_thresholds_cache[thresh_key_from_config]}.")
            else:
                comparison_mode_val = thresh_params_from_config.get("comparison_mode", "value") 
                calculated_dyn_val = self._calculate_dynamic_threshold_core_logic(thresh_params_from_config, cleaned_hist_series_for_calc, comparison_mode_val)
                self.resolved_dynamic_thresholds_cache[thresh_key_from_config] = calculated_dyn_val if calculated_dyn_val is not None else thresh_params_from_config.get("fallback_value")
                if calculated_dyn_val is not None: dyn_res_logger.debug(f"Resolved strat_thresh '{thresh_key_from_config}' (metric '{metric_history_key_name}') to {calculated_dyn_val:.4f}")
                else: dyn_res_logger.debug(f"Failed to calc strat_thresh '{thresh_key_from_config}', using fallback: {self.resolved_dynamic_thresholds_cache[thresh_key_from_config]}")
        
        # --- Part 2: Resolve dynamic thresholds defined in 'market_regime_engine_settings.dynamic_threshold_references_for_mre' ---
        mre_dyn_refs_config = self.mre_config_orch.get("dynamic_threshold_references_for_mre", {})
        dyn_res_logger.debug(f"Resolving MRE-specific dynamic thresholds (count: {len(mre_dyn_refs_config)})...")

        if isinstance(mre_dyn_refs_config, dict):
            for mre_threshold_variable_name, metric_ref_and_op_str in mre_dyn_refs_config.items():
                if not isinstance(metric_ref_and_op_str, str): 
                    dyn_res_logger.warning(f"Invalid MRE dynamic ref for '{mre_threshold_variable_name}': '{metric_ref_and_op_str}' not a string. Skipping."); continue

                # Regex to parse: MetricName[OPERATION=Value_Modifier] e.g., GIB_OI_based_Und[PERCENTILE=10_ABS_NEG]
                match_mre_dyn_ref = re.match(r"([a-zA-Z0-9_.:@\[\]]+)\[([A-Z]+)=([\d\.]+(?:_ABS|_ABS_NEG)?)\]", metric_ref_and_op_str)
                if not match_mre_dyn_ref:
                    dyn_res_logger.warning(f"Could not parse MRE dynamic threshold ref string for '{mre_threshold_variable_name}': '{metric_ref_and_op_str}'.")
                    self.resolved_dynamic_thresholds_cache[mre_threshold_variable_name] = None 
                    continue

                mre_hist_metric_key_name = match_mre_dyn_ref.group(1) 
                mre_op_type_str = match_mre_dyn_ref.group(2).upper() # Ensure uppercase for matching       
                mre_op_value_with_modifier_str = match_mre_dyn_ref.group(3) 
                
                # Construct a temporary threshold definition dict for _calculate_dynamic_threshold_core_logic
                temp_mre_thresh_definition: Dict[str, Any] = {"history_key": mre_hist_metric_key_name, "fallback_value": None} 
                
                comparison_mode_for_core_logic = "value" # Default
                op_value_for_core_logic_str = mre_op_value_with_modifier_str
                if mre_op_value_with_modifier_str.endswith("_ABS_NEG"):
                    comparison_mode_for_core_logic = "abs_neg_value"
                    op_value_for_core_logic_str = mre_op_value_with_modifier_str[:-len("_ABS_NEG")]
                elif mre_op_value_with_modifier_str.endswith("_ABS"):
                    comparison_mode_for_core_logic = "abs_value"
                    op_value_for_core_logic_str = mre_op_value_with_modifier_str[:-len("_ABS")]

                try:
                    op_numeric_value = float(op_value_for_core_logic_str)
                except ValueError:
                    dyn_res_logger.warning(f"Invalid numeric part '{op_value_for_core_logic_str}' in MRE dyn_ref '{mre_threshold_variable_name}'. Skipping.")
                    self.resolved_dynamic_thresholds_cache[mre_threshold_variable_name] = None; continue

                if mre_op_type_str == "PERCENTILE":
                    temp_mre_thresh_definition["type"] = "relative_percentile"
                    temp_mre_thresh_definition["percentile"] = op_numeric_value
                elif mre_op_type_str == "MEAN_FACTOR": # Assumes 'factor' if no 'num_std_devs'
                    temp_mre_thresh_definition["type"] = "relative_mean_factor"
                    temp_mre_thresh_definition["factor"] = op_numeric_value 
                # Add other MRE specific operation types if needed (e.g., "STD_DEVS_FROM_MEAN")
                else: 
                    dyn_res_logger.warning(f"Unsupported op_type '{mre_op_type_str}' in MRE dyn_ref for '{mre_threshold_variable_name}'. Skipping.")
                    self.resolved_dynamic_thresholds_cache[mre_threshold_variable_name] = None; continue
                
                # Fetch or use cached historical series for this MRE-specific metric
                if mre_hist_metric_key_name not in self.metric_history_series_for_thresholds or \
                   self.metric_history_series_for_thresholds[mre_hist_metric_key_name] is None or \
                   len(self.metric_history_series_for_thresholds[mre_hist_metric_key_name]) < min_hist_len_for_calc:
                    
                    fetched_hist_series_mre_hdm = self.historical_data_manager.get_metric_distribution_for_threshold(
                        symbol=symbol_context_for_hist, metric_key=mre_hist_metric_key_name, 
                        days_history=days_history_to_fetch_val, current_trading_date=current_date_for_hist_lookup
                    )
                    self.metric_history_series_for_thresholds[mre_hist_metric_key_name] = fetched_hist_series_mre_hdm if fetched_hist_series_mre_hdm is not None else pd.Series(dtype=float)

                hist_series_for_mre_calc = self.metric_history_series_for_thresholds[mre_hist_metric_key_name]
                cleaned_hist_series_mre_calc = pd.to_numeric(hist_series_for_mre_calc, errors='coerce').dropna() if hist_series_for_mre_calc is not None else pd.Series(dtype=float)

                if len(cleaned_hist_series_mre_calc) < min_hist_len_for_calc:
                    self.resolved_dynamic_thresholds_cache[mre_threshold_variable_name] = None # Fallback is None for MRE-specific if history fails
                    dyn_res_logger.warning(f"Insufficient history for MRE dyn_ref '{mre_hist_metric_key_name}'. '{mre_threshold_variable_name}' set to None.")
                else:
                    calculated_mre_dyn_val = self._calculate_dynamic_threshold_core_logic(temp_mre_thresh_definition, cleaned_hist_series_mre_calc, comparison_mode_for_core_logic)
                    self.resolved_dynamic_thresholds_cache[mre_threshold_variable_name] = calculated_mre_dyn_val 
                    if calculated_mre_dyn_val is not None:
                        dyn_res_logger.info(f"Resolved MRE dyn_thresh '{mre_threshold_variable_name}' (from {metric_ref_and_op_str}) to {calculated_mre_dyn_val:.4f}")
                    else:
                        dyn_res_logger.warning(f"Failed to calculate MRE dyn_thresh for '{mre_threshold_variable_name}' (from {metric_ref_and_op_str}). Set to None.")
        
        dyn_res_logger.info(f"All dynamic thresholds resolved for cycle {symbol_context_for_hist}. Final cache size: {len(self.resolved_dynamic_thresholds_cache)}")        
          
    def run_analysis_cycle_v2_4(
        self,
        symbol: str,                                
        raw_options_df_from_fetcher: pd.DataFrame,
        raw_underlying_data_dict_from_fetcher: Dict[str, Any], # From ConvexValue fetcher
        current_processing_datetime: datetime       
    ) -> Dict[str, Any]:
        cycle_logger = self.logger.getChild(f"RunAnalysisCycle.{symbol}")
        cycle_logger.info(f"--- Orchestrator: Starting Analysis Cycle for '{symbol}' at {current_processing_datetime.isoformat()} ---")
        self.last_analysis_timestamp = current_processing_datetime

        # Initialize variables that will hold the main data products of the cycle
        df_chain_all_metrics_output: pd.DataFrame = pd.DataFrame()      # Renamed for clarity within this scope
        df_strike_all_metrics_output: pd.DataFrame = pd.DataFrame()     # Renamed for clarity
        und_data_enriched_output: Dict[str, Any] = {}                 # Renamed for clarity
        generated_signals_this_cycle: Dict[str, Dict[str, List[Dict[str,Any]]]] = {
            'directional': {'bullish': [], 'bearish': []}, 
            'volatility': {'expansion': [], 'contraction': []}, 
            'time_decay': {'pin_risk': [], 'charm_cascade': []}, 
            'complex': {'structure_change': [], 'flow_divergence': [], 'sdag_conviction': []},
            'v2_4_new': {
                'vanna_cascade_alert': [], 'volatility_skew_shift_alert': [],
                'eod_hedging_pressure': [], 'bubble_warning_signal': [],
                'rolling_flow_momentum_signal': [], 'unusual_customer_greek_flow_signal': []
            }
        }
        
        processed_data_bundle_from_idp: Optional[Dict[str, Any]] = None
        
        fetcher_error_message_from_input: Optional[str] = raw_underlying_data_dict_from_fetcher.get("error") if isinstance(raw_underlying_data_dict_from_fetcher, dict) else None

        if self.initialization_failed:
            cycle_logger.critical(f"Analysis cycle for {symbol} aborted: Orchestrator initialization previously failed.")
            return self._create_empty_analysis_bundle("Orchestrator Initialization Failed")

        if self.current_symbol_being_managed != symbol:
            cycle_logger.info(f"Symbol changed from '{self.current_symbol_being_managed}' to '{symbol}'. Resetting active recommendations and caches.")
            self.active_recommendations = []
            if self.recommendation_generator and hasattr(self.recommendation_generator, 'recommendation_id_counter'):
                self.recommendation_generator.recommendation_id_counter = 0
            self.current_symbol_being_managed = symbol
            if hasattr(self, 'metric_history_series_for_thresholds'): self.metric_history_series_for_thresholds.clear()
            self.resolved_dynamic_thresholds_cache.clear()
            self.processed_strike_df_history.clear()
            self.processed_und_data_history.clear()

        current_cycle_underlying_data = raw_underlying_data_dict_from_fetcher.copy() if isinstance(raw_underlying_data_dict_from_fetcher, dict) else {}
        if 'symbol' not in current_cycle_underlying_data and symbol : current_cycle_underlying_data['symbol'] = symbol

        if self.tradier_data_fetcher:
            cycle_logger.info(f"[{symbol}] Step 0.A: Fetching and storing HISTORICAL OHLCV data from Tradier (if needed by HDM)...")
            # This call ensures your historical Parquet files are up-to-date for ATR.
            # It fetches a lookback, not just today's snapshot.
            self._fetch_and_store_tradier_ohlcv(symbol, current_processing_datetime) 
            
            cycle_logger.info(f"[{symbol}] Step 0.B: Fetching and integrating specific IV APPROXIMATION metrics from Tradier...")
            # This fetches things like IV5_approx and adds them to current_cycle_underlying_data
            self._fetch_and_integrate_tradier_iv_metrics(symbol, current_cycle_underlying_data)
        # --- End call to existing Tradier methods ---

        # vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
        # --- START: Tradier Integration for CURRENT DAY'S OHLCV SNAPSHOT (NEW SNIPPET PLACEMENT) ---
        # This part fetches the *latest daily quote* from Tradier to ensure
        # open, high, low, last (as close), volume for the *current processing snapshot*
        # are as accurate as possible and updates current_cycle_underlying_data.
        # This is crucial for HP_EOD and MetricsCalculator's _ensure_ohlcv_fallbacks.
        tradier_integration_logger = self.logger.getChild(f"TradierSnapshotInt.{symbol}") # Local logger for this block
        if self.tradier_data_fetcher and hasattr(self.tradier_data_fetcher, 'get_underlying_quote'):
            tradier_integration_logger.info(f"Attempting to fetch current day's OHLCV snapshot from Tradier for {symbol} to augment main underlying data.")
            tradier_quote_snapshot = self.tradier_data_fetcher.get_underlying_quote(symbol)

            if tradier_quote_snapshot and not tradier_quote_snapshot.get("error"):
                tradier_integration_logger.debug(f"Tradier quote snapshot received: {tradier_quote_snapshot}")
                greeks_und_map = self._get_config_value_its(["strategy_settings", "greeks_from_und"], {})
                if not isinstance(greeks_und_map, dict): 
                    greeks_und_map = {}
                    tradier_integration_logger.error("Config 'strategy_settings.greeks_from_und' is not a dict. Using empty map for Tradier OHLCV keys. This will cause issues.")

                ohlcv_conceptual_to_actual_keys = {
                    "day_open_price_und": greeks_und_map.get("day_open_price_und", "day_open_price"),
                    "day_high_price_und": greeks_und_map.get("day_high_price_und", "day_high_price"),
                    "day_low_price_und": greeks_und_map.get("day_low_price_und", "day_low_price"),
                    "day_close_price_und": greeks_und_map.get("day_close_price_und", "day_close_price"),
                    "day_volume_und": greeks_und_map.get("day_volume_und", "day_volume")
                }
                main_price_key = self.col_und_price_orch 

                def get_tradier_val(tradier_key: str, data_type: type = float):
                    val = tradier_quote_snapshot.get(tradier_key)
                    if val is None: return None
                    try:
                        if data_type == float: return float(val)
                        if data_type == int: return int(float(val))
                        return val
                    except (ValueError, TypeError):
                        tradier_integration_logger.warning(f"Could not convert Tradier value for '{tradier_key}' ('{val}') to {data_type}.")
                        return None

                current_cycle_underlying_data[ohlcv_conceptual_to_actual_keys["day_open_price_und"]] = get_tradier_val('open')
                current_cycle_underlying_data[ohlcv_conceptual_to_actual_keys["day_high_price_und"]] = get_tradier_val('high')
                current_cycle_underlying_data[ohlcv_conceptual_to_actual_keys["day_low_price_und"]] = get_tradier_val('low')
                current_cycle_underlying_data[ohlcv_conceptual_to_actual_keys["day_volume_und"]] = get_tradier_val('volume', int)

                tradier_last_price = get_tradier_val('last')
                if tradier_last_price is not None:
                    current_cycle_underlying_data[ohlcv_conceptual_to_actual_keys["day_close_price_und"]] = tradier_last_price
                    current_cycle_underlying_data[main_price_key] = tradier_last_price
                    tradier_integration_logger.info(f"[{symbol}] Main underlying price field '{main_price_key}' updated with Tradier 'last': {tradier_last_price:.2f}")
                else:
                    existing_main_price = current_cycle_underlying_data.get(main_price_key)
                    if existing_main_price is not None:
                        current_cycle_underlying_data[ohlcv_conceptual_to_actual_keys["day_close_price_und"]] = existing_main_price
                        tradier_integration_logger.warning(f"[{symbol}] Tradier 'last' price is None. Using existing main price '{existing_main_price}' for conceptual 'day_close_price_und'.")
                    else:
                        current_cycle_underlying_data[ohlcv_conceptual_to_actual_keys["day_close_price_und"]] = None
                        tradier_integration_logger.error(f"[{symbol}] Tradier 'last' price AND existing main price are None. Conceptual 'day_close_price_und' set to None. This will cause issues for HP_EOD reference if day_close is used.")
                
                log_msg_ohlcv_new_snippet = (
                    f"[{symbol}] Tradier SNAPSHOT OHLCV integrated into current_cycle_underlying_data: "
                    f"Open({ohlcv_conceptual_to_actual_keys['day_open_price_und']}): {current_cycle_underlying_data.get(ohlcv_conceptual_to_actual_keys['day_open_price_und'])}, "
                    f"High({ohlcv_conceptual_to_actual_keys['day_high_price_und']}): {current_cycle_underlying_data.get(ohlcv_conceptual_to_actual_keys['day_high_price_und'])}, "
                    f"Low({ohlcv_conceptual_to_actual_keys['day_low_price_und']}): {current_cycle_underlying_data.get(ohlcv_conceptual_to_actual_keys['day_low_price_und'])}, "
                    f"Close({ohlcv_conceptual_to_actual_keys['day_close_price_und']}): {current_cycle_underlying_data.get(ohlcv_conceptual_to_actual_keys['day_close_price_und'])}, "
                    f"Volume({ohlcv_conceptual_to_actual_keys['day_volume_und']}): {current_cycle_underlying_data.get(ohlcv_conceptual_to_actual_keys['day_volume_und'])}. "
                    f"Main Price Field ('{main_price_key}') now: {current_cycle_underlying_data.get(main_price_key)}"
                )
                tradier_integration_logger.info(log_msg_ohlcv_new_snippet)

            elif tradier_quote_snapshot: 
                tradier_integration_logger.warning(f"[{symbol}] Tradier quote fetch for snapshot returned an error: {tradier_quote_snapshot.get('error')}. MetricsCalculator will rely on fallbacks for current day's OHLCV.")
            else: 
                tradier_integration_logger.warning(f"[{symbol}] No valid quote data returned from Tradier for current snapshot OHLCV. MetricsCalculator will rely on fallbacks.")
        else:
            tradier_integration_logger.warning(f"[{symbol}] TradierDataFetcher not available or configured. Skipping current day OHLCV snapshot fetch from Tradier. MetricsCalculator fallbacks will be critical.")
        # --- END: Tradier Integration for CURRENT DAY'S OHLCV SNAPSHOT ---
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


        cycle_logger.info(f"[{symbol}] Step 1: Initiating Initial Data Processing (which includes Metrics Calculation)...")
        if not self.initial_data_processor or not hasattr(self.initial_data_processor, 'process_option_chain_snapshot_v2_4'):
            # ... (handle missing initial_data_processor) ...
            return self._create_empty_analysis_bundle("InitialDataProcessor component missing")
        
        try:
            # `current_cycle_underlying_data` now contains ConvexValue data + Tradier snapshot OHLCV + Tradier IV approx
            processed_data_bundle_from_idp = self.initial_data_processor.process_option_chain_snapshot_v2_4(
                options_df_raw=raw_options_df_from_fetcher, 
                underlying_data_raw=current_cycle_underlying_data, # This is the crucial dictionary
                current_time_dt=current_processing_datetime,
                symbol=symbol
            )
        except Exception as e_idp_call: 
            # ... (handle exception during IDP call) ...
            return self._create_empty_analysis_bundle(f"InitialDataProcessor Call Failed: {str(e_idp_call)[:100]}")

        if not processed_data_bundle_from_idp or "ERROR" in processed_data_bundle_from_idp.get("status","").upper():
            err_msg_idp_status = processed_data_bundle_from_idp.get("error_message", "Unknown error in IDP") if processed_data_bundle_from_idp else "IDP returned None"
            cycle_logger.error(f"IDP & Metrics Calc FAILED for {symbol}: {err_msg_idp_status}")
            # Initialize to empty DataFrames/dict if IDP failed before these were assigned
            df_chain_all_metrics_output = pd.DataFrame()
            df_strike_all_metrics_output = pd.DataFrame()
            und_data_enriched_output = current_cycle_underlying_data.copy() # Start with what we had
            if isinstance(und_data_enriched_output, dict): # Ensure it's a dict
                und_data_enriched_output['error_idp_metrics'] = err_msg_idp_status # Add specific error
            # No early return here, let it flow to Step 10 to package an error bundle
        else:
            # **THIS IS THE CRITICAL ASSIGNMENT**
            df_chain_all_metrics_output = processed_data_bundle_from_idp.get("options_df_with_metrics_obj", pd.DataFrame())
            df_strike_all_metrics_output = processed_data_bundle_from_idp.get("df_strike_level_metrics_obj", pd.DataFrame())
            und_data_enriched_output = processed_data_bundle_from_idp.get("underlying_data_enriched_obj", current_cycle_underlying_data.copy())

        current_price_after_idp = und_data_enriched_output.get(self.col_und_price_orch)
        if not isinstance(und_data_enriched_output, dict) or not und_data_enriched_output or \
           current_price_after_idp is None or pd.isna(current_price_after_idp) or float(current_price_after_idp) <= 0:
            err_msg_no_und_price_after_idp = f"Critical: Enriched underlying data for {symbol} missing/invalid price after IDP/Metrics. Price: {current_price_after_idp}"
            cycle_logger.error(err_msg_no_und_price_after_idp)
            # If IDP/Metrics succeeded but somehow lost price, this is also a critical failure for subsequent steps.
            # Use the error from IDP if it exists, otherwise use this new one.
            idp_error = processed_data_bundle_from_idp.get("error_message") if processed_data_bundle_from_idp else None
            return self._create_empty_analysis_bundle(idp_error or err_msg_no_und_price_after_idp)

        cycle_logger.info(f"[{symbol}] Step 1 (Initial Data Processing & Metrics Calculation) complete.")
        cycle_logger.debug(f"  df_chain_all_metrics_output shape: {df_chain_all_metrics_output.shape}")
        cycle_logger.debug(f"  df_strike_all_metrics_output shape: {df_strike_all_metrics_output.shape}")
        cycle_logger.debug(f"  und_data_enriched_output keys count: {len(und_data_enriched_output.keys())}")

        if isinstance(df_strike_all_metrics_output, pd.DataFrame) and not df_strike_all_metrics_output.empty:
            self.processed_strike_df_history.append(df_strike_all_metrics_output.copy(deep=True))
        if isinstance(und_data_enriched_output, dict) and und_data_enriched_output: 
            self.processed_und_data_history.append(und_data_enriched_output.copy())
        cycle_logger.info(f"[{symbol}] Step 2 (Update short-term history deques) complete.")

        cycle_logger.info(f"[{symbol}] Step 3: Resolving all dynamic thresholds...")
        self._resolve_all_dynamic_thresholds_for_cycle(symbol, current_processing_datetime.date())
        cycle_logger.info(f"[{symbol}] Step 3 (Resolve Dynamic Thresholds) complete.")

        cycle_logger.info(f"[{symbol}] Step 4: Determining Market Regime...")
        if not self.market_regime_engine or not hasattr(self.market_regime_engine, 'determine_market_regime_v2_4'):
            self.current_market_regime = self._get_config_value_its(["market_regime_engine_settings", "default_regime"], "REGIME_ERROR_MRE_UNAVAILABLE")
            if isinstance(und_data_enriched_output, dict): und_data_enriched_output['current_market_regime'] = self.current_market_regime
        else:
            try:
                if 'current_processing_dte_context' not in und_data_enriched_output:
                     if isinstance(df_chain_all_metrics_output, pd.DataFrame) and not df_chain_all_metrics_output.empty and 'dte_calc' in df_chain_all_metrics_output.columns:
                         min_dte_val = df_chain_all_metrics_output['dte_calc'].min()
                         und_data_enriched_output['current_processing_dte_context'] = int(min_dte_val) if pd.notna(min_dte_val) else -1 
                     else: und_data_enriched_output['current_processing_dte_context'] = -1
                
                self.current_market_regime = self.market_regime_engine.determine_market_regime_v2_4(
                    und_data_aggregates=und_data_enriched_output, 
                    df_strike_level_metrics=df_strike_all_metrics_output,
                    current_time_dt=current_processing_datetime, 
                    symbol_context=symbol,
                    resolved_dynamic_thresholds_from_orchestrator=self.resolved_dynamic_thresholds_cache
                )
                und_data_enriched_output['current_market_regime'] = self.current_market_regime
            except Exception as e_mre_call:
                 self.current_market_regime = self._get_config_value_its(["market_regime_engine_settings", "default_regime"], "REGIME_ERROR_MRE_CALL")
                 if isinstance(und_data_enriched_output, dict): und_data_enriched_output['current_market_regime'] = self.current_market_regime
        cycle_logger.info(f"[{symbol}] Market Regime classified as: '{self.current_market_regime}'.")
        
        cycle_logger.info(f"[{symbol}] Step 5: Generating Trading Signals...")
        if not self.signal_generator or not hasattr(self.signal_generator, 'generate_all_signals_v2_4'):
             # generated_signals_this_cycle remains as initialized (empty structure)
             if isinstance(und_data_enriched_output, dict): und_data_enriched_output["error_signal_generation"] = "SignalGenerator unavailable"
        else:
            try:
                generated_signals_this_cycle = self.signal_generator.generate_all_signals_v2_4(
                    df_metrics_strike_level=df_strike_all_metrics_output,
                    und_data_aggregates=und_data_enriched_output,
                    current_market_regime=self.current_market_regime, 
                    current_time_dt=current_processing_datetime, 
                    resolved_dynamic_thresholds=self.resolved_dynamic_thresholds_cache
                )
            except Exception as e_sg_call:
                 if isinstance(und_data_enriched_output, dict): und_data_enriched_output["error_signal_generation"] = str(e_sg_call)
        cycle_logger.info(f"[{symbol}] Step 5 (Signal Generation) complete.")    
        
        cycle_logger.info(f"[{symbol}] Step 6: Formulating Recommendations...")
        pending_recommendations_this_cycle: List[Dict[str, Any]] = [] 
        if not self.recommendation_generator or not hasattr(self.recommendation_generator, 'formulate_recommendations_v2_4'):
            if isinstance(und_data_enriched_output, dict): und_data_enriched_output["error_recommendation_formulation"] = "RecoGenerator unavailable"
        else:
            try:
                pending_recommendations_this_cycle = self.recommendation_generator.formulate_recommendations_v2_4(
                    generated_signals_dict_from_sg=generated_signals_this_cycle,
                    df_strike_level_metrics_input=df_strike_all_metrics_output,
                    und_data_aggregates_input=und_data_enriched_output,
                    current_market_regime_input=self.current_market_regime, 
                    current_time_dt_input=current_processing_datetime, 
                    symbol_for_reco=symbol
                )
            except Exception as e_rg_call:
                 if isinstance(und_data_enriched_output, dict): und_data_enriched_output["error_recommendation_formulation"] = str(e_rg_call)
        cycle_logger.info(f"[{symbol}] Step 6 (Reco Formulation) complete. Pending: {len(pending_recommendations_this_cycle)}.")
        
        cycle_logger.info(f"[{symbol}] Step 7: Optimizing Trade Parameters for {len(pending_recommendations_this_cycle)} pending recommendations...")
        newly_parameterized_and_activated_recommendations: List[Dict[str, Any]] = []
        if not self.trade_parameter_optimizer or not hasattr(self.trade_parameter_optimizer, 'optimize_parameters_for_recommendation'):
            if isinstance(und_data_enriched_output, dict): und_data_enriched_output["error_tpo"] = "TPO unavailable"
            for reco_no_tpo in pending_recommendations_this_cycle:
                reco_no_tpo["status"] = "ERROR_PARAMETERS"; reco_no_tpo["status_update"] = "TPO unavailable."
                newly_parameterized_and_activated_recommendations.append(reco_no_tpo)
        else:
            for pending_reco_payload in pending_recommendations_this_cycle:
                try:
                    parameterized_reco_payload = self.trade_parameter_optimizer.optimize_parameters_for_recommendation(
                        recommendation_payload=pending_reco_payload,
                        df_strike_level_metrics=df_strike_all_metrics_output,
                        und_data_aggregates=und_data_enriched_output, 
                        symbol=symbol,
                        current_time=current_processing_datetime
                    )
                    newly_parameterized_and_activated_recommendations.append(parameterized_reco_payload)
                except Exception as e_tpo_call: 
                    error_reco_payload_tpo_fail = pending_reco_payload.copy()
                    error_reco_payload_tpo_fail["status"] = "ERROR_PARAMETERS"; error_reco_payload_tpo_fail["status_update"] = f"TPO call failed: {str(e_tpo_call)[:50]}"
                    newly_parameterized_and_activated_recommendations.append(error_reco_payload_tpo_fail)
                    if isinstance(und_data_enriched_output, dict) and "error_tpo" not in und_data_enriched_output : und_data_enriched_output["error_tpo"] = str(e_tpo_call)
        cycle_logger.info(f"[{symbol}] Step 7 (TPO) complete. Parameterized: {len(newly_parameterized_and_activated_recommendations)}.")    
        
        cycle_logger.info(f"[{symbol}] Step 8: Performing Stateful Management of Active Recommendations...")
        if not self.exit_config or not self.target_config or not self.reco_config: 
            self.active_recommendations = newly_parameterized_and_activated_recommendations
            if isinstance(und_data_enriched_output, dict): und_data_enriched_output["error_state_management"] = "SM impaired by missing configs."
        else:
            try:
                self.active_recommendations = self._update_active_recommendations_and_manage_state_v2_4(
                    newly_generated_and_parameterized_recos=newly_parameterized_and_activated_recommendations,
                    latest_signals_dict_for_exits=generated_signals_this_cycle,
                    latest_df_strike_level_metrics_for_exits=df_strike_all_metrics_output,
                    latest_und_data_aggregates_for_exits=und_data_enriched_output,
                    latest_market_regime_for_exits=self.current_market_regime,
                    current_time_dt_for_lifecycle=current_processing_datetime,
                    symbol_for_lifecycle=symbol
                )
            except Exception as e_sm_call:
                temp_recos_on_sm_fail = self.active_recommendations[:] 
                temp_recos_on_sm_fail.extend(newly_parameterized_and_activated_recommendations)
                self.active_recommendations = temp_recos_on_sm_fail
                if isinstance(und_data_enriched_output, dict): und_data_enriched_output["error_state_management"] = str(e_sm_call)
        cycle_logger.info(f"[{symbol}] Step 8 (Stateful Management) complete. Active recos: {len(self.active_recommendations)}.")
        
        cycle_logger.info(f"[{symbol}] Step 9: Storing Historical Data...")
        # --- Step 9: Storing Historical Data (with toggle) ---
        if self.historical_data_manager and component_activation_cfg.get("historical_data_storage_active", True):
            cycle_logger.info(f"[{symbol}] Step 9: Storing Historical Data (Activated)...") # Log that it's active

            # Store daily metrics
            if hasattr(self.historical_data_manager, 'store_daily_metric_value') and \
            hasattr(self, 'metrics_for_dyn_thresh_keys') and self.metrics_for_dyn_thresh_keys and \
            isinstance(und_data_enriched_output, dict):
                    for metric_key_to_store in self.metrics_for_dyn_thresh_keys:
                        if metric_key_to_store in und_data_enriched_output:
                            self.historical_data_manager.store_daily_metric_value(
                                symbol=symbol, data_date=current_processing_datetime.date(),
                                metric_key=metric_key_to_store, value=und_data_enriched_output[metric_key_to_store]
                            )
            else:
                cycle_logger.debug(f"[{symbol}] Skipping metric storage due to missing HDM method, keys, or invalid und_data.")

            # Store daily OHLCV
            # Initialize ohlcv_to_store_hist before the if hasattr block to ensure it's always defined
            ohlcv_to_store_hist: Dict[str, Any] = {} # Initialize
            if hasattr(self.historical_data_manager, 'store_daily_ohlcv') and \
            isinstance(und_data_enriched_output, dict) and \
            hasattr(self, 'col_u_day_open_price') and self.col_u_day_open_price: # Ensure self has these attributes
                
                # Ensure all necessary column name attributes exist on self before trying to get them
                # These should be initialized in ITSOrchestrator's __init__ from config
                day_open_col = getattr(self, 'col_u_day_open_price', None)
                day_high_col = getattr(self, 'col_u_day_high_price_orch', None)
                day_low_col = getattr(self, 'col_u_day_low_price_orch', None)
                und_price_col = getattr(self, 'col_und_price_orch', None) # This is likely self.col_und_price_cfg
                day_volume_col = getattr(self, 'col_u_day_volume_orch', None)

                if all([day_open_col, day_high_col, day_low_col, und_price_col, day_volume_col]):
                    ohlcv_to_store_hist = {
                        'open': und_data_enriched_output.get(day_open_col),
                        'high': und_data_enriched_output.get(day_high_col),
                        'low': und_data_enriched_output.get(day_low_col),
                        'close': und_data_enriched_output.get(und_price_col), # Assuming orchestrator's price col for 'close'
                        'volume': und_data_enriched_output.get(day_volume_col)
                    }
                    # Check if all required OHLCV values were successfully retrieved before attempting to store
                    if all(pd.notna(v) and v is not None for v in ohlcv_to_store_hist.values()):
                        self.historical_data_manager.store_daily_ohlcv(
                            symbol, current_processing_datetime.date(), ohlcv_to_store_hist
                        )
                    else:
                        cycle_logger.warning(f"[{symbol}] Incomplete OHLCV data in und_data_enriched_output. Skipping OHLCV storage. Data: {ohlcv_to_store_hist}")
                else:
                    cycle_logger.warning(f"[{symbol}] One or more OHLCV column name attributes missing in ITSOrchestrator. Skipping OHLCV storage.")
            else:
                cycle_logger.debug(f"[{symbol}] Skipping OHLCV storage due to missing HDM method or invalid und_data.")
            
            cycle_logger.info(f"[{symbol}] Step 9 (Historical Data Storage) processing complete based on activation.")
        else:
            cycle_logger.info(f"[{symbol}] Step 9: Historical Data Storage SKIPPED by config.")

        # --- Step 10: Prepare final analysis bundle ---
        cycle_logger.info(f"[{symbol}] Step 10: Preparing final analysis bundle for output...")
        final_cycle_error_messages_list: List[str] = []
        
        if fetcher_error_message_from_input:
            final_cycle_error_messages_list.append(f"PrimaryDataFetcher: {str(fetcher_error_message_from_input)[:150]}")
        
        if processed_data_bundle_from_idp and processed_data_bundle_from_idp.get("error_message"):
            final_cycle_error_messages_list.append(f"IDP_MetricsCalc: {str(processed_data_bundle_from_idp['error_message'])[:150]}")
        
        # Check for errors populated into und_data_enriched_output by later stages
        if isinstance(und_data_enriched_output, dict):
            if und_data_enriched_output.get("error_signal_generation"): final_cycle_error_messages_list.append(f"SignalGen: {str(und_data_enriched_output['error_signal_generation'])[:100]}")
            if und_data_enriched_output.get("error_recommendation_formulation"): final_cycle_error_messages_list.append(f"RecoForm: {str(und_data_enriched_output['error_recommendation_formulation'])[:100]}")
            if und_data_enriched_output.get("error_tpo"): final_cycle_error_messages_list.append(f"TPO: {str(und_data_enriched_output['error_tpo'])[:100]}")
            if und_data_enriched_output.get("error_state_management"): final_cycle_error_messages_list.append(f"StateMgmt: {str(und_data_enriched_output['error_state_management'])[:100]}")
        
        combined_error_message_final = " | ".join(final_cycle_error_messages_list) if final_cycle_error_messages_list else None

        analysis_bundle = self._create_empty_analysis_bundle(
            error_message=combined_error_message_final or "Cycle Completed (Review Logs for Details)"
        )
        
        analysis_bundle.update({
            "timestamp": current_processing_datetime.isoformat(),
            "symbol": symbol,
            "current_market_regime": self.current_market_regime,
            "df_chain_metrics_CANONICAL_OBJ": df_chain_all_metrics_output,    # USE _output SUFFIX
            "df_strike_metrics_CANONICAL_OBJ": df_strike_all_metrics_output, # USE _output SUFFIX
            "und_data_aggregates_CANONICAL_OBJ": und_data_enriched_output,  # USE _output SUFFIX
            "raw_signals_generated_this_cycle": generated_signals_this_cycle,
            "active_recommendations_managed": self.active_recommendations,
            "resolved_dynamic_thresholds_this_cycle": self.resolved_dynamic_thresholds_cache.copy(),
            "config_snapshot_info": {
                "version": self._get_config_value_its(["version"], "N/A_ITS_BUNDLE"),
                "config_file_path": self.config_manager.get_abs_config_path_instance() if hasattr(self.config_manager, 'get_abs_config_path_instance') else "N/A_CM_Path"
            },
            "cycle_error_summary": combined_error_message_final,
            "data_processing_error_detail": processed_data_bundle_from_idp.get("error_message") if processed_data_bundle_from_idp else \
                                           (fetcher_error_message_from_input if fetcher_error_message_from_input and not (processed_data_bundle_from_idp and processed_data_bundle_from_idp.get("error_message")) else None)
        })
        
        tradier_iv_target_dte_for_log_final = int(self._get_config_value_its(['tradier_api_settings', 'iv_approximation_target_dte'], 5))
        iv_key_to_check_final = f"tradier_iv{tradier_iv_target_dte_for_log_final}_approx_smv_avg"
        if isinstance(analysis_bundle.get("und_data_aggregates_CANONICAL_OBJ"), dict) and \
           iv_key_to_check_final in analysis_bundle["und_data_aggregates_CANONICAL_OBJ"]:
            cycle_logger.debug(f"[{symbol}] Confirmed Tradier IV '{iv_key_to_check_final}' is present in final bundle.")
        elif isinstance(analysis_bundle.get("und_data_aggregates_CANONICAL_OBJ"), dict):
            cycle_logger.debug(f"[{symbol}] Tradier IV key '{iv_key_to_check_final}' NOT found in final bundle's und_data.")

        cycle_logger.info(f"[{symbol}] Analysis bundle prepared. Regime: {self.current_market_regime}. Active Recos: {len(self.active_recommendations)}. Errors: {'Yes' if analysis_bundle.get('cycle_error_summary') else 'No'}")
        
        self.logger.info(f"--- Orchestrator: Analysis Cycle for {symbol} at {self.last_analysis_timestamp.isoformat()} COMPLETE ---")
        return analysis_bundle
    
    def _create_empty_analysis_bundle(self, error_message: str) -> Dict[str, Any]:
        """
        Creates a standardized empty or error-state analysis bundle.
        """
        # Try to get default regime from config, otherwise use a hardcoded error regime
        default_regime_val = "REGIME_ERROR_BUNDLE"
        if hasattr(self, 'mre_config_orch') and isinstance(self.mre_config_orch, dict) and self.mre_config_orch.get("default_regime"):
            default_regime_val = self.mre_config_orch["default_regime"]
        elif hasattr(self, 'config_manager') and hasattr(self.config_manager, 'get_setting'): # Check if config_manager is valid
            default_regime_val = self._get_config_value_its("market_regime_engine_settings.default_regime", "REGIME_ERROR_BUNDLE_NO_MRE_CFG")
        
        current_sym_ctx = self.current_symbol_being_managed if self.current_symbol_being_managed else "UNKNOWN_SYM_ERR"
        
        # Ensure col_und_price_orch is initialized even if __init__ had issues
        price_col_name = self.col_und_price_orch if hasattr(self, 'col_und_price_orch') else "price"

        return {
            "timestamp": datetime.now().isoformat(), 
            "symbol": current_sym_ctx,
            "current_market_regime": default_regime_val,
            "df_chain_metrics_CANONICAL_OBJ": pd.DataFrame(), 
            "df_strike_metrics_CANONICAL_OBJ": pd.DataFrame(),
            "und_data_aggregates_CANONICAL_OBJ": {"error": error_message, price_col_name: None, "symbol": current_sym_ctx},
            "raw_signals_generated_this_cycle": {}, 
            "active_recommendations_managed": [], 
            "resolved_dynamic_thresholds_this_cycle": {}, 
            "config_snapshot_info": {
                "error": "Bundle creation failed due to: " + error_message, 
                "version": self._get_config_value_its(["version"],"N/A_CFG_ERR_BUNDLE") if hasattr(self, 'config_manager') else "N/A_NO_CM"
            },
            "cycle_error_summary": error_message, 
            "data_processing_error_detail": error_message # Can be refined if specific stage is known
        }

    # --- Stateful Recommendation Management Methods ---
    def _update_active_recommendations_and_manage_state_v2_4(
        self, 
        newly_generated_and_parameterized_recos: List[Dict[str, Any]], 
        latest_signals_dict_for_exits: Dict[str, Dict[str, List[Dict[str, Any]]]], 
        latest_df_strike_level_metrics_for_exits: pd.DataFrame,
        latest_und_data_aggregates_for_exits: Dict[str, Any], 
        latest_market_regime_for_exits: str,
        current_time_dt_for_lifecycle: datetime,
        symbol_for_lifecycle: str
    ) -> List[Dict[str, Any]]:
        """
        Manages the lifecycle of active recommendations:
        - Checks existing active recommendations for exit conditions.
        - Adjusts parameters of active recommendations.
        - Integrates newly generated and parameterized recommendations.
        """
        state_mgmt_logger = self.logger.getChild(f"StateManagement.{symbol_for_lifecycle}")
        state_mgmt_logger.info(f"Starting stateful management for {len(self.active_recommendations)} existing and "
                               f"{len(newly_generated_and_parameterized_recos)} new potential recommendations.")

        next_state_recommendations: List[Dict[str, Any]] = []
        
        # Ensure current underlying price is available for price-based checks
        current_price_raw_for_state = latest_und_data_aggregates_for_exits.get(self.col_und_price_orch)
        current_price_for_state: Optional[float] = None
        if current_price_raw_for_state is not None and pd.notna(current_price_raw_for_state):
            try:
                current_price_for_state = float(current_price_raw_for_state)
            except (ValueError, TypeError):
                state_mgmt_logger.error(f"Invalid current price '{current_price_raw_for_state}' for state management. Price-based exits/adjustments will be impaired.")
        else:
            state_mgmt_logger.error("Current price missing for state management. Price-based exits/adjustments will be impaired.")


        # --- Process Existing Active Recommendations ---
        for active_reco_payload in self.active_recommendations:
            current_reco_status = active_reco_payload.get("status", "")
            reco_id_log = active_reco_payload.get('id', 'UnknownID')

            # Skip already exited or errored recommendations
            if not (current_reco_status.startswith("ACTIVE_NEW") or current_reco_status.startswith("ACTIVE_ADJUSTED")):
                next_state_recommendations.append(active_reco_payload) 
                continue

            # 1. Check for Immediate Exit Conditions
            exit_check_result = self._is_immediate_exit_warranted_v2_4(
                active_reco_payload, 
                latest_signals_dict_for_exits, 
                latest_df_strike_level_metrics_for_exits, 
                latest_und_data_aggregates_for_exits, 
                latest_market_regime_for_exits, 
                current_price_for_state # Pass potentially None price
            )

            if exit_check_result["exit_warranted"]:
                active_reco_payload["status"] = "EXITED_AUTO"
                active_reco_payload["exit_reason"] = exit_check_result["reason"]
                # Use current_price_for_state if available, otherwise keep existing or None
                active_reco_payload["exit_price"] = current_price_for_state if current_price_for_state is not None else active_reco_payload.get("exit_price")
                active_reco_payload["exit_timestamp"] = current_time_dt_for_lifecycle.isoformat()
                active_reco_payload["status_update"] = f"Exited: {exit_check_result['reason']} at Px ~{active_reco_payload['exit_price']:.2f}" if active_reco_payload.get("exit_price") is not None else f"Exited (no price): {exit_check_result['reason']}"
                state_mgmt_logger.info(f"Recommendation '{reco_id_log}' EXITED: {exit_check_result['reason']}")
                next_state_recommendations.append(active_reco_payload)
                continue # Move to the next active recommendation

            # 2. Adjust Parameters for Active (Non-Exited) Recommendations
            # Only adjust for categories that typically have ongoing parameter management (e.g., directional)
            reco_category_for_adj = active_reco_payload.get("category", "").lower()
            # These categories are candidates for TSL and parameter re-evaluation
            adjustable_categories = ["directional trades", "eod_hedging_pressure", "rolling_flow_momentum_signal"] 
            
            if any(cat_key_sm in reco_category_for_adj for cat_key_sm in adjustable_categories) and current_price_for_state is not None:
                adjusted_reco_payload = self._adjust_active_recommendation_parameters_v2_4( 
                    active_reco_payload=active_reco_payload, 
                    latest_df_strike_metrics=latest_df_strike_level_metrics_for_exits, 
                    latest_und_data_aggregates=latest_und_data_aggregates_for_exits,
                    latest_market_regime=latest_market_regime_for_exits, 
                    current_und_price=current_price_for_state, # Pass valid float price
                    symbol_for_adj=symbol_for_lifecycle, 
                    current_processing_date_for_atr=current_time_dt_for_lifecycle.date()
                )
                next_state_recommendations.append(adjusted_reco_payload)
            else: 
                # If not adjustable or price is missing for adjustment, keep as is but update timestamp
                active_reco_payload["last_adjusted_ts"] = current_time_dt_for_lifecycle.isoformat() 
                if current_price_for_state is None and any(cat_key_sm in reco_category_for_adj for cat_key_sm in adjustable_categories):
                    active_reco_payload["status_update"] = "Parameter adjustment skipped (missing current price)."
                next_state_recommendations.append(active_reco_payload)
        
        # --- Integrate Newly Generated and Parameterized Recommendations ---
        min_reissue_seconds_cfg = int(self.reco_config.get("min_reissue_time_seconds", 180)) 
        min_reissue_time_delta_obj = timedelta(seconds=min_reissue_seconds_cfg)

        for new_potential_reco in newly_generated_and_parameterized_recos:
            if "ERROR" in new_potential_reco.get("status", ""): 
                state_mgmt_logger.warning(f"New recommendation {new_potential_reco.get('id','NewRecoUnknownID')} has error status '{new_potential_reco.get('status')}'. Adding to list as is.")
                next_state_recommendations.append(new_potential_reco)
                continue

            is_considered_duplicate_or_too_soon = False
            # Check against all recommendations currently in next_state_recommendations that are active
            for existing_reco_check_dupe in [r for r in next_state_recommendations if r.get("status","").startswith("ACTIVE")]: 
                # Define similarity criteria (can be refined)
                if existing_reco_check_dupe.get("trigger_signal_name") == new_potential_reco.get("trigger_signal_name") and \
                   existing_reco_check_dupe.get("strike_price_signal") == new_potential_reco.get("strike_price_signal") and \
                   existing_reco_check_dupe.get("bias") == new_potential_reco.get("bias") and \
                   existing_reco_check_dupe.get("category") == new_potential_reco.get("category"):
                    
                    # Check timestamp of the existing similar recommendation
                    last_event_ts_existing_iso = existing_reco_check_dupe.get("last_adjusted_ts", existing_reco_check_dupe.get("timestamp_issued"))
                    if last_event_ts_existing_iso:
                        try:
                            # Ensure timezone awareness or consistent naive datetime comparison
                            last_event_dt_existing_obj = datetime.fromisoformat(last_event_ts_existing_iso.replace("Z", "+00:00"))
                            if current_time_dt_for_lifecycle.tzinfo is None and last_event_dt_existing_obj.tzinfo is not None:
                                last_event_dt_existing_obj = last_event_dt_existing_obj.replace(tzinfo=None) # Make naive if current is naive
                            
                            if current_time_dt_for_lifecycle - last_event_dt_existing_obj < min_reissue_time_delta_obj:
                                is_considered_duplicate_or_too_soon = True
                                state_mgmt_logger.info(f"Skipping issuance of new reco (Trigger: {new_potential_reco.get('trigger_signal_name')}, "
                                                       f"Strike: {new_potential_reco.get('strike_price_signal')}, Bias: {new_potential_reco.get('bias')}) "
                                                       f"as a similar recommendation '{existing_reco_check_dupe.get('id')}' was issued/adjusted recently.")
                                break # Found a recent similar recommendation
                        except ValueError: 
                            state_mgmt_logger.warning(f"Could not parse timestamp '{last_event_ts_existing_iso}' for duplicate check on reco {existing_reco_check_dupe.get('id')}.")
            
            if not is_considered_duplicate_or_too_soon:
                next_state_recommendations.append(new_potential_reco)
                if new_potential_reco.get("status","").startswith("ACTIVE"): # Should be ACTIVE_NEW_NO_TSL from TPO
                     state_mgmt_logger.info(f"New recommendation '{new_potential_reco.get('id')}' added to active list with status '{new_potential_reco.get('status')}'.")
        
        return next_state_recommendations          
          
    def _is_immediate_exit_warranted_v2_4(
        self, active_reco_payload: Dict[str, Any], 
        latest_signals: Dict[str, Dict[str, List[Dict[str, Any]]]],
        latest_df_strike_metrics: pd.DataFrame, 
        latest_und_data_aggregates: Dict[str, Any],
        latest_market_regime: str,
        current_und_price: Optional[float] # Can be None if price data is missing
    ) -> Dict[str, Any]: 
        """
        Checks various conditions to determine if an active recommendation should be exited.
        Returns a dict: {"exit_warranted": bool, "reason": str}
        """
        exit_check_logger = self.logger.getChild(f"ExitCheck.{active_reco_payload.get('id','UnknownRecoID')}")
        exit_info: Dict[str, Any] = {"exit_warranted": False, "reason": ""}

        # Price-based exits (only if current_und_price is valid)
        if current_und_price is not None and current_und_price > 0:
            stop_loss_val = active_reco_payload.get("stop_loss")
            reco_bias_is_bullish = active_reco_payload.get("bias", "Neutral").lower() == "bullish"
            
            if stop_loss_val is not None and pd.notna(stop_loss_val):
                sl_float = float(stop_loss_val)
                if (reco_bias_is_bullish and current_und_price <= sl_float) or \
                   (not reco_bias_is_bullish and current_und_price >= sl_float):
                    return {"exit_warranted": True, "reason": f"StopLoss Hit ({sl_float:.2f})"}
            
            target_2_val = active_reco_payload.get("target_2") # Assuming T2 is an exit target
            if target_2_val is not None and pd.notna(target_2_val):
                t2_float = float(target_2_val)
                if (reco_bias_is_bullish and current_und_price >= t2_float) or \
                   (not reco_bias_is_bullish and current_und_price <= t2_float):
                     return {"exit_warranted": True, "reason": f"Target 2 Hit ({t2_float:.2f})"} 
        elif current_und_price is None: # Only log if a price-based exit might have occurred
            if active_reco_payload.get("stop_loss") is not None or active_reco_payload.get("target_2") is not None:
                exit_check_logger.debug("Current underlying price is None. Skipping price-based exit checks (SL/T2).")


        # Regime Shift Exit Logic
        if self.exit_config.get("regime_shift_exit_enabled", True):
            original_regime_at_issuance = active_reco_payload.get("current_market_regime_at_issuance")
            if original_regime_at_issuance and original_regime_at_issuance != latest_market_regime:
                reco_category_key = active_reco_payload.get('category', 'UnknownCategory') 
                reco_bias_key = active_reco_payload.get('bias', 'Neutral').upper() 
                
                # Construct a key for the exit rules, e.g., "Directional Trades.BULLISH"
                full_trade_type_for_exit_rules = f"{reco_category_key}.{reco_bias_key}"
                if reco_category_key == "Volatility Plays": # Special handling for Vol Plays
                    if "expansion" in active_reco_payload.get("trigger_signal_name","").lower():
                        full_trade_type_for_exit_rules = "Volatility Plays.Expansion" 
                    elif "contraction" in active_reco_payload.get("trigger_signal_name","").lower():
                        full_trade_type_for_exit_rules = "Volatility Plays.Contraction"
                
                # Ensure exit_config and regime_shift_exit_rules are valid dicts
                regime_exit_rules_map = self.exit_config.get("regime_shift_exit_rules", {})
                if not isinstance(regime_exit_rules_map, dict): regime_exit_rules_map = {}
                
                exit_rules_for_this_trade_type = regime_exit_rules_map.get(full_trade_type_for_exit_rules, {})
                if not isinstance(exit_rules_for_this_trade_type, dict): exit_rules_for_this_trade_type = {}

                if latest_market_regime in exit_rules_for_this_trade_type:
                    exit_action_str = exit_rules_for_this_trade_type[latest_market_regime]
                    if isinstance(exit_action_str, str) and exit_action_str.startswith("EXIT_IMMEDIATE"):
                        return {"exit_warranted": True, "reason": f"AdverseRegimeShift: {original_regime_at_issuance} -> {latest_market_regime} (Rule: {exit_action_str})"}
        
        # Contradictory Signal Exit Logic
        reco_strike_raw = active_reco_payload.get("strike_price_signal")
        reco_strike_float: Optional[float] = None
        if reco_strike_raw is not None and pd.notna(reco_strike_raw): 
            try: reco_strike_float = float(reco_strike_raw)
            except: pass # reco_strike_float remains None

        if reco_strike_float is not None: # Only check strike-specific contradictory signals if reco has a strike
            contra_stars_min = int(self.exit_config.get("contradiction_stars_threshold", 4))
            opposing_bias_str = "bearish" if active_reco_payload.get("bias", "").lower() == "bullish" else "bullish"
            
            # Ensure latest_signals and its nested structures are dicts before accessing
            directional_signals = latest_signals.get("directional", {}) if isinstance(latest_signals, dict) else {}
            opposing_directional_signals_list = directional_signals.get(opposing_bias_str, []) if isinstance(directional_signals, dict) else []
            
            for contra_sig_payload in opposing_directional_signals_list:
                if not isinstance(contra_sig_payload, dict): continue # Skip if payload is not a dict

                contra_sig_strike_raw = contra_sig_payload.get(self.col_strike_orch) 
                contra_sig_strike_float: Optional[float] = None
                if contra_sig_strike_raw is not None and pd.notna(contra_sig_strike_raw):
                    try: contra_sig_strike_float = float(contra_sig_strike_raw)
                    except: pass
                
                if contra_sig_strike_float is not None and math.isclose(contra_sig_strike_float, reco_strike_float):
                    contra_sig_stars = int(contra_sig_payload.get("initial_stars", 0)) 
                    if contra_sig_stars >= contra_stars_min:
                        return {"exit_warranted": True, "reason": f"StrongContraDirSignal '{contra_sig_payload.get('type')}' ({contra_sig_stars}*)"}
            
            # MSPI Flip Exit (if strike data is available)
            if isinstance(latest_df_strike_metrics, pd.DataFrame) and not latest_df_strike_metrics.empty and \
               self.mspi_col in latest_df_strike_metrics.columns and self.col_strike_orch in latest_df_strike_metrics.columns:
                
                temp_strike_df = latest_df_strike_metrics.copy() # Work on a copy for safe type conversion
                temp_strike_df[self.col_strike_orch] = pd.to_numeric(temp_strike_df[self.col_strike_orch], errors='coerce')
                strike_metrics_now_df_filtered = temp_strike_df[np.isclose(temp_strike_df[self.col_strike_orch].fillna(np.nan), reco_strike_float)]
                
                if not strike_metrics_now_df_filtered.empty:
                    mspi_now_val = strike_metrics_now_df_filtered.iloc[0].get(self.mspi_col)
                    mspi_at_issue_val = active_reco_payload.get("key_metrics_at_issuance",{}).get("MSPI_at_strike") 
                    mspi_flip_abs_thresh = float(self.exit_config.get("mspi_flip_threshold", 0.7))

                    if mspi_now_val is not None and mspi_at_issue_val is not None and pd.notna(mspi_now_val) and pd.notna(mspi_at_issue_val):
                        if (active_reco_payload.get("bias", "").lower() == "bullish" and mspi_now_val < -mspi_flip_abs_thresh and mspi_at_issue_val > 0) or \
                           (active_reco_payload.get("bias", "").lower() == "bearish" and mspi_now_val > mspi_flip_abs_thresh and mspi_at_issue_val < 0):
                            return {"exit_warranted": True, "reason": f"MSPIFlipAgainst (Now:{mspi_now_val:.2f}|Issue:{mspi_at_issue_val:.2f})"}
        
        # Vanna Cascade Exit Override
        if self.exit_config.get("vanna_cascade_exit_override_enabled", True):
            v2_4_new_signals = latest_signals.get("v2_4_new", {}) if isinstance(latest_signals, dict) else {}
            vanna_alerts_list = v2_4_new_signals.get("vanna_cascade_alert", []) if isinstance(v2_4_new_signals, dict) else []
            vanna_exit_stars_min = int(self.exit_config.get("vanna_cascade_exit_stars_thresh", 3))
            for v_alert_payload in vanna_alerts_list:
                if not isinstance(v_alert_payload, dict): continue
                alert_type_str = v_alert_payload.get("type","").lower()
                alert_stars_val = int(v_alert_payload.get("initial_stars", 0)) 
                if alert_stars_val >= vanna_exit_stars_min:
                    if active_reco_payload.get("bias", "").lower() == "bullish" and "bearish" in alert_type_str: 
                        return {"exit_warranted": True, "reason": f"ContraVannaCascade_Bearish"}
                    if active_reco_payload.get("bias", "").lower() == "bearish" and "bullish" in alert_type_str: 
                        return {"exit_warranted": True, "reason": f"ContraVannaCascade_Bullish"}
        
        # Bubble Warning Exit
        if self.exit_config.get("bubble_warning_exit_conviction_thresh", 0) > 0 : 
            bubble_exit_stars_min = int(self.exit_config.get("bubble_warning_exit_conviction_thresh", 3))
            v2_4_new_signals_bubble = latest_signals.get("v2_4_new", {}) if isinstance(latest_signals, dict) else {}
            bubble_warning_signals_list = v2_4_new_signals_bubble.get("bubble_warning_signal", []) if isinstance(v2_4_new_signals_bubble, dict) else []
            for bubble_sig_payload in bubble_warning_signals_list:
                if not isinstance(bubble_sig_payload, dict): continue
                bubble_sig_stars = int(bubble_sig_payload.get("initial_stars",0)) 
                if bubble_sig_stars >= bubble_exit_stars_min:
                    return {"exit_warranted": True, "reason": f"BubbleWarningActive (Exit Trade)"}

        return exit_info # No exit condition met

    def _adjust_active_recommendation_parameters_v2_4(
        self, active_reco_payload: Dict[str, Any],
        latest_df_strike_metrics: pd.DataFrame,
        latest_und_data_aggregates: Dict[str, Any],
        latest_market_regime: str,
        current_und_price: float, # Assumed to be a valid float by caller
        symbol_for_adj: str,
        current_processing_date_for_atr: date 
    ) -> Dict[str, Any]:
        """
        Adjusts parameters (SL, potentially targets) for an active recommendation.
        Implements profit-taking adjustments and ATR-based trailing stops.
        """
        adj_params_logger = self.logger.getChild(f"AdjustParams.{active_reco_payload.get('id','UnknownRecoID')}")
        updated_reco_payload = active_reco_payload.copy()
        status_updates_list_for_reco: List[str] = []

        original_entry_price_val = float(active_reco_payload.get("entry_price_at_signal", current_und_price)) 
        is_bullish_trade_adj = active_reco_payload.get("bias", "Neutral").lower() == "bullish"
        current_sl_val = active_reco_payload.get("stop_loss") # This could be None
        current_t1_val = active_reco_payload.get("target_1") # This could be None
        current_t2_val = active_reco_payload.get("target_2") # This could be None

        # --- 1. ATR Calculation ---
        atr_for_trailing = self._get_atr(symbol_for_adj, current_und_price, current_trading_date=current_processing_date_for_atr)
        if atr_for_trailing <= EPSILON_ORCH: 
            # Use a small fraction of price if ATR is too small or zero, to avoid zero-width buffers
            atr_for_trailing = max(current_und_price * 0.001, DEFAULT_ATR_FALLBACK_MIN_VALUE_ORCH) 
            adj_params_logger.debug(f"ATR for trailing SL was too small or zero, using fallback: {atr_for_trailing:.4f}")
            
        sl_after_profit_take = current_sl_val # Start with current SL, which could be None

        # --- 2. Profit Taking Adjustments ---
        # T1 Hit: Adjust SL to Entry + Buffer
        if self.exit_config.get("profit_take_t1_active", True) and \
           current_t1_val is not None and pd.notna(current_t1_val) and \
           not updated_reco_payload.get("t1_hit_sl_adjusted", False): 
            
            if (is_bullish_trade_adj and current_und_price >= float(current_t1_val)) or \
               (not is_bullish_trade_adj and current_und_price <= float(current_t1_val)):
                
                sl_adj_atr_mult_t1_cfg = float(self.exit_config.get("profit_take_t1_sl_to_entry_plus_buffer_atr_mult", 0.05))
                buffer_t1 = atr_for_trailing * sl_adj_atr_mult_t1_cfg
                new_sl_val_t1 = original_entry_price_val + buffer_t1 if is_bullish_trade_adj else original_entry_price_val - buffer_t1
                
                # Only move SL if it's an improvement (tighter for longs, higher for shorts)
                if (is_bullish_trade_adj and (sl_after_profit_take is None or pd.isna(sl_after_profit_take) or new_sl_val_t1 > float(sl_after_profit_take))) or \
                   (not is_bullish_trade_adj and (sl_after_profit_take is None or pd.isna(sl_after_profit_take) or new_sl_val_t1 < float(sl_after_profit_take))):
                    sl_after_profit_take = round(new_sl_val_t1, 2)
                    status_updates_list_for_reco.append(f"T1 Hit({current_t1_val:.2f})! SL to Entry+Buf({sl_after_profit_take:.2f}).")
                    updated_reco_payload["t1_hit_sl_adjusted"] = True
                    updated_reco_payload["status"] = "ACTIVE_ADJUSTED_T1_HIT"


        # T2 Hit: Adjust SL to T1 + Buffer (only if T1 was already hit and SL adjusted for it)
        if self.exit_config.get("profit_take_t2_active", True) and \
           current_t1_val is not None and pd.notna(current_t1_val) and \
           current_t2_val is not None and pd.notna(current_t2_val) and \
           updated_reco_payload.get("t1_hit_sl_adjusted", False) and \
           not updated_reco_payload.get("t2_hit_sl_adjusted", False): 
            
            if (is_bullish_trade_adj and current_und_price >= float(current_t2_val)) or \
               (not is_bullish_trade_adj and current_und_price <= float(current_t2_val)):
                
                sl_adj_atr_mult_t2_cfg = float(self.exit_config.get("profit_take_t2_sl_to_t1_plus_buffer_atr_mult", 0.15))
                buffer_t2 = atr_for_trailing * sl_adj_atr_mult_t2_cfg
                new_sl_val_t2 = float(current_t1_val) + buffer_t2 if is_bullish_trade_adj else float(current_t1_val) - buffer_t2
                
                if (is_bullish_trade_adj and (sl_after_profit_take is None or pd.isna(sl_after_profit_take) or new_sl_val_t2 > float(sl_after_profit_take))) or \
                   (not is_bullish_trade_adj and (sl_after_profit_take is None or pd.isna(sl_after_profit_take) or new_sl_val_t2 < float(sl_after_profit_take))):
                    sl_after_profit_take = round(new_sl_val_t2, 2)
                    status_updates_list_for_reco.append(f"T2 Hit({current_t2_val:.2f})! SL to T1+Buf({sl_after_profit_take:.2f}).")
                    updated_reco_payload["t2_hit_sl_adjusted"] = True
                    updated_reco_payload["status"] = "ACTIVE_ADJUSTED_T2_HIT" 

        # --- 3. ATR Trailing Stop Logic ---
        regime_mults_for_trail = self.target_config.get("regime_specific_target_multipliers", {}).get(latest_market_regime, {})
        sl_trail_activation_atr_mult_cfg = float(regime_mults_for_trail.get("sl_trail_activation_mult", self.target_config.get("sl_trailing_activation_buffer_atr_mult", 1.25)))
        sl_trail_buffer_atr_mult_cfg = float(regime_mults_for_trail.get("sl_trail_buffer_mult", self.target_config.get("sl_trailing_buffer_atr_mult", 0.3)))
        
        proposed_atr_trail_sl: Optional[float] = None
        if is_bullish_trade_adj and current_und_price > (original_entry_price_val + atr_for_trailing * sl_trail_activation_atr_mult_cfg):
            proposed_atr_trail_sl = current_und_price - (atr_for_trailing * sl_trail_buffer_atr_mult_cfg)
        elif not is_bullish_trade_adj and current_und_price < (original_entry_price_val - atr_for_trailing * sl_trail_activation_atr_mult_cfg):
            proposed_atr_trail_sl = current_und_price + (atr_for_trailing * sl_trail_buffer_atr_mult_cfg)
        
        if proposed_atr_trail_sl is not None:
            if (is_bullish_trade_adj and (sl_after_profit_take is None or pd.isna(sl_after_profit_take) or proposed_atr_trail_sl > float(sl_after_profit_take))) or \
               (not is_bullish_trade_adj and (sl_after_profit_take is None or pd.isna(sl_after_profit_take) or proposed_atr_trail_sl < float(sl_after_profit_take))):
                sl_after_profit_take = round(proposed_atr_trail_sl, 2)
                status_updates_list_for_reco.append(f"ATR Trail SL to {sl_after_profit_take:.2f}.")
                if not updated_reco_payload.get("t1_hit_sl_adjusted") and not updated_reco_payload.get("t2_hit_sl_adjusted"): 
                    updated_reco_payload["status"] = "ACTIVE_ADJUSTED_TSL"

        # --- 4. Final SL Update ---
        if sl_after_profit_take is not None and pd.notna(sl_after_profit_take) and \
           (current_sl_val is None or pd.isna(current_sl_val) or not math.isclose(float(current_sl_val), sl_after_profit_take, rel_tol=EPSILON_ORCH/100)):
            updated_reco_payload["stop_loss"] = sl_after_profit_take # Already rounded
            if not any(s.startswith("T1 Hit") or s.startswith("T2 Hit") or s.startswith("ATR Trail SL") for s in status_updates_list_for_reco):
                 status_updates_list_for_reco.append(f"Final SL updated to {updated_reco_payload['stop_loss']:.2f}.")
        
        # --- 5. Update Status and Timestamp if any changes occurred ---
        if status_updates_list_for_reco: 
            unique_status_updates_final = list(OrderedDict.fromkeys(status_updates_list_for_reco)) 
            # Update status only if it's not already a more specific "HIT" status
            if not updated_reco_payload.get("status","").startswith("ACTIVE_ADJUSTED_T"): 
                 updated_reco_payload["status"] = "ACTIVE_ADJUSTED"
            updated_reco_payload["status_update"] = " | ".join(unique_status_updates_final)
            updated_reco_payload["last_adjusted_ts"] = datetime.now().isoformat() 
            adj_params_logger.info(f"Reco '{active_reco_payload['id']}' PARAMS ADJUSTED: {updated_reco_payload['status_update']}")
        
        return updated_reco_payload
    
    # --- Output & Cleanup ---
    def get_visualization_data_bundle(self, analysis_bundle_from_cycle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepares the full analysis_bundle for consumption by the dashboard,
        primarily by converting DataFrames to JSON-serializable formats (list of records).
        Handles potential NaN/Inf values in DataFrames before serialization.
        """
        vis_bundle_logger = self.logger.getChild("VizBundlePrep_Orch")
        if not isinstance(analysis_bundle_from_cycle, dict):
            vis_bundle_logger.error("Received invalid analysis_bundle (not a dict). Returning error bundle for visualization.")
            return {"error": "Invalid analysis_bundle type received by orchestrator for visualization."}

        vis_bundle_output: Dict[str, Any] = {}
        for key, value in analysis_bundle_from_cycle.items():
            if isinstance(value, pd.DataFrame):
                if not value.empty:
                    try: 
                        # Replace Inf/-Inf with None (which becomes null in JSON)
                        # NaNs are handled by to_dict(orient='records') by default (often becoming null)
                        df_copy_for_json = value.replace([np.inf, -np.inf], None) 
                        vis_bundle_output[key] = df_copy_for_json.to_dict(orient='records')
                    except Exception as e_todict_vis:
                        vis_bundle_logger.error(f"Error serializing DataFrame '{key}' to dict: {e_todict_vis}", exc_info=True)
                        vis_bundle_output[key] = [{"error_serialization": str(e_todict_vis)}] # Return error in list
                else: 
                    vis_bundle_output[key] = [] # Empty list for empty DataFrame
            elif isinstance(value, dict): 
                # Recursively clean dicts (though less common to have DataFrames nested deeply here)
                vis_bundle_output[key] = self.get_visualization_data_bundle(value) if key != "config_snapshot_info" else value.copy()
            elif isinstance(value, list): 
                 # Check if list contains DataFrames (less common at top level of bundle, but possible)
                cleaned_list = []
                contains_df = False
                for item in value:
                    if isinstance(item, pd.DataFrame):
                        contains_df = True
                        if not item.empty:
                            try:
                                df_item_copy = item.replace([np.inf, -np.inf], None)
                                cleaned_list.append(df_item_copy.to_dict(orient='records'))
                            except Exception as e_item_df:
                                cleaned_list.append([{"error_serialization_list_item": str(e_item_df)}])
                        else:
                            cleaned_list.append([])
                    else: # For lists of dicts, strings, numbers etc.
                        cleaned_list.append(item) # Assume other types are JSON serializable
                vis_bundle_output[key] = cleaned_list
                if contains_df: vis_bundle_logger.debug(f"Processed list '{key}' which contained DataFrames.")
            else: # Primitive types (str, int, float, bool, None)
                vis_bundle_output[key] = value
        
        vis_bundle_logger.debug(f"Visualization data bundle prepared for symbol {vis_bundle_output.get('symbol', 'N/A')}.")
        return vis_bundle_output

    def shutdown_cleanup(self) -> None:
        """
        Performs cleanup tasks when the system is shutting down.
        Calls shutdown methods on components like HistoricalDataManager and DataFetcher if they exist.
        """
        cleanup_logger_orch = self.logger.getChild("ShutdownCleanup_Orch")
        cleanup_logger_orch.info("ITS V2.4 Orchestrator performing shutdown cleanup procedures...")
        
        # Shutdown HistoricalDataManager
        if hasattr(self, 'historical_data_manager') and self.historical_data_manager and \
           hasattr(self.historical_data_manager, 'shutdown') and callable(getattr(self.historical_data_manager, 'shutdown')):
            try: 
                self.historical_data_manager.shutdown()
                cleanup_logger_orch.info("HistoricalDataManager shutdown successfully.")
            except Exception as e_hdm_sd: 
                cleanup_logger_orch.error(f"Error during HistoricalDataManager shutdown: {e_hdm_sd}", exc_info=True)
        else:
            cleanup_logger_orch.debug("HistoricalDataManager not available or no shutdown method found.")
        
        # Shutdown DataFetcher
        if hasattr(self, 'data_fetcher') and self.data_fetcher and \
           hasattr(self.data_fetcher, 'shutdown') and callable(getattr(self.data_fetcher, 'shutdown')):
            try: 
                self.data_fetcher.shutdown()
                cleanup_logger_orch.info("DataFetcher shutdown successfully.")
            except Exception as e_df_sd: 
                cleanup_logger_orch.error(f"Error during DataFetcher shutdown: {e_df_sd}", exc_info=True)
        else:
            cleanup_logger_orch.debug("DataFetcher not available or no shutdown method found.")
        
        # Add other component shutdowns here if they implement a shutdown method
        # e.g., self.metrics_calculator.shutdown() if it exists

        # --- ADDED: Shutdown for TradierDataFetcher ---
        if hasattr(self, 'tradier_data_fetcher') and self.tradier_data_fetcher and \
           hasattr(self.tradier_data_fetcher, 'shutdown') and callable(getattr(self.tradier_data_fetcher, 'shutdown')):
            try:
                self.logger.info("ITS Orchestrator: Shutting down TradierDataFetcher...")
                self.tradier_data_fetcher.shutdown()
                self.logger.info("ITS Orchestrator: TradierDataFetcher shutdown successfully.")
            except Exception as e_tdf_sd:
                self.logger.error(f"Error during TradierDataFetcher shutdown: {e_tdf_sd}", exc_info=True)
        else:
            self.logger.debug("TradierDataFetcher not available or no shutdown method found for orchestrator cleanup.")
        # --- END OF ADDED SECTION ---
        
        self.logger.info("ITS V2.4 Orchestrator shutdown cleanup finished.")

if __name__ == '__main__': # pragma: no cover
    if not logging.getLogger().hasHandlers(): 
          logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
                            format='[%(levelname)s] (%(name)s:%(lineno)d) %(asctime)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    main_test_logger_its = logging.getLogger(__name__) 
    main_test_logger_its.info("ITS V2.4 Orchestrator - Standalone test execution started (using sample config dict).")
    
    sample_test_config_its = { 
        "version": "TestConfig_ITS_Orch_Standalone_v2.4.1",
        "system_settings": {
            "log_level": "DEBUG", "df_history_maxlen": 3, 
            "metrics_for_dynamic_threshold_distribution_tracking": ["ssi_agg_und_avg", "GIB_OI_based_Und"],
            "min_days_for_dynamic_threshold_activation": 2
        },
        "runner_settings": { 
            "data_fetcher_module_path": "data_management.fetcher", "data_fetcher_class_name": "DataFetcherV2_4",
            "initial_processor_module_path": "data_management.initial_processor", "initial_processor_class_name": "InitialDataProcessorV2_4",
            "metrics_calculator_module_path": "core_analytics_engine.metrics_calculator", "metrics_calculator_class_name": "MetricsCalculatorV2_4",
            "historical_manager_module_path": "data_management.historical_data_manager", "historical_manager_class_name": "HistoricalDataManagerV2_4", # Corrected from _V2_4
            "market_regime_engine_module_path": "core_analytics_engine.market_regime_engine", "market_regime_engine_class_name": "MarketRegimeEngineV2_4_Superior",
            "signal_generator_module_path": "core_analytics_engine.signal_generator", "signal_generator_class_name": "SignalGeneratorV2_4",
            "recommendation_logic_module_path": "core_analytics_engine.recommendation_logic", "recommendation_logic_class_name": "RecommendationGeneratorV2_4",
            "trade_parameter_optimizer_module_path": "core_analytics_engine.trade_parameter_optimizer", "trade_parameter_optimizer_class_name": "TradeParameterOptimizerV2_4",
            "paths": {"historical_ohlc_store": "test_data/its_ohlc", "historical_metric_store": "test_data/its_metrics"}
        },
        "strategy_settings": { 
            "strike_col_name": "strike", "underlying_price_col_name": "price", "contract_multiplier_col_name": "multiplier",
            "option_kind_col_name": "opt_kind", "oi_col_name": "oi", "expiration_col_name": "expiration",
            "recommendations": {"min_directional_stars_to_issue": 1, "conviction_map_low": 0.5},
            "exits": {}, "targets": {"target_atr_stop_loss_multiplier": 1.5}, 
            "thresholds": { 
                "ssi_structure_change": {"type":"fixed", "fallback_value": 0.3, "value": 0.3} 
            },
            "greeks_from_und": { # Added for _initialize_critical_configs_and_columns
                "day_open_price_und": "day_open_price", "day_high_price_und": "day_high_price", 
                "day_low_price_und": "day_low_price", "day_volume_und": "day_volume"
            }
        },
        "market_regime_engine_settings": {"default_regime": "REGIME_ITS_TEST_DEFAULT", "regime_rules": {"REGIME_ITS_TEST_DEFAULT":{}}}, 
        "validation": {"required_top_level_sections": ["system_settings", "runner_settings", "strategy_settings", "market_regime_engine_settings"]},
        "data_fetcher_settings": {}, "data_processor_settings": {"approximations":{"generic_atr_period":14}}, "visualization_settings": {} 
    }

    class TestCMForITS: 
        def __init__(self, cfg): self.config = cfg; self._project_root_path = os.getcwd() 
        def get_setting(self, path, default_value_to_return=None, quiet=False): 
            val = self.config; p_list = path.split('.') if isinstance(path,str) else path
            try: 
                for k in p_list: val = val[k]
                return val if val is not None else default_value_to_return
            except (KeyError, TypeError): return default_value_to_return
        def get_config(self): return self.config
        def get_resolved_path(self, path, default_rel=None, quiet=False): 
            val = self.get_setting(path, default_value_to_return=default_rel, quiet=quiet) 
            if val: return os.path.join(self._project_root_path, val) if not os.path.isabs(val) else val
            return None

    test_its_cm = TestCMForITS(sample_test_config_its)

    try:
        orchestrator = IntegratedTradingSystemV2_4(
            loaded_config_manager_instance=test_its_cm
        )

        if orchestrator.initialization_failed:
            main_test_logger_its.critical("Orchestrator test aborted: Initialization indicated failure.")
        else:
            main_test_logger_its.info("ITS Orchestrator initialized for test (may be using some internal dummies if component loads failed).")
            
            mock_raw_options_df = pd.DataFrame({'strike': [100], 'oi': [10], 'price': [1.0], 'expiration': ['2025-12-31'], 'opt_kind': ['C']}) 
            mock_raw_und_data = {'price': 100.50, 'multiplier': 100.0, 'symbol': "DUMMYTEST"}
            mock_current_time = datetime.now()

            main_test_logger_its.info(f"Running a conceptual analysis cycle for DUMMYTEST...")
            # First, fetch data using the orchestrator's method
            fetched_data_bundle = orchestrator.fetch_data_for_analysis_cycle(
                symbol="DUMMYTEST",
                dte_list_for_api_call=None, # Use fetcher's defaults
                price_range_percentage_for_api=None # Use fetcher's defaults
            )
            
            if fetched_data_bundle.get("error"):
                 main_test_logger_its.error(f"Data fetch failed for DUMMYTEST: {fetched_data_bundle.get('error')}")
            else:
                analysis_bundle = orchestrator.run_analysis_cycle_v2_4(
                    symbol="DUMMYTEST",
                    raw_options_df_from_fetcher=fetched_data_bundle["raw_options_df"],
                    raw_underlying_data_dict_from_fetcher=fetched_data_bundle["raw_underlying_dict"],
                    current_processing_datetime=mock_current_time
                )
                main_test_logger_its.info(f"Analysis cycle complete. Current Regime: {analysis_bundle.get('current_market_regime')}")
                main_test_logger_its.info(f"Active recommendations count: {len(analysis_bundle.get('active_recommendations_managed', []))}") 
            
            orchestrator.shutdown_cleanup()
    except Exception as e_its_test:
        main_test_logger_its.error(f"Error during ITS Orchestrator standalone test: {e_its_test}", exc_info=True)
    main_test_logger_its.info("ITS V2.4 Orchestrator - Standalone test execution finished.")
