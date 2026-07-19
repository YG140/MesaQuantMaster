from datetime import date
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PortfolioPosition(BaseModel):
    asset_id: UUID

    ticker: str

    asset_name: str

    asset_type: str | None = None

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

    valuation_basis: str | None = None

    valuation_status: str = "unpriced"

    quote_updated_at: datetime | None = None


class PortfolioSummary(BaseModel):
    total_invested: Decimal

    total_market_value: Decimal

    total_profit: Decimal

    # NOVOS CAMPOS

    profitability: Decimal = Decimal("0")

    allocation: list[dict] = Field(default_factory=list)

    valuation_basis: str | None = None

    market_data_status: str = "unavailable"

    quote_updated_at: datetime | None = None

    unpriced_symbols: list[str] = Field(default_factory=list)

    positions: list[PortfolioPosition]


class InvestmentCreate(BaseModel):
    brokerage_id: UUID
    ticker: str = Field(..., max_length=20)
    name: str = Field(..., max_length=200)
    asset_type: str = Field(..., max_length=50)
    operation_date: date
    quantity: Decimal
    unit_price: Decimal
    fees: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")
    notes: str | None = None


class InvestmentCreateResponse(BaseModel):
    asset_id: UUID
    operation_id: UUID
    brokerage_id: UUID
    asset_created: bool


class InitialPortfolioImportItem(BaseModel):
    ticker: str = Field(..., max_length=20)
    name: str | None = Field(default=None, max_length=200)
    asset_type: str = Field(default="STOCK", max_length=50)
    quantity: Decimal
    average_price: Decimal
    reference_date: date | None = None
    notes: str | None = None


class InitialPortfolioImport(BaseModel):
    brokerage_id: UUID
    positions: list[InitialPortfolioImportItem]


class InitialPortfolioImportResponse(BaseModel):
    assets_created: int
    assets_reused: int
    operations_created: int
    brokerage_id: UUID
