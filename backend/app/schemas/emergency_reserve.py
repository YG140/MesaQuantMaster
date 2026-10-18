"""Preview da reserva de emergência: sem criação de operações ou custódia."""
from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class EmergencyReservePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    essential_monthly_expenses: Decimal = Field(gt=0, le=Decimal("1000000000"))
    current_reserve: Decimal = Field(ge=0, le=Decimal("100000000000"))
    monthly_available: Decimal = Field(ge=0, le=Decimal("1000000000"))


class ReserveBucket(BaseModel):
    label: str
    target_amount: Decimal
    suggested_months: int
    description: str


class EmergencyReservePlanResponse(BaseModel):
    status: str
    basis: str
    essential_monthly_expenses: Decimal
    target_months: int
    target_amount: Decimal
    current_reserve: Decimal
    months_covered: Decimal
    progress_percentage: Decimal
    shortfall: Decimal
    monthly_available: Decimal
    suggested_next_reserve_contribution: Decimal
    remaining_next_contribution: Decimal
    estimated_months_to_goal: int | None = None
    allocation_targets: list[ReserveBucket]
    has_relevant_debt: bool
    warnings: list[str]
