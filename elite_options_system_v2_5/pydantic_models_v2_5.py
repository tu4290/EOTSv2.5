# pydantic_models_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date

# --- Utility Functions for Pydantic Models (if needed) ---
def to_camel(string: str) -> str:
    return ''.join(word.capitalize() for word in string.split('_'))

class EOTSBaseModel(BaseModel):
    class Config:
        alias_generator = to_camel
        populate_by_name = True # Changed from allow_population_by_field_name for Pydantic v2
        extra = 'ignore' # Ignore extra fields from input data not defined in model

# --- Raw Data Models (as fetched or initially combined) ---

class OptionContractRawV2_5(EOTSBaseModel):
    # Fields directly from ConvexValue get_chain_as_rows (prefix + additional)
    # These field names should match the DataFrame columns *after* fetcher's initial renaming
    # but *before* InitialDataProcessor adds more context or MetricsCalculator adds metrics.

    # Prefix columns (example names, actual names depend on fetcher's output mapping)
    option_symbol_api_raw_cv: Optional[str] = Field(None, alias="optionSymbolApiRawCv") # Example alias
    expiration_days_from_epoch_calc: Optional[float] = None # Or int, depends on CV output for this field
    strike: Optional[float] = None
    opt_kind: Optional[str] = None # 'call' or 'put'

    # Common required fields (examples, ensure these match config for required raw cols)
    oi: Optional[float] = Field(None, description="Open Interest")
    price: Optional[float] = Field(None, alias="optionPrice", description="Option's last traded price or mark")
    volatility: Optional[float] = Field(None, alias="optionImpliedVol", description="Option's Implied Volatility")
    multiplier: Optional[float] = Field(None, description="Contract multiplier, e.g., 100")

    # Greeks (examples, full list from config: metrics_io_params.convexvalue_fields.get_chain_additional_params)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    charm: Optional[float] = None
    vanna: Optional[float] = None
    vomma: Optional[float] = None

    # Exposures (OI-weighted Greeks)
    dxoi: Optional[float] = Field(None, alias="deltaTimesOi")
    gxoi: Optional[float] = Field(None, alias="gammaTimesOi")
    vxoi: Optional[float] = Field(None, alias="vegaTimesOi")
    txoi: Optional[float] = Field(None, alias="thetaTimesOi")
    charmxoi: Optional[float] = Field(None, alias="charmTimesOi")
    vannaxoi: Optional[float] = Field(None, alias="vannaTimesOi")
    vommaxoi: Optional[float] = Field(None, alias="vommaTimesOi")

    # Volume-weighted Greeks (Proxies for Greek flow if signed flow not available per contract)
    dxvolm: Optional[float] = Field(None, alias="deltaTimesVol")
    gxvolm: Optional[float] = Field(None, alias="gammaTimesVol")
    # ... add others like vxvolm, txvolm, charmxvolm, vannaxvolm, vommaxvolm

    # Signed Net Flows per contract (if available from CV, otherwise these might be calculated at strike level)
    # These are typically rolling sums like valuebs_5m, volmbs_5m, etc.
    # For Pydantic, it's cleaner to have these as nested dicts if there are many intervals
    # Or list them if there are only a few fixed ones.
    valuebs_5m: Optional[float] = Field(None, alias="valueBuySell5m")
    volmbs_5m: Optional[float] = Field(None, alias="volumeBuySell5m")
    valuebs_15m: Optional[float] = Field(None, alias="valueBuySell15m")
    volmbs_15m: Optional[float] = Field(None, alias="volumeBuySell15m")
    # ... add other configured rolling flow intervals from CV ...

    # Other specific fields from get_chain additional params
    # Example:
    # bid: Optional[float] = None
    # ask: Optional[float] = None
    # total_volume: Optional[float] = Field(None, alias="totalVolume")
    # smv_vol: Optional[float] = Field(None, alias="smvVolatility") # Surface/model volatility

    # Field for any other dynamic parameters fetched via get_chain_additional_params
    additional_cv_fields: Dict[str, Any] = Field(default_factory=dict)


class UnderlyingDataRawAPIV2_5(EOTSBaseModel): # Data from ConvexValue get_und
    symbol: str
    fetch_timestamp_parser_cv: Optional[datetime] = None
    api_response_symbol_und_cv: Optional[str] = None

    # Fields from config: metrics_io_params.convexvalue_fields.get_und_params
    # These are just examples, the actual fields will be dynamically populated based on config
    price: Optional[float] = Field(None, description="Underlying price from CV")
    u_volatility: Optional[float] = Field(None, description="Underlying overall IV from CV")
    # Example: gib_oi_based_und (if CV provides this directly, though guide implies calculation)
    # Example: net_gamma_flow_call_und, net_gamma_flow_put_und (if CV provides these directly)

    # Catch-all for other fields fetched based on config's get_und_params list
    # The keys in this dict will be the exact strings from the config list.
    additional_und_cv_fields: Dict[str, Any] = Field(default_factory=dict)


class TradierQuoteV2_5(EOTSBaseModel): # For Tradier /quotes endpoint
    symbol: str
    description: Optional[str] = None
    exch: Optional[str] = None
    type: Optional[str] = None # e.g., stock, etf
    last: Optional[float] = None
    change: Optional[float] = None
    change_percentage: Optional[float] = Field(None, alias="changePercentage")
    volume: Optional[float] = None
    average_volume: Optional[float] = Field(None, alias="averageVolume")
    last_volume: Optional[float] = Field(None, alias="lastVolume")
    trade_date: Optional[datetime] = Field(None, alias="tradeDate") # Timestamp
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    prevclose: Optional[float] = None
    week_52_high: Optional[float] = Field(None, alias="week52High")
    week_52_low: Optional[float] = Field(None, alias="week52Low")
    bid: Optional[float] = None
    bidsize: Optional[int] = Field(None, alias="bidSize")
    bidexch: Optional[str] = Field(None, alias="bidExch")
    bid_date: Optional[datetime] = Field(None, alias="bidDate")
    ask: Optional[float] = None
    asksize: Optional[int] = Field(None, alias="askSize")
    askexch: Optional[str] = Field(None, alias="askExch")
    ask_date: Optional[datetime] = Field(None, alias="askDate")
    root_symbols: Optional[str] = Field(None, alias="rootSymbols") # For stocks with options

class TradierOHLCVBarV2_5(EOTSBaseModel): # For Tradier /history endpoint (daily bar)
    date: date # Expecting YYYY-MM-DD string from API, Pydantic will parse to date
    open: float
    high: float
    low: float
    close: float
    volume: float

class UnderlyingDataCombinedV2_5(EOTSBaseModel): # Input to InitialProcessor
    # Combines CV underlying data with Tradier enrichments
    symbol: str
    fetch_timestamp_payload_cv: Optional[datetime] = None
    fetch_timestamp_payload_tradier: Optional[datetime] = None # If Tradier fetch has its own ts

    # Core fields (prioritized from CV if available, else Tradier)
    price: Optional[float] = None # This should be the primary underlying price for calculations

    # From ConvexValue (UnderlyingDataRawAPIV2_5 fields)
    u_volatility_cv: Optional[float] = Field(None, alias="uVolatilityCv")
    additional_und_cv_fields_combined: Dict[str, Any] = Field(default_factory=dict, alias="additionalUndCvFields")

    # From Tradier (TradierQuoteV2_5 fields, potentially prefixed)
    tradier_open: Optional[float] = None
    tradier_high: Optional[float] = None
    tradier_low: Optional[float] = None
    tradier_close: Optional[float] = None # This might be 'prevclose' if 'close' is intraday last
    tradier_prev_close: Optional[float] = None
    tradier_volume: Optional[float] = None
    tradier_iv5_approx_smv_avg: Optional[float] = Field(None, description="Tradier IV5 approx from SMV")
    # ... other relevant fields from TradierQuote ...

    # Placeholder for contract multiplier, to be filled by InitialProcessor from options chain
    multiplier: Optional[float] = None


class RawDataBundleV2_5(EOTSBaseModel): # Output from Fetchers, Input to InitialProcessor
    symbol: str
    raw_options_df_data: List[Dict[str, Any]] # List of dicts that can be loaded into OptionContractRawV2_5 or directly into DataFrame
    raw_underlying_dict_combined_data: Dict[str, Any] # Data for UnderlyingDataCombinedV2_5
    fetch_timestamp_bundle_master: datetime = Field(default_factory=datetime.now)
    error_details_cv: Optional[str] = None
    error_details_tradier: Optional[str] = None


# --- Processed Data Models (After InitialProcessor & MetricsCalculator) ---

class OptionContractProcessedV2_5(OptionContractRawV2_5): # Inherits all raw fields
    # Context fields added by InitialProcessor
    underlying_price_at_fetch: Optional[float] = None
    current_time_dt: Optional[datetime] = None # Processing time context
    processing_time_dt_obj: Optional[datetime] = None # Alias or specific time
    underlying_symbol_ctx: Optional[str] = Field(None, alias="underlyingSymbol") # Added by InitialProcessor
    dte_calculated: Optional[float] = Field(None, alias="dte") # Calculated DTE

    # Metrics added by MetricsCalculatorV2_5 (Tier 2 Adaptive per-contract metrics)
    # These are examples, full list based on what's calculated per contract
    a_dag_contract_value: Optional[float] = Field(None, alias="aDagContract") # Example if A-DAG is also on contract level
    # If E-SDAGs, D-TDPI, VRI 2.0 have per-contract versions, add them here.
    # Typically, these might be more strike-level.

    # Placeholder for any other per-contract metrics calculated
    custom_contract_metrics: Dict[str, Any] = Field(default_factory=dict)


class StrikeLevelMetricsV2_5(EOTSBaseModel):
    symbol: str
    strike: float
    # Metrics from MetricsCalculatorV2_5 (df_strike_level_metrics_obj)
    # Tier 1 (Examples)
    nvp_strike: Optional[float] = Field(None, alias="nvpAtStrike")
    nvp_vol_strike: Optional[float] = Field(None, alias="nvpVolAtStrike")
    # ... other aggregated v2.4 style metrics if calculated at strike ...

    # Tier 2 Adaptive Metrics (Examples of strike-level outputs)
    a_dag_strike_norm: Optional[float] = Field(None, alias="aDagStrikeNormalized")
    e_sdag_mult_strike_norm: Optional[float] = Field(None, alias="eSdagMultStrikeNormalized")
    e_sdag_dir_strike_norm: Optional[float] = Field(None, alias="eSdagDirStrikeNormalized")
    e_sdag_w_strike_norm: Optional[float] = Field(None, alias="eSdagWStrikeNormalized")
    e_sdag_vf_strike_norm: Optional[float] = Field(None, alias="eSdagVfStrikeNormalized")
    d_tdpi_strike_norm: Optional[float] = Field(None, alias="dTdpiStrikeNormalized")
    vri_2_0_strike_norm: Optional[float] = Field(None, alias="vri20StrikeNormalized")

    a_mspi_strike: Optional[float] = Field(None, alias="aMspiAtStrike") # Adaptive MSPI
    a_sai_strike: Optional[float] = Field(None, alias="aSaiAtStrike")   # Adaptive SAI
    a_ssi_strike: Optional[float] = Field(None, alias="aSsiAtStrike")   # Adaptive SSI

    # Data for Enhanced Heatmaps (Examples of strike-level scores)
    sgdhp_score_strike: Optional[float] = Field(None, alias="sgdhpScore")
    ugch_score_strike: Optional[float] = Field(None, alias="ugchScore")
    # IVSDH is typically a surface (strike vs DTE), so might not be a single score here unless aggregated

    # Other strike-level aggregations
    total_call_oi_strike: Optional[float] = None
    total_put_oi_strike: Optional[float] = None
    # ... etc. ...

class UnderlyingDataEnrichedV2_5(UnderlyingDataCombinedV2_5): # Inherits from combined raw
    # Context added by system
    current_market_regime_v2_5: Optional[str] = Field(None, alias="marketRegimeV25")
    ticker_context_dict_v2_5: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="tickerContextV25")

    # Aggregate Metrics (Tier 1 - Examples)
    gib_oi_based_und: Optional[float] = Field(None, alias="gibOiBased")
    hp_eod_und: Optional[float] = Field(None, alias="hpEod")
    td_gib_und: Optional[float] = Field(None, alias="tdGib")
    arfi_overall_und_avg: Optional[float] = Field(None, alias="arfiOverallAvg")
    # ... Net Customer Greek Flows (Delta, Gamma, Vega, Theta) ...
    # ... 0DTE Suite aggregates (vri_0dte_agg, vfi_0dte_agg, vvr_0dte_agg, vci_0dte_agg) ...
    # ... Standard Rolling Net Signed Flows (NetValueFlow_5m_Und, NetVolFlow_15m_Und etc.) ...

    # Aggregate Metrics (Tier 3 - Enhanced Rolling Flows)
    vapi_fa_z_score_und: Optional[float] = Field(None, alias="vapiFaZscore")
    dwfd_z_score_und: Optional[float] = Field(None, alias="dwfdZscore")
    tw_laf_z_score_und: Optional[float] = Field(None, alias="twLafZscore")

    # Summaries or data structures for Enhanced Heatmaps if stored at underlying level
    # ivsdh_surface_data_v2_5: Optional[Dict[str, List[Dict[str, Any]]]] = Field(None, alias="ivsdhSurfaceData") # Example: {dte_str: [{strike: val}, ...]}

    # ATR for TPO usage
    underlying_atr_value: Optional[float] = Field(None, alias="underlyingAtr")


class ProcessedDataBundleV2_5(EOTSBaseModel): # Output from InitialProcessor (containing MetricsCalculator results)
    symbol: str
    status: str # e.g., "SUCCESS", "ERROR", "SUCCESS_NO_OPTIONS_DATA"
    error_message: Optional[str] = None
    processing_timestamp_initial_processor_v2_5: datetime
    fetch_timestamp_original_cv: Optional[datetime] = None
    fetch_timestamp_original_tradier: Optional[datetime] = None

    # DataFrames as objects for internal use, or can be lists of Pydantic models
    options_df_with_metrics_obj: List[OptionContractProcessedV2_5] = Field(default_factory=list)
    df_strike_level_metrics_obj: List[StrikeLevelMetricsV2_5] = Field(default_factory=list)
    underlying_data_enriched_obj: UnderlyingDataEnrichedV2_5 # Must have one

    # Optional: Store the input to metrics calculator for debugging/reference
    options_df_input_to_metrics_calc_obj_ref: Optional[List[Dict[str, Any]]] = Field(None, alias="optionsDfInputRef") # Or specific model
    underlying_data_input_to_metrics_calc_obj_ref: Optional[Dict[str, Any]]] = Field(None, alias="underlyingDataInputRef")


# --- Models for Downstream Components (SignalGen, KeyLevels, ATIF, TPO) ---

class KeyLevelV2_5(EOTSBaseModel):
    level_price: float = Field(..., alias="levelPrice")
    level_type: str = Field(..., alias="levelType") # "Support", "Resistance", "PinZone", "VolTrigger", "MajorWall"
    conviction_score: float = Field(..., alias="convictionScore")
    contributing_metrics: List[str] = Field(default_factory=list, alias="contributingMetrics")
    source_component: Optional[str] = Field(None, alias="sourceComponent") # e.g., "A-MSPI", "NVP", "SGDHP"

class SignalPayloadV2_5(EOTSBaseModel):
    signal_id: str = Field(..., alias="signalId")
    timestamp_generated: datetime = Field(default_factory=datetime.now)
    symbol: str
    signal_type: str = Field(..., alias="signalType") # e.g., "AdaptiveDirectional_Bullish", "VAPI_FA_Surge_Bearish"
    base_score: float = Field(..., alias="baseScore") # Initial score from SignalGenerator
    # Details specific to the signal type
    strike_price: Optional[float] = Field(None, alias="strikePrice")
    primary_metric_value: Optional[float] = Field(None, alias="primaryMetricValue")
    supporting_metrics_summary: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="supportingMetrics")
    market_regime_at_signal: Optional[str] = Field(None, alias="marketRegimeAtSignal")
    ticker_context_at_signal: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="tickerContextAtSignal")

class ATIFContextV2_5(EOTSBaseModel): # Context passed to ATIF for decision making
    symbol: str
    current_time: datetime
    current_market_regime: str = Field(..., alias="currentMarketRegime")
    ticker_context_flags: Dict[str, Any] = Field(default_factory=dict, alias="tickerContextFlags")
    key_levels: List[KeyLevelV2_5] = Field(default_factory=list, alias="keyLevels")
    # Potentially other high-level market data like current underlying price, IV rank etc.
    current_underlying_price: Optional[float] = Field(None, alias="currentUnderlyingPrice")
    current_vri_2_0_aggregate: Optional[float] = Field(None, alias="currentVri20Agg") # Example


class ATIFTradeIdeaDirectiveV2_5(EOTSBaseModel): # Output from ATIF (Component 3) to TPO
    trade_idea_id: str = Field(..., alias="tradeIdeaId")
    symbol: str
    timestamp_generated: datetime = Field(default_factory=datetime.now)
    situational_assessment_profile: Dict[str, Any] = Field(default_factory=dict, alias="situationalAssessment") # ATIF's internal view
    final_conviction_score: float = Field(..., alias="finalConvictionScore") # 0-5 scale

    selected_strategy_type: str = Field(..., alias="selectedStrategyType") # e.g., "LongCall", "BullCallSpread"
    target_dte_min: Optional[int] = Field(None, alias="targetDteMin")
    target_dte_max: Optional[int] = Field(None, alias="targetDteMax")
    target_delta_long_leg_min: Optional[float] = Field(None, alias="targetDeltaLongMin")
    target_delta_long_leg_max: Optional[float] = Field(None, alias="targetDeltaLongMax")
    target_delta_short_leg_min: Optional[float] = Field(None, alias="targetDeltaShortMin")
    target_delta_short_leg_max: Optional[float] = Field(None, alias="targetDeltaShortMax")
    # Could include other strategy specific hints for TPO, e.g., preferred spread width, IV preference


class OptionLegDefinitionV2_5(EOTSBaseModel): # For TPO output
    option_symbol_selected: str = Field(..., alias="optionSymbol") # Full OCC symbol
    strike: float
    expiration_date: date = Field(..., alias="expirationDate")
    option_type: str = Field(..., alias="optionType") # 'call' or 'put'
    action: str # 'BUY_TO_OPEN', 'SELL_TO_OPEN', 'BUY_TO_CLOSE', 'SELL_TO_CLOSE'
    quantity: int = Field(default=1) # Default to 1 contract per leg for now
    entry_price_leg_estimate: Optional[float] = Field(None, alias="entryPriceLegEstimate") # If applicable

class TradeRecommendationV2_5(EOTSBaseModel): # Final output from TPO, managed by Orchestrator
    recommendation_id: str = Field(..., alias="recommendationId") # Generated by Orchestrator or TPO
    trade_idea_id_ref: str = Field(..., alias="tradeIdeaIdRef") # Reference to ATIF's idea
    symbol: str
    timestamp_parameterized: datetime = Field(default_factory=datetime.now)
    strategy_type: str = Field(..., alias="strategyType")
    trade_bias: str # "Bullish", "Bearish", "NeutralVol", "BearishVol"

    legs: List[OptionLegDefinitionV2_5] = Field(default_factory=list)

    calculated_entry_price_net: Optional[float] = Field(None, alias="entryPriceNet") # For the overall strategy
    stop_loss_underlying_price: Optional[float] = Field(None, alias="stopLossUnderlying")
    stop_loss_option_premium_net: Optional[float] = Field(None, alias="stopLossOptionNet") # If applicable

    target_1_underlying_price: Optional[float] = Field(None, alias="target1Underlying")
    target_1_option_premium_net: Optional[float] = Field(None, alias="target1OptionNet")
    target_2_underlying_price: Optional[float] = Field(None, alias="target2Underlying")
    target_2_option_premium_net: Optional[float] = Field(None, alias="target2OptionNet")
    target_3_underlying_price: Optional[float] = Field(None, alias="target3Underlying")
    target_3_option_premium_net: Optional[float] = Field(None, alias="target3OptionNet")

    target_rationale: Optional[str] = Field(None, alias="targetRationale")
    initial_risk_reward_ratio_t1: Optional[float] = Field(None, alias="initialRrT1")

    atif_conviction_score_at_generation: float = Field(..., alias="atifConviction")
    market_regime_at_generation: str = Field(..., alias="marketRegimeAtGeneration")
    key_metrics_at_generation: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="keyMetricsAtGeneration")

    status: str = Field(default="PENDING_NEW", alias="tradeStatus") # e.g., PENDING_NEW, ACTIVE_NEW_NO_TSL, ACTIVE_TSL_ADJUSTED, EXITED_T1, EXITED_SL
    status_update_reason: Optional[str] = Field(None, alias="statusReason")
    # Timestamps for lifecycle
    entry_timestamp_actual: Optional[datetime] = Field(None, alias="entryTimestampActual")
    exit_timestamp_actual: Optional[datetime] = Field(None, alias="exitTimestampActual")
    pnl_actual: Optional[float] = Field(None, alias="pnlActual")

    # For ATIF management directives
    current_stop_loss_underlying: Optional[float] = Field(None, alias="currentSlUnderlying")
    current_target_1_underlying: Optional[float] = Field(None, alias="currentTarget1Underlying")
    # ... other manageable parameters ...

# Example Usage (Illustrative)
if __name__ == '__main__':
    # Raw data example
    raw_option_data = {
        "strike": 4500, "optKind": "call", "expirationDaysFromEpochCalc": 19800.0,
        "oi": 1500, "optionPrice": 2.50, "optionImpliedVol": 0.25, "multiplier": 100.0,
        "delta": 0.55, "gamma": 0.02, "theta": -0.05, "vega": 0.10,
        "deltaTimesOi": 825.0, "gammaTimesOi": 30.0,
        "valueBuySell5m": 10000.0, "volumeBuySell5m": 50.0
    }
    contract_raw = OptionContractRawV2_5(**raw_option_data)
    print("\n--- Raw Option Contract ---")
    print(contract_raw.model_dump_json(indent=2, by_alias=True))

    underlying_cv_data = {
        "symbol": "SPY", "price": 450.10, "uVolatilityCv": 0.22,
        "additionalUndCvFields": {"gib_raw_cv": -500e9}
    }
    und_raw = UnderlyingDataRawAPIV2_5(**underlying_cv_data)
    print("\n--- Underlying Raw API Data ---")
    print(und_raw.model_dump_json(indent=2, by_alias=True))

    # Combined underlying data
    combined_und = UnderlyingDataCombinedV2_5(
        symbol="SPY", price=450.10, uVolatilityCv=0.22,
        tradierOpen=449.80, tradierIv5ApproxSmvAvg=0.215, multiplier=100.0
    )
    print("\n--- Underlying Combined Data ---")
    print(combined_und.model_dump_json(indent=2, by_alias=True))

    # Processed option contract
    processed_contract_data = raw_option_data.copy() # Start with raw
    processed_contract_data.update({
        "underlyingPriceAtFetch": 450.10, "dte": 0.5, "aDagContract": 15.7
    })
    contract_processed = OptionContractProcessedV2_5(**processed_contract_data)
    print("\n--- Processed Option Contract ---")
    print(contract_processed.model_dump_json(indent=2, by_alias=True))

    # Enriched underlying data
    enriched_und_data = combined_und.model_dump(by_alias=False) # Get as dict
    enriched_und_data.update({
        "marketRegimeV25": "REGIME_SPY_0DTE_AFTERNOON_LOW_VOL",
        "tickerContextV25": {"is_0DTE": True, "session": "Afternoon"},
        "gibOiBased": -450e9, "vapiFaZscore": 1.8, "underlyingAtr": 2.5
    })
    und_enriched = UnderlyingDataEnrichedV2_5(**enriched_und_data)
    print("\n--- Underlying Enriched Data ---")
    print(und_enriched.model_dump_json(indent=2, by_alias=True))

    # Processed Data Bundle
    processed_bundle = ProcessedDataBundleV2_5(
        symbol="SPY",
        status="SUCCESS",
        processing_timestamp_initial_processor_v2_5=datetime.now(),
        options_df_with_metrics_obj=[contract_processed],
        df_strike_level_metrics_obj=[ # Example strike level data
            StrikeLevelMetricsV2_5(symbol="SPY", strike=4500, aMspiAtStrike=50.0, sgdhpScore=75.0),
            StrikeLevelMetricsV2_5(symbol="SPY", strike=4510, aMspiAtStrike=-40.0, ugchScore=-60.0)
        ],
        underlying_data_enriched_obj=und_enriched
    )
    print("\n--- Processed Data Bundle ---")
    # print(processed_bundle.model_dump_json(indent=2, by_alias=True)) # Can be very long
    print(f"Processed Bundle for {processed_bundle.symbol} with status {processed_bundle.status} created.")

    # Trade Recommendation Example
    reco = TradeRecommendationV2_5(
        recommendationId="TRADE_001",
        tradeIdeaIdRef="ATIF_IDEA_XYZ",
        symbol="SPY",
        strategyType="BullCallSpread",
        tradeBias="Bullish",
        legs=[
            OptionLegDefinitionV2_5(optionSymbol="SPY231215C00450000", strike=450, expirationDate=date(2023,12,15), optionType='call', action='BUY_TO_OPEN', entryPriceLegEstimate=2.50),
            OptionLegDefinitionV2_5(optionSymbol="SPY231215C00455000", strike=455, expirationDate=date(2023,12,15), optionType='call', action='SELL_TO_OPEN', entryPriceLegEstimate=1.00)
        ],
        calculatedEntryPriceNet=1.50,
        stopLossUnderlyingPrice=448.00,
        target1UnderlyingPrice=453.00,
        atifConvictionScoreAtGeneration=4.5,
        marketRegimeAtGeneration="REGIME_BULL_TREND_CONFIRMED"
    )
    print("\n--- Trade Recommendation ---")
    print(reco.model_dump_json(indent=2, by_alias=True))
