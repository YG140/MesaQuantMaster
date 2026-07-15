from decimal import Decimal

from app.providers.base_provider import BaseMarketProvider
from app.schemas.market import QuoteResponse


class BrapiProvider(BaseMarketProvider):
    """
    Implementação inicial da BRAPI.

    Nesta sprint utilizaremos dados simulados.
    Na próxima sprint integraremos a API real.
    """

    def get_quote(self, ticker: str) -> QuoteResponse:
        return QuoteResponse(
            ticker=ticker.upper(),
            price=Decimal("0"),
            source="BRAPI",
        )
