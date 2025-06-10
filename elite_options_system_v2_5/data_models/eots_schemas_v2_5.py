# elite_options_system_v2_5/data_models/eots_schemas_v2_5.py
# Canonical Pydantic Schemas for EOTS V2.5 "Apex Predator"

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, date
import uuid

# --- Base Model ---
class EOTSBaseModel(BaseModel):
    model_config = ConfigDict(
        extra='allow', # Allow for raw, change to 'ignore' for processed if needed
        arbitrary_types_allowed=True,
        populate_by_name=True,
        validate_assignment=True
    )

# === DIRECTIVE 1.2: Canonical Raw Data Models (User Provided) ===
class RawOptionsContractV2_5(EOTSBaseModel):
    contract_symbol: str
    strike: float
    opt_kind: str
    expiration_date: str
    price: Optional[float] = None
    volatility: Optional[float] = None
    oi: Optional[int] = None
    volm: Optional[int] = None
    multiplier: Optional[int] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    vanna: Optional[float] = None
    vomma: Optional[float] = None
    charm: Optional[float] = None
    dxoi: Optional[float] = None
    gxoi: Optional[float] = None
    vxoi: Optional[float] = None
    txoi: Optional[float] = None
    vannaxoi: Optional[float] = None
    vommaxoi: Optional[float] = None
    charmxoi: Optional[float] = None
    dxvolm: Optional[float] = None
    gxvolm: Optional[float] = None
    vxvolm: Optional[float] = None
    txvolm: Optional[float] = None
    vannaxvolm: Optional[float] = None
    vommaxvolm: Optional[float] = None
    charmxvolm: Optional[float] = None
    value_bs: Optional[float] = None
    volm_bs: Optional[float] = None
    deltas_buy: Optional[float] = None
    deltas_sell: Optional[float] = None
    gammas_buy: Optional[float] = None
    gammas_sell: Optional[float] = None
    vegas_buy: Optional[float] = None
    vegas_sell: Optional[float] = None
    thetas_buy: Optional[float] = None
    thetas_sell: Optional[float] = None
    valuebs_5m: Optional[float] = None
    volmbs_5m: Optional[float] = None
    valuebs_15m: Optional[float] = None
    volmbs_15m: Optional[float] = None
    valuebs_30m: Optional[float] = None
    volmbs_30m: Optional[float] = None
    valuebs_60m: Optional[float] = None
    volmbs_60m: Optional[float] = None
    volm_buy: Optional[int] = None
    volm_sell: Optional[int] = None
    value_buy: Optional[float] = None
    value_sell: Optional[float] = None

class RawUnderlyingDataV2_5(EOTSBaseModel):
    symbol: str
    timestamp: datetime
    price: Optional[float] = None
    volatility: Optional[float] = None
    day_volume: Optional[int] = None
    call_gxoi: Optional[float] = None
    put_gxoi: Optional[float] = None
    gammas_call_buy: Optional[float] = None
    gammas_call_sell: Optional[float] = None
    gammas_put_buy: Optional[float] = None
    gammas_put_sell: Optional[float] = None
    deltas_call_buy: Optional[float] = None
    deltas_call_sell: Optional[float] = None
    deltas_put_buy: Optional[float] = None
    deltas_put_sell: Optional[float] = None
    vegas_call_buy: Optional[float] = None
    vegas_call_sell: Optional[float] = None
    vegas_put_buy: Optional[float] = None
    vegas_put_sell: Optional[float] = None
    thetas_call_buy: Optional[float] = None
    thetas_call_sell: Optional[float] = None
    thetas_put_buy: Optional[float] = None
    thetas_put_sell: Optional[float] = None
    call_vxoi: Optional[float] = None
    put_vxoi: Optional[float] = None
    call_dxoi: Optional[float] = None
    put_dxoi: Optional[float] = None
    value_bs: Optional[float] = None
    volm_bs: Optional[float] = None
    deltas_buy: Optional[float] = None
    deltas_sell: Optional[float] = None
    vegas_buy: Optional[float] = None
    vegas_sell: Optional[float] = None
    thetas_buy: Optional[float] = None
    thetas_sell: Optional[float] = None
    volm_call_buy: Optional[float] = None
    volm_put_buy: Optional[float] = None
    volm_call_sell: Optional[float] = None
    volm_put_sell: Optional[float] = None
    value_call_buy: Optional[float] = None
    value_put_buy: Optional[float] = None
    value_call_sell: Optional[float] = None
    value_put_sell: Optional[float] = None
    vflowratio: Optional[float] = None
    dxoi: Optional[float] = None
    gxoi: Optional[float] = None
    vxoi: Optional[float] = None
    txoi: Optional[float] = None
    day_open_price_und: Optional[float] = None
    day_high_price_und: Optional[float] = None
    day_low_price_und: Optional[float] = None
    prev_day_close_price_und: Optional[float] = None

# --- Tradier Specific Models (if TradierFetcher returns these) ---
class TradierQuoteV2_5(EOTSBaseModel):
    symbol: str = Field(...)
    description: Optional[str] = None
    last: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    prevclose: Optional[float] = None
    volume: Optional[int] = None

class TradierOHLCVBarV2_5(EOTSBaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int

# --- Bundle Models ---
class UnprocessedDataBundleV2_5(EOTSBaseModel):
    symbol: str = Field(...)
    raw_options_contracts: List[RawOptionsContractV2_5] = Field(default_factory=list)
    raw_underlying_data: RawUnderlyingDataV2_5
    fetch_timestamp_master: datetime = Field(default_factory=datetime.now)
    errors_cv: List[str] = Field(default_factory=list)
    errors_tradier: List[str] = Field(default_factory=list)

# --- Processed Data Models ---
class OptionContractProcessedV2_5(RawOptionsContractV2_5):
    underlying_price_at_fetch: Optional[float] = Field(None)
    current_time_dt_context: Optional[datetime] = Field(None)
    dte: Optional[float] = Field(None, description="Calculated Days To Expiration")

class StrikeLevelMetricsV2_5(EOTSBaseModel):
    symbol: str = Field(...)
    strike: float = Field(...)

class UnderlyingDataEnrichedV2_5(RawUnderlyingDataV2_5):
    current_market_regime_v2_5: Optional[str] = Field(None)
    ticker_context_dict_v2_5: Optional[Dict[str, Any]] = Field(default_factory=dict)
    resolved_dynamic_thresholds_v2_5: Optional[Dict[str, Any]] = Field(default_factory=dict)
    underlying_atr_value: Optional[float] = Field(None)

class ProcessedDataBundleV2_5(EOTSBaseModel):
    symbol: str = Field(...)
    status: str = Field(...)
    error_message: Optional[str] = Field(None)
    timestamp_processed: datetime = Field(default_factory=datetime.now)
    options_contracts_processed: List[OptionContractProcessedV2_5] = Field(default_factory=list)
    strike_level_metrics_processed: List[StrikeLevelMetricsV2_5] = Field(default_factory=list)
    underlying_data_enriched: UnderlyingDataEnrichedV2_5

# --- Analytical Output & Config Models (Placeholders for now) ---
class FinalAnalysisBundleV2_5(EOTSBaseModel): pass
class KeyLevelV2_5(EOTSBaseModel): pass
class SignalPayloadV2_5(EOTSBaseModel): pass
class TickerContextOutputV2_5(EOTSBaseModel): pass
class ATIFContextInputV2_5(EOTSBaseModel): pass
class ATIFTradeIdeaDirectiveV2_5(EOTSBaseModel): pass
class OptionLegDefinitionV2_5(EOTSBaseModel): pass
class TradeRecommendationV2_5(EOTSBaseModel): pass
class ConfigSystemSettings(EOTSBaseModel): pass
class ConfigPaths(EOTSBaseModel): pass
class EOTSConfigV2_5(EOTSBaseModel): pass # Master Config Model


# --- Analytical Output Models (from KLI, SG, ATIF, TPO) ---

class KeyLevelV2_5(EOTSBaseModel):
    level_price: float = Field(...)
    level_type: str = Field(..., description="Support, Resistance, PinZone, VolTrigger, MajorWall")
    conviction_score: float = Field(...)
    contributing_metrics: List[str] = Field(default_factory=list)
    source_component: Optional[str] = Field(None, description="e.g., A-MSPI, NVP, SGDHP")

class SignalPayloadV2_5(EOTSBaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_generated: datetime = Field(default_factory=datetime.now)
    symbol: str = Field(...)
    signal_type: str = Field(..., description="e.g., AdaptiveDirectional_Bullish, VAPI_FA_Surge_Bearish")
    base_score: float = Field(..., description="Initial score from SignalGenerator")
    strike_price: Optional[float] = Field(None)
    primary_metric_value: Optional[Any] = Field(None, description="Value of the primary metric triggering signal")
    supporting_metrics_summary: Optional[Dict[str, Any]] = Field(default_factory=dict)
    market_regime_at_signal: Optional[str] = Field(None)
    ticker_context_at_signal: Optional[Dict[str, Any]] = Field(default_factory=dict)

class TickerContextOutputV2_5(EOTSBaseModel):
    symbol: str = Field(...)
    current_datetime_utc: datetime
    is_spy_spx: bool = Field(default=False)
    expiration_context: Dict[str, Any] = Field(default_factory=dict)
    intraday_session_context: Dict[str, Any] = Field(default_factory=dict)
    behavioral_patterns_active: Dict[str, Any] = Field(default_factory=dict)
    liquidity_profile: Dict[str, Any] = Field(default_factory=dict)
    volatility_character: Dict[str, Any] = Field(default_factory=dict)
    event_context: Dict[str, Any] = Field(default_factory=dict)

class ATIFContextInputV2_5(EOTSBaseModel):
    symbol: str = Field(...)
    current_time_utc: datetime
    current_market_regime: str = Field(...)
    ticker_context_dict: TickerContextOutputV2_5 # type: ignore
    scored_signals: Dict[str, List[SignalPayloadV2_5]] = Field(default_factory=dict)
    key_levels: List[KeyLevelV2_5] = Field(default_factory=list)
    underlying_data_enriched: 'UnderlyingDataEnrichedV2_5' # Forward ref as string

class ATIFTradeIdeaDirectiveV2_5(EOTSBaseModel):
    trade_idea_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = Field(...)
    timestamp_generated: datetime = Field(default_factory=datetime.now)
    situational_assessment_profile: Dict[str, Any] = Field(default_factory=dict)
    final_conviction_score: float = Field(...)
    trade_bias: str = Field(..., description="Bullish, Bearish, NeutralVol, etc.")
    selected_strategy_type: str = Field(...)
    target_dte_min: Optional[int] = Field(None)
    target_dte_max: Optional[int] = Field(None)
    target_delta_long_leg_min: Optional[float] = Field(None)
    target_delta_long_leg_max: Optional[float] = Field(None)
    target_delta_short_leg_min: Optional[float] = Field(None)
    target_delta_short_leg_max: Optional[float] = Field(None)
    supportive_rationale_summary: Optional[str] = Field(None)

class OptionLegDefinitionV2_5(EOTSBaseModel):
    option_symbol_selected: str = Field(..., description="Full OCC symbol")
    strike: float
    expiration_date: date
    option_type: str = Field(..., description="call or put")
    action: str = Field(..., description="BUY_TO_OPEN, SELL_TO_OPEN, etc.")
    quantity: int = Field(default=1)
    entry_price_leg_estimate_bid: Optional[float] = Field(None)
    entry_price_leg_estimate_ask: Optional[float] = Field(None)
    entry_price_leg_estimate_mid: Optional[float] = Field(None)

class TradeRecommendationV2_5(EOTSBaseModel):
    recommendation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trade_idea_id_ref: str = Field(..., description="Reference to ATIF idea")
    symbol: str = Field(...)
    timestamp_parameterized: datetime = Field(default_factory=datetime.now)
    strategy_type: str = Field(...)
    trade_bias: str = Field(...)
    legs: List[OptionLegDefinitionV2_5] = Field(default_factory=list)
    calculated_entry_price_net: Optional[float] = Field(None)
    stop_loss_underlying_price: Optional[float] = Field(None)
    stop_loss_option_premium_net: Optional[float] = Field(None)
    target_1_underlying_price: Optional[float] = Field(None)
    target_1_option_premium_net: Optional[float] = Field(None)
    target_2_underlying_price: Optional[float] = Field(None)
    target_2_option_premium_net: Optional[float] = Field(None)
    target_3_underlying_price: Optional[float] = Field(None)
    target_3_option_premium_net: Optional[float] = Field(None)
    target_rationale: Optional[str] = Field(None)
    initial_risk_reward_ratio_t1: Optional[float] = Field(None)
    atif_conviction_score_at_generation: float = Field(...)
    market_regime_at_generation: str = Field(...)
    key_metrics_at_generation: Optional[Dict[str, Any]] = Field(default_factory=dict)
    status: str = Field(default="PENDING_NEW", description="Lifecycle status")
    status_update_reason: Optional[str] = Field(None)
    entry_timestamp_actual: Optional[datetime] = Field(None)
    exit_timestamp_actual: Optional[datetime] = Field(None)
    pnl_actual: Optional[float] = Field(None)
    current_stop_loss_underlying: Optional[float] = Field(None)
    current_target_1_underlying: Optional[float] = Field(None)

class FinalAnalysisBundleV2_5(EOTSBaseModel):
    symbol: str = Field(...)
    orchestration_timestamp_utc: datetime
    status: str # From ProcessedDataBundle
    error_message: Optional[str] = Field(None)
    underlying_data_enriched: 'UnderlyingDataEnrichedV2_5' # Forward ref
    options_contracts_processed: List['OptionContractProcessedV2_5'] = Field(default_factory=list) # Forward ref
    strike_level_metrics_processed: List[StrikeLevelMetricsV2_5] = Field(default_factory=list)
    key_levels: List[KeyLevelV2_5] = Field(default_factory=list)
    signals_output: Dict[str, List[SignalPayloadV2_5]] = Field(default_factory=dict)
    active_recommendations: List[TradeRecommendationV2_5] = Field(default_factory=list)

if __name__ == '__main__':
    print("EOTS V2.5 Schemas file (with analytical models) loaded and self-tested.")
    kl_data = {"level_price": 500, "level_type": "Resistance", "conviction_score": 3.5, "contributing_metrics": ["NVP", "A_MSPI"]}
    kl = KeyLevelV2_5(**kl_data)
    print(f"KeyLevel: Price {kl.level_price}, Type: {kl.level_type}, Score: {kl.conviction_score}")

# Resolve forward references if Python version < 3.9 or models are complexly ordered
# Pydantic v2 typically handles forward references automatically with type hints.
# However, explicit update_forward_refs() can be added if needed after all models are defined.
# Example:
# ATIFContextInputV2_5.model_rebuild()
# FinalAnalysisBundleV2_5.model_rebuild()
# ProcessedDataBundleV2_5.model_rebuild()


# === DIRECTIVE 1.2: Canonical Configuration Models ===
# These models will parse config_v2_5.json into a master EOTSConfigV2_5 object.
# Field names here should match keys in config_v2_5.json.
# Using populate_by_name=True in EOTSBaseModel helps if JSON uses camelCase and model fields are snake_case with aliases.

class ConfigSystemSettings(EOTSBaseModel):
    default_symbol: str = Field(default="SPY")
    log_level: str = Field(default="INFO")
    log_levels: Optional[Dict[str, str]] = Field(default_factory=dict, description="Specific log levels for modules")
    metrics_for_dynamic_threshold_distribution_tracking: List[str] = Field(default_factory=list)
    min_days_for_dynamic_threshold_activation: int = Field(default=20)
    dynamic_threshold_history_days: int = Field(default=60)
    historical_data_manager_activation: Dict[str, bool] = Field(default_factory=lambda: {"enable_ohlcv_storage": True, "enable_ohlcv_retrieval": True, "enable_metric_storage": True, "enable_metric_retrieval": True, "enable_average_iv_retrieval": True})
    performance_tracker_activation: Dict[str, bool] = Field(default_factory=lambda: {"enable_tracking": True, "enable_retrieval": True})

class ConfigPaths(EOTSBaseModel):
    data_cache_root_dir: str = Field(default="data_cache")
    performance_data_store_dir: str = Field(default="data_cache/performance_data_store") # Corrected default
    historical_data_store_dir: str = Field(default="data_cache/historical_data_store") # Corrected default
    log_file_path: str = Field(default="logs/eots_v2_5.log")

class ConfigCVFetcherCreds(EOTSBaseModel):
    email_env_var: str = Field(default="CONVEX_EMAIL")
    password_env_var: str = Field(default="CONVEX_PASSWORD")
    environment: str = Field(default="pro")

class ConfigCVFetcherFetch(EOTSBaseModel):
    max_retries: int = Field(default=3)
    base_retry_delay_seconds: float = Field(default=1.0)
    max_retry_delay_seconds: float = Field(default=10.0)
    inter_call_delay_seconds: float = Field(default=0.25)
    default_dte_range: List[int] = Field(default_factory=lambda: [0, 1, 7, 14, 30, 60, 90])
    default_price_range_pct: float = Field(default=0.075)

class ConfigCVFetcher(EOTSBaseModel):
    api_credentials: ConfigCVFetcherCreds = Field(default_factory=ConfigCVFetcherCreds)
    fetch_config: ConfigCVFetcherFetch = Field(default_factory=ConfigCVFetcherFetch)

class ConfigTradierAPI(EOTSBaseModel):
    base_url: str = Field(default="https://api.tradier.com/v1/")
    access_token_env_var: str = Field(default="TRADIER_ACCESS_TOKEN_V2_5")
    request_timeout_seconds: float = Field(default=20.0)

class ConfigTradierRetry(EOTSBaseModel):
    max_retries: int = Field(default=3)
    base_delay_seconds: float = Field(default=1.0)
    max_delay_seconds: float = Field(default=10.0)
    jitter: bool = Field(default=True)

class ConfigTradierFeatures(EOTSBaseModel):
    ohlcv_default_days_back: int = Field(default=35)
    iv_approximation_target_dte: int = Field(default=5)

class ConfigTradierFetcher(EOTSBaseModel):
    api_config: ConfigTradierAPI = Field(default_factory=ConfigTradierAPI)
    retry_config: ConfigTradierRetry = Field(default_factory=ConfigTradierRetry)
    feature_config: ConfigTradierFeatures = Field(default_factory=ConfigTradierFeatures)

class ConfigDataFetcherSettings(EOTSBaseModel):
    convexvalue: ConfigCVFetcher = Field(default_factory=ConfigCVFetcher)
    tradier: ConfigTradierFetcher = Field(default_factory=ConfigTradierFetcher)
    default_fetch_params: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ConfigMetricsIOParamsCVFields(EOTSBaseModel):
    get_und_params: List[str] = Field(default_factory=list)
    get_chain_additional_params: List[str] = Field(default_factory=list)
    get_chain_prefix_params: List[str] = Field(default_factory=list)

class ConfigMetricsIOParams(EOTSBaseModel):
    convexvalue_fields: ConfigMetricsIOParamsCVFields = Field(default_factory=ConfigMetricsIOParamsCVFields)
    historical_iv_metric_key: str = Field(default="underlying_iv_daily")

class ConfigColumnNameMappingsInputChain(EOTSBaseModel):
    strike_col: str = Field(default="strike")
    option_kind_col: str = Field(default="opt_kind")
    # Add all relevant mappings from config_v2_5.json for input_chain_fields

class ConfigColumnNameMappings(EOTSBaseModel):
    input_chain_fields: ConfigColumnNameMappingsInputChain = Field(default_factory=ConfigColumnNameMappingsInputChain)
    convexvalue_internal: Optional[Dict[str,str]] = Field(default_factory=dict)
    underlying_fields: Optional[Dict[str,str]] = Field(default_factory=dict)
    strike_level_metric_cols: Optional[Dict[str,str]] = Field(default_factory=dict)
    underlying_metric_keys: Optional[Dict[str,str]] = Field(default_factory=dict)

class ConfigATIF(EOTSBaseModel):
    min_conviction_to_initiate_trade: float = Field(default=2.5)
    signal_integration_params: Optional[Dict[str, Any]] = Field(default_factory=dict)
    conviction_mapping_params: Optional[Dict[str, Any]] = Field(default_factory=dict)
    strategy_specificity_rules: Optional[Dict[str, Any]] = Field(default_factory=dict)
    intelligent_recommendation_management_rules: Optional[Dict[str, Any]] = Field(default_factory=dict)
    learning_params: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ConfigMRE(EOTSBaseModel):
    default_regime: str = Field(default="REGIME_UNDEFINED_V2_5")
    regime_evaluation_order: List[str] = Field(default_factory=list)
    regime_rules: Dict[str, Any] = Field(default_factory=dict)
    time_of_day_definitions: Dict[str, Any] = Field(default_factory=dict)
    dynamic_threshold_definitions: Dict[str, Any] = Field(default_factory=dict)

# --- Master Configuration Model ---
class EOTSConfigV2_5(EOTSBaseModel): # Master Config Model
    system_settings: ConfigSystemSettings = Field(default_factory=ConfigSystemSettings)
    paths: ConfigPaths = Field(default_factory=ConfigPaths)
    data_fetcher_settings: ConfigDataFetcherSettings = Field(default_factory=ConfigDataFetcherSettings)
    metrics_io_params: ConfigMetricsIOParams = Field(default_factory=ConfigMetricsIOParams)
    column_name_mappings: ConfigColumnNameMappings = Field(default_factory=ConfigColumnNameMappings)
    adaptive_metric_params: Optional[Dict[str, Any]] = Field(default_factory=dict)
    enhanced_flow_metric_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    adaptive_trade_idea_framework_settings: ConfigATIF = Field(default_factory=ConfigATIF)
    ticker_context_analyzer_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    market_regime_engine_settings: ConfigMRE = Field(default_factory=ConfigMRE)
    key_level_identifier_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    signal_generator_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    trade_parameter_optimizer_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    heatmap_generation_settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    symbol_specific_overrides: Dict[str, Any] = Field(default_factory=dict, description="Can contain partial EOTSConfigV2_5 like structures for overrides")

if __name__ == '__main__':
    print("EOTS V2.5 Schemas file (with initial config models) loaded.")
    try:
        base_config = EOTSConfigV2_5()
        print(f"Default symbol from config model: {base_config.system_settings.default_symbol}")
        print(f"Default CV Fetcher retries: {base_config.data_fetcher_settings.convexvalue.fetch_config.max_retries}")
        print(f"ATIF min conviction: {base_config.adaptive_trade_idea_framework_settings.min_conviction_to_initiate_trade}")
        # Test accessing a potentially camelCased key if config file was camelCase
        # Example: if JSON had 'defaultSymbol' under 'systemSettings'
        # config_dict_example = {'systemSettings': {'defaultSymbol': 'TEST', 'logLevel': 'DEBUG'}}
        # test_config = EOTSConfigV2_5(**config_dict_example)
        # print(f'Tested with camelCase input: {test_config.system_settings.default_symbol}')
    except Exception as e:
        print(f"Error instantiating EOTSConfigV2_5 in __main__: {e}")

# Forward reference resolution
ATIFContextInputV2_5.model_rebuild()
FinalAnalysisBundleV2_5.model_rebuild()
ProcessedDataBundleV2_5.model_rebuild()
