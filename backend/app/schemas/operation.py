from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OperationBase(BaseModel):
    asset_id: UUID
    brokerage_id: UUID | None = None

    operation_type: str = Field(..., max_length=30)

    operation_date: date

    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)

    fees: Decimal = Field(default=Decimal("0"), ge=0)
    taxes: Decimal = Field(default=Decimal("0"), ge=0)

    notes: str | None = None
    source: str | None = None


class OperationCreate(OperationBase):
    pass


class OperationUpdate(BaseModel):
    brokerage_id: UUID | None = None
    operation_type: str | None = Field(default=None, max_length=30)

    operation_date: date | None = None

    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, gt=0)

    fees: Decimal | None = Field(default=None, ge=0)
    taxes: Decimal | None = Field(default=None, ge=0)

    notes: str | None = None
    source: str | None = None


class OperationResponse(OperationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID

    created_at: datetime
    updated_at: datetime
