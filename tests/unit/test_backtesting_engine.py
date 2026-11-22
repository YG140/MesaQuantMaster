from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.engines.backtesting_engine import (
    BacktestingEngine,
    BacktestingPrice,
    BacktestingSignal,
)


BASE_DATE = datetime(2026, 1, 1, 10, 0, 0)


def price(days: int, close: str) -> BacktestingPrice:
    return BacktestingPrice(
        timestamp=BASE_DATE + timedelta(days=days),
        close=Decimal(close),
    )


def signal(days: int, action: str) -> BacktestingSignal:
    return BacktestingSignal(
        timestamp=BASE_DATE + timedelta(days=days),
        signal=action,
    )


def run(
    historical_data: list[BacktestingPrice] | None = None,
    signals: list[BacktestingSignal] | None = None,
    initial_capital: str = "1000",
    fee_percent: str = "0",
    fixed_fee: str = "0",
    benchmark_data: list[BacktestingPrice] | None = None,
):
    if historical_data is None:
        historical_data = [price(0, "10"), price(1, "12"), price(2, "15")]

    return BacktestingEngine.run(
        initial_capital=Decimal(initial_capital),
        historical_data=historical_data,
        signals=signals,
        benchmark_data=benchmark_data,
        fee_percent=Decimal(fee_percent),
        fixed_fee=Decimal(fixed_fee),
    )


def test_empty_series_raises_error():
    with pytest.raises(ValueError, match="Serie historica nao pode ser vazia"):
        run(historical_data=[])


@pytest.mark.parametrize("capital", ["0", "-1"])
def test_initial_capital_must_be_positive(capital):
    with pytest.raises(ValueError, match="Capital inicial deve ser maior que zero"):
        run(initial_capital=capital)


def test_invalid_price_raises_error():
    with pytest.raises(ValueError, match="preco invalido"):
        run(historical_data=[price(0, "10"), price(1, "0")])


def test_out_of_order_dates_raise_error():
    with pytest.raises(ValueError, match="ordem cronologica"):
        run(historical_data=[price(1, "10"), price(0, "11")])


def test_duplicate_dates_raise_error():
    duplicate = BASE_DATE

    with pytest.raises(ValueError, match="datas duplicadas"):
        run(
            historical_data=[
                BacktestingPrice(timestamp=duplicate, close=Decimal("10")),
                BacktestingPrice(timestamp=duplicate, close=Decimal("11")),
            ]
        )


def test_no_trades_keeps_capital_and_builds_curve():
    result = run()

    assert result.final_equity == Decimal("1000.00")
    assert result.trades_count == 0
    assert result.open_position.is_open is False
    assert len(result.equity_curve) == 3


def test_buy_and_sell_with_profit_executes_after_signal_close():
    result = run(signals=[signal(0, "BUY"), signal(1, "SELL")])

    assert result.final_equity == Decimal("1250.00")
    assert result.trades_count == 1
    assert result.trades[0].entry_price == Decimal("12")
    assert result.trades[0].exit_price == Decimal("15")
    assert result.trades[0].net_profit == Decimal("250.00")
    assert result.winning_trades == 1
    assert result.losing_trades == 0


def test_buy_and_sell_with_loss():
    result = run(
        historical_data=[price(0, "10"), price(1, "8"), price(2, "7")],
        signals=[signal(0, "BUY"), signal(1, "SELL")],
    )

    assert result.final_equity == Decimal("875.00")
    assert result.trades[0].entry_price == Decimal("8")
    assert result.trades[0].exit_price == Decimal("7")
    assert result.trades[0].net_profit == Decimal("-125.00")
    assert result.winning_trades == 0
    assert result.losing_trades == 1


def test_fixed_fees_reduce_result():
    result = run(
        historical_data=[price(0, "10"), price(1, "20"), price(2, "20")],
        signals=[signal(0, "BUY"), signal(1, "SELL")],
        fixed_fee="10",
    )

    assert result.final_equity == Decimal("980.00")
    assert result.total_fees == Decimal("20.00")
    assert result.trades[0].fees == Decimal("20.00")


def test_percent_fees_reduce_result():
    result = run(
        historical_data=[price(0, "10"), price(1, "20"), price(2, "20")],
        signals=[signal(0, "BUY"), signal(1, "SELL")],
        fee_percent="1",
    )

    assert result.final_equity == Decimal("980.20")
    assert result.total_fees == Decimal("19.80")


def test_negative_costs_raise_error():
    with pytest.raises(ValueError, match="Custos nao podem ser negativos"):
        run(fixed_fee="-1")


def test_open_position_is_marked_to_market_at_end():
    result = run(signals=[signal(0, "BUY")])

    assert result.final_equity == Decimal("1250.00")
    assert result.trades_count == 0
    assert result.open_position.is_open is True
    assert result.open_position.market_value == Decimal("1250.00")


def test_duplicate_buy_while_in_position_is_ignored():
    result = run(
        historical_data=[price(0, "10"), price(1, "12"), price(2, "15"), price(3, "14")],
        signals=[signal(0, "BUY"), signal(1, "BUY"), signal(2, "SELL")],
    )

    assert result.trades_count == 1
    assert result.trades[0].entry_price == Decimal("12")
    assert result.trades[0].exit_price == Decimal("14")


def test_sell_without_position_is_ignored():
    result = run(
        historical_data=[price(0, "10"), price(1, "12"), price(2, "15"), price(3, "16")],
        signals=[signal(0, "SELL"), signal(1, "BUY"), signal(2, "SELL")],
    )

    assert result.trades_count == 1
    assert result.trades[0].entry_price == Decimal("15")
    assert result.trades[0].exit_price == Decimal("16")


def test_final_equity_is_cash_plus_open_position_value():
    result = run(
        historical_data=[price(0, "25"), price(1, "30"), price(2, "36")],
        signals=[signal(0, "BUY")],
    )

    assert result.final_equity == Decimal("1200.00")
    assert result.equity_curve[-1].equity == Decimal("1200.00")


def test_equity_curve_tracks_cash_position_value_and_equity():
    result = run(signals=[signal(0, "BUY"), signal(2, "SELL")])

    first = result.equity_curve[0]
    assert first.cash == Decimal("1000.00")
    assert first.position_value == Decimal("0.00")
    assert first.equity == Decimal("1000.00")
    second = result.equity_curve[1]
    assert second.cash == Decimal("0.00")
    assert second.position_value == Decimal("1000.00")


def test_max_drawdown_is_calculated():
    result = run(
        historical_data=[price(0, "10"), price(1, "10"), price(2, "5"), price(3, "15")],
        signals=[signal(0, "BUY"), signal(2, "SELL")],
    )

    assert result.max_drawdown_percent == Decimal("50.00")
    assert result.equity_curve[2].drawdown_percent == Decimal("50.00")


def test_win_rate_uses_closed_trades():
    result = run(
        historical_data=[
            price(0, "10"),
            price(1, "10"),
            price(2, "20"),
            price(3, "20"),
            price(4, "10"),
            price(5, "8"),
        ],
        signals=[
            signal(0, "BUY"),
            signal(2, "SELL"),
            signal(3, "BUY"),
            signal(4, "SELL"),
        ],
    )

    assert result.trades_count == 2
    assert result.winning_trades == 1
    assert result.losing_trades == 1
    assert result.win_rate_percent == Decimal("50.00")


def test_benchmark_buy_and_hold_uses_optional_series():
    result = run(
        benchmark_data=[price(0, "100"), price(1, "120"), price(2, "150")],
    )

    assert result.benchmark_return_percent == Decimal("50.00")


def test_excess_return_is_strategy_return_minus_benchmark():
    result = run(
        historical_data=[price(0, "10"), price(1, "12"), price(2, "15"), price(3, "15")],
        signals=[signal(0, "BUY"), signal(2, "SELL")],
        benchmark_data=[price(0, "100"), price(1, "110"), price(2, "125"), price(3, "125")],
    )

    assert result.total_return_percent == Decimal("25.00")
    assert result.benchmark_return_percent == Decimal("25.00")
    assert result.excess_return_percent == Decimal("0.00")


def test_momentum_strategy_generates_transition_signals():
    historical_data = [
        price(0, "10"),
        price(1, "11"),
        price(2, "12"),
        price(3, "9"),
    ]

    signals = BacktestingEngine.momentum_signals(
        historical_data=historical_data,
        moving_average_window=2,
    )

    assert [item.signal for item in signals] == ["HOLD", "BUY", "HOLD", "SELL"]


def test_signal_generated_at_close_executes_on_next_available_observation():
    result = run(
        historical_data=[price(0, "10"), price(1, "20"), price(2, "30")],
        signals=[signal(0, "BUY"), signal(1, "SELL")],
    )

    assert result.trades[0].entry_date == price(1, "20").timestamp
    assert result.trades[0].entry_price == Decimal("20")
    assert result.trades[0].exit_date == price(2, "30").timestamp
    assert result.trades[0].exit_price == Decimal("30")


def test_same_input_produces_deterministic_result():
    signals = [signal(0, "BUY"), signal(2, "SELL")]

    first = run(signals=signals)
    second = run(signals=signals)

    assert first == second
