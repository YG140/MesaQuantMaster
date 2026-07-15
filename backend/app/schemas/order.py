from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    asset_id: UUID

    operation: str = Field(
        ...,
        examples=["BUY", "SELL"],
    )

    quantity: Decimal

    unit_price: Decimal

    fees: Decimal = Decimal("0")

    taxes: Decimal = Decimal("0")


class OrderResponse(BaseModel):
    success: bool

    message: str

    operation_id: UUID | None = None
