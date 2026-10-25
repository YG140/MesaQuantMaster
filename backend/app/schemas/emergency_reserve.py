"""Preview da reserva de emergência: sem criação de operações ou custódia."""
from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class EmergencyReservePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    essential_monthly_expenses: Decimal = Field(gt=0, le=Decimal("1000000000"))
    current_reserve: Decimal = Field(ge=0, le=Decimal("100000000000"))
    monthly_available: Decimal = Field(ge=0, le=Decimal("1000000000"))
    income_unstable: bool = False


class ReserveBucket(BaseModel):
    label: str
    target_amount: Decimal
    suggested_months: int
    description: str


class ReserveAssetAllocation(BaseModel):
    """Alocação em reais por tipo de instrumento, nunca ordem de compra.

    Os produtos individuais/emissores não foram consultados nem verificados.
    """
    asset_type: str
    suggested_asset: str
    target_amount: Decimal
    next_contribution_amount: Decimal
    rationale: str
    selection_status: str = "categoria_sem_produto_validado"
    liquidity_warning: str


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
    asset_allocations: list[ReserveAssetAllocation] = Field(default_factory=list)
    has_relevant_debt: bool
    warnings: list[str]
