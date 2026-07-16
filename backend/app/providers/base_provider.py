from abc import ABC, abstractmethod

from app.schemas.market import MarketAssetResponse, QuoteResponse


class BaseMarketProvider(ABC):
    """
    Interface base para provedores de dados de mercado.
    """

    @abstractmethod
    def get_quote(self, ticker: str) -> QuoteResponse:
        """
        Retorna a cotacao atual de um ativo.
        """
        raise NotImplementedError

    @abstractmethod
    def search_assets(self, query: str, limit: int = 10) -> list[MarketAssetResponse]:
        """
        Pesquisa ativos por codigo ou nome.
        """
        raise NotImplementedError

    @abstractmethod
    def get_asset(self, ticker: str) -> MarketAssetResponse | None:
        """
        Retorna metadados consolidados de um ativo.
        """
        raise NotImplementedError
