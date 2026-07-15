from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssetBase(BaseModel):
    ticker: str = Field(..., max_length=20)
    name: str = Field(..., max_length=200)
    asset_type: str = Field(..., max_length=50)

    sector: str | None = None
    country: str | None = None
    currency: str = "BRL"
    exchange: str | None = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    ticker: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, max_length=200)
    asset_type: str | None = Field(default=None, max_length=50)

    sector: str | None = None
    country: str | None = None
    currency: str | None = None
    exchange: str | None = None
    is_active: bool | None = None


class AssetResponse(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool

    created_at: datetime
    updated_at: datetime
