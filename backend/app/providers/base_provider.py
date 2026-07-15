from abc import ABC, abstractmethod

from app.schemas.market import QuoteResponse


class BaseMarketProvider(ABC):
    """
    Interface base para provedores de dados de mercado.
    """

    @abstractmethod
    def get_quote(self, ticker: str) -> QuoteResponse:
        """
        Retorna a cotação atual de um ativo.
        """
        raise NotImplementedError
