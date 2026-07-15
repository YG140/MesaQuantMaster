from __future__ import annotations

from decimal import Decimal


class StrategyEngine:
    """
    Motor responsável por executar estratégias de investimento.

    Este Engine não consulta banco de dados e não acessa APIs.
    Apenas recebe indicadores já calculados e aplica regras.
    """

    @staticmethod
    def graham(
        pl: Decimal,
        pvp: Decimal,
    ) -> bool:
        """
        Estratégia simplificada de Benjamin Graham.
        """

        return pl <= Decimal("15") and pvp <= Decimal("1.5")

    @staticmethod
    def bazin(
        dividend_yield: Decimal,
    ) -> bool:
        """
        Estratégia de Décio Bazin.
        """

        return dividend_yield >= Decimal("6")

    @staticmethod
    def buy_and_hold(
        roe: Decimal,
        dividend_yield: Decimal,
    ) -> bool:

        return roe >= Decimal("15") and dividend_yield >= Decimal("4")

    @staticmethod
    def momentum(
        current_price: Decimal,
        moving_average_200: Decimal,
    ) -> bool:

        return current_price > moving_average_200

    @staticmethod
    def magic_formula(
        roe: Decimal,
        ev_ebit: Decimal,
    ) -> bool:

        return roe >= Decimal("20") and ev_ebit <= Decimal("10")

    @staticmethod
    def score(
        **criteria,
    ) -> int:
        """
        Retorna uma pontuação baseada nos critérios aprovados.
        """

        return sum(1 for value in criteria.values() if value)
