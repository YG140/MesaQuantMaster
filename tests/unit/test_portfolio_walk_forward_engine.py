"""Testes determinísticos do backtest de carteiras com dados SINTÉTICOS.

Todos os índices, sinais e empresas aqui são fictícios.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.engines.portfolio_walk_forward_engine import PortfolioWalkForwardEngine
from app.schemas.intelligence import BuildPortfolioRequest
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot, ConfidenceLevel, IndicatorStatus, InvestmentClass,
    NormalizedIndicator, RecommendationAction, ValuationAssessment, ValuationStatus,
)
from app.schemas.portfolio_validation import (
    AdjustedReturnInterval, BenchmarkInterval, HistoricalCandidate,
    WalkForwardPeriod, WalkForwardRequest,
)

D1 = datetime(2026, 1, 5, 19, tzinfo=timezone.utc)
D2 = datetime(2026, 2, 5, 19, tzinfo=timezone.utc)
D3 = datetime(2026, 3, 5, 19, tzinfo=timezone.utc)


def profile():
    return BuildPortfolioRequest(
        available_amount=Decimal("1000"),
        objective="crescimento",
        horizon="longo prazo",
        risk_profile="moderado",
        max_percentage_per_asset=Decimal("100"),
        max_percentage_per_class=Decimal("100"),
        max_percentage_per_sector=Decimal("100"),
        max_assets=10,
    )


def snapshot(when=D1, *, symbol="EXEM3", price="10", signal=RecommendationAction.ANALYZE_TO_BUY):
    indicator = NormalizedIndicator(
        key="price_earnings",
        label="P/L",
        value=Decimal("8"),
        unit="ratio",
        status=IndicatorStatus.AVAILABLE,
        source="CVM (exemplo sintético)",
        source_type="official",
        reference_date=when - timedelta(days=10),
        collected_at=when,
        valid_until=when + timedelta(days=60),
        confidence=ConfidenceLevel.HIGH,
    )
    return AssetIntelligenceSnapshot(
        symbol=symbol,
        name="Exemplo sintético",
        asset_class=InvestmentClass.STOCK,
        currency="BRL",
        current_price=Decimal(price),
        market_updated_at=when,
        indicators=[indicator],
        quality_score=Decimal("80"),
        valuation_score=Decimal("82"),
        overall_score=Decimal("81"),
        recommendation=signal,
        valuation_status=ValuationStatus.ATTRACTIVE,
        valuation=ValuationAssessment(
            status=ValuationStatus.ATTRACTIVE,
            confidence=ConfidenceLevel.MEDIUM,
            methods=["Faixa de múltiplos comparáveis de teste"],
            estimated_range_low=Decimal("15"),
            estimated_range_high=Decimal("18"),
            data_date=when,
        ),
        confidence=ConfidenceLevel.HIGH,
        coverage_percentage=Decimal("90"),
        available_indicators_count=1,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=when,
    )


def period(start=D1, end=D2, *, start_index="100", end_index="110",
           bench_start="100", bench_end="105", signal=RecommendationAction.ANALYZE_TO_BUY,
           missing_return=False):
    return WalkForwardPeriod(
        decision_at=start,
        evaluation_at=end,
        profile_recorded_at=start,
        request=profile(),
        candidates=[HistoricalCandidate(snapshot=snapshot(start, signal=signal), sector="Energia", issuer="EXEM")],
        realized_returns=(
            [] if missing_return else [
                AdjustedReturnInterval(
                    symbol="EXEM3",
                    start_index=Decimal(start_index),
                    end_index=Decimal(end_index),
                    start_observed_at=start,
                    end_observed_at=end,
                    source="Índice ajustado sintético",
                )
            ]
        ),
        benchmark=BenchmarkInterval(
            name="IBOV (exemplo)",
            start_index=Decimal(bench_start),
            end_index=Decimal(bench_end),
            start_observed_at=start,
            end_observed_at=end,
            source="Índice sintético",
        ),
    )


def run(periods=None, *, fee_bps="0"):
    return PortfolioWalkForwardEngine.run(
        WalkForwardRequest(
            initial_capital=Decimal("1000"),
            fee_bps=Decimal(fee_bps),
            periods=periods if periods is not None else [period()],
        )
    )


def test_historical_selection_is_applied_before_future_returns_and_compared_with_benchmark():
    result = run()
    assert result.validation_status == "simulation_only"
    assert result.periods[0].selected_symbols == ["EXEM3"]
    assert result.ending_equity == Decimal("1100.00")
    assert result.benchmark_ending_equity == Decimal("1050.00")
    assert result.net_return_percent == Decimal("10.00")
    assert result.excess_return_percentage_points == Decimal("5.00")
    assert result.maximum_sampled_drawdown_percent == Decimal("0.00")


def test_two_contiguous_rebalances_compound_correctly():
    result = run([
        period(), period(D2, D3, start_index="110", end_index="121", bench_start="105", bench_end="110.25")
    ])
    assert result.ending_equity == Decimal("1210.00")
    assert result.benchmark_ending_equity == Decimal("1102.50")
    assert result.periods_count == 2
    assert result.periods[1].turnover_percentage == Decimal("0.00")


def test_transaction_costs_change_net_result_and_not_benchmark():
    result = run(fee_bps="100")
    assert result.total_fees == Decimal("10.00")
    assert result.ending_equity == Decimal("1089.00")
    assert result.benchmark_ending_equity == Decimal("1050.00")
    assert result.periods[0].turnover_percentage == Decimal("100.00")


def test_losses_create_sampled_drawdown_not_fabricated_win():
    result = run([period(end_index="90", bench_end="95")])
    assert result.ending_equity == Decimal("900.00")
    assert result.maximum_sampled_drawdown_percent == Decimal("10.00")
    assert result.positive_periods == 0


def test_no_buy_signal_keeps_cash_and_does_not_fake_performance():
    result = run([period(signal=RecommendationAction.HOLD, missing_return=True)])
    assert result.periods[0].selected_symbols == []
    assert result.ending_equity == Decimal("1000.00")
    assert result.periods[0].cash_percentage == Decimal("100.00")
    assert result.benchmark_ending_equity == Decimal("1050.00")


def test_missing_realized_return_for_selected_stock_fails_closed():
    with pytest.raises(ValueError, match="retorno total ajustado ausente"):
        run([period(missing_return=True)])


def test_future_indicator_collection_makes_simulation_invalid():
    p = period()
    s = p.candidates[0].snapshot
    indicator = s.indicators[0].model_copy(update={"collected_at": D1 + timedelta(days=1)})
    p.candidates[0].snapshot = s.model_copy(update={"indicators": [indicator]})
    with pytest.raises(ValueError, match="look-ahead"):
        run([p])


def test_later_published_report_is_not_available_as_of_decision():
    p = period()
    s = p.candidates[0].snapshot
    indicator = s.indicators[0].model_copy(update={"reference_date": D1 + timedelta(days=2)})
    p.candidates[0].snapshot = s.model_copy(update={"indicators": [indicator]})
    with pytest.raises(ValueError, match="look-ahead"):
        run([p])


def test_future_profile_and_future_price_are_rejected():
    p = period()
    p.profile_recorded_at = D1 + timedelta(seconds=1)
    with pytest.raises(ValueError, match="look-ahead"):
        run([p])
    p = period()
    p.candidates[0].snapshot = p.candidates[0].snapshot.model_copy(
        update={"market_updated_at": D1 + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="cotação posterior"):
        run([p])


def test_future_backtest_period_is_not_accepted():
    p = period(start=D1, end=datetime(2030, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="passado"):
        run([p])


def test_noncontiguous_periods_and_incompatible_benchmark_are_rejected():
    late = period(D2 + timedelta(days=1), D3)
    with pytest.raises(ValueError, match="contíguos"):
        run([period(), late])
    late = period(D2, D3, bench_start="106")
    with pytest.raises(ValueError, match="contínuos"):
        run([period(), late])


def test_same_period_is_deterministic_with_exact_decimal_arithmetic():
    original = run([period()], fee_bps="15")
    repeated = run([period()], fee_bps="15")
    assert original.model_dump() == repeated.model_dump()


def test_duplicate_candidate_symbol_is_rejected():
    p = period()
    p.candidates.append(p.candidates[0].model_copy(deep=True))
    with pytest.raises(ValueError, match="duplicado"):
        run([p])


def test_prices_without_observation_timezone_are_rejected():
    p = period()
    p.realized_returns[0].end_observed_at = D2.replace(tzinfo=None)
    with pytest.raises(ValueError, match="fuso horário"):
        run([p])
