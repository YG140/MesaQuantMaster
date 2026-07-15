from decimal import Decimal

from pydantic import BaseModel


class ConcentrationItem(BaseModel):
    ticker: str
    allocation: Decimal
    market_value: Decimal


class RiskAlert(BaseModel):
    ticker: str
    allocation: Decimal
    message: str


class RiskSummary(BaseModel):
    total_market_value: Decimal
    total_positions: int
    portfolio_is_empty: bool
    concentration: list[ConcentrationItem]
    alerts: list[RiskAlert]
