from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.engines.strategy_engine import StrategyEngine
from app.schemas.backtesting import (
    BacktestingOpenPosition,
    BacktestingResult,
    BacktestingTrade,
    EquityCurvePoint,
    SignalAction,
)

PERCENT = Decimal("100")
MONEY = Decimal("0.01")


@dataclass(frozen=True)
class BacktestingPrice:
    timestamp: datetime
    close: Decimal


@dataclass(frozen=True)
class BacktestingSignal:
    timestamp: datetime
    signal: SignalAction


@dataclass
class OpenTrade:
    entry_date: datetime
    entry_price: Decimal
    quantity: Decimal
    entry_notional: Decimal
    entry_fee: Decimal


class BacktestingEngine:
    """
    Engine puro para simular backtests long-only de um unico ativo.

    A posicao aberta no encerramento e marcada a mercado no ultimo preco e nao
    entra na lista de trades fechados nem no calculo de taxa de acerto.
    """

    @classmethod
    def run(
        cls,
        initial_capital: Decimal,
        historical_data: list[BacktestingPrice],
        signals: list[BacktestingSignal] | None = None,
        benchmark_data: list[BacktestingPrice] | None = None,
        fee_percent: Decimal = Decimal("0"),
        fixed_fee: Decimal = Decimal("0"),
    ) -> BacktestingResult:
        cls._validate_inputs(
            initial_capital=initial_capital,
            historical_data=historical_data,
            benchmark_data=benchmark_data,
            fee_percent=fee_percent,
            fixed_fee=fixed_fee,
        )
        signal_by_timestamp = cls._build_signal_map(signals or [], historical_data)

        cash = initial_capital
        quantity = Decimal("0")
        total_fees = Decimal("0")
        open_trade: OpenTrade | None = None
        trades: list[BacktestingTrade] = []
        equity_curve: list[EquityCurvePoint] = []
        peak_equity = initial_capital
        max_drawdown = Decimal("0")

        for point in historical_data:
            signal = signal_by_timestamp.get(point.timestamp, "HOLD")

            if signal == "BUY" and quantity == 0:
                fee_multiplier = Decimal("1") + (fee_percent / PERCENT)
                investable_cash = cash - fixed_fee
                if investable_cash > 0:
                    entry_notional = investable_cash / fee_multiplier
                    entry_fee = cls._calculate_fee(
                        notional=entry_notional,
                        fee_percent=fee_percent,
                        fixed_fee=fixed_fee,
                    )
                    quantity = entry_notional / point.close
                    cash -= entry_notional + entry_fee
                    total_fees += entry_fee
                    open_trade = OpenTrade(
                        entry_date=point.timestamp,
                        entry_price=point.close,
                        quantity=quantity,
                        entry_notional=entry_notional,
                        entry_fee=entry_fee,
                    )
            elif signal == "SELL" and quantity > 0 and open_trade is not None:
                exit_notional = quantity * point.close
                exit_fee = cls._calculate_fee(
                    notional=exit_notional,
                    fee_percent=fee_percent,
                    fixed_fee=fixed_fee,
                )
                gross_profit = exit_notional - open_trade.entry_notional
                fees = open_trade.entry_fee + exit_fee
                net_profit = gross_profit - fees
                cash += exit_notional - exit_fee
                total_fees += exit_fee
                trades.append(
                    BacktestingTrade(
                        entry_date=open_trade.entry_date,
                        entry_price=open_trade.entry_price,
                        exit_date=point.timestamp,
                        exit_price=point.close,
                        quantity=quantity,
                        gross_profit=cls._money(gross_profit),
                        fees=cls._money(fees),
                        net_profit=cls._money(net_profit),
                        return_percent=cls._percent(
                            net_profit,
                            open_trade.entry_notional + open_trade.entry_fee,
                        ),
                    )
                )
                quantity = Decimal("0")
                open_trade = None

            equity = cash + (quantity * point.close)
            peak_equity = max(peak_equity, equity)
            drawdown = cls._percent(peak_equity - equity, peak_equity)
            max_drawdown = max(max_drawdown, drawdown)
            equity_curve.append(
                EquityCurvePoint(
                    timestamp=point.timestamp,
                    cash=cls._money(cash),
                    position_value=cls._money(quantity * point.close),
                    equity=cls._money(equity),
                    drawdown_percent=drawdown,
                )
            )

        last_point = historical_data[-1]
        final_equity = cash + (quantity * last_point.close)
        benchmark_return = cls._benchmark_return(benchmark_data or historical_data)
        total_return = cls._percent(final_equity - initial_capital, initial_capital)
        winning_trades = len([trade for trade in trades if trade.net_profit > 0])
        losing_trades = len([trade for trade in trades if trade.net_profit < 0])

        return BacktestingResult(
            initial_capital=cls._money(initial_capital),
            final_equity=cls._money(final_equity),
            total_return_percent=total_return,
            benchmark_return_percent=benchmark_return,
            excess_return_percent=total_return - benchmark_return,
            max_drawdown_percent=max_drawdown,
            total_fees=cls._money(total_fees),
            trades_count=len(trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_percent=cls._win_rate(winning_trades, len(trades)),
            open_position=cls._open_position(open_trade, last_point),
            equity_curve=equity_curve,
            trades=trades,
        )

    @classmethod
    def momentum_signals(
        cls,
        historical_data: list[BacktestingPrice],
        moving_average_window: int,
    ) -> list[BacktestingSignal]:
        if moving_average_window <= 0:
            raise ValueError("Janela de media movel deve ser maior que zero.")

        signals: list[BacktestingSignal] = []
        previous_approved = False

        for index, point in enumerate(historical_data):
            if index + 1 < moving_average_window:
                signals.append(BacktestingSignal(point.timestamp, "HOLD"))
                continue

            window = historical_data[index + 1 - moving_average_window : index + 1]
            moving_average = sum(
                (item.close for item in window),
                Decimal("0"),
            ) / Decimal(len(window))
            approved = StrategyEngine.momentum(
                current_price=point.close,
                moving_average_200=moving_average,
            )

            if approved and not previous_approved:
                signal: SignalAction = "BUY"
            elif not approved and previous_approved:
                signal = "SELL"
            else:
                signal = "HOLD"

            signals.append(BacktestingSignal(point.timestamp, signal))
            previous_approved = approved

        return signals

    @classmethod
    def _validate_inputs(
        cls,
        initial_capital: Decimal,
        historical_data: list[BacktestingPrice],
        benchmark_data: list[BacktestingPrice] | None,
        fee_percent: Decimal,
        fixed_fee: Decimal,
    ) -> None:
        if initial_capital <= 0:
            raise ValueError("Capital inicial deve ser maior que zero.")
        if not historical_data:
            raise ValueError("Serie historica nao pode ser vazia.")
        if fee_percent < 0 or fixed_fee < 0:
            raise ValueError("Custos nao podem ser negativos.")

        cls._validate_price_series(historical_data, "Serie historica")

        if benchmark_data is not None:
            cls._validate_price_series(benchmark_data, "Benchmark")
            if (
                benchmark_data[0].timestamp != historical_data[0].timestamp
                or benchmark_data[-1].timestamp != historical_data[-1].timestamp
            ):
                raise ValueError(
                    "Benchmark deve estar alinhado ao inicio e fim da serie historica."
                )

    @staticmethod
    def _validate_price_series(
        series: list[BacktestingPrice],
        label: str,
    ) -> None:
        seen_timestamps: set[datetime] = set()
        previous_timestamp: datetime | None = None

        for point in series:
            if point.close <= 0:
                raise ValueError(f"{label} contem preco invalido.")
            if point.timestamp in seen_timestamps:
                raise ValueError(f"{label} contem datas duplicadas.")
            if previous_timestamp is not None and point.timestamp < previous_timestamp:
                raise ValueError(f"{label} deve estar em ordem cronologica.")

            seen_timestamps.add(point.timestamp)
            previous_timestamp = point.timestamp

    @staticmethod
    def _build_signal_map(
        signals: list[BacktestingSignal],
        historical_data: list[BacktestingPrice],
    ) -> dict[datetime, SignalAction]:
        valid_timestamps = {point.timestamp for point in historical_data}
        signal_by_timestamp: dict[datetime, SignalAction] = {}

        for signal in signals:
            if signal.timestamp not in valid_timestamps:
                raise ValueError("Sinal informado fora da serie historica.")
            if signal.timestamp in signal_by_timestamp:
                raise ValueError("Sinais contem datas duplicadas.")
            signal_by_timestamp[signal.timestamp] = signal.signal

        return signal_by_timestamp

    @staticmethod
    def _calculate_fee(
        notional: Decimal,
        fee_percent: Decimal,
        fixed_fee: Decimal,
    ) -> Decimal:
        return notional * (fee_percent / PERCENT) + fixed_fee

    @classmethod
    def _benchmark_return(cls, benchmark_data: list[BacktestingPrice]) -> Decimal:
        first_price = benchmark_data[0].close
        last_price = benchmark_data[-1].close
        return cls._percent(last_price - first_price, first_price)

    @staticmethod
    def _percent(value: Decimal, base: Decimal) -> Decimal:
        if base == 0:
            return Decimal("0.00")
        return ((value / base) * PERCENT).quantize(MONEY)

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(MONEY)

    @classmethod
    def _win_rate(cls, winning_trades: int, trades_count: int) -> Decimal:
        if trades_count == 0:
            return Decimal("0.00")
        return cls._percent(Decimal(winning_trades), Decimal(trades_count))

    @classmethod
    def _open_position(
        cls,
        open_trade: OpenTrade | None,
        last_point: BacktestingPrice,
    ) -> BacktestingOpenPosition:
        if open_trade is None:
            return BacktestingOpenPosition(is_open=False)

        market_value = open_trade.quantity * last_point.close
        unrealized_profit = (
            market_value - open_trade.entry_notional - open_trade.entry_fee
        )

        return BacktestingOpenPosition(
            is_open=True,
            entry_date=open_trade.entry_date,
            entry_price=open_trade.entry_price,
            quantity=open_trade.quantity,
            market_price=last_point.close,
            market_value=cls._money(market_value),
            unrealized_profit=cls._money(unrealized_profit),
            unrealized_return_percent=cls._percent(
                unrealized_profit,
                open_trade.entry_notional + open_trade.entry_fee,
            ),
        )
