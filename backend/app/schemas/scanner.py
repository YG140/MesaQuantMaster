from decimal import Decimal

from pydantic import BaseModel


class PriceCheckRequest(BaseModel):
    ticker: str
    target_price: Decimal


class PriceCheckResponse(BaseModel):
    ticker: str
    target_price: Decimal
    triggered: bool


class PortfolioAnalysisResponse(BaseModel):
    total_invested: Decimal
    total_market_value: Decimal
    positions: list
    concentration: list
