from abc import ABC, abstractmethod

from app.schemas.market import MarketAssetResponse, MarketProfileResponse, QuoteResponse


class BaseMarketProvider(ABC):
    """
    Interface base para provedores de dados de mercado.
    """

    # Mercado que este provider comprovadamente atende (ex.: "B3"), usado
    # por app.services.symbol_identity.market_context_of() para decidir se
    # regras específicas de um mercado (ex.: canonicalização do sufixo
    # fracionário B3) podem se aplicar aos símbolos que ele resolve. `None`
    # é o default seguro: nenhuma regra específica de mercado é aplicada
    # a um provider que não declara explicitamente o seu.
    market: str | None = None

    @abstractmethod
    def get_quote(self, ticker: str) -> QuoteResponse:
        """
        Retorna a cotacao atual de um ativo.
        """
        raise NotImplementedError

    @abstractmethod
    def get_quotes(self, tickers: list[str]) -> list[QuoteResponse]:
        """
        Retorna cotacoes atuais em lote.
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

    @abstractmethod
    def get_profile(self, ticker: str) -> MarketProfileResponse:
        """
        Retorna perfil normalizado de um ativo.
        """
        raise NotImplementedError
