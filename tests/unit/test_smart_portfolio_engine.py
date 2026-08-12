from datetime import datetime, timezone
from decimal import Decimal

from app.engines.smart_portfolio_engine import PortfolioCandidate, SmartPortfolioEngine
from app.schemas.intelligence import BuildPortfolioRequest
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot,
    ConfidenceLevel,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
    RecommendationAction,
    ValuationAssessment,
    ValuationStatus,
)

NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def request(**updates):
    values = dict(
        available_amount=Decimal("10000"),
        objective="crescimento",
        horizon="longo prazo",
        risk_profile="moderado",
        max_percentage_per_asset=Decimal("20"),
        max_percentage_per_class=Decimal("40"),
        max_percentage_per_sector=Decimal("30"),
        max_assets=10,
    )
    values.update(updates)
    return BuildPortfolioRequest(**values)


def candidate(
    symbol,
    asset_class=InvestmentClass.STOCK,
    coverage="80",
    score="75",
    sector="Energia",
):
    indicator = NormalizedIndicator(
        key="price_earnings",
        label="P/L",
        value=Decimal("8"),
        display_value="8",
        unit="ratio",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        source_type="snapshot",
        reference_date=NOW,
        collected_at=NOW,
        valid_until=NOW,
        confidence=ConfidenceLevel.HIGH,
    )
    snapshot = AssetIntelligenceSnapshot(
        symbol=symbol,
        name=symbol,
        asset_class=asset_class,
        current_price=Decimal("10"),
        indicators=[indicator],
        overall_score=Decimal(score),
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.NEAR_ESTIMATED_VALUE,
        valuation=ValuationAssessment(
            status=ValuationStatus.NEAR_ESTIMATED_VALUE,
            confidence=ConfidenceLevel.MEDIUM,
        ),
        confidence=ConfidenceLevel.MEDIUM,
        coverage_percentage=Decimal(coverage),
        available_indicators_count=1,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=NOW,
    )
    return PortfolioCandidate(snapshot=snapshot, sector=sector, issuer=symbol)


def test_allocation_obeys_limits_and_preserves_provenance():
    result = SmartPortfolioEngine.build(
        request(),
        [
            candidate("AAAA3"),
            candidate("BBBB3"),
            candidate("CCCC11", InvestmentClass.FII, sector="Imobiliário"),
        ],
    )
    assert result.assets
    assert result.total_allocated_percentage <= Decimal("100")
    assert all(item.recommended_percentage <= Decimal("20") for item in result.assets)
    assert all(item.percentage <= Decimal("40") for item in result.class_allocations)
    assert result.total_allocated_amount + result.unallocated_amount == Decimal(
        "10000.00"
    )
    assert all(item.indicators_used[0].source == "snapshot" for item in result.assets)


def test_insufficient_coverage_is_excluded_and_missing_is_not_zero():
    result = SmartPortfolioEngine.build(request(), [candidate("LOW3", coverage="39")])
    assert result.assets == []
    assert result.unallocated_amount == Decimal("10000.00")
    assert result.exclusions[0].symbol == "LOW3"


def test_same_inputs_are_deterministic_except_timestamp():
    candidates = [candidate("BBBB3"), candidate("AAAA3")]
    first = SmartPortfolioEngine.build(request(), candidates)
    second = SmartPortfolioEngine.build(request(), list(reversed(candidates)))
    assert [(item.symbol, item.recommended_percentage) for item in first.assets] == [
        (item.symbol, item.recommended_percentage) for item in second.assets
    ]


def test_prohibited_class_and_conservative_crypto_are_excluded():
    result = SmartPortfolioEngine.build(
        request(risk_profile="conservador", prohibited_classes=["FIIs"]),
        [
            candidate("FII11", InvestmentClass.FII),
            candidate("BTC", InvestmentClass.CRYPTO),
        ],
    )
    assert not result.assets
    assert {item.symbol for item in result.exclusions} == {"FII11", "BTC"}
