from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PortfolioPosition(BaseModel):
    asset_id: UUID

    ticker: str

    asset_name: str

    quantity: Decimal

    average_price: Decimal

    invested_amount: Decimal

    current_price: Decimal | None = None

    market_value: Decimal | None = None

    unrealized_profit: Decimal | None = None

    unrealized_profit_percent: Decimal | None = None

    # NOVOS CAMPOS

    allocation: Decimal | None = None

    weight: Decimal | None = None


class PortfolioSummary(BaseModel):
    total_invested: Decimal

    total_market_value: Decimal

    total_profit: Decimal

    # NOVOS CAMPOS

    profitability: Decimal = Decimal("0")

    allocation: list[dict] = Field(default_factory=list)

    positions: list[PortfolioPosition]
