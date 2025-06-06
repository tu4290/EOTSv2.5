/elite_options_system_v2_5/
|
|-- config_v2_5.json                       # Main configuration (evolved from v2.4)
|-- config.schema.v2.5.json                # JSON Schema for validating config_v2_5.json (Primary schema)
|-- run_system_dashboard_v2_5.py           # Primary script to launch EOTS v2.5 (evolved)
|-- README_v2_5.md                         # The new comprehensive guide (we will build this)
|-- requirements_v2_5.txt                  # Updated Python package dependencies (e.g., Pydantic if adopted)
|-- .env                                   # (Optional) For environment variables (API keys, etc.)
|
|-- data_management/                       # Handles all data fetching, initial processing, and storage
|   |-- __init__.py
|   |-- fetcher_convexvalue_v2_5.py        # (Evolved from v2.4 fetcher.py) Fetches from ConvexValue
|   |-- fetcher_tradier_v2_5.py            # (Evolved from v2.4 tradier_data_fetcher.py) Fetches from Tradier
|   |-- historical_data_manager_v2_5.py    # (Evolved) Manages historical OHLCV, IV, and NEW V2.5 AGGREGATE METRICS for dynamic thresholds & performance tracking
|   |-- initial_processor_v2_5.py          # (Evolved) Cleans raw data, basic transformations, prepares for MetricsCalculatorV2_5
|   |-- performance_tracker_v2_5.py        # [NEW] Stores/retrieves historical signal/recommendation performance data for ATIF
|   |
|   |-- data_cache/                          # General cache directory
|       |-- raw_data_cache/                  # Stores fetched raw data (daily API pulls)
|       |-- processed_data_cache/            # Stores data after initial_processor (ready for core analytics)
|       |-- historical_metric_store/         # Stores historical V2.5 aggregate metrics
|       |-- historical_ohlcv_store/          # Stores historical OHLCV from Tradier/other
|       |-- performance_data_store/          # [NEW] Stores performance tracking data
|
|-- core_analytics_engine/                 # The "brain" and "nervous system" of EOTS v2.5
|   |-- __init__.py
|   |-- its_orchestrator_v2_5.py           # (Significantly Evolved) Main class orchestrating the entire v2.5 analysis cycle, invokes ATIF
|   |
|   |-- metrics_calculator_v2_5.py         # [NEW or Heavily Refactored] Calculates ALL metrics:
|   |                                        #   - Base V2.4 metrics (GIB, NVP, etc.)
|   |                                        #   - New Enhanced Rolling Flow Metrics (VAPI-FA, DWFD, TW-LAF)
|   |                                        #   - New Adaptive Metrics (A-DAG, E-SDAG, D-TDPI, VRI 2.0)
|   |                                        #   - Data for new Enhanced Heatmaps (SGDHP, IVSDH, UGCH)
|   |
|   |-- market_regime_engine_v2_5.py       # (Evolved) Classifies market regime using richer V2.5 metric inputs and SPY/SPX context
|   |
|   |-- spyspx_optimizer_v2_5.py           # [NEW or Integrated Logic] Handles SPY/SPX specific logic:
|   |                                        #   - Expiration calendar awareness
|   |                                        #   - Behavior pattern recognition
|   |                                        #   - Intraday pattern adjustments
|   |                                        #   - Outputs context to MRE, MetricsCalculator, ATIF
|   |
|   |-- signal_generator_v2_5.py           # (Evolved) Generates more nuanced, potentially scored signals based on V2.5 metrics, regime, and SPY/SPX context
|   |
|   |-- adaptive_trade_idea_framework_v2_5.py # [NEW - CENTRAL BRAIN] Replaces/augments recommendation_logic.py
|   |                                        #   - Dynamic Signal Integration (performance-based weighting)
|   |                                        #   - Performance-Based Conviction Mapping
|   |                                        #   - Enhanced Strategy Specificity (option selection)
|   |                                        #   - Intelligent Recommendation Management (adaptive exits, partial positions - directives)
|   |
|   |-- trade_parameter_optimizer_v2_5.py    # (Evolved) Calculates precise entry/targets/stops using ATIF strategy choice, Enhanced Key Levels, and VRI 2.0 for ATR multipliers
|   |
|   |-- key_level_identifier_v2_5.py       # [NEW or Integrated Logic] Implements Enhanced Key Level ID:
|   |                                        #   - Multi-timeframe analysis
|   |                                        #   - Advanced Wall/Trigger detection (using GIB, SGDHP, UGCH)
|   |                                        #   - Conviction-based level scoring
|
|-- dashboard_application_v2_5/            # Dash application for visualization and interaction
|   |-- __init__.py
|   |-- app_main_v2_5.py                   # (Evolved) Main Dash app definition, server instantiation
|   |-- layout_manager_v2_5.py             # (Evolved) Dynamically builds V2.5 dashboard layout (new heatmaps, flow metrics)
|   |-- callback_manager_v2_5.py           # (Evolved) Registers and organizes all V2.5 Dash callbacks
|   |-- styling_v2_5.py                    # (Evolved) CSS variables, Plotly templates, themes for V2.5
|   |-- utils_dashboard_v2_5.py            # (Evolved) Shared utilities for V2.5 dashboard
|   |
|   |-- assets/                            # Static assets (custom.css, images, fonts)
|   |   |-- custom_v2_5.css
|   |
|   |-- modes/                             # Sub-package for different dashboard views/modes
|       |-- __init__.py
|       |-- main_dashboard_display_v2_5.py     # (Evolved) Logic for the core/main dashboard layout and its charts
|       |-- flow_metrics_display_v2_5.py       # [NEW or Enhanced] Display for VAPI-FA, DWFD, TW-LAF
|       |-- advanced_heatmaps_display_v2_5.py  # [NEW] Display for SGDHP, IVSDH, UGCH
|       |-- volatility_deep_dive_v2_5.py   # (Evolved) For VRI 2.0, 0DTE vol metrics
|       |-- structure_analysis_v2_5.py     # (Evolved) For A-DAG, E-SDAG, new Key Levels
|       |-- spyspx_context_display_v2_5.py   # [NEW] Displays active SPY/SPX patterns, expiration info
|       |-- performance_review_display_v2_5.py # [NEW] Displays ATIF performance metrics, signal weights (optional)
|       |-- # (Potentially other evolved/new display modules)
|
|-- utils/                                 # General utility functions (if any are not dashboard specific)
|   |-- __init__.py
|   |-- config_manager_v2_5.py             # [NEW/EVOLVED] Pydantic-based or schema-enforcing config loader
|   |-- common_data_structures_v2_5.py     # (Optional) Pydantic models for shared data if not in each module
|
|-- notebooks/                             # (Optional) Jupyter notebooks for research, testing, analysis
|   |-- 01_metric_validation_v2_5.ipynb
|   |-- 02_regime_backtesting_v2_5.ipynb
|
|-- tests/                                 # Unit and integration tests
    |-- __init__.py
    |-- test_data_management_v2_5/
    |-- test_core_analytics_v2_5/
    |   |-- test_metrics_calculator_v2_5.py
    |   |-- test_market_regime_engine_v2_5.py
    |   |-- test_atif_v2_5.py
    |   |-- # ... other analytics tests
    |-- test_dashboard_v2_5/
