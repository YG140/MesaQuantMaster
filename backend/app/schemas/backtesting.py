from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SignalAction = Literal["BUY", "SELL", "HOLD"]


class BacktestingPricePoint(BaseModel):
    timestamp: datetime
    close: Decimal = Field(gt=0)


class BacktestingSignalPoint(BaseModel):
    timestamp: datetime
    signal: SignalAction


class BacktestingStrategyConfig(BaseModel):
    name: str
    moving_average_window: int = Field(default=200, gt=0)


class BacktestingRequest(BaseModel):
    initial_capital: Decimal = Field(gt=0)
    historical_data: list[BacktestingPricePoint] = Field(min_length=1)
    signals: list[BacktestingSignalPoint] | None = None
    strategy: BacktestingStrategyConfig | None = None
    benchmark_data: list[BacktestingPricePoint] | None = None
    fee_percent: Decimal = Field(default=Decimal("0"), ge=0)
    fixed_fee: Decimal = Field(default=Decimal("0"), ge=0)


class EquityCurvePoint(BaseModel):
    timestamp: datetime
    cash: Decimal
    position_value: Decimal
    equity: Decimal
    drawdown_percent: Decimal


class BacktestingTrade(BaseModel):
    entry_date: datetime
    entry_price: Decimal
    exit_date: datetime
    exit_price: Decimal
    quantity: Decimal
    gross_profit: Decimal
    fees: Decimal
    net_profit: Decimal
    return_percent: Decimal


class BacktestingOpenPosition(BaseModel):
    is_open: bool
    entry_date: datetime | None = None
    entry_price: Decimal | None = None
    quantity: Decimal = Decimal("0")
    market_price: Decimal | None = None
    market_value: Decimal = Decimal("0")
    unrealized_profit: Decimal = Decimal("0")
    unrealized_return_percent: Decimal = Decimal("0")


class BacktestingResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    initial_capital: Decimal
    final_equity: Decimal
    total_return_percent: Decimal
    benchmark_return_percent: Decimal
    excess_return_percent: Decimal
    max_drawdown_percent: Decimal
    total_fees: Decimal
    trades_count: int
    winning_trades: int
    losing_trades: int
    win_rate_percent: Decimal
    open_position: BacktestingOpenPosition
    equity_curve: list[EquityCurvePoint]
    trades: list[BacktestingTrade]
