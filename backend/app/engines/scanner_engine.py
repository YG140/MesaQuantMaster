from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.schemas.market import QuoteResponse
from app.schemas.portfolio import PortfolioPosition


class ScannerEngine:
    """
    Motor responsável por executar análises quantitativas.

    O ScannerEngine não acessa banco de dados e não consulta APIs.
    Ele apenas processa os dados recebidos e retorna os resultados.
    """

    @staticmethod
    def price_above(
        quote: QuoteResponse,
        target_price: Decimal,
    ) -> bool:
        return Decimal(str(quote.price)) > target_price

    @staticmethod
    def price_below(
        quote: QuoteResponse,
        target_price: Decimal,
    ) -> bool:
        return Decimal(str(quote.price)) < target_price

    @staticmethod
    def find_empty_positions(
        positions: Iterable[PortfolioPosition],
    ) -> list[PortfolioPosition]:

        return [position for position in positions if position.quantity <= 0]
