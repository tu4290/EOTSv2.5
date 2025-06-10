# pydantic_models_v2_5.py
# (Elite Options Trading System Version 2.5 - Apex Predator)

from pydantic import BaseModel, Field, ConfigDict # Import ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import uuid

class EOTSBaseModel(BaseModel):
    model_config = ConfigDict( # Pydantic v2 style
        extra='ignore',
        arbitrary_types_allowed=True,
        populate_by_name=True # Allow population by field name OR alias
    )

class OptionContractRawV2_5(EOTSBaseModel): # RESTORED TO FULL DEFINITION
    # Prefix columns (names here should match Python field names)
    option_symbol_api_raw_cv: Optional[str] = Field(None, alias="optionSymbolApiRawCv")
    expiration_days_from_epoch_calc: Optional[float] = Field(None, alias="expirationDaysFromEpochCalc")
    strike: Optional[float] = Field(None)
    opt_kind: Optional[str] = Field(None, alias="optKind")

    # Common required fields (Python field names)
    oi: Optional[float] = Field(None, alias="oi", description="Open Interest") # Added alias for consistency
    price: Optional[float] = Field(None, alias="optionPrice", description="Option's last traded price or mark")
    volatility: Optional[float] = Field(None, alias="optionImpliedVol", description="Option's Implied Volatility")
    multiplier: Optional[float] = Field(None, alias="multiplier", description="Contract multiplier, e.g., 100") # Added alias

    # Greeks (Python field names)
    delta: Optional[float] = Field(None, alias="delta")
    gamma: Optional[float] = Field(None, alias="gamma")
    theta: Optional[float] = Field(None, alias="theta")
    vega: Optional[float] = Field(None, alias="vega")
    charm: Optional[float] = Field(None, alias="charm")
    vanna: Optional[float] = Field(None, alias="vanna")
    vomma: Optional[float] = Field(None, alias="vomma")

    # Exposures (OI-weighted Greeks) - Aliases match common external data keys
    dxoi: Optional[float] = Field(None, alias="deltaTimesOi")
    gxoi: Optional[float] = Field(None, alias="gammaTimesOi")
    vxoi: Optional[float] = Field(None, alias="vegaTimesOi")
    txoi: Optional[float] = Field(None, alias="thetaTimesOi")
    charmxoi: Optional[float] = Field(None, alias="charmTimesOi")
    vannaxoi: Optional[float] = Field(None, alias="vannaTimesOi")
    vommaxoi: Optional[float] = Field(None, alias="vommaTimesOi")

    # Volume-weighted Greeks (Proxies) - Aliases match common external data keys
    dxvolm: Optional[float] = Field(None, alias="deltaTimesVol")
    gxvolm: Optional[float] = Field(None, alias="gammaTimesVol")
    vxvolm: Optional[float] = Field(None, alias="vegaTimesVol")
    txvolm: Optional[float] = Field(None, alias="thetaTimesVol")
    charmxvolm: Optional[float] = Field(None, alias="charmTimesVol")
    vannaxvolm: Optional[float] = Field(None, alias="vannaTimesVol")
    vommaxvolm: Optional[float] = Field(None, alias="vommaTimesVol")


    # Signed Net Flows per contract - Aliases match common external data keys
    valuebs_5m: Optional[float] = Field(None, alias="valueBuySell5m")
    volmbs_5m: Optional[float] = Field(None, alias="volumeBuySell5m")
    valuebs_15m: Optional[float] = Field(None, alias="valueBuySell15m")
    volmbs_15m: Optional[float] = Field(None, alias="volumeBuySell15m")

    # Other specific fields from get_chain additional params
    bid: Optional[float] = Field(None, alias="bid") # Added alias
    ask: Optional[float] = Field(None, alias="ask") # Added alias
    total_volume: Optional[float] = Field(None, alias="totalVolume")
    smv_vol: Optional[float] = Field(None, alias="smvVolatility")
    additional_cv_fields: Dict[str, Any] = Field(default_factory=dict, alias="additionalCvFields") # Added alias


class UnderlyingDataRawAPIV2_5(EOTSBaseModel):
    symbol: str
    fetch_timestamp_parser_cv: Optional[datetime] = Field(None, alias="fetchTimestampParserCv")
    api_response_symbol_und_cv: Optional[str] = Field(None, alias="apiResponseSymbolUndCv")
    price: Optional[float] = Field(None, alias="price", description="Underlying price from CV")
    u_volatility_cv: Optional[float] = Field(None, alias="uVolatilityCv", description="Underlying overall IV from CV")
    additional_und_cv_fields: Dict[str, Any] = Field(default_factory=dict, alias="additionalUndCvFields")

class TradierQuoteV2_5(EOTSBaseModel):
    symbol: str
    description: Optional[str] = Field(None)
    exch: Optional[str] = Field(None)
    type: Optional[str] = Field(None)
    last: Optional[float] = Field(None)
    change: Optional[float] = Field(None)
    change_percentage: Optional[float] = Field(None, alias="changePercentage")
    volume: Optional[float] = Field(None)
    average_volume: Optional[float] = Field(None, alias="averageVolume")
    last_volume: Optional[float] = Field(None, alias="lastVolume")
    trade_date: Optional[datetime] = Field(None, alias="tradeDate")
    open: Optional[float] = Field(None)
    high: Optional[float] = Field(None)
    low: Optional[float] = Field(None)
    close: Optional[float] = Field(None)
    prevclose: Optional[float] = Field(None)
    week_52_high: Optional[float] = Field(None, alias="week52High")
    week_52_low: Optional[float] = Field(None, alias="week52Low")
    bid: Optional[float] = Field(None)
    bidsize: Optional[int] = Field(None, alias="bidSize")
    bidexch: Optional[str] = Field(None, alias="bidExch")
    bid_date: Optional[datetime] = Field(None, alias="bidDate")
    ask: Optional[float] = Field(None)
    asksize: Optional[int] = Field(None, alias="askSize")
    askexch: Optional[str] = Field(None, alias="askExch")
    ask_date: Optional[datetime] = Field(None, alias="askDate")
    root_symbols: Optional[str] = Field(None, alias="rootSymbols")

class TradierOHLCVBarV2_5(EOTSBaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

class UnderlyingDataCombinedV2_5(EOTSBaseModel):
    symbol: str
    fetch_timestamp_payload_cv: Optional[datetime] = Field(None, alias="fetchTimestampPayloadCv")
    fetch_timestamp_payload_tradier: Optional[datetime] = Field(None, alias="fetchTimestampPayloadTradier")
    price: Optional[float] = Field(None)
    u_volatility_cv: Optional[float] = Field(None, alias="uVolatilityCv")
    additional_und_cv_fields: Dict[str, Any] = Field(default_factory=dict, alias="additionalUndCvFields")
    tradier_open: Optional[float] = Field(None, alias="tradierOpen")
    tradier_high: Optional[float] = Field(None, alias="tradierHigh")
    tradier_low: Optional[float] = Field(None, alias="tradierLow")
    tradier_close: Optional[float] = Field(None, alias="tradierClose")
    tradier_prev_close: Optional[float] = Field(None, alias="tradierPrevClose")
    tradier_volume: Optional[float] = Field(None, alias="tradierVolume")
    tradier_iv5_approx_smv_avg: Optional[float] = Field(None, alias="tradierIv5ApproxSmvAvg", description="Tradier IV5 approx from SMV")
    multiplier: Optional[float] = Field(None)

class RawDataBundleV2_5(EOTSBaseModel):
    symbol: str
    raw_options_df_data: List[Dict[str, Any]] = Field(default_factory=list, alias="rawOptionsDfData")
    raw_underlying_dict_combined_data: Dict[str, Any] = Field(default_factory=dict, alias="rawUnderlyingDictCombinedData")
    fetch_timestamp_bundle_master: datetime = Field(default_factory=datetime.now, alias="fetchTimestampBundleMaster")
    error_details_cv: Optional[str] = Field(None, alias="errorDetailsCv")
    error_details_tradier: Optional[str] = Field(None, alias="errorDetailsTradier")

class OptionContractProcessedV2_5(OptionContractRawV2_5):
    underlying_price_at_fetch: Optional[float] = Field(None)
    current_time_dt: Optional[datetime] = Field(None)
    processing_time_dt_obj: Optional[datetime] = Field(None)
    underlying_symbol_ctx: Optional[str] = Field(None, alias="underlyingSymbol")
    dte_calculated: Optional[float] = Field(None, alias="dte")
    custom_contract_metrics: Dict[str, Any] = Field(default_factory=dict)

class StrikeLevelMetricsV2_5(EOTSBaseModel):
    symbol: str
    strike: float
    nvp_strike: Optional[float] = Field(None, alias="nvpAtStrike")
    a_mspi_strike: Optional[float] = Field(None, alias="aMspiAtStrike")

class UnderlyingDataEnrichedV2_5(UnderlyingDataCombinedV2_5):
    current_market_regime_v2_5: Optional[str] = Field(None, alias="marketRegimeV25")
    ticker_context_dict_v2_5: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="tickerContextV25")
    gib_oi_based_und: Optional[float] = Field(None, alias="gibOiBased")
    vapi_fa_z_score_und: Optional[float] = Field(None, alias="vapiFaZscore")
    underlying_atr_value: Optional[float] = Field(None, alias="underlyingAtr")

class ProcessedDataBundleV2_5(EOTSBaseModel):
    symbol: str
    status: str
    error_message: Optional[str] = Field(None)
    processing_timestamp_initial_processor_v2_5: datetime
    options_df_with_metrics_obj: List[OptionContractProcessedV2_5] = Field(default_factory=list)
    df_strike_level_metrics_obj: List[StrikeLevelMetricsV2_5] = Field(default_factory=list)
    underlying_data_enriched_obj: UnderlyingDataEnrichedV2_5
    options_df_input_to_metrics_calc_obj_ref: Optional[List[Dict[str, Any]]] = Field(None, alias="optionsDfInputRef")
    underlying_data_input_to_metrics_calc_obj_ref: Optional[Dict[str, Any]] = Field(None, alias="underlyingDataInputRef")

class KeyLevelV2_5(EOTSBaseModel):
    level_price: float
    level_type: str
    conviction_score: float
    contributing_metrics: List[str] = Field(default_factory=list)
    source_component: Optional[str] = Field(None)

class SignalPayloadV2_5(EOTSBaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_generated: datetime = Field(default_factory=datetime.now)
    symbol: str
    signal_type: str
    base_score: float
    strike_price: Optional[float] = Field(None)
    primary_metric_value: Optional[Any] = Field(None)
    supporting_metrics_summary: Optional[Dict[str, Any]] = Field(default_factory=dict)
    market_regime_at_signal: Optional[str] = Field(None)
    ticker_context_at_signal: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ATIFContextV2_5(EOTSBaseModel):
    symbol: str
    current_time: datetime
    current_market_regime: str
    ticker_context_flags: Dict[str, Any] = Field(default_factory=dict)
    key_levels: List[KeyLevelV2_5] = Field(default_factory=list)
    current_underlying_price: Optional[float] = Field(None)
    current_vri_2_0_aggregate: Optional[float] = Field(None)

class ATIFTradeIdeaDirectiveV2_5(EOTSBaseModel):
    trade_idea_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    timestamp_generated: datetime = Field(default_factory=datetime.now)
    final_conviction_score: float
    selected_strategy_type: str
    target_dte_min: Optional[int] = Field(None)
    # ... other fields ...

class OptionLegDefinitionV2_5(EOTSBaseModel):
    option_symbol_selected: str
    strike: float
    expiration_date: date
    option_type: str
    action: str
    # ... other fields ...

class TradeRecommendationV2_5(EOTSBaseModel):
    recommendation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trade_idea_id_ref: str
    symbol: str
    # ... other fields ...
    legs: List[OptionLegDefinitionV2_5] = Field(default_factory=list)
    status: str = Field(default="PENDING_NEW")

if __name__ == '__main__':
    print("Pydantic models v2.5 file syntax check (full models, populate_by_name=True).")
    test_data_full_contract = {
        "optionSymbolApiRawCv": "SPY241220C00500000",
        "expirationDaysFromEpochCalc": 19700.0,
        "strike": 500.0, "optKind": "call", "oi": 1200.0,
        "optionPrice": 10.50,
        "optionImpliedVol": 0.225,
        "multiplier": 100.0, "delta": 0.55, "gamma": 0.015, "theta": -0.08, "vega": 0.25,
        "deltaTimesOi": 660.0,
        "gammaTimesOi": 18.0,
        "valueBuySell5m": 50000.0,
        "volumeBuySell5m": 250.0,
        "bid": 10.45, "ask": 10.55, "totalVolume": 15000, "smvVolatility": 0.220
    }
    try:
        contract_alias = OptionContractRawV2_5(**test_data_full_contract)
        print(f"Full OptionContractRawV2_5 (aliases): price={contract_alias.price}, opt_kind={contract_alias.opt_kind}, dxoi={contract_alias.dxoi}")
        assert contract_alias.price == 10.50
        assert contract_alias.opt_kind == "call"
        assert contract_alias.dxoi == 660.0
        print("Full OptionContractRawV2_5 can be instantiated via aliases (with populate_by_name=True).")

        test_data_field_names = {
            "option_symbol_api_raw_cv": "SPY241220P00400000",
            "expiration_days_from_epoch_calc": 19700.0,
            "strike": 400.0, "opt_kind": "put", "oi": 100.0,
            "price": 8.20, "volatility": 0.28,
            "multiplier": 100.0, "delta": -0.35, "gamma": 0.010, "theta": -0.07, "vega": 0.20,
            "dxoi": -35.0, "gxoi": 1.0,
            "valuebs_5m": -20000.0, "volmbs_5m": -100.0,
            "bid": 11.95, "ask": 12.05, "total_volume": 8000, "smv_vol": 0.275
        }
        contract_field = OptionContractRawV2_5(**test_data_field_names)
        print(f"Full OptionContractRawV2_5 (field names): price={contract_field.price}, opt_kind={contract_field.opt_kind}, dxoi={contract_field.dxoi}")
        assert contract_field.price == 8.20
        assert contract_field.opt_kind == "put"
        assert contract_field.dxoi == -35.0
        print("Full OptionContractRawV2_5 can be instantiated via field names (with populate_by_name=True).")

    except Exception as e:
        print(f"Error instantiating OptionContractRawV2_5 in __main__: {e}")
