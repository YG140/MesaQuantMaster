"""Regressões de segurança para recomendações de novos aportes em ações.

Nenhum preço, múltiplo ou sinal destes testes representa dados reais.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.engines.smart_portfolio_engine import PortfolioCandidate, SmartPortfolioEngine
from app.engines.stock_purchase_eligibility import stock_purchase_exclusion_reason
from app.schemas.intelligence import BuildPortfolioRequest
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot,
    ConfidenceLevel,
    DataQualityReport,
    InvestmentClass,
    RecommendationAction,
    ValuationAssessment,
    ValuationStatus,
)

NOW = datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)


def stock_snapshot():
    return AssetIntelligenceSnapshot(
        symbol="EXEM3",
        name="Exemplo sintético",
        asset_class=InvestmentClass.STOCK,
        currency="BRL",
        current_price=Decimal("75"),
        market_updated_at=NOW,
        indicators=[],
        overall_score=Decimal("93"),
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.ATTRACTIVE,
        valuation=ValuationAssessment(
            status=ValuationStatus.ATTRACTIVE,
            confidence=ConfidenceLevel.MEDIUM,
            methods=["Faixa relativa setorial: LPA × P/L e VPA × P/VP"],
            estimated_range_low=Decimal("100"),
            estimated_range_high=Decimal("110"),
            data_date=NOW,
        ),
        confidence=ConfidenceLevel.HIGH,
        coverage_percentage=Decimal("98"),
        available_indicators_count=0,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=NOW,
    )


def build(snapshot):
    return SmartPortfolioEngine.build(
        BuildPortfolioRequest(
            available_amount=Decimal("10000"),
            objective="crescimento",
            horizon="longo prazo",
            risk_profile="moderado",
        ),
        [PortfolioCandidate(snapshot=snapshot, sector="Energia", issuer="EXEM")],
    )


def test_discounted_stock_with_auditable_reference_is_eligible_for_review():
    result = build(stock_snapshot())
    assert [item.symbol for item in result.assets] == ["EXEM3"]
    assert result.assets[0].valuation_status == ValuationStatus.ATTRACTIVE.value
    assert result.assets[0].estimated_range_low == Decimal("100")
    assert any("não é valor justo intrínseco" in r for r in result.assets[0].risks)


@pytest.mark.parametrize(
    "status",
    [
        ValuationStatus.NEAR_ESTIMATED_VALUE,
        ValuationStatus.ELEVATED,
        ValuationStatus.VERY_ELEVATED,
        ValuationStatus.INSUFFICIENT_DATA,
    ],
)
def test_high_score_and_data_confidence_cannot_override_unattractive_price(status):
    base = stock_snapshot()
    assessment = base.valuation.model_copy(update={"status": status})
    snapshot = base.model_copy(update={
        "valuation_status": status,
        "valuation": assessment,
    })
    result = build(snapshot)
    assert not result.assets
    assert result.status == "unavailable"
    assert result.unallocated_amount == Decimal("10000.00")
    assert "preço atrativo" in result.exclusions[0].reasons[0]


def test_high_score_does_not_override_no_buy_signal():
    snapshot = stock_snapshot().model_copy(update={"recommendation": RecommendationAction.HOLD})
    result = build(snapshot)
    assert not result.assets
    assert "sem sinal" in result.exclusions[0].reasons[0]


def test_relative_margin_of_safety_is_enforced():
    snapshot = stock_snapshot().model_copy(update={"current_price": Decimal("85")})
    assert "20%" in stock_purchase_exclusion_reason(snapshot)
    assert not build(snapshot).assets


@pytest.mark.parametrize(
    "change",
    [
        {"valuation": stock_snapshot().valuation.model_copy(update={"estimated_range_low": None})},
        {"valuation": stock_snapshot().valuation.model_copy(update={"estimated_range_high": Decimal("50")})},
        {"valuation": stock_snapshot().valuation.model_copy(update={"methods": []})},
        {"valuation": stock_snapshot().valuation.model_copy(update={"confidence": ConfidenceLevel.LOW})},
        {"valuation": stock_snapshot().valuation.model_copy(update={"data_date": NOW - timedelta(days=8)})},
        {"market_updated_at": NOW - timedelta(days=8)},
        {"confidence": ConfidenceLevel.LOW},
        {"valuation_status": ValuationStatus.NEAR_ESTIMATED_VALUE},
    ],
)
def test_incomplete_or_inconsistent_evidence_blocks_new_purchase(change):
    snapshot = stock_snapshot().model_copy(update=change)
    assert stock_purchase_exclusion_reason(snapshot) is not None
    result = build(snapshot)
    assert result.assets == []
    assert result.exclusions


def test_blocked_data_quality_blocks_even_when_score_is_high():
    quality = DataQualityReport(
        data_completeness=Decimal("80"),
        data_freshness=Decimal("100"),
        recommendation_blocked=True,
        blocking_reason="Falha de validação.",
    )
    result = build(stock_snapshot().model_copy(update={"data_quality": quality}))
    assert result.assets == []
    assert "qualidade dos dados" in result.exclusions[0].reasons[0]


def test_failure_to_qualify_keeps_money_unallocated_instead_of_reinvesting_in_weak_stock():
    no_buy = stock_snapshot().model_copy(update={
        "recommendation": RecommendationAction.REVIEW_DATA,
    })
    result = build(no_buy)
    assert result.total_allocated_amount == Decimal("0")
    assert result.unallocated_amount == Decimal("10000.00")
    assert result.total_allocated_amount + result.unallocated_amount == Decimal("10000.00")
