from app.providers.provider_factory import ProviderFactory
from app.schemas.market import MarketAssetResponse, QuoteResponse


class MarketService:
    """
    Servico responsavel por obter dados de mercado via providers.
    """

    def __init__(self):
        self.provider = ProviderFactory.get_provider()

    def get_quote(self, ticker: str) -> QuoteResponse:
        return self.provider.get_quote(ticker)

    def search_assets(self, query: str, limit: int = 10) -> list[MarketAssetResponse]:
        return self.provider.search_assets(query, limit=limit)

    def get_asset(self, ticker: str) -> MarketAssetResponse | None:
        return self.provider.get_asset(ticker)
