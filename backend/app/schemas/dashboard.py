from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    patrimonio_total: Decimal

    valor_investido: Decimal

    lucro_prejuizo: Decimal

    rentabilidade: Decimal

    caixa: Decimal

    ativos: int

    operacoes: int

    proventos: Decimal

    ultima_atualizacao: datetime

    market_data_status: str = "unavailable"

    quote_updated_at: datetime | None = None

    unpriced_symbols: list[str] = Field(default_factory=list)
