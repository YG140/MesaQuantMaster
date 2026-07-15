from __future__ import annotations

from app.engines.backtesting_engine import (
    BacktestingEngine,
    BacktestingPrice,
    BacktestingSignal,
)
from app.schemas.backtesting import BacktestingRequest, BacktestingResult


class BacktestingService:
    def run(self, request: BacktestingRequest) -> BacktestingResult:
        historical_data = [
            BacktestingPrice(
                timestamp=point.timestamp,
                close=point.close,
            )
            for point in request.historical_data
        ]
        benchmark_data = (
            [
                BacktestingPrice(
                    timestamp=point.timestamp,
                    close=point.close,
                )
                for point in request.benchmark_data
            ]
            if request.benchmark_data is not None
            else None
        )

        signals = self._resolve_signals(request, historical_data)

        return BacktestingEngine.run(
            initial_capital=request.initial_capital,
            historical_data=historical_data,
            signals=signals,
            benchmark_data=benchmark_data,
            fee_percent=request.fee_percent,
            fixed_fee=request.fixed_fee,
        )

    @staticmethod
    def _resolve_signals(
        request: BacktestingRequest,
        historical_data: list[BacktestingPrice],
    ) -> list[BacktestingSignal]:
        if request.signals is not None and request.strategy is not None:
            raise ValueError("Informe sinais ou estrategia, nao ambos.")

        if request.strategy is not None:
            strategy_name = request.strategy.name.lower()
            if strategy_name != "momentum":
                raise ValueError("Estrategia nao suportada.")
            return BacktestingEngine.momentum_signals(
                historical_data=historical_data,
                moving_average_window=request.strategy.moving_average_window,
            )

        if request.signals is None:
            return []

        return [
            BacktestingSignal(
                timestamp=signal.timestamp,
                signal=signal.signal,
            )
            for signal in request.signals
        ]
