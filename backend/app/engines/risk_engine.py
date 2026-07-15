from __future__ import annotations

from decimal import Decimal


class RiskEngine:
    """
    Motor responsavel pelas regras de risco da carteira.

    Nao acessa banco de dados.
    Nao consulta APIs.
    Apenas aplica regras sobre indicadores ja calculados.
    """

    CONCENTRATION_LIMIT = Decimal("20.00")

    @classmethod
    def concentration_alerts(
        cls,
        concentration: list[dict],
    ) -> list[dict]:
        alerts = []

        for item in concentration:
            if item["allocation"] >= cls.CONCENTRATION_LIMIT:
                alerts.append(
                    {
                        "ticker": item["ticker"],
                        "allocation": item["allocation"],
                        "message": ("Concentracao acima do limite recomendado."),
                    }
                )

        return alerts

    @staticmethod
    def portfolio_is_empty(
        total_positions: int,
    ) -> bool:
        return total_positions == 0
