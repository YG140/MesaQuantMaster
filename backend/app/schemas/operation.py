from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OperationBase(BaseModel):
    asset_id: UUID
    brokerage_id: UUID | None = None

    operation_type: str = Field(..., max_length=30)

    operation_date: date

    quantity: Decimal
    unit_price: Decimal

    fees: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")

    notes: str | None = None
    source: str | None = None


class OperationCreate(OperationBase):
    pass


class OperationUpdate(BaseModel):
    operation_type: str | None = Field(default=None, max_length=30)

    operation_date: date | None = None

    quantity: Decimal | None = None
    unit_price: Decimal | None = None

    fees: Decimal | None = None
    taxes: Decimal | None = None

    notes: str | None = None
    source: str | None = None


class OperationResponse(OperationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID

    created_at: datetime
    updated_at: datetime
