from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
