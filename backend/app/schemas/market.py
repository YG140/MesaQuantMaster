from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MarketAssetResponse(BaseModel):
    ticker: str
    symbol: str | None = None
    name: str | None = None
    long_name: str | None = None
    asset_type: str | None = None
    asset_subtype: str | None = None
    sector: str | None = None
    subsector: str | None = None
    country: str | None = None
    exchange: str | None = None
    currency: str | None = None
    logo_url: str | None = None
    current_price: Decimal | None = None
    change_value: Decimal | None = None
    change_percent: Decimal | None = None
    last_updated: datetime | None = None
    updated_at: datetime | None = None
    provider: str
    cache_hit: bool = False
    limited_mode: bool = False


class QuoteResponse(BaseModel):
    ticker: str
    symbol: str | None = None
    requested_symbol: str | None = None
    symbol_changed: bool = False
    price: Decimal | None = None
    current_price: Decimal | None = None
    previous_close: Decimal | None = None
    change: Decimal | None = None
    change_value: Decimal | None = None
    change_percent: Decimal | None = None
    high: Decimal | None = None
    day_high: Decimal | None = None
    low: Decimal | None = None
    day_low: Decimal | None = None
    open: Decimal | None = None
    open_price: Decimal | None = None
    volume: int | None = None
    market_cap: Decimal | None = None
    currency: str | None = None
    market_time: datetime | None = None
    source: str
    logo_url: str | None = None

    name: str | None = None
    asset_type: str | None = None
    asset_subtype: str | None = None
    sector: str | None = None
    subsector: str | None = None
    country: str | None = None
    exchange: str | None = None
    last_updated: datetime | None = None
    updated_at: datetime | None = None
    provider: str | None = None
    cache_hit: bool = False
    limited_mode: bool = False


class MarketProfileResponse(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    website: str | None = None
    description: str | None = None
    cnpj: str | None = None
    logo_url: str | None = None
    provider: str
    cache_hit: bool = False
    limited_mode: bool = False


class QuotesRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=50)


class QuotesResponse(BaseModel):
    quotes: list[QuoteResponse]
    provider: str = "BRAPI"
    cache_hit: bool = False
    limited_mode: bool = False
    unavailable_symbols: list[str] = Field(default_factory=list)


class ProviderCapabilitiesResponse(BaseModel):
    provider: str
    configured: bool
    reachable: bool | None
    supported_domains: list[str]
    accessible_domains: list[str]
    restricted_domains: list[str]
    last_checked_at: datetime
