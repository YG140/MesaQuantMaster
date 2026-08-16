from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.engines.indicator_catalog import (
    canonical_pillars_for_class,
    evaluate_indicator_pillar,
    indicator_temporal_validity_days,
    indicators_for_class,
)
from app.engines.market_intelligence_engine import AssetAnalysisEngine
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
from app.schemas.market_intelligence import (
    AnalyzeAssetsRequest,
    AssetIntelligenceSnapshot,
    ConfidenceLevel,
    IndicatorImportance,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
    RecommendationAction,
    ValuationAssessment,
    ValuationStatus,
)
from app.services.indicator_normalization_service import IndicatorNormalizationService
from app.services.indicator_validation_service import IndicatorValidationService
from app.services.market_intelligence_service import (
    MarketIntelligenceService,
    infer_class_from_symbol,
    strategy_fit,
)
from app.services.portfolio_service import PortfolioService


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
    assert result.overall_score is None
    assert result.valuation_status == ValuationStatus.INSUFFICIENT_DATA
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
