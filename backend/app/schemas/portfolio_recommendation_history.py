"""User-scoped, read-only views of saved portfolio recommendation decisions."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class RecommendationHistorySummary(BaseModel):
    id: UUID
    generated_at: datetime
    created_at: datetime
    engine_version: str
    status: str
    selected_count: int
    considered_count: int
    content_sha256: str


class RecommendationHistoryDetail(RecommendationHistorySummary):
    record: dict[str, Any]
    integrity_verified: bool = True


class RecommendationPriceObservation(BaseModel):
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    price_change_percent: Decimal


class RecommendationPerformanceResponse(BaseModel):
    """Avaliação de preço SEM proventos; nunca confundir com lucro real."""

    run_id: UUID
    generated_at: datetime
    horizon_months: int
    status: str  # pending | unavailable | price_only
    benchmark_symbol: str = "BOVA11"
    benchmark_description: str = "Preço BOVA11 (proxy, não Ibovespa de retorno total)"
    entry_date: date | None = None
    observation_date: date | None = None
    analyzed_assets: int = 0
    observed_initial_notional: Decimal | None = None
    portfolio_price_change_percent: Decimal | None = None
    benchmark_price_change_percent: Decimal | None = None
    price_difference_percentage_points: Decimal | None = None
    dividends_status: str = "not_verified"
    costs_and_taxes_status: str = "not_verified"
    realized_profit_status: str = "not_calculated"
    total_return_status: str = "not_calculated"
    observations: list[RecommendationPriceObservation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
