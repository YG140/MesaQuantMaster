from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class OrderSimulationRequest(BaseModel):
    asset_id: UUID

    operation: str = Field(..., examples=["BUY", "SELL"])

    quantity: Decimal

    unit_price: Decimal

    fees: Decimal = Decimal("0")

    taxes: Decimal = Decimal("0")


class OrderSimulationResponse(BaseModel):
    ticker: str

    operation: str

    gross_value: Decimal

    fees: Decimal

    taxes: Decimal

    total_value: Decimal

    current_quantity: Decimal

    new_quantity: Decimal

    current_average_price: Decimal

    new_average_price: Decimal

    warning: str | None = None
