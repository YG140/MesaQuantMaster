from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class InvestmentClass(StrEnum):
    STOCK = "stock"
    FII = "fii"
    ETF = "etf"
    TREASURY = "treasury"
    CDB = "cdb"
    LCI = "lci"
    LCA = "lca"
    DEBENTURE = "debenture"
    INVESTMENT_FUND = "investment_fund"
    BDR = "bdr"
    INTERNATIONAL = "international"
    CRYPTO = "crypto"
    UNKNOWN = "unknown"


class IndicatorStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_DATA = "insufficient_data"
    POTENTIALLY_INCONSISTENT = "potentially_inconsistent"
    PARTIAL = "partial"
    INVALID = "invalid"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class IndicatorDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    IDEAL_RANGE = "ideal_range"
    INFORMATIONAL = "informational"
    CONTEXT_DEPENDENT = "context_dependent"


class IndicatorLayer(StrEnum):
    FUNDAMENTAL = "fundamental"
    CLASS_SPECIFIC = "class_specific"
    MACRO_MARKET = "macro_market"
    TECHNICAL_ALTERNATIVE = "technical_alternative"


class AnalysisImpact(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    BLOCKING = "blocking"
    INFORMATIONAL = "informational"
    UNKNOWN = "unknown"


class RecommendationAction(StrEnum):
    ANALYZE_TO_BUY = "analyze_to_buy"
    BUY_GRADUALLY = "buy_gradually"
    INCREASE_POSITION = "increase_position"
    HOLD = "hold"
    WAIT = "wait"
    REDUCE_EXPOSURE = "reduce_exposure"
    CONSIDER_SELLING = "consider_selling"
    REVIEW_DATA = "review_data"
    INSUFFICIENT_DATA = "insufficient_data"


class ValuationStatus(StrEnum):
    VERY_ATTRACTIVE = "very_attractive"
    ATTRACTIVE = "attractive"
    NEAR_ESTIMATED_VALUE = "near_estimated_value"
    ELEVATED = "elevated"
    VERY_ELEVATED = "very_elevated"
    INSUFFICIENT_DATA = "insufficient_data"


class IndicatorCatalogEntry(BaseModel):
    key: str
    label: str
    description: str
    formula_or_origin: str = "Provider de mercado"
    unit: str
    category: str = "qualidade dos dados"
    layer: IndicatorLayer = IndicatorLayer.FUNDAMENTAL
    applicable_classes: list[InvestmentClass]
    excluded_sectors: list[str] = Field(default_factory=list)
    direction: IndicatorDirection
    plausible_min: Decimal | None = None
    plausible_max: Decimal | None = None
    requires_history: bool = False
    temporal_validity_days: int | None = 2
    source: str = "BRAPI"
    updated_at: datetime | None = None
    availability: IndicatorStatus = IndicatorStatus.UNAVAILABLE
    required: bool = False
    default_weight: Decimal = Decimal("1")
    sector_comparable: bool = False
    history_comparable: bool = False


class NormalizedIndicator(BaseModel):
    key: str
    label: str
    description: str | None = None
    category: str = "qualidade dos dados"
    layer: IndicatorLayer = IndicatorLayer.FUNDAMENTAL
    value: Decimal | str | None = None
    display_value: str | None = None
    unit: str
    status: IndicatorStatus
    source: str
    source_type: str = "provider"
    reference_date: datetime | None = None
    collected_at: datetime
    valid_until: datetime | None = None
    freshness_status: str = "current"
    confidence: ConfidenceLevel
    period: str | None = None
    unavailable_reason: str | None = None
    sector_comparison: str | None = None
    historical_comparison: str | None = None
    explanation: str | None = None
    impact: AnalysisImpact = AnalysisImpact.UNKNOWN


class ScoreBreakdown(BaseModel):
    value: Decimal | None = None
    available_indicators: int
    missing_indicators: int
    stale_indicators: int
    coverage_percentage: Decimal
    confidence: ConfidenceLevel
    reasons: list[str] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    data_quality_score: Decimal | None = None
    data_completeness: Decimal
    data_freshness: Decimal
    anomaly_flags: list[str] = Field(default_factory=list)
    missing_indicators: list[str] = Field(default_factory=list)
    non_applicable_indicators: list[str] = Field(default_factory=list)
    recommendation_blocked: bool = False
    blocking_reason: str | None = None


class MacroIndicatorDefinition(BaseModel):
    key: str
    label: str
    description: str
    region: str
    unit: str
    frequency: str
    source: str
    state: IndicatorStatus = IndicatorStatus.UNAVAILABLE


class MacroIndicatorSnapshot(BaseModel):
    key: str
    label: str
    value: Decimal | str | None = None
    period: str | None = None
    source: str
    updated_at: datetime | None = None
    frequency: str
    history_available: bool = False
    state: IndicatorStatus


class ValuationAssessment(BaseModel):
    status: ValuationStatus
    methods: list[str] = Field(default_factory=list)
    used_indicators: list[str] = Field(default_factory=list)
    missing_indicators: list[str] = Field(default_factory=list)
    historical_comparison: str | None = None
    peer_comparison: str | None = None
    estimated_range_low: Decimal | None = None
    estimated_range_high: Decimal | None = None
    confidence: ConfidenceLevel
    data_date: datetime | None = None


class AssetIntelligenceSnapshot(BaseModel):
    asset_id: UUID | None = None
    symbol: str
    name: str | None = None
    asset_class: InvestmentClass
    current_price: Decimal | None = None
    currency: str | None = None
    market_updated_at: datetime | None = None
    indicators: list[NormalizedIndicator]
    quality_score: Decimal | None = None
    valuation_score: Decimal | None = None
    income_score: Decimal | None = None
    growth_score: Decimal | None = None
    debt_score: Decimal | None = None
    risk_score: Decimal | None = None
    liquidity_score: Decimal | None = None
    data_quality_score: Decimal | None = None
    strategy_fit_score: Decimal | None = None
    overall_score: Decimal | None = None
    recommendation: RecommendationAction
    valuation_status: ValuationStatus
    valuation: ValuationAssessment
    confidence: ConfidenceLevel
    coverage_percentage: Decimal
    available_indicators_count: int
    missing_indicators_count: int
    stale_indicators_count: int
    non_applicable_indicators_count: int = 0
    anomaly_flags: list[str] = Field(default_factory=list)
    data_quality: DataQualityReport | None = None
    positive_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    calculated_at: datetime


class AssetAnalysisError(BaseModel):
    symbol: str
    message: str


class AnalyzeAssetsRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=50)


class BatchAssetAnalysisResponse(BaseModel):
    snapshots: list[AssetIntelligenceSnapshot]
    errors: list[AssetAnalysisError] = Field(default_factory=list)
    provider_calls: int = 0
    calculated_at: datetime


class AssetIntelligenceHistoryResponse(BaseModel):
    symbol: str
    snapshots: list[AssetIntelligenceSnapshot] = Field(default_factory=list)
    message: str
