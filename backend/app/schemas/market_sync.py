from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class MarketSyncRequest(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=50)
    max_assets: int = Field(default=20, ge=1, le=50)
    max_calls: int = Field(default=1, ge=1, le=10)
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    offline: bool = False


class MarketSyncSnapshot(BaseModel):
    symbol: str
    asset_class: str
    indicator_key: str
    value: Decimal
    unit: str
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    provider: str
    source_type: str
    reference_date: datetime
    collected_at: datetime
    valid_until: datetime

    @field_validator("reference_date", "collected_at", "valid_until")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps devem possuir timezone")
        return value

    @model_validator(mode="after")
    def validity_must_follow_collection(self):
        if self.valid_until <= self.collected_at:
            raise ValueError("valid_until deve ser posterior a collected_at")
        return self


class MarketSyncReport(BaseModel):
    dry_run: bool
    requested: int
    processed: int
    calls_used: int
    snapshots_ready: int
    snapshots_written: int
    unavailable_symbols: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    snapshots: list[MarketSyncSnapshot] = Field(default_factory=list)
