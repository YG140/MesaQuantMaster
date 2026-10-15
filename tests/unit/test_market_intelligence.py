from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.engines.indicator_catalog import (
    canonical_pillars_for_class,
    coverage_breakdown_for_asset,
    evaluate_indicator_pillar,
    indicator_temporal_validity_days,
    indicators_for_class,
    pillar_group_coverage,
    provider_coverage_for_indicators,
    scoring_coverage_for_indicators,
)
from app.engines.market_intelligence_engine import (
    AssetAnalysisEngine,
    ScoringEngine,
    ValuationEngine,
    RecommendationEngine,
    confidence_for_asset,
    warning_reasons,
)
from app.models.asset import Asset
from app.models.indicator_snapshot import IndicatorSnapshot
from app.models.portfolio_policy import PortfolioPolicy, PortfolioPolicyAllocation
from app.repositories.asset_repository import AssetRepository
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.operation_repository import OperationRepository
from app.repositories.indicator_snapshot_repository import (
    IndicatorSnapshotRepository,
)
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.schemas.market import QuoteResponse, QuotesResponse
from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketRateLimitError,
)
from app.schemas.market_intelligence import (
    AnalyzeAssetsRequest,
    AssetIntelligenceSnapshot,
    ConfidenceLevel,
    CoverageBreakdown,
    DataQualityReport,
    IndicatorImportance,
    IndicatorPillar,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
    ProviderFailureReason,
    ProviderResolutionAttempt,
    RecommendationAction,
    ResolutionOutcome,
    ScoreBreakdown,
    ValuationAssessment,
    ValuationStatus,
)
from app.services.indicator_normalization_service import (
    IndicatorNormalizationService,
    classify_provider_failure_reason,
)
from app.services.indicator_resolver_service import build_resolution_summary
from app.services.indicator_validation_service import IndicatorValidationService
from app.services.market_intelligence_service import (
    MarketIntelligenceService,
    infer_class_from_symbol,
    strategy_fit,
)
from app.services.portfolio_service import PortfolioService
from app.services.symbol_identity import B3_MARKET


def quote(symbol: str = "PETR4", *, change_percent: Decimal = Decimal("1.25")):
    return QuoteResponse(
        ticker=symbol,
        requested_symbol=symbol,
        current_price=Decimal("39.89"),
        price=Decimal("39.89"),
        previous_close=Decimal("39.40"),
        change_percent=change_percent,
        high=Decimal("40.10"),
        day_high=Decimal("40.10"),
        low=Decimal("39.10"),
        day_low=Decimal("39.10"),
        volume=1000000,
        market_cap=Decimal("500000000000"),
        currency="BRL",
        market_time=datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc),
        source="BRAPI",
        name="Petrobras PN",
        asset_type="Ação",
        provider="BRAPI",
    )


class FakeMarketService:
    def __init__(self, quotes):
        self.quotes = {item.ticker.upper(): item for item in quotes}
        self.calls = 0

    def get_quotes(self, symbols):
        self.calls += 1
        found = [self.quotes[symbol] for symbol in symbols if symbol in self.quotes]
        unavailable = [symbol for symbol in symbols if symbol not in self.quotes]
        return QuotesResponse(quotes=found, unavailable_symbols=unavailable)


class FakePolicy:
    def __init__(self, allocations):
        self.allocations = allocations


class FakeAllocation:
    def __init__(
        self,
        *,
        asset_class,
        minimum_percentage=Decimal("10"),
        maximum_percentage=Decimal("30"),
        enabled=True,
    ):
        self.asset_class = asset_class
        self.minimum_percentage = minimum_percentage
        self.maximum_percentage = maximum_percentage
        self.enabled = enabled


def test_normalizer_marks_missing_fundamentals_without_zero():
    normalizer = IndicatorNormalizationService()

    asset_class, indicators = normalizer.normalize_quote(
        quote(),
        requested_symbol="PETR4",
        asset_type="Ação",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    by_key = {item.key: item for item in indicators}
    assert asset_class == InvestmentClass.STOCK
    assert by_key["current_price"].value == Decimal("39.89")
    assert by_key["price_earnings"].status == IndicatorStatus.UNAVAILABLE
    assert by_key["price_earnings"].value is None
    assert "nao entrega" in (by_key["price_earnings"].unavailable_reason or "")


def test_normalizer_rejects_out_of_range_values():
    normalizer = IndicatorNormalizationService()

    _, indicators = normalizer.normalize_quote(
        quote(change_percent=Decimal("2000")),
        requested_symbol="PETR4",
        asset_type="Ação",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    change = next(item for item in indicators if item.key == "daily_change")
    assert change.status == IndicatorStatus.INVALID
    assert change.value == Decimal("2000")


def test_no_score_when_coverage_is_insufficient():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    snapshot = AssetIntelligenceSnapshot(
        symbol="TESOURO-SELIC",
        asset_class=InvestmentClass.TREASURY,
        indicators=[],
        recommendation=RecommendationAction.INSUFFICIENT_DATA,
        valuation_status=ValuationStatus.INSUFFICIENT_DATA,
        valuation=ValuationAssessment(
            status=ValuationStatus.INSUFFICIENT_DATA,
            confidence=ConfidenceLevel.INSUFFICIENT,
        ),
        confidence=ConfidenceLevel.INSUFFICIENT,
        coverage_percentage=Decimal("0"),
        available_indicators_count=0,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=now,
    )

    result = AssetAnalysisEngine.build_snapshot(snapshot)

    assert result.overall_score is None
    assert result.recommendation == RecommendationAction.INSUFFICIENT_DATA


def test_missing_fundamental_categories_do_not_score_as_zero():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    _, indicators = IndicatorNormalizationService().normalize_quote(
        quote(),
        requested_symbol="PETR4",
        asset_type="Ação",
        collected_at=now,
    )
    base = AssetIntelligenceSnapshot(
        symbol="PETR4",
        asset_class=InvestmentClass.STOCK,
        current_price=Decimal("39.89"),
        currency="BRL",
        market_updated_at=now,
        indicators=indicators,
        recommendation=RecommendationAction.INSUFFICIENT_DATA,
        valuation_status=ValuationStatus.INSUFFICIENT_DATA,
        valuation=ValuationAssessment(
            status=ValuationStatus.INSUFFICIENT_DATA,
            confidence=ConfidenceLevel.INSUFFICIENT,
        ),
        confidence=ConfidenceLevel.INSUFFICIENT,
        coverage_percentage=Decimal("0"),
        available_indicators_count=0,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=now,
    )

    result = AssetAnalysisEngine.build_snapshot(base)

    assert result.valuation_score is None
    assert result.income_score is None
    assert result.growth_score is None
    assert result.debt_score is None
    assert result.quality_score is None
    assert result.liquidity_score is not None
    # Cotação + volume não demonstram rentabilidade, solvência nem
    # valuation. Disponibilidade de indicadores não é nota de qualidade.
    assert result.overall_score is None
    assert result.valuation_status == ValuationStatus.INSUFFICIENT_DATA
    # required (valuation/profitability/leverage) continua incompleto com só
    # a quote mínima, então confidence continua INSUFFICIENT — overall_score
    # e confidence são sinais independentes (P4).
    assert result.confidence == ConfidenceLevel.INSUFFICIENT


def test_batch_analysis_uses_single_market_call_and_keeps_partial_success(
    db_session,
    active_user,
):
    market = FakeMarketService([quote("PETR4")])
    service = MarketIntelligenceService(
        market_service=market,
        asset_repository=AssetRepository(db_session),
        portfolio_service=PortfolioService(
            operation_repository=OperationRepository(db_session),
            asset_repository=AssetRepository(db_session),
            brokerage_repository=BrokerageRepository(db_session),
            market_service=market,
        ),
        policy_repository=PortfolioPolicyRepository(db_session),
    )

    result = service.analyze_assets(
        data=AnalyzeAssetsRequest(symbols=["PETR4", "MISSING"]),
        user_id=active_user.id,
    )

    assert market.calls == 1
    assert result.provider_calls == 1
    assert [item.symbol for item in result.snapshots] == ["PETR4", "MISSING"]
    assert result.errors[0].symbol == "MISSING"
    assert result.snapshots[1].current_price is None


def test_required_flag_remains_compatible_with_explicit_importance():
    entry = next(
        item
        for item in __import__("app.engines.indicator_catalog", fromlist=["ALL_INDICATORS"]).ALL_INDICATORS
        if item.key == "current_price"
    )
    assert entry.required is True
    assert entry.importance == IndicatorImportance.REQUIRED


def test_requirement_mode_enforces_literal_values():
    valid_any = __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
        key="valuation",
        requirement_mode="ANY_OF",
        indicator_keys=["price_book", "price_earnings"],
    )
    valid_all = __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
        key="price",
        requirement_mode="ALL_OF",
        indicator_keys=["current_price"],
    )
    assert valid_any.requirement_mode == "ANY_OF"
    assert valid_all.requirement_mode == "ALL_OF"
    try:
        __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
            key="bad",
            requirement_mode="OR",
            indicator_keys=["current_price"],
        )
        raise AssertionError("expected validation failure")
    except Exception:
        pass


def test_all_of_requires_every_applicable_member_to_be_available():
    pillar = __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
        key="price",
        requirement_mode="ALL_OF",
        indicator_keys=["current_price", "previous_close"],
    )

    available_a = NormalizedIndicator(
        key="current_price",
        label="Preço atual",
        unit="currency",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("39.89"),
    )
    available_b = NormalizedIndicator(
        key="previous_close",
        label="Fechamento anterior",
        unit="currency",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("39.40"),
    )
    missing_b = [available_a]
    unavailable_b = [available_a, NormalizedIndicator(
        key="previous_close",
        label="Fechamento anterior",
        unit="currency",
        status=IndicatorStatus.UNAVAILABLE,
        source="snapshot",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.LOW,
    )]
    stale_b = [available_a, NormalizedIndicator(
        key="previous_close",
        label="Fechamento anterior",
        unit="currency",
        status=IndicatorStatus.STALE,
        source="snapshot",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.LOW,
    )]
    invalid_b = [available_a, NormalizedIndicator(
        key="previous_close",
        label="Fechamento anterior",
        unit="currency",
        status=IndicatorStatus.INVALID,
        source="snapshot",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.LOW,
    )]
    not_applicable_b = [available_a, NormalizedIndicator(
        key="previous_close",
        label="Fechamento anterior",
        unit="currency",
        status=IndicatorStatus.NOT_APPLICABLE,
        source="snapshot",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.LOW,
    )]
    all_not_applicable = [
        NormalizedIndicator(
            key="current_price",
            label="Preço atual",
            unit="currency",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
        NormalizedIndicator(
            key="previous_close",
            label="Fechamento anterior",
            unit="currency",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]

    assert evaluate_indicator_pillar(pillar, [available_a, available_b])["satisfied"] is True
    assert evaluate_indicator_pillar(pillar, missing_b)["satisfied"] is False
    assert evaluate_indicator_pillar(pillar, unavailable_b)["satisfied"] is False
    assert evaluate_indicator_pillar(pillar, stale_b)["satisfied"] is False
    assert evaluate_indicator_pillar(pillar, invalid_b)["satisfied"] is False
    assert evaluate_indicator_pillar(pillar, not_applicable_b)["satisfied"] is True
    assert evaluate_indicator_pillar(pillar, all_not_applicable)["satisfied"] is False


def test_any_of_pillar_is_satisfied_with_one_available_indicator():
    pillars = canonical_pillars_for_class(InvestmentClass.STOCK)
    valuation = next(item for item in pillars if item.key == "valuation")
    indicators = [
        NormalizedIndicator(
            key="price_book",
            label="P/VP",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
        ),
        NormalizedIndicator(
            key="price_earnings",
            label="P/L",
            unit="ratio",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]

    result = evaluate_indicator_pillar(valuation, indicators)
    assert result["satisfied"] is True
    assert result["coverage"] == Decimal("100")
    assert result["requirement_mode"] == "ANY_OF"


def test_sector_specific_rule_marks_banks_as_not_applicable():
    service = IndicatorValidationService()
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="ev_ebitda",
            label="EV/EBITDA",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("12.5"),
        )
    ]

    validated, _ = service.validate(indicators, sector="banco", collected_at=now)
    assert validated[0].status == IndicatorStatus.NOT_APPLICABLE


def test_quarterly_indicator_remains_valid_within_policy_window():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicator = NormalizedIndicator(
        key="price_earnings",
        label="P/L",
        unit="ratio",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        reference_date=now - timedelta(days=30),
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("14.0"),
    )

    assert indicator_temporal_validity_days("price_earnings") == 90
    assert IndicatorValidationService().validate([indicator], collected_at=now)[0][0].status == IndicatorStatus.AVAILABLE


def test_not_applicable_is_excluded_from_denominator_for_coverage():
    pillars = canonical_pillars_for_class(InvestmentClass.STOCK)
    valuation = next(item for item in pillars if item.key == "valuation")
    indicators = [
        NormalizedIndicator(
            key="price_book",
            label="P/VP",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
        ),
        NormalizedIndicator(
            key="price_earnings",
            label="P/L",
            unit="ratio",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]

    result = evaluate_indicator_pillar(valuation, indicators)
    assert result["effective_indicators"] == ["price_book"]
    assert result["satisfied"] is True


def test_negative_earnings_make_pe_not_applicable():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="price_earnings",
            label="P/L",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("15.0"),
        ),
        NormalizedIndicator(
            key="net_margin",
            label="Margem líquida",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("-2.5"),
        ),
    ]

    validated, _ = IndicatorValidationService().validate(indicators, collected_at=now)
    assert validated[0].status == IndicatorStatus.NOT_APPLICABLE
    assert validated[1].status == IndicatorStatus.AVAILABLE


def test_bank_inapplicable_metrics_are_excluded():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="ev_ebitda",
            label="EV/EBITDA",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("12.5"),
        ),
        NormalizedIndicator(
            key="net_debt_ebitda",
            label="Dívida líquida/EBITDA",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("1.5"),
        ),
        NormalizedIndicator(
            key="roic",
            label="ROIC",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("10.0"),
        ),
        NormalizedIndicator(
            key="ebitda_margin",
            label="Margem EBITDA",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("18.0"),
        ),
    ]

    validated, _ = IndicatorValidationService().validate(indicators, sector="banco", collected_at=now)
    assert {item.key: item.status for item in validated} == {
        "ev_ebitda": IndicatorStatus.NOT_APPLICABLE,
        "net_debt_ebitda": IndicatorStatus.NOT_APPLICABLE,
        "roic": IndicatorStatus.NOT_APPLICABLE,
        "ebitda_margin": IndicatorStatus.NOT_APPLICABLE,
    }


def test_insurer_inapplicable_metrics_are_excluded():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="ev_ebitda",
            label="EV/EBITDA",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("12.5"),
        ),
        NormalizedIndicator(
            key="net_debt_ebitda",
            label="Dívida líquida/EBITDA",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("1.5"),
        ),
        NormalizedIndicator(
            key="roic",
            label="ROIC",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("10.0"),
        ),
    ]

    validated, _ = IndicatorValidationService().validate(indicators, sector="seguradora", collected_at=now)
    assert all(item.status == IndicatorStatus.NOT_APPLICABLE for item in validated)


def test_fii_papel_physical_vacancy_is_not_applicable():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="physical_vacancy",
            label="Vacância física",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("10.0"),
        )
    ]
    validated, _ = IndicatorValidationService().validate(indicators, sector="papel", collected_at=now)
    assert validated[0].status == IndicatorStatus.NOT_APPLICABLE


def test_fii_tijolo_physical_vacancy_remains_applicable():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="physical_vacancy",
            label="Vacância física",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("10.0"),
        )
    ]
    validated, _ = IndicatorValidationService().validate(indicators, sector="tijolo", collected_at=now)
    assert validated[0].status == IndicatorStatus.AVAILABLE


def test_fii_tijolo_receivable_metric_is_not_applicable():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="receivable_quality",
            label="Qualidade dos recebíveis",
            unit="text",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value="alto",
        )
    ]
    validated, _ = IndicatorValidationService().validate(indicators, sector="tijolo", collected_at=now)
    assert validated[0].status == IndicatorStatus.NOT_APPLICABLE


def test_quarterly_fundamentals_without_valid_until_remain_available_after_90_days():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicator = NormalizedIndicator(
        key="price_earnings",
        label="P/L",
        unit="ratio",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        reference_date=now - timedelta(days=120),
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("14.0"),
    )
    validated, _ = IndicatorValidationService().validate([indicator], collected_at=now)
    assert validated[0].status == IndicatorStatus.AVAILABLE


def test_valid_until_expired_marks_indicator_stale():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicator = NormalizedIndicator(
        key="price_earnings",
        label="P/L",
        unit="ratio",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        reference_date=now - timedelta(days=120),
        valid_until=now - timedelta(days=1),
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("14.0"),
    )
    validated, _ = IndicatorValidationService().validate([indicator], collected_at=now)
    assert validated[0].status == IndicatorStatus.STALE


def test_treasury_title_does_not_go_stale_after_two_days():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicator = NormalizedIndicator(
        key="treasury_title",
        label="Título",
        unit="text",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        reference_date=now - timedelta(days=10),
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value="Tesouro Selic 2029",
    )
    validated, _ = IndicatorValidationService().validate([indicator], collected_at=now)
    assert validated[0].status == IndicatorStatus.AVAILABLE


def test_stock_required_pillars_can_be_satisfied_with_optional_indicator_missing():
    pillars = canonical_pillars_for_class(InvestmentClass.STOCK)
    price_pillar = next(item for item in pillars if item.key == "price")
    liquidity_pillar = next(item for item in pillars if item.key == "liquidity")
    valuation_pillar = next(item for item in pillars if item.key == "valuation")
    indicators = [
        NormalizedIndicator(
            key="current_price",
            label="Preço atual",
            unit="currency",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("39.89"),
        ),
        NormalizedIndicator(
            key="volume",
            label="Volume",
            unit="quantity",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("1000000"),
        ),
        NormalizedIndicator(
            key="price_book",
            label="P/VP",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("1.25"),
        ),
    ]

    assert "roe" not in {item.key for item in indicators}
    assert evaluate_indicator_pillar(price_pillar, indicators)["satisfied"] is True
    assert evaluate_indicator_pillar(liquidity_pillar, indicators)["satisfied"] is True
    assert evaluate_indicator_pillar(valuation_pillar, indicators)["satisfied"] is True
    assert all(item.value is not None for item in indicators)


def test_treasury_required_pillars_require_execution_price():
    pillars = canonical_pillars_for_class(InvestmentClass.TREASURY)
    execution_pillar = next(item for item in pillars if item.key == "execution_price")
    indicators = [
        NormalizedIndicator(
            key="treasury_title",
            label="Título",
            unit="text",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="Tesouro Selic 2029",
        ),
        NormalizedIndicator(
            key="indexer",
            label="Indexador",
            unit="text",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="SELIC",
        ),
        NormalizedIndicator(
            key="treasury_rate",
            label="Taxa",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("13.65"),
        ),
        NormalizedIndicator(
            key="maturity_date",
            label="Vencimento",
            unit="date",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="2029-01-01",
        ),
    ]

    assert evaluate_indicator_pillar(execution_pillar, indicators)["satisfied"] is False
    indicators.append(
        NormalizedIndicator(
            key="current_price",
            label="Preço",
            unit="currency",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("1000.00"),
        )
    )
    assert evaluate_indicator_pillar(execution_pillar, indicators)["satisfied"] is True


def test_cdb_fgc_is_applicable_when_product_is_eligible():
    pillar = __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
        key="fgc_eligibility",
        requirement_mode="ALL_OF",
        indicator_keys=["fgc_eligible"],
    )
    indicators = [
        NormalizedIndicator(
            key="fgc_eligible",
            label="Elegível ao FGC",
            unit="text",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="sim",
        )
    ]
    assert evaluate_indicator_pillar(pillar, indicators)["satisfied"] is True


def test_debenture_does_not_require_fgc_for_required_pillars():
    pillars = canonical_pillars_for_class(InvestmentClass.DEBENTURE)
    declared_keys = {key for pillar in pillars for key in pillar.indicator_keys}

    assert "fgc_eligible" not in declared_keys
    assert "fgc_coverage" not in declared_keys
    assert "fgc_covered_amount" not in declared_keys

    issuer_pillar = next(item for item in pillars if item.key == "issuer")
    indicators = [
        NormalizedIndicator(
            key="issuer",
            label="Emissor",
            unit="text",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="Banco do Brasil",
        ),
        NormalizedIndicator(
            key="indexer",
            label="Indexador",
            unit="text",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="CDI",
        ),
        NormalizedIndicator(
            key="maturity_date",
            label="Vencimento",
            unit="date",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="2035-01-01",
        ),
    ]

    assert evaluate_indicator_pillar(issuer_pillar, indicators)["satisfied"] is True
    assert all("fgc_eligible" not in pillar.indicator_keys for pillar in pillars)


def test_cdb_fgc_policy_is_preserved():
    cdb_indicators = {item.key for item in indicators_for_class(InvestmentClass.CDB)}
    pillars = canonical_pillars_for_class(InvestmentClass.CDB)

    assert "fgc_eligible" in cdb_indicators
    assert "fgc_coverage" in cdb_indicators
    assert all("fgc_eligible" not in pillar.indicator_keys for pillar in pillars)
    assert all("fgc_coverage" not in pillar.indicator_keys for pillar in pillars)


def test_bdr_underlying_symbol_alone_does_not_satisfy_required_pillars():
    pillars = canonical_pillars_for_class(InvestmentClass.BDR)
    price_pillar = next(item for item in pillars if item.key == "price")
    liquidity_pillar = next(item for item in pillars if item.key == "liquidity")
    underlying_pillar = next(item for item in pillars if item.key == "underlying")
    base_indicators = [
        NormalizedIndicator(
            key="underlying_symbol",
            label="Símbolo do ativo subjacente",
            unit="text",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value="AAPL",
        )
    ]

    assert evaluate_indicator_pillar(price_pillar, base_indicators)["satisfied"] is False
    assert evaluate_indicator_pillar(liquidity_pillar, base_indicators)["satisfied"] is False
    assert evaluate_indicator_pillar(underlying_pillar, base_indicators)["satisfied"] is True

    enriched = base_indicators + [
        NormalizedIndicator(
            key="current_price",
            label="Preço atual",
            unit="currency",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("160.00"),
        ),
        NormalizedIndicator(
            key="volume",
            label="Volume",
            unit="quantity",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("2000000"),
        ),
    ]
    assert evaluate_indicator_pillar(price_pillar, enriched)["satisfied"] is True
    assert evaluate_indicator_pillar(liquidity_pillar, enriched)["satisfied"] is True
    assert evaluate_indicator_pillar(underlying_pillar, enriched)["satisfied"] is True


def test_crypto_does_not_require_onchain_indicators():
    pillars = canonical_pillars_for_class(InvestmentClass.CRYPTO)
    price_pillar = next(item for item in pillars if item.key == "price")
    liquidity_pillar = next(item for item in pillars if item.key == "liquidity")
    risk_pillar = next(item for item in pillars if item.key == "risk_history")
    indicators = [
        NormalizedIndicator(
            key="price",
            label="Preço",
            unit="currency",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("50000.00"),
        ),
        NormalizedIndicator(
            key="volume",
            label="Volume",
            unit="quantity",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("50000000"),
        ),
        NormalizedIndicator(
            key="historical_return",
            label="Retorno histórico",
            unit="percent",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("25.0"),
        ),
    ]

    assert evaluate_indicator_pillar(price_pillar, indicators)["satisfied"] is True
    assert evaluate_indicator_pillar(liquidity_pillar, indicators)["satisfied"] is True
    assert evaluate_indicator_pillar(risk_pillar, indicators)["satisfied"] is True
    assert all(item.key not in {"network_activity", "active_addresses"} for item in indicators)

    missing = [
        NormalizedIndicator(
            key="price",
            label="Preço",
            unit="currency",
            status=IndicatorStatus.UNAVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
        NormalizedIndicator(
            key="volume",
            label="Volume",
            unit="quantity",
            status=IndicatorStatus.UNAVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]
    assert evaluate_indicator_pillar(price_pillar, missing)["satisfied"] is False
    assert evaluate_indicator_pillar(liquidity_pillar, missing)["satisfied"] is False


def test_annual_fundamental_remains_available_within_annual_policy():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicator = NormalizedIndicator(
        key="revenue_cagr_3y",
        label="CAGR de receitas 3Y",
        unit="percent",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        reference_date=now - timedelta(days=180),
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("12.0"),
    )
    assert indicator_temporal_validity_days("revenue_cagr_3y") == 365
    validated, _ = IndicatorValidationService().validate([indicator], collected_at=now)
    assert validated[0].status == IndicatorStatus.AVAILABLE


def test_any_of_pillar_is_not_satisfied_when_no_applicable_indicator_is_available():
    pillar = __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
        key="valuation",
        requirement_mode="ANY_OF",
        indicator_keys=["price_earnings", "price_book"],
    )
    unavailable = [
        NormalizedIndicator(
            key="price_earnings",
            label="P/L",
            unit="ratio",
            status=IndicatorStatus.UNAVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
        NormalizedIndicator(
            key="price_book",
            label="P/VP",
            unit="ratio",
            status=IndicatorStatus.UNAVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]
    not_applicable = [
        NormalizedIndicator(
            key="price_earnings",
            label="P/L",
            unit="ratio",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
        NormalizedIndicator(
            key="price_book",
            label="P/VP",
            unit="ratio",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]
    assert evaluate_indicator_pillar(pillar, unavailable)["satisfied"] is False
    assert evaluate_indicator_pillar(pillar, not_applicable)["satisfied"] is False


def test_all_of_pillar_is_not_satisfied_when_one_required_indicator_is_missing():
    pillar = __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
        key="price",
        requirement_mode="ALL_OF",
        indicator_keys=["current_price", "previous_close"],
    )
    partial = [
        NormalizedIndicator(
            key="current_price",
            label="Preço atual",
            unit="currency",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("39.89"),
        )
    ]
    complete = partial + [
        NormalizedIndicator(
            key="previous_close",
            label="Fechamento anterior",
            unit="currency",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("39.40"),
        )
    ]

    assert evaluate_indicator_pillar(pillar, partial)["satisfied"] is False
    assert evaluate_indicator_pillar(pillar, complete)["satisfied"] is True


def test_all_of_pillar_ignores_explicit_not_applicable_member():
    pillar = __import__("app.schemas.market_intelligence", fromlist=["IndicatorPillar"]).IndicatorPillar(
        key="valuation",
        requirement_mode="ALL_OF",
        indicator_keys=["price_book", "price_earnings"],
    )
    available_then_not_applicable = [
        NormalizedIndicator(
            key="price_book",
            label="P/VP",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("1.25"),
        ),
        NormalizedIndicator(
            key="price_earnings",
            label="P/L",
            unit="ratio",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]
    all_not_applicable = [
        NormalizedIndicator(
            key="price_book",
            label="P/VP",
            unit="ratio",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
        NormalizedIndicator(
            key="price_earnings",
            label="P/L",
            unit="ratio",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]

    assert evaluate_indicator_pillar(pillar, available_then_not_applicable)["satisfied"] is True
    assert evaluate_indicator_pillar(pillar, all_not_applicable)["satisfied"] is False


def test_analysis_with_provider_candidate_does_not_persist_or_flush(
    db_session,
    active_user,
    monkeypatch,
):
    market = FakeMarketService([quote("PETR4")])
    commit_calls = 0
    flush_calls = 0
    original_commit = db_session.commit
    original_flush = db_session.flush

    def count_commit(*args, **kwargs):
        nonlocal commit_calls
        commit_calls += 1
        return original_commit(*args, **kwargs)

    def count_flush(*args, **kwargs):
        nonlocal flush_calls
        flush_calls += 1
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "commit", count_commit)
    monkeypatch.setattr(db_session, "flush", count_flush)
    service = MarketIntelligenceService(
        market_service=market,
        asset_repository=AssetRepository(db_session),
        portfolio_service=PortfolioService(
            operation_repository=OperationRepository(db_session),
            asset_repository=AssetRepository(db_session),
            brokerage_repository=BrokerageRepository(db_session),
            market_service=market,
        ),
        policy_repository=PortfolioPolicyRepository(db_session),
        snapshot_repository=IndicatorSnapshotRepository(db_session),
    )

    result = service.analyze_asset("PETR4", active_user.id)

    assert result.current_price == Decimal("39.89")
    assert db_session.query(IndicatorSnapshot).count() == 0
    assert commit_calls == 0
    assert flush_calls == 0


def test_analysis_reads_valid_snapshot_without_writing(
    db_session, active_user, monkeypatch
):
    collected_at = datetime(2026, 7, 16, tzinfo=timezone.utc)
    db_session.add(
        IndicatorSnapshot(
            symbol="PETR4",
            asset_class="stock",
            indicator_key="price_earnings",
            value=Decimal("8.75"),
            unit="ratio",
            period="current",
            source="TEST_PROVIDER",
            source_type="provider",
            reference_date=collected_at,
            collected_at=collected_at,
            valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
            provenance_json='{"fixture": true}',
        )
    )
    db_session.commit()
    commit_calls = 0
    flush_calls = 0

    def count_commit(*args, **kwargs):
        nonlocal commit_calls
        commit_calls += 1

    def count_flush(*args, **kwargs):
        nonlocal flush_calls
        flush_calls += 1

    monkeypatch.setattr(db_session, "commit", count_commit)
    monkeypatch.setattr(db_session, "flush", count_flush)
    market = FakeMarketService([quote("PETR4")])
    service = MarketIntelligenceService(
        market_service=market,
        asset_repository=AssetRepository(db_session),
        portfolio_service=PortfolioService(
            operation_repository=OperationRepository(db_session),
            asset_repository=AssetRepository(db_session),
            brokerage_repository=BrokerageRepository(db_session),
            market_service=market,
        ),
        policy_repository=PortfolioPolicyRepository(db_session),
        snapshot_repository=IndicatorSnapshotRepository(db_session),
    )

    result = service.analyze_asset("PETR4", active_user.id)
    price_earnings = next(
        item for item in result.indicators if item.key == "price_earnings"
    )

    assert price_earnings.value == Decimal("8.75")
    assert price_earnings.source == "TEST_PROVIDER"
    assert db_session.query(IndicatorSnapshot).count() == 1
    assert commit_calls == 0
    assert flush_calls == 0


def test_provider_failure_during_read_leaves_no_snapshot(db_session, active_user):
    class FailingMarketService(FakeMarketService):
        def get_quotes(self, symbols):
            raise RuntimeError("controlled provider failure")

    market = FailingMarketService([])
    service = MarketIntelligenceService(
        market_service=market,
        asset_repository=AssetRepository(db_session),
        portfolio_service=PortfolioService(
            operation_repository=OperationRepository(db_session),
            asset_repository=AssetRepository(db_session),
            brokerage_repository=BrokerageRepository(db_session),
            market_service=market,
        ),
        policy_repository=PortfolioPolicyRepository(db_session),
        snapshot_repository=IndicatorSnapshotRepository(db_session),
    )

    result = service.analyze_asset("PETR4", active_user.id)

    assert result.current_price is None
    assert db_session.query(IndicatorSnapshot).count() == 0


def test_recommendation_respects_policy_when_class_is_above_limit(
    db_session,
    active_user,
):
    asset = Asset(
        ticker="PETR4",
        name="Petrobras PN",
        asset_type="Ação",
        currency="BRL",
    )
    db_session.add(asset)
    policy = PortfolioPolicy(
        user_id=active_user.id,
        name="Minha estratégia",
        objective="crescimento patrimonial",
        risk_profile="moderado",
        investment_horizon="longo prazo",
        monthly_contribution=Decimal("900"),
        liquidity_need="média",
        income_need=False,
        emergency_reserve_months=6,
        maximum_weight_per_asset=Decimal("20"),
        maximum_weight_per_sector=Decimal("30"),
        maximum_weight_per_issuer=Decimal("30"),
        rebalance_tolerance=Decimal("5"),
    )
    db_session.add(policy)
    db_session.flush()
    db_session.add(
        PortfolioPolicyAllocation(
            policy_id=policy.id,
            asset_class="Ações",
            target_percentage=Decimal("20"),
            minimum_percentage=Decimal("10"),
            maximum_percentage=Decimal("30"),
            enabled=True,
        )
    )
    db_session.commit()
    market = FakeMarketService([quote("PETR4")])
    service = MarketIntelligenceService(
        market_service=market,
        asset_repository=AssetRepository(db_session),
        portfolio_service=PortfolioService(
            operation_repository=OperationRepository(db_session),
            asset_repository=AssetRepository(db_session),
            brokerage_repository=BrokerageRepository(db_session),
            market_service=market,
        ),
        policy_repository=PortfolioPolicyRepository(db_session),
    )

    snapshot = service._snapshot_for_symbol(
        symbol="PETR4",
        quote=quote("PETR4"),
        local_asset=asset,
        position=type("Position", (), {"allocation": Decimal("60")})(),
        policy=policy,
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    assert snapshot.strategy_fit_score == Decimal("25")
    assert snapshot.recommendation == RecommendationAction.INSUFFICIENT_DATA
    assert snapshot.data_quality is not None
    assert snapshot.data_quality.recommendation_blocked is True


def test_strategy_fit_keeps_policy_signal_separate_from_asset_quality():
    policy = FakePolicy(
        [
            FakeAllocation(asset_class="Ações"),
            FakeAllocation(asset_class="ETFs", enabled=False),
        ]
    )

    assert strategy_fit(
        asset_class=InvestmentClass.STOCK,
        current_weight=Decimal("20"),
        policy=policy,
    ) == Decimal("90")
    assert strategy_fit(
        asset_class=InvestmentClass.STOCK,
        current_weight=Decimal("29"),
        policy=policy,
    ) == Decimal("90")
    assert strategy_fit(
        asset_class=InvestmentClass.STOCK,
        current_weight=Decimal("60"),
        policy=policy,
    ) == Decimal("25")
    assert strategy_fit(
        asset_class=InvestmentClass.ETF,
        current_weight=Decimal("0"),
        policy=policy,
    ) == Decimal("20")
    assert (
        strategy_fit(
            asset_class=InvestmentClass.STOCK,
            current_weight=Decimal("20"),
            policy=None,
        )
        is None
    )


def test_financial_sector_marks_incompatible_indicators_not_applicable():
    normalizer = IndicatorNormalizationService()
    validator = IndicatorValidationService()
    _, indicators = normalizer.normalize_quote(
        quote(),
        requested_symbol="PETR4",
        asset_type="Ação",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    validated, report = validator.validate(
        indicators,
        sector="Bancos",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    ev_ebitda = next(item for item in validated if item.key == "ev_ebitda")
    assert ev_ebitda.status == IndicatorStatus.NOT_APPLICABLE
    assert "EV/EBITDA" in report.non_applicable_indicators


def test_extreme_dividend_yield_blocks_recommendation_quality():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    validator = IndicatorValidationService()
    indicator = next(
        item
        for item in IndicatorNormalizationService().normalize_quote(
            quote(), requested_symbol="PETR4", asset_type="Ação", collected_at=now
        )[1]
        if item.key == "dividend_yield"
    ).model_copy(
        update={
            "value": Decimal("35"),
            "display_value": "35.00%",
            "status": IndicatorStatus.AVAILABLE,
        }
    )

    validated, report = validator.validate([indicator], collected_at=now)

    assert validated[0].status == IndicatorStatus.POTENTIALLY_INCONSISTENT
    assert report.anomaly_flags
    assert report.recommendation_blocked is True


def test_etf_structural_indicators_do_not_invent_values():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    asset_class, indicators = IndicatorNormalizationService().normalize_quote(
        quote("BOVA11"),
        requested_symbol="BOVA11",
        asset_type="ETF",
        collected_at=now,
    )

    by_key = {item.key: item for item in indicators}

    assert asset_class == InvestmentClass.ETF
    assert by_key["tracking_error"].status == IndicatorStatus.UNAVAILABLE
    assert by_key["tracking_error"].value is None
    assert by_key["management_fee"].status == IndicatorStatus.UNAVAILABLE
    assert by_key["management_fee"].value is None


def test_known_b3_etf_symbol_overrides_generic_provider_type():
    assert infer_class_from_symbol("BOVA11", "FII") == InvestmentClass.ETF


def test_b3_fii_symbol_overrides_generic_fund_provider_type():
    assert (
        infer_class_from_symbol("HGLG11", "Fundo de investimento")
        == InvestmentClass.FII
    )


def test_fractional_stock_ticker_is_still_classified_as_stock():
    """Requer contexto B3 explícito (ver Prompt 3, seção 5) -- nunca
    assumido implicitamente. `MarketIntelligenceService._market_context()`
    é quem prova esse contexto em produção, derivado do provider
    realmente em uso (ver test_market_service_symbol_identity.py)."""
    assert (
        infer_class_from_symbol("PETR4F", "stock", market=B3_MARKET)
        == InvestmentClass.STOCK
    )
    assert (
        infer_class_from_symbol("PETR4F", None, market=B3_MARKET)
        == InvestmentClass.STOCK
    )


def test_hypothetical_fractional_fii_keeps_fii_class_via_canonical_11_suffix():
    """Prompt 2, seção 23: o sufixo "F" do mercado fracionário nunca pode
    mascarar o "11" que identifica FII/ETF -- a classificação usa a
    identidade econômica (canonical_symbol), não o símbolo de negociação
    bruto. Mesmo sem asset_type resolvido (provider indisponível/perfil
    vazio, exatamente o cenário que a auditoria encontrou para
    fracionários), "MXRF11F" continua FII -- com contexto B3 comprovado."""
    assert (
        infer_class_from_symbol("MXRF11F", None, market=B3_MARKET)
        == InvestmentClass.FII
    )


def test_hypothetical_fractional_etf_keeps_known_etf_override():
    assert (
        infer_class_from_symbol("BOVA11F", "FII", market=B3_MARKET)
        == InvestmentClass.ETF
    )


def test_standard_fii_and_etf_symbols_are_unaffected_by_the_fractional_rule():
    assert infer_class_from_symbol("MXRF11", None) == InvestmentClass.FII
    assert infer_class_from_symbol("BOVA11", "FII") == InvestmentClass.ETF


# --- Sem contexto B3 comprovado, o "F" nunca é removido (Prompt 3, seção
#     10, caso B) ------------------------------------------------------------


def test_fractional_looking_symbol_without_b3_context_never_canonicalizes():
    """Sem `market=B3_MARKET` (default: nenhum contexto), um símbolo com o
    formato estrutural de um fracionário B3 válido nunca é canonicalizado
    -- protege qualquer ticker internacional legitimamente terminado em
    "F" que passe por este classificador fora de um fluxo B3 comprovado.
    """
    assert infer_class_from_symbol("PETR4F", "stock") == InvestmentClass.STOCK
    assert infer_class_from_symbol("MXRF11F", None) != InvestmentClass.FII


def test_fractional_looking_symbol_in_a_different_proven_market_never_canonicalizes():
    assert (
        infer_class_from_symbol("PETR4F", "stock", market="NASDAQ")
        == InvestmentClass.STOCK
    )


def test_quote_volume_and_liquidity_explain_limited_data():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    _, indicators = IndicatorNormalizationService().normalize_quote(
        quote(),
        requested_symbol="PETR4",
        asset_type="Ação",
        collected_at=now,
    )

    by_key = {item.key: item for item in indicators}

    assert by_key["volume"].label == "Volume negociado"
    assert by_key["liquidity"].label == "Liquidez estimada com dados limitados"
    assert by_key["liquidity"].value == Decimal("39890000.00")
    assert by_key["liquidity"].explanation is not None
    assert "não representa média histórica" in by_key["liquidity"].explanation


def test_extreme_rsi_blocks_automatic_recommendation_quality():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicator = next(
        item
        for item in IndicatorNormalizationService().normalize_quote(
            quote("BTC"),
            requested_symbol="BTC",
            asset_type="Criptomoeda",
            collected_at=now,
        )[1]
        if item.key == "rsi"
    ).model_copy(
        update={
            "value": Decimal("91"),
            "display_value": "91.00",
            "status": IndicatorStatus.AVAILABLE,
        }
    )

    validated, report = IndicatorValidationService().validate(
        [indicator], collected_at=now
    )

    assert validated[0].status == IndicatorStatus.POTENTIALLY_INCONSISTENT
    assert report.anomaly_flags
    assert report.recommendation_blocked is True


# =====================================================================
# P1 — cobertura desmembrada, confidence estruturado e diagnóstico de
# falhas de provider. Mapeamento dos 28 cenários canônicos do prompt
# operacional (seção 27): cada teste abaixo está rotulado com o número
# do cenário que cobre.
# =====================================================================


def _etf_indicator(
    key: str,
    label: str,
    unit: str,
    *,
    status: IndicatorStatus = IndicatorStatus.AVAILABLE,
    value=None,
    provider_failure_reason: ProviderFailureReason | None = None,
) -> NormalizedIndicator:
    return NormalizedIndicator(
        key=key,
        label=label,
        unit=unit,
        status=status,
        source="snapshot",
        collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.HIGH if status == IndicatorStatus.AVAILABLE else ConfidenceLevel.LOW,
        value=value,
        provider_failure_reason=provider_failure_reason,
    )


def _perfect_breakdown(scoring_coverage: Decimal) -> CoverageBreakdown:
    return CoverageBreakdown(
        required_coverage=Decimal("100.00"),
        required_satisfied=3,
        required_total=3,
        scoring_coverage=scoring_coverage,
    )


def _two_category_scores(value: Decimal) -> dict[str, ScoreBreakdown]:
    breakdown = ScoreBreakdown(
        value=value,
        available_indicators=2,
        missing_indicators=0,
        stale_indicators=0,
        coverage_percentage=Decimal("100"),
        confidence=ConfidenceLevel.HIGH,
    )
    return {"quality": breakdown, "valuation": breakdown}


# Cenário 1: todos REQUIRED satisfeitos -> required_coverage = 100%.
def test_required_coverage_is_100_when_all_required_pillars_satisfied():
    indicators = [
        _etf_indicator("current_price", "Preço atual", "currency", value=Decimal("100.00")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("500000")),
        _etf_indicator("tracked_index", "Índice", "text", value="IBOV"),
    ]
    breakdown = coverage_breakdown_for_asset(InvestmentClass.ETF, indicators)
    assert breakdown.required_total == 3
    assert breakdown.required_satisfied == 3
    assert breakdown.required_coverage == Decimal("100.00")


# Cenário 2: um REQUIRED aplicável ausente -> required_coverage < 100%.
def test_required_coverage_drops_when_required_pillar_is_missing():
    indicators = [
        _etf_indicator("current_price", "Preço atual", "currency", value=Decimal("100.00")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("500000")),
        # "strategy" pillar (tracked_index/fund_strategy) ausente por completo.
    ]
    breakdown = coverage_breakdown_for_asset(InvestmentClass.ETF, indicators)
    assert breakdown.required_total == 3
    assert breakdown.required_satisfied == 2
    assert breakdown.required_coverage == Decimal("66.67")
    assert breakdown.required_coverage < Decimal("100")


# Cenário 3: RECOMMENDED ausente -> required_coverage permanece 100%.
def test_recommended_gap_does_not_affect_required_coverage():
    indicators = [
        _etf_indicator("current_price", "Preço atual", "currency", value=Decimal("100.00")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("500000")),
        _etf_indicator("tracked_index", "Índice", "text", value="IBOV"),
        # management_fee (RECOMMENDED) ausente.
    ]
    breakdown = coverage_breakdown_for_asset(InvestmentClass.ETF, indicators)
    assert breakdown.required_coverage == Decimal("100.00")
    assert breakdown.recommended_coverage == Decimal("0.00")


# Cenário 4: recommended_coverage considera somente RECOMMENDED (métrica independente).
def test_recommended_coverage_is_independent_metric():
    base = [
        _etf_indicator("current_price", "Preço atual", "currency", value=Decimal("100.00")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("500000")),
        _etf_indicator("tracked_index", "Índice", "text", value="IBOV"),
    ]
    with_fee = base + [_etf_indicator("management_fee", "Taxa de administração", "percent", value=Decimal("0.5"))]

    without = coverage_breakdown_for_asset(InvestmentClass.ETF, base)
    with_ = coverage_breakdown_for_asset(InvestmentClass.ETF, with_fee)

    assert without.recommended_coverage == Decimal("0.00")
    assert with_.recommended_coverage == Decimal("100.00")
    assert without.required_coverage == with_.required_coverage == Decimal("100.00")


# Cenário 5: OPTIONAL ausente não altera required_coverage nem recommended_coverage.
def test_optional_gap_does_not_affect_required_or_recommended_coverage():
    required_pillar = IndicatorPillar(
        key="req", importance=IndicatorImportance.REQUIRED, requirement_mode="ALL_OF", indicator_keys=["a"]
    )
    recommended_pillar = IndicatorPillar(
        key="rec", importance=IndicatorImportance.RECOMMENDED, requirement_mode="ALL_OF", indicator_keys=["b"]
    )
    optional_pillar = IndicatorPillar(
        key="opt", importance=IndicatorImportance.OPTIONAL, requirement_mode="ALL_OF", indicator_keys=["c"]
    )
    indicators = [
        _etf_indicator("a", "A", "text", value="x"),
        _etf_indicator("b", "B", "text", value="y"),
        # "c" (OPTIONAL) ausente.
    ]

    required_coverage, _, _ = pillar_group_coverage([required_pillar], indicators)
    recommended_coverage, _, _ = pillar_group_coverage([recommended_pillar], indicators)
    optional_coverage, _, _ = pillar_group_coverage([optional_pillar], indicators)

    assert required_coverage == Decimal("100.00")
    assert recommended_coverage == Decimal("100.00")
    assert optional_coverage == Decimal("0.00")


# Cenário 6: EXPERIMENTAL ausente não reduz total_coverage normal.
def test_experimental_pillar_excluded_from_total_coverage(monkeypatch):
    required_pillar = IndicatorPillar(
        key="req", importance=IndicatorImportance.REQUIRED, requirement_mode="ALL_OF", indicator_keys=["a"]
    )
    experimental_pillar = IndicatorPillar(
        key="exp", importance=IndicatorImportance.EXPERIMENTAL, requirement_mode="ALL_OF", indicator_keys=["z"]
    )
    monkeypatch.setattr(
        "app.engines.indicator_catalog.canonical_pillars_for_class",
        lambda asset_class: [required_pillar, experimental_pillar],
    )
    indicators = [_etf_indicator("a", "A", "text", value="x")]  # "z" (EXPERIMENTAL) ausente.

    breakdown = coverage_breakdown_for_asset(InvestmentClass.STOCK, indicators)

    assert breakdown.total_applicable == 1
    assert breakdown.total_coverage == Decimal("100.00")


# Cenário 7: NOT_APPLICABLE é removido do denominador (a nível de pilar inteiro).
def test_not_applicable_pillar_excluded_from_coverage_denominator():
    price_pillar = IndicatorPillar(
        key="price", importance=IndicatorImportance.REQUIRED, requirement_mode="ALL_OF", indicator_keys=["current_price"]
    )
    fully_na_pillar = IndicatorPillar(
        key="extra", importance=IndicatorImportance.REQUIRED, requirement_mode="ALL_OF", indicator_keys=["fgc_eligible"]
    )
    indicators = [
        _etf_indicator("current_price", "Preço", "currency", value=Decimal("10.00")),
        NormalizedIndicator(
            key="fgc_eligible",
            label="FGC",
            unit="text",
            status=IndicatorStatus.NOT_APPLICABLE,
            source="snapshot",
            collected_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
            confidence=ConfidenceLevel.LOW,
        ),
    ]

    coverage, satisfied, total = pillar_group_coverage([price_pillar, fully_na_pillar], indicators)

    assert total == 1
    assert satisfied == 1
    assert coverage == Decimal("100.00")


# Cenário 8: ANY_OF com um membro disponível satisfaz o pilar e alimenta required_coverage.
def test_any_of_pillar_satisfied_with_one_member_feeds_required_coverage():
    pillars = canonical_pillars_for_class(InvestmentClass.ETF)
    liquidity_pillar = next(item for item in pillars if item.key == "liquidity")
    indicators = [_etf_indicator("volume", "Volume", "quantity", value=Decimal("1000"))]

    result = evaluate_indicator_pillar(liquidity_pillar, indicators)
    coverage, satisfied, total = pillar_group_coverage([liquidity_pillar], indicators)

    assert result["satisfied"] is True
    assert (satisfied, total) == (1, 1)
    assert coverage == Decimal("100.00")


# Cenário 9: ALL_OF com membro aplicável ausente reduz required_coverage.
def test_all_of_missing_member_reduces_required_coverage():
    indicators = [
        _etf_indicator("treasury_title", "Título", "text", value="Tesouro Selic 2029"),
        _etf_indicator("indexer", "Indexador", "text", value="SELIC"),
        _etf_indicator("treasury_rate", "Taxa", "percent", value=Decimal("13.65")),
        _etf_indicator("maturity_date", "Vencimento", "date", value="2029-01-01"),
        # current_price (execution_price, ALL_OF) ausente.
    ]
    breakdown = coverage_breakdown_for_asset(InvestmentClass.TREASURY, indicators)

    assert breakdown.required_total == 5
    assert breakdown.required_satisfied == 4
    assert breakdown.required_coverage == Decimal("80.00")


# Cenário 10: scoring_coverage considera somente indicadores/categorias reais de scoring.
def test_scoring_coverage_considers_only_real_scoring_categories():
    indicators = [
        _etf_indicator("roe", "ROE", "percent", value=Decimal("15.0")),
        _etf_indicator("price_earnings", "P/L", "ratio", value=Decimal("10.0")),
        _etf_indicator("net_debt_equity", "Dívida/PL", "ratio", status=IndicatorStatus.UNAVAILABLE),
    ]
    coverage, available, total = scoring_coverage_for_indicators(indicators)

    assert total == 3
    assert available == 2
    assert coverage == Decimal("66.67")


# Cenário 11: campo descritivo não aumenta scoring_coverage.
def test_descriptive_field_does_not_increase_scoring_coverage():
    baseline_coverage, baseline_available, baseline_total = scoring_coverage_for_indicators(
        [_etf_indicator("roe", "ROE", "percent", value=Decimal("15.0"))]
    )
    with_descriptive = [
        _etf_indicator("roe", "ROE", "percent", value=Decimal("15.0")),
        _etf_indicator("segment", "Segmento", "text", value="tijolo"),
    ]
    coverage, available, total = scoring_coverage_for_indicators(with_descriptive)

    assert total == baseline_total
    assert available == baseline_available
    assert coverage == baseline_coverage


# Cenário 12: provider_coverage baixo, com essenciais válidos, não bloqueia sozinho.
def test_low_provider_coverage_does_not_force_insufficient_confidence():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("100.00"),
        required_satisfied=3,
        required_total=3,
        scoring_coverage=Decimal("85.00"),
        provider_coverage=Decimal("10.00"),
        provider_resolved=2,
        provider_requested=20,
    )
    confidence = confidence_for_asset(
        coverage_breakdown=breakdown,
        scores=_two_category_scores(Decimal("85")),
        overall_score=Decimal("85"),
        data_quality=DataQualityReport(data_completeness=Decimal("90"), data_freshness=Decimal("90")),
        anomaly_flags=[],
    )
    assert confidence != ConfidenceLevel.INSUFFICIENT
    assert confidence == ConfidenceLevel.HIGH


# Cenário 13: confidence LOW não bloqueia automaticamente (é um valor alcançável e final).
def test_low_confidence_is_reachable_and_does_not_raise_or_block():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("45.00")),
        scores=_two_category_scores(Decimal("45")),
        overall_score=Decimal("45"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.LOW


# Cenário 14: REQUIRED indispensável ausente -> INSUFFICIENT.
def test_missing_required_pillar_forces_insufficient_confidence():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("66.67"), required_satisfied=2, required_total=3, scoring_coverage=Decimal("90.00")
    )
    confidence = confidence_for_asset(
        coverage_breakdown=breakdown,
        scores=_two_category_scores(Decimal("90")),
        overall_score=Decimal("90"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.INSUFFICIENT


# Cenário 15: preço indispensável ausente -> INSUFFICIENT (fim a fim via build_snapshot).
def test_missing_price_forces_insufficient_confidence_end_to_end():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="current_price",
            label="Preço atual",
            unit="currency",
            status=IndicatorStatus.UNAVAILABLE,
            source="snapshot",
            collected_at=now,
            confidence=ConfidenceLevel.INSUFFICIENT,
            unavailable_reason="Provedor não retornou cotação.",
        ),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("1000000")),
        _etf_indicator("roe", "ROE", "percent", value=Decimal("15.0")),
        _etf_indicator("price_book", "P/VP", "ratio", value=Decimal("1.2")),
        _etf_indicator("net_debt_equity", "Dívida/PL", "ratio", value=Decimal("0.5")),
    ]
    base = AssetIntelligenceSnapshot(
        symbol="XYZ4",
        asset_class=InvestmentClass.STOCK,
        indicators=indicators,
        recommendation=RecommendationAction.INSUFFICIENT_DATA,
        valuation_status=ValuationStatus.INSUFFICIENT_DATA,
        valuation=ValuationAssessment(status=ValuationStatus.INSUFFICIENT_DATA, confidence=ConfidenceLevel.INSUFFICIENT),
        confidence=ConfidenceLevel.INSUFFICIENT,
        coverage_percentage=Decimal("0"),
        available_indicators_count=0,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=now,
    )

    result = AssetAnalysisEngine.build_snapshot(base)

    assert result.confidence == ConfidenceLevel.INSUFFICIENT
    assert result.coverage_breakdown.required_satisfied < result.coverage_breakdown.required_total


# Cenário 16: identifier_unresolved crítico -> INSUFFICIENT independente da cobertura.
def test_identifier_unresolved_anomaly_forces_insufficient_confidence():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("95.00")),
        scores=_two_category_scores(Decimal("95")),
        overall_score=Decimal("95"),
        data_quality=None,
        anomaly_flags=["identifier_unresolved"],
    )
    assert confidence == ConfidenceLevel.INSUFFICIENT


# Cenário 17: anomalia crítica (conflito entre fontes) -> INSUFFICIENT.
def test_critical_conflicting_sources_anomaly_forces_insufficient_confidence():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("95.00")),
        scores=_two_category_scores(Decimal("95")),
        overall_score=Decimal("95"),
        data_quality=None,
        anomaly_flags=["conflicting_sources"],
    )
    assert confidence == ConfidenceLevel.INSUFFICIENT


# Cenário 18: rate_limited real é preservado como rate_limited (não rebaixado a genérico).
def test_rate_limited_failure_is_preserved_not_downgraded():
    assert classify_provider_failure_reason(MarketRateLimitError()) == ProviderFailureReason.RATE_LIMITED


# Cenário 19: not_applicable não é tratado como falha real do provider.
def test_not_applicable_is_not_treated_as_a_real_provider_failure():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        NormalizedIndicator(
            key="ev_ebitda",
            label="EV/EBITDA",
            unit="ratio",
            status=IndicatorStatus.AVAILABLE,
            source="snapshot",
            reference_date=now,
            collected_at=now,
            confidence=ConfidenceLevel.HIGH,
            value=Decimal("12.5"),
        ),
    ]
    validated, _ = IndicatorValidationService().validate(indicators, sector="banco", collected_at=now)

    assert validated[0].status == IndicatorStatus.NOT_APPLICABLE
    assert validated[0].provider_failure_reason == ProviderFailureReason.NOT_APPLICABLE

    coverage, resolved, requested = provider_coverage_for_indicators(validated)
    assert requested == 0
    assert coverage is None


# Cenário 20: causa desconhecida nunca inventa unauthorized/rate_limited/provider_unavailable.
def test_unknown_provider_failure_never_invents_a_specific_cause():
    assert classify_provider_failure_reason(None) == ProviderFailureReason.NOT_REPORTED
    assert classify_provider_failure_reason(RuntimeError("erro genérico")) == ProviderFailureReason.NOT_REPORTED
    assert classify_provider_failure_reason(MarketAssetNotFoundError()) not in {
        ProviderFailureReason.RATE_LIMITED,
        ProviderFailureReason.UNAUTHORIZED,
        ProviderFailureReason.PROVIDER_UNAVAILABLE,
    }


# Cenário 21: coverage_percentage legado continua existindo ao lado do novo breakdown.
def test_legacy_coverage_percentage_field_still_exists():
    assert "coverage_percentage" in AssetIntelligenceSnapshot.model_fields
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    _, indicators = IndicatorNormalizationService().normalize_quote(
        quote(), requested_symbol="PETR4", asset_type="Ação", collected_at=now
    )
    base = AssetIntelligenceSnapshot(
        symbol="PETR4",
        asset_class=InvestmentClass.STOCK,
        indicators=indicators,
        recommendation=RecommendationAction.INSUFFICIENT_DATA,
        valuation_status=ValuationStatus.INSUFFICIENT_DATA,
        valuation=ValuationAssessment(status=ValuationStatus.INSUFFICIENT_DATA, confidence=ConfidenceLevel.INSUFFICIENT),
        confidence=ConfidenceLevel.INSUFFICIENT,
        coverage_percentage=Decimal("0"),
        available_indicators_count=0,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=now,
    )

    result = AssetAnalysisEngine.build_snapshot(base)

    assert isinstance(result.coverage_percentage, Decimal)
    assert isinstance(result.coverage_breakdown, CoverageBreakdown)


# Cenário 22: dado ausente nunca é convertido para zero.
def test_missing_indicator_value_is_never_coerced_to_zero():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    quote_without_volume = quote().model_copy(update={"volume": None})

    _, indicators = IndicatorNormalizationService().normalize_quote(
        quote_without_volume, requested_symbol="PETR4", asset_type="Ação", collected_at=now
    )
    by_key = {item.key: item for item in indicators}

    assert by_key["volume"].status == IndicatorStatus.UNAVAILABLE
    assert by_key["volume"].value is None
    assert by_key["liquidity"].status == IndicatorStatus.UNAVAILABLE
    assert by_key["liquidity"].value is None


# Cenário 23: mesmos inputs produzem sempre o mesmo resultado (determinismo).
def test_coverage_breakdown_is_deterministic_for_same_inputs():
    indicators = [
        _etf_indicator("current_price", "Preço", "currency", value=Decimal("10.00")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("1000")),
        _etf_indicator("tracked_index", "Índice", "text", value="IBOV"),
    ]
    first = coverage_breakdown_for_asset(InvestmentClass.ETF, indicators)
    second = coverage_breakdown_for_asset(InvestmentClass.ETF, indicators)
    assert first == second


# Cenário 24: denominador vazio é tratado explicitamente, sem divisão por zero.
def test_empty_denominator_returns_none_without_zero_division():
    assert canonical_pillars_for_class(InvestmentClass.INVESTMENT_FUND) == []
    breakdown = coverage_breakdown_for_asset(InvestmentClass.INVESTMENT_FUND, [])

    assert breakdown.required_coverage is None
    assert breakdown.required_total == 0
    assert breakdown.recommended_coverage is None
    assert breakdown.total_coverage is None
    assert breakdown.scoring_coverage is None
    assert breakdown.provider_coverage is None


# Cenário 25: required completo + scoring alto -> HIGH.
def test_required_complete_and_high_scoring_yields_high_confidence():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("85.00")),
        scores=_two_category_scores(Decimal("85")),
        overall_score=Decimal("85"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.HIGH


# Cenário 26: required completo + scoring intermediário -> MEDIUM.
def test_required_complete_and_intermediate_scoring_yields_medium_confidence():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("65.00")),
        scores=_two_category_scores(Decimal("65")),
        overall_score=Decimal("65"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.MEDIUM


# Cenário 27: required completo + scoring baixo porém ainda suficiente -> LOW.
def test_required_complete_and_low_but_sufficient_scoring_yields_low_confidence():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("45.00")),
        scores=_two_category_scores(Decimal("45")),
        overall_score=Decimal("45"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.LOW


# Cenário 28: ausência de diagnóstico detalhado de provider não cria falso bloqueio.
def test_missing_provider_failure_detail_does_not_force_blocking():
    indicators = [
        _etf_indicator("current_price", "Preço", "currency", value=Decimal("10.00")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("1000")),
        _etf_indicator("tracked_index", "Índice", "text", value="IBOV"),
        _etf_indicator(
            "beta", "Beta", "ratio", status=IndicatorStatus.UNAVAILABLE, provider_failure_reason=None
        ),
    ]
    breakdown = coverage_breakdown_for_asset(InvestmentClass.ETF, indicators)
    assert breakdown.required_coverage == Decimal("100.00")

    confidence = confidence_for_asset(
        coverage_breakdown=breakdown.model_copy(update={"scoring_coverage": Decimal("70.00")}),
        scores=_two_category_scores(Decimal("70")),
        overall_score=Decimal("70"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence != ConfidenceLevel.INSUFFICIENT


# =====================================================================
# CORREÇÃO — desacoplamento do confidence do gate legado de coverage (P1),
# e fechamento final em P4: RecommendationEngine/overall_score também
# deixaram de usar coverage_percentage legado como gate universal.
#
# confidence_for_asset não usa `overall_score is None` nem
# `data_quality.recommendation_blocked` como gates diretos: ambos podiam
# disparar puramente por causa do coverage_percentage legado (que mistura
# indicadores não essenciais) ou por completeness/freshness não crítica,
# contaminando indiretamente o confidence. Na fase P1, RecommendationEngine e
# SmartPortfolio continuavam lendo esses mesmos campos legados sem alteração
# — isso está registrado nos cenários A e I abaixo, que P4 atualizou para o
# comportamento final: RecommendationEngine agora usa o confidence estrutural
# (não mais coverage_percentage legado) como gate universal; SmartPortfolio
# já usava confidence desde o P2 e permanece inalterado. Cada teste abaixo
# está rotulado com a letra do cenário correspondente do prompt de correção.
# =====================================================================


def _stock_indicators_required_satisfied_but_low_legacy_coverage(now):
    """59 indicadores do catálogo STOCK, apenas 7 AVAILABLE.

    Satisfaz todos os pilares REQUIRED e alcança >=2 categorias de scoring
    reais, mas o coverage_percentage legado (available/total sobre TODO o
    catálogo) fica bem abaixo de 40 — o cenário exato que o gate antigo
    penalizava indevidamente.
    """
    available_values = {
        "current_price": Decimal("39.89"),
        "volume": Decimal("1000000"),
        "price_book": Decimal("1.25"),
        "net_margin": Decimal("12.0"),
        "net_debt_equity": Decimal("0.8"),
        "dividend_yield": Decimal("5.5"),
        "day_range": Decimal("2.1"),
    }
    indicators = []
    for entry in indicators_for_class(InvestmentClass.STOCK):
        if entry.key in available_values:
            indicators.append(
                NormalizedIndicator(
                    key=entry.key,
                    label=entry.label,
                    unit=entry.unit,
                    status=IndicatorStatus.AVAILABLE,
                    source="snapshot",
                    reference_date=now,
                    collected_at=now,
                    confidence=ConfidenceLevel.HIGH,
                    value=available_values[entry.key],
                )
            )
        else:
            indicators.append(
                NormalizedIndicator(
                    key=entry.key,
                    label=entry.label,
                    unit=entry.unit,
                    status=IndicatorStatus.UNAVAILABLE,
                    source="snapshot",
                    collected_at=now,
                    confidence=ConfidenceLevel.INSUFFICIENT,
                    unavailable_reason="Provedor não retornou este indicador.",
                )
            )
    return indicators


def _stock_required_satisfied_small_indicator_set():
    return [
        _etf_indicator("current_price", "Preço atual", "currency", value=Decimal("39.89")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("1000000")),
        _etf_indicator("price_book", "P/VP", "ratio", value=Decimal("1.25")),
        _etf_indicator("net_margin", "Margem líquida", "percent", value=Decimal("12.0")),
        _etf_indicator("net_debt_equity", "Dívida/PL", "ratio", value=Decimal("0.8")),
    ]


def _base_stock_snapshot(indicators, now, *, data_quality=None):
    return AssetIntelligenceSnapshot(
        symbol="XYZ4",
        asset_class=InvestmentClass.STOCK,
        indicators=indicators,
        data_quality=data_quality,
        recommendation=RecommendationAction.INSUFFICIENT_DATA,
        valuation_status=ValuationStatus.INSUFFICIENT_DATA,
        valuation=ValuationAssessment(status=ValuationStatus.INSUFFICIENT_DATA, confidence=ConfidenceLevel.INSUFFICIENT),
        confidence=ConfidenceLevel.INSUFFICIENT,
        coverage_percentage=Decimal("0"),
        available_indicators_count=0,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=now,
    )


# Cenário A: required=100 + scoring suficiente + coverage_percentage legado
# < 40 por indicadores não essenciais -> confidence NÃO é INSUFFICIENT
# (prova fim a fim via build_snapshot, não apenas chamando confidence_for_asset
# com overall_score preenchido manualmente). P4: overall_score e
# RecommendationEngine também deixaram de depender do coverage legado, então
# o mesmo cenário agora produz overall_score real e uma recomendação
# estrutural, não mais INSUFFICIENT_DATA.
def test_confidence_end_to_end_ignores_legacy_coverage_percentage_gate():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = _stock_indicators_required_satisfied_but_low_legacy_coverage(now)
    base = _base_stock_snapshot(indicators, now)

    result = AssetAnalysisEngine.build_snapshot(base)

    # coverage_percentage legado continua existindo e baixo (compatibilidade)...
    assert result.coverage_percentage < Decimal("40")
    # ...mas não bloqueia mais overall_score nem a recomendação (P4): há
    # categorias reais de score suficientes, então ambos são calculados de
    # verdade, nunca None/insuficiente só por causa do coverage legado.
    assert result.overall_score is not None
    assert result.recommendation != RecommendationAction.INSUFFICIENT_DATA
    # o novo confidence enxerga required=100% e categorias reais de score
    # suficientes, e permanece LOW (não bloqueante) — nunca INSUFFICIENT.
    assert result.coverage_breakdown.required_coverage == Decimal("100.00")
    assert result.confidence != ConfidenceLevel.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW


# Cenário B: required completos + scoring suficiente + data_quality.
# recommendation_blocked=True (por completeness/freshness não crítica) ->
# confidence NÃO é automaticamente INSUFFICIENT (fim a fim via build_snapshot).
def test_confidence_end_to_end_ignores_non_critical_recommendation_blocked():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = _stock_required_satisfied_small_indicator_set()
    blocked_quality = DataQualityReport(
        data_completeness=Decimal("30.00"),
        data_freshness=Decimal("30.00"),
        data_quality_score=Decimal("21.00"),
        recommendation_blocked=True,
        blocking_reason="Não foi possível emitir uma avaliação confiável devido à qualidade ou à ausência dos dados.",
    )
    base = _base_stock_snapshot(indicators, now, data_quality=blocked_quality)

    result = AssetAnalysisEngine.build_snapshot(base)

    assert result.data_quality is not None
    assert result.data_quality.recommendation_blocked is True
    # RecommendationEngine (legado, intocado) ainda reage ao bloqueio.
    assert result.recommendation == RecommendationAction.REVIEW_DATA
    assert result.coverage_breakdown.required_coverage == Decimal("100.00")
    assert result.confidence != ConfidenceLevel.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.HIGH


# Cenário C: REQUIRED ausente -> continua INSUFFICIENT.
def test_confidence_regression_missing_required_pillar_stays_insufficient():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("66.67"), required_satisfied=2, required_total=3, scoring_coverage=Decimal("95.00")
    )
    confidence = confidence_for_asset(
        coverage_breakdown=breakdown,
        scores=_two_category_scores(Decimal("95")),
        overall_score=Decimal("95"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.INSUFFICIENT


# Cenário D: identifier_unresolved -> continua INSUFFICIENT.
def test_confidence_regression_identifier_unresolved_stays_insufficient():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("95.00")),
        scores=_two_category_scores(Decimal("95")),
        overall_score=Decimal("95"),
        data_quality=None,
        anomaly_flags=["identifier_unresolved"],
    )
    assert confidence == ConfidenceLevel.INSUFFICIENT


# Cenário E: conflicting_sources crítico -> continua INSUFFICIENT.
def test_confidence_regression_conflicting_sources_stays_insufficient():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("95.00")),
        scores=_two_category_scores(Decimal("95")),
        overall_score=Decimal("95"),
        data_quality=None,
        anomaly_flags=["conflicting_sources"],
    )
    assert confidence == ConfidenceLevel.INSUFFICIENT


# Cenário F: menos de duas categorias reais de scoring -> continua INSUFFICIENT.
def test_confidence_regression_insufficient_scoring_categories_stays_insufficient():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("100.00"), required_satisfied=3, required_total=3, scoring_coverage=Decimal("95.00")
    )
    only_one_scored = {
        "quality": ScoreBreakdown(
            value=Decimal("95"),
            available_indicators=2,
            missing_indicators=0,
            stale_indicators=0,
            coverage_percentage=Decimal("100"),
            confidence=ConfidenceLevel.HIGH,
        ),
        "valuation": ScoreBreakdown(
            value=None,
            available_indicators=0,
            missing_indicators=2,
            stale_indicators=0,
            coverage_percentage=Decimal("0"),
            confidence=ConfidenceLevel.INSUFFICIENT,
        ),
    }
    confidence = confidence_for_asset(
        coverage_breakdown=breakdown,
        scores=only_one_scored,
        overall_score=Decimal("95"),
        data_quality=None,
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.INSUFFICIENT


# Cenário G: LOW continua alcançável e não bloqueante, mesmo com
# overall_score=None e recommendation_blocked=True simultaneamente.
def test_confidence_regression_low_remains_reachable_and_non_blocking():
    confidence = confidence_for_asset(
        coverage_breakdown=_perfect_breakdown(Decimal("50.00")),
        scores=_two_category_scores(Decimal("50")),
        overall_score=None,
        data_quality=DataQualityReport(
            data_completeness=Decimal("50"), data_freshness=Decimal("50"), recommendation_blocked=True
        ),
        anomaly_flags=None,
    )
    assert confidence == ConfidenceLevel.LOW


# Cenário H: coverage_percentage legado continua existente e com a mesma
# fórmula de sempre (available/total sobre todos os indicadores passados).
def test_confidence_regression_legacy_coverage_percentage_field_untouched():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = _stock_indicators_required_satisfied_but_low_legacy_coverage(now)
    base = _base_stock_snapshot(indicators, now)

    result = AssetAnalysisEngine.build_snapshot(base)

    total = len(indicators)
    available = sum(1 for item in indicators if item.status == IndicatorStatus.AVAILABLE)
    expected = (Decimal(available) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01"))

    assert "coverage_percentage" in AssetIntelligenceSnapshot.model_fields
    assert result.coverage_percentage == expected


# Cenário I (atualizado em P4): na fase P1, RecommendationEngine ainda
# gateava em coverage_percentage legado mesmo com confidence desacoplado —
# esse comportamento estava documentado como deliberadamente adiado para P4.
# P4 fecha essa lacuna: RecommendationEngine agora usa o mesmo confidence
# estrutural, então required=100% + scoring suficiente (confidence LOW, não
# INSUFFICIENT) já não é mais bloqueado por coverage_percentage < 40.
def test_recommendation_engine_no_longer_gates_on_legacy_coverage_percentage_alone():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = _stock_indicators_required_satisfied_but_low_legacy_coverage(now)
    base = _base_stock_snapshot(indicators, now)

    result = AssetAnalysisEngine.build_snapshot(base)

    assert result.coverage_percentage < Decimal("40")
    assert result.confidence == ConfidenceLevel.LOW
    assert result.recommendation != RecommendationAction.INSUFFICIENT_DATA


# =====================================================================
# P4 — fechamento estrutural: RecommendationEngine agora gateia por
# confidence (não mais coverage_percentage legado), warning_reasons com
# causa específica, resolution_summary agregado a partir de P3.
# =====================================================================


def _valuation(
    status=ValuationStatus.NEAR_ESTIMATED_VALUE, confidence=ConfidenceLevel.MEDIUM
):
    return ValuationAssessment(status=status, confidence=confidence)


def _snapshot_for_recommend(
    *, confidence=ConfidenceLevel.MEDIUM, data_quality=None, strategy_fit_score=None
):
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    return AssetIntelligenceSnapshot(
        symbol="XYZ4",
        asset_class=InvestmentClass.STOCK,
        indicators=[],
        data_quality=data_quality,
        strategy_fit_score=strategy_fit_score,
        recommendation=RecommendationAction.INSUFFICIENT_DATA,
        valuation_status=ValuationStatus.INSUFFICIENT_DATA,
        valuation=ValuationAssessment(
            status=ValuationStatus.INSUFFICIENT_DATA, confidence=ConfidenceLevel.INSUFFICIENT
        ),
        confidence=confidence,
        coverage_percentage=Decimal("0"),
        available_indicators_count=0,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=now,
    )


def test_recommendation_engine_blocks_only_when_confidence_is_insufficient():
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.INSUFFICIENT)
    action = RecommendationEngine.recommend(
        snapshot,
        scores={},
        valuation=_valuation(),
        confidence=ConfidenceLevel.INSUFFICIENT,
        overall_score=Decimal("90"),
    )
    assert action == RecommendationAction.INSUFFICIENT_DATA


def test_recommendation_engine_does_not_block_on_low_medium_or_high_confidence():
    for level in (ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH):
        snapshot = _snapshot_for_recommend(confidence=level)
        action = RecommendationEngine.recommend(
            snapshot,
            scores={},
            valuation=_valuation(),
            confidence=level,
            overall_score=Decimal("80"),
        )
        assert action != RecommendationAction.INSUFFICIENT_DATA


def test_recommendation_engine_still_reviews_on_data_quality_block():
    blocked_quality = DataQualityReport(
        data_completeness=Decimal("30"),
        data_freshness=Decimal("30"),
        recommendation_blocked=True,
    )
    snapshot = _snapshot_for_recommend(
        confidence=ConfidenceLevel.MEDIUM, data_quality=blocked_quality
    )
    action = RecommendationEngine.recommend(
        snapshot,
        scores={},
        valuation=_valuation(),
        confidence=ConfidenceLevel.MEDIUM,
        overall_score=Decimal("80"),
    )
    assert action == RecommendationAction.REVIEW_DATA


def test_recommendation_engine_reviews_when_valuation_insufficient_but_confidence_ok():
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.MEDIUM)
    action = RecommendationEngine.recommend(
        snapshot,
        scores={},
        valuation=_valuation(
            status=ValuationStatus.INSUFFICIENT_DATA, confidence=ConfidenceLevel.INSUFFICIENT
        ),
        confidence=ConfidenceLevel.MEDIUM,
        overall_score=Decimal("80"),
    )
    assert action == RecommendationAction.REVIEW_DATA


def test_recommendation_engine_analyze_to_buy_above_threshold_with_ok_confidence():
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.HIGH)
    action = RecommendationEngine.recommend(
        snapshot,
        scores={},
        valuation=_valuation(),
        confidence=ConfidenceLevel.HIGH,
        overall_score=Decimal("80"),
    )
    assert action == RecommendationAction.ANALYZE_TO_BUY


def test_warning_reasons_never_uses_generic_insufficient_message_for_missing_required():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("66.67"), required_satisfied=2, required_total=3
    )
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.INSUFFICIENT)
    reasons = warning_reasons(
        snapshot, coverage_breakdown=breakdown, confidence=ConfidenceLevel.INSUFFICIENT
    )
    assert reasons
    assert "Não existem dados suficientes" not in reasons[0]
    assert "pilar" in reasons[0].lower()


def test_warning_reasons_cites_scoring_categories_when_required_is_complete():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("100.00"), required_satisfied=3, required_total=3
    )
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.INSUFFICIENT)
    reasons = warning_reasons(
        snapshot, coverage_breakdown=breakdown, confidence=ConfidenceLevel.INSUFFICIENT
    )
    assert reasons
    assert "categorias" in reasons[0].lower()


def test_warning_reasons_cites_identity_or_conflict_for_critical_anomaly():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("100.00"), required_satisfied=3, required_total=3
    )
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.INSUFFICIENT).model_copy(
        update={"anomaly_flags": ["identifier_unresolved"]}
    )
    reasons = warning_reasons(
        snapshot, coverage_breakdown=breakdown, confidence=ConfidenceLevel.INSUFFICIENT
    )
    assert reasons
    assert "identidade" in reasons[0].lower()


def test_warning_reasons_empty_when_confidence_not_insufficient():
    breakdown = CoverageBreakdown(
        required_coverage=Decimal("100.00"), required_satisfied=3, required_total=3
    )
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.HIGH).model_copy(
        update={"market_updated_at": now}
    )
    reasons = warning_reasons(
        snapshot, coverage_breakdown=breakdown, confidence=ConfidenceLevel.HIGH
    )
    assert reasons == []


# --- resolution_summary agregado (P4) a partir de resolution_attempts (P3) ---


def _attempt(outcome, *, provider="BRAPI", reason=None, source_type="provider"):
    return ProviderResolutionAttempt(
        provider=provider,
        source_type=source_type,
        outcome=outcome,
        provider_failure_reason=reason,
        attempted_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )


def test_resolution_summary_counts_attempts_successes_failures_and_fallback():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    resolved_first_try = NormalizedIndicator(
        key="current_price",
        label="Preço",
        unit="currency",
        status=IndicatorStatus.AVAILABLE,
        source="BRAPI",
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("10"),
        resolution_attempts=[_attempt(ResolutionOutcome.SUCCESS)],
    )
    fallback_resolved = NormalizedIndicator(
        key="treasury_rate",
        label="Taxa",
        unit="percent",
        status=IndicatorStatus.AVAILABLE,
        source="Tesouro Transparente",
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("6"),
        resolution_attempts=[
            _attempt(
                ResolutionOutcome.FAILURE,
                provider="BRAPI",
                reason=ProviderFailureReason.RATE_LIMITED,
            ),
            _attempt(
                ResolutionOutcome.SUCCESS,
                provider="Tesouro Transparente",
                source_type="official",
            ),
        ],
    )
    still_missing = NormalizedIndicator(
        key="dividend_yield",
        label="DY",
        unit="percent",
        status=IndicatorStatus.UNAVAILABLE,
        source="BRAPI",
        collected_at=now,
        confidence=ConfidenceLevel.INSUFFICIENT,
        resolution_attempts=[
            _attempt(ResolutionOutcome.FAILURE, reason=ProviderFailureReason.NOT_REPORTED)
        ],
    )
    stale_one = NormalizedIndicator(
        key="price_book",
        label="P/VP",
        unit="ratio",
        status=IndicatorStatus.STALE,
        source="CVM",
        collected_at=now,
        confidence=ConfidenceLevel.LOW,
        resolution_attempts=[
            _attempt(
                ResolutionOutcome.SUCCESS, provider="CVM", reason=ProviderFailureReason.STALE
            )
        ],
    )

    summary = build_resolution_summary(
        [resolved_first_try, fallback_resolved, still_missing, stale_one]
    )

    assert summary.attempt_count == 5
    assert summary.success_count == 3
    assert summary.failure_count == 2
    assert summary.fallback_success_count == 1
    assert summary.unresolved_count == 1
    assert summary.stale_count == 1
    assert "BRAPI" in summary.sources_used
    assert "Tesouro Transparente" in summary.sources_used
    assert summary.failure_reason_counts["rate_limited"] == 1
    assert summary.failure_reason_counts["not_reported"] == 1


def test_resolution_summary_empty_when_no_attempts_ever_made():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    available = NormalizedIndicator(
        key="current_price",
        label="Preço",
        unit="currency",
        status=IndicatorStatus.AVAILABLE,
        source="BRAPI",
        collected_at=now,
        confidence=ConfidenceLevel.HIGH,
        value=Decimal("10"),
    )
    summary = build_resolution_summary([available])
    assert summary.attempt_count == 0
    assert summary.success_count == 0
    assert summary.sources_used == []


def test_resolution_summary_failure_reason_counts_never_carry_raw_detail():
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicator = NormalizedIndicator(
        key="current_price",
        label="Preço",
        unit="currency",
        status=IndicatorStatus.UNAVAILABLE,
        source="BRAPI",
        collected_at=now,
        confidence=ConfidenceLevel.INSUFFICIENT,
        resolution_attempts=[
            ProviderResolutionAttempt(
                provider="BRAPI",
                source_type="provider",
                outcome=ResolutionOutcome.FAILURE,
                provider_failure_reason=ProviderFailureReason.UNAUTHORIZED,
                attempted_at=now,
                detail="[REDACTED]",
            )
        ],
    )
    summary = build_resolution_summary([indicator])
    assert list(summary.failure_reason_counts.keys()) == ["unauthorized"]
    assert "Bearer" not in str(summary.failure_reason_counts)


# --- fim a fim (cenários 36-38 do prompt P4) -------------------------------


def test_end_to_end_partial_fallback_low_confidence_still_gets_recommendation():
    """Cenário 36: required completo + >=2 categorias reais + coverage legado
    < 40 + fallback parcial resolvido + confidence LOW -> NÃO vira
    INSUFFICIENT_DATA só por causa do coverage legado ou do fallback parcial."""
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = _stock_indicators_required_satisfied_but_low_legacy_coverage(now)
    # marca um dos indicadores como resolvido via fallback após uma falha real.
    by_key = {item.key: item for item in indicators}
    rate_limited = by_key["dividend_yield"].model_copy(
        update={
            "resolution_attempts": [
                _attempt(
                    ResolutionOutcome.FAILURE,
                    provider="BRAPI",
                    reason=ProviderFailureReason.RATE_LIMITED,
                ),
                _attempt(ResolutionOutcome.SUCCESS, provider="CVM Dados Abertos", source_type="official"),
            ]
        }
    )
    indicators = [rate_limited if item.key == "dividend_yield" else item for item in indicators]
    base = _base_stock_snapshot(indicators, now)

    result = AssetAnalysisEngine.build_snapshot(base)

    assert result.confidence == ConfidenceLevel.LOW
    assert result.recommendation != RecommendationAction.INSUFFICIENT_DATA
    assert result.overall_score is not None


def test_end_to_end_partial_valuation_insufficiency_does_not_block_whole_asset():
    """Cenário 37: required completo + scoring suficiente, mas valuation
    isoladamente insuficiente -> REVIEW_DATA, nunca ANÁLISE INSUFICIENTE.

    O pilar REQUIRED "valuation" aceita price_earnings/price_book/ev_ebitda
    (ANY_OF), enquanto ValuationEngine.assess só reconhece
    price_earnings/price_book/dividend_yield. Usando ev_ebitda em vez de
    price_book satisfaz o pilar estrutural sem satisfazer ValuationEngine —
    prova que os dois são sinais independentes.
    """
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    indicators = [
        _etf_indicator("current_price", "Preço atual", "currency", value=Decimal("39.89")),
        _etf_indicator("volume", "Volume", "quantity", value=Decimal("1000000")),
        _etf_indicator("ev_ebitda", "EV/EBITDA", "ratio", value=Decimal("6.5")),
        _etf_indicator("net_margin", "Margem líquida", "percent", value=Decimal("12.0")),
        _etf_indicator("net_debt_equity", "Dívida/PL", "ratio", value=Decimal("0.8")),
    ]
    base = _base_stock_snapshot(indicators, now)

    result = AssetAnalysisEngine.build_snapshot(base)

    assert result.coverage_breakdown.required_coverage == Decimal("100.00")
    assert result.valuation_status == ValuationStatus.INSUFFICIENT_DATA
    assert result.confidence != ConfidenceLevel.INSUFFICIENT
    assert result.recommendation == RecommendationAction.REVIEW_DATA


def test_end_to_end_total_fallback_failure_never_becomes_zero_and_explains_cause():
    """Cenário 38: nenhuma fonte resolve um indicador REQUIRED -> valor
    continua None (nunca 0), confidence pode ficar INSUFFICIENT, e a
    mensagem explica a causa real (pilar obrigatório), não genérica."""
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    price = NormalizedIndicator(
        key="current_price",
        label="Preço atual",
        unit="currency",
        status=IndicatorStatus.UNAVAILABLE,
        source="BRAPI",
        collected_at=now,
        confidence=ConfidenceLevel.INSUFFICIENT,
        unavailable_reason="Nenhuma fonte resolveu o preço.",
        resolution_attempts=[
            _attempt(ResolutionOutcome.FAILURE, reason=ProviderFailureReason.PROVIDER_UNAVAILABLE),
            _attempt(ResolutionOutcome.FAILURE, provider="CVM Dados Abertos", source_type="official", reason=ProviderFailureReason.NOT_SYNCED),
        ],
    )
    base = _base_stock_snapshot([price], now)

    result = AssetAnalysisEngine.build_snapshot(base)

    resolved_price = next(item for item in result.indicators if item.key == "current_price")
    assert resolved_price.value is None
    assert resolved_price.value != Decimal("0")
    assert result.confidence == ConfidenceLevel.INSUFFICIENT
    assert result.warning_reasons
    assert "Não existem dados suficientes" not in result.warning_reasons[0]
    summary = build_resolution_summary(result.indicators)
    assert summary.failure_count == 2
    assert summary.unresolved_count == 1


# Nova pontuação das ações: valores, e não a contagem de indicadores.
def _stock_ratio(key: str, amount: str, *, stale: bool = False):
    return NormalizedIndicator(
        key=key, label=key, value=Decimal(amount), unit="percent" if key == "roe" else "ratio",
        status=IndicatorStatus.STALE if stale else IndicatorStatus.AVAILABLE,
        source="test", collected_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.HIGH,
    )


def test_stock_quality_distinguishes_low_and_high_roe_at_equal_coverage():
    weak = ScoringEngine.score_category(InvestmentClass.STOCK, [_stock_ratio("roe", "2")], ["roe"])
    strong = ScoringEngine.score_category(InvestmentClass.STOCK, [_stock_ratio("roe", "22")], ["roe"])
    assert weak.coverage_percentage == strong.coverage_percentage == Decimal("100")
    assert weak.value is not None and strong.value is not None
    assert strong.value > weak.value


def test_stock_valuation_uses_the_pe_value_not_just_its_presence():
    cheap = ScoringEngine.score_category(
        InvestmentClass.STOCK, [_stock_ratio("price_earnings", "9")], ["price_earnings"]
    )
    expensive = ScoringEngine.score_category(
        InvestmentClass.STOCK, [_stock_ratio("price_earnings", "28")], ["price_earnings"]
    )
    assert cheap.coverage_percentage == expensive.coverage_percentage == Decimal("100")
    assert cheap.value > expensive.value


def test_raw_company_size_does_not_receive_a_fake_stock_score():
    raw = ScoringEngine.score_category(
        InvestmentClass.STOCK, [_stock_ratio("assets", "500000000000")], ["assets"]
    )
    assert raw.coverage_percentage == Decimal("100")
    assert raw.value is None


def test_stale_stock_ratio_does_not_feed_the_score():
    stale = ScoringEngine.score_category(
        InvestmentClass.STOCK, [_stock_ratio("roe", "22", stale=True)], ["roe"]
    )
    assert stale.value is None
    assert stale.stale_indicators == 1


def test_negative_earnings_pe_is_not_rewarded_as_cheap():
    result = ScoringEngine.score_category(
        InvestmentClass.STOCK, [_stock_ratio("price_earnings", "-8")], ["price_earnings"]
    )
    assert result.value is None


def test_dividend_yield_alone_does_not_duplicate_into_stock_valuation():
    dividend = NormalizedIndicator(
        key="dividend_yield", label="Dividend Yield", value=Decimal("6"), unit="percent",
        status=IndicatorStatus.AVAILABLE, source="test",
        collected_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        confidence=ConfidenceLevel.HIGH,
    )
    valuation = ScoringEngine.score_category(
        InvestmentClass.STOCK, [dividend], ["price_earnings", "price_book", "dividend_yield"]
    )
    income = ScoringEngine.score_category(
        InvestmentClass.STOCK, [dividend], ["dividend_yield", "income_12m"]
    )
    assert valuation.value is None
    assert income.value is not None


def test_pe_and_pb_do_not_invent_an_intrinsic_price():
    two_ratios = [
        _stock_ratio("price_earnings", "9"),
        _stock_ratio("price_book", "1.2"),
    ]
    assessment = ValuationEngine.assess(two_ratios)
    assert assessment.status == ValuationStatus.INSUFFICIENT_DATA
    assert assessment.estimated_range_low is None
    assert assessment.estimated_range_high is None
    assert assessment.confidence == ConfidenceLevel.INSUFFICIENT
    assert "price_earnings" not in assessment.missing_indicators


def test_no_buy_signal_from_unvalidated_fair_value():
    snapshot = _snapshot_for_recommend(confidence=ConfidenceLevel.HIGH)
    valuation = ValuationEngine.assess(
        [_stock_ratio("price_earnings", "9"), _stock_ratio("price_book", "1.2")]
    )
    recommendation = RecommendationEngine.recommend(
        snapshot,
        scores={},
        valuation=valuation,
        confidence=ConfidenceLevel.HIGH,
        overall_score=Decimal("90"),
    )
    assert recommendation == RecommendationAction.REVIEW_DATA
