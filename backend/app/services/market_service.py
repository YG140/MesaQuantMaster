from app.providers.provider_factory import ProviderFactory
from app.schemas.market import QuoteResponse


class MarketService:
    """
    Serviço responsável por obter dados de mercado.
    """

    def __init__(self):
        self.provider = ProviderFactory.get_provider()

    def get_quote(self, ticker: str) -> QuoteResponse:
        return self.provider.get_quote(ticker)
