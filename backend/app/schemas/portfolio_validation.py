"""Contratos de validação histórica de carteiras com snapshots point-in-time.

Não autentica nem certifica provedores informados no corpo da requisição.
O resultado é uma simulação e NÃO comprovação de retorno real.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.intelligence import BuildPortfolioRequest
from app.schemas.market_intelligence import AssetIntelligenceSnapshot


class HistoricalCandidate(BaseModel):
    snapshot: AssetIntelligenceSnapshot
    sector: str | None = None
    issuer: str | None = None
    market_context: str = "B3"


class AdjustedReturnInterval(BaseModel):
    """Índice de retorno total ajustado: inclui proventos e eventos societários.

    end_observed_at é posterior à avaliação; nunca é insumo do ranking.
    As fontes são declaradas pelo solicitante, NÃO certificadas pelo servidor.
    """
    symbol: str = Field(min_length=1, max_length=32)
    start_index: Decimal = Field(gt=0)
    end_index: Decimal = Field(gt=0)
    start_observed_at: datetime
    end_observed_at: datetime
    source: str = Field(min_length=2, max_length=120)


class BenchmarkInterval(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    start_index: Decimal = Field(gt=0)
    end_index: Decimal = Field(gt=0)
    start_observed_at: datetime
    end_observed_at: datetime
    source: str = Field(min_length=2, max_length=120)


class WalkForwardPeriod(BaseModel):
    decision_at: datetime
    evaluation_at: datetime
    profile_recorded_at: datetime
    request: BuildPortfolioRequest
    candidates: list[HistoricalCandidate] = Field(min_length=1, max_length=50)
    realized_returns: list[AdjustedReturnInterval] = Field(min_length=1, max_length=50)
    benchmark: BenchmarkInterval


class WalkForwardRequest(BaseModel):
    initial_capital: Decimal = Field(gt=0)
    fee_bps: Decimal = Field(default=Decimal("0"), ge=0, le=500)
    periods: list[WalkForwardPeriod] = Field(min_length=1, max_length=36)


class WalkForwardPeriodResult(BaseModel):
    decision_at: datetime
    evaluation_at: datetime
    selected_symbols: list[str]
    excluded_symbols: list[str]
    starting_equity: Decimal
    ending_equity: Decimal
    benchmark_ending_equity: Decimal
    net_return_percent: Decimal
    benchmark_return_percent: Decimal
    invested_percentage: Decimal
    cash_percentage: Decimal
    turnover_percentage: Decimal
    fee_paid: Decimal
    sampled_drawdown_percent: Decimal


class WalkForwardResult(BaseModel):
    validation_status: Literal["simulation_only"] = "simulation_only"
    validation_message: str = (
        "Simulação com dados fornecidos na requisição; fontes, históricos de "
        "publicação e universo de ativos não foram auditados externamente. "
        "Não comprova retorno nem qualidade preditiva das recomendações."
    )
    initial_capital: Decimal
    ending_equity: Decimal
    benchmark_ending_equity: Decimal
    net_return_percent: Decimal
    benchmark_return_percent: Decimal
    excess_return_percentage_points: Decimal
    maximum_sampled_drawdown_percent: Decimal
    positive_periods: int
    periods_count: int
    total_fees: Decimal
    total_turnover_percentage: Decimal
    periods: list[WalkForwardPeriodResult]
    limitations: list[str] = Field(default_factory=lambda: [
        "Dados e datas declarados pelo cliente; autenticidade das fontes não comprovada.",
        "Universo histórico e survivorship bias não auditados.",
        "Índices de retorno total ajustado obrigatórios; impostos, spread e "
        "custos adicionais além da taxa declarada não modelados.",
        "Drawdown calculado nas datas de avaliação, sem variações intraperíodo.",
        "Resultados históricos não garantem resultados futuros.",
    ])
