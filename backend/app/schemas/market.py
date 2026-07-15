from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class MarketAssetResponse(BaseModel):
    ticker: str
    name: str | None = None
    asset_type: str | None = None
    sector: str | None = None
    country: str | None = None
    exchange: str | None = None
    currency: str | None = None
    current_price: Decimal | None = None
    last_updated: datetime | None = None
    provider: str


class QuoteResponse(BaseModel):
    ticker: str
    price: Decimal
    previous_close: Decimal | None = None
    change: Decimal | None = None
    change_percent: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    open: Decimal | None = None
    volume: int | None = None
    currency: str = "BRL"
    market_time: datetime | None = None
    source: str

    name: str | None = None
    asset_type: str | None = None
    sector: str | None = None
    country: str | None = None
    exchange: str | None = None
    current_price: Decimal | None = None
    last_updated: datetime | None = None
    provider: str | None = None
