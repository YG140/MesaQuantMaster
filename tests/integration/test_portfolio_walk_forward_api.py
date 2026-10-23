"""API autenticada: validação histórica nunca escreve operações nem carteira."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot, ConfidenceLevel, InvestmentClass,
    RecommendationAction, ValuationAssessment, ValuationStatus,
)
from app.schemas.portfolio_validation import (
    AdjustedReturnInterval, BenchmarkInterval, HistoricalCandidate,
    WalkForwardPeriod, WalkForwardRequest,
)
from app.schemas.intelligence import BuildPortfolioRequest

D1 = datetime(2026, 4, 10, 19, tzinfo=timezone.utc)
D2 = datetime(2026, 5, 10, 19, tzinfo=timezone.utc)


def payload(*, missing_return=False):
    snap = AssetIntelligenceSnapshot(
        symbol="EXEM3", name="Exemplo sintético",
        asset_class=InvestmentClass.STOCK, currency="BRL",
        current_price=Decimal("10"), market_updated_at=D1,
        indicators=[], overall_score=Decimal("88"),
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.ATTRACTIVE,
        valuation=ValuationAssessment(
            status=ValuationStatus.ATTRACTIVE, confidence=ConfidenceLevel.MEDIUM,
            methods=["Benchmark sintético"],
            estimated_range_low=Decimal("15"), estimated_range_high=Decimal("17"),
            data_date=D1,
        ),
        confidence=ConfidenceLevel.HIGH,
        coverage_percentage=Decimal("90"),
        available_indicators_count=0, missing_indicators_count=0,
        stale_indicators_count=0, calculated_at=D1,
    )
    request = WalkForwardRequest(
        initial_capital=Decimal("1000"),
        periods=[
            WalkForwardPeriod(
                decision_at=D1, evaluation_at=D2, profile_recorded_at=D1,
                request=BuildPortfolioRequest(
                    available_amount=Decimal("1000"),
                    objective="crescimento", horizon="longo prazo",
                    risk_profile="moderado", max_percentage_per_asset=Decimal("100"),
                    max_percentage_per_class=Decimal("100"),
                    max_percentage_per_sector=Decimal("100"),
                ),
                candidates=[HistoricalCandidate(snapshot=snap, sector="Energia", issuer="EXEM")],
                realized_returns=[] if missing_return else [
                    AdjustedReturnInterval(
                        symbol="EXEM3", start_index=Decimal("100"), end_index=Decimal("110"),
                        start_observed_at=D1, end_observed_at=D2, source="Dados sintéticos",
                    )
                ],
                benchmark=BenchmarkInterval(
                    name="IBOV (exemplo)", start_index=Decimal("100"), end_index=Decimal("105"),
                    start_observed_at=D1, end_observed_at=D2, source="Dados sintéticos",
                ),
            )
        ],
    )
    return request.model_dump(mode="json")


def test_portfolio_walk_forward_api_is_serialized_and_labeled_as_unverified(client):
    response = client.post("/backtesting/portfolio-walk-forward", json=payload())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["validation_status"] == "simulation_only"
    assert result["ending_equity"] == "1100.00"
    assert result["benchmark_ending_equity"] == "1050.00"
    assert result["periods"][0]["selected_symbols"] == ["EXEM3"]
    assert result["limitations"]


def test_portfolio_walk_forward_api_rejects_missing_outcome_instead_of_zero_filling(client):
    response = client.post("/backtesting/portfolio-walk-forward", json=payload(missing_return=True))
    assert response.status_code == 400
    assert "retorno total ajustado ausente" in response.json()["detail"]


def test_portfolio_walk_forward_api_rejects_future_snapshot(client):
    doc = payload()
    doc["periods"][0]["candidates"][0]["snapshot"]["calculated_at"] = (D1 + timedelta(days=1)).isoformat()
    response = client.post("/backtesting/portfolio-walk-forward", json=doc)
    assert response.status_code == 400
    assert "look-ahead" in response.json()["detail"]
