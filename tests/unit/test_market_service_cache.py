from decimal import Decimal

import pytest

from app.providers.exceptions import MarketProviderUnavailableError
from app.schemas.market import QuoteResponse
from app.services.market_cache import TTLCache
from app.services.market_service import MarketService


class QuoteProvider:
    limited_mode = False

    def __init__(self):
        self.calls = 0
        self.fail = False

    def get_quotes(self, tickers: list[str]):
        self.calls += 1
        if self.fail:
            raise MarketProviderUnavailableError("down")
        return [
            QuoteResponse(
                ticker=ticker.upper(),
                symbol=ticker.upper(),
                requested_symbol=ticker.upper(),
                price=Decimal("10"),
                current_price=Decimal("10"),
                currency="BRL",
                source="BRAPI",
                provider="BRAPI",
            )
            for ticker in tickers
        ]

    def get_quote(self, ticker: str):
        return self.get_quotes([ticker])[0]

    def search_assets(self, query: str, limit: int = 10):
        return []

    def get_asset(self, ticker: str):
        return None

    def get_profile(self, ticker: str):
        raise AssertionError("not used")


class EmptyBatchProvider(QuoteProvider):
    def get_quotes(self, tickers: list[str]):
        if len(tickers) > 1:
            self.calls += 1
            return []
        return super().get_quotes(tickers)


class FailingBatchProvider(QuoteProvider):
    def get_quotes(self, tickers: list[str]):
        if len(tickers) > 1:
            self.calls += 1
            raise MarketProviderUnavailableError("batch down")
        return super().get_quotes(tickers)


def setup_function():
    MarketService.clear_caches()


def test_market_service_cache_hit_for_quotes():
    provider = QuoteProvider()
    service = MarketService(provider=provider)

    first = service.get_quotes(["PETR4"])
    second = service.get_quotes(["PETR4"])

    assert provider.calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.quotes[0].cache_hit is True


def test_ttl_cache_expires_deterministically():
    now = 100.0
    cache = TTLCache(clock=lambda: now)
    cache.set("key", "value", ttl_seconds=10)

    assert cache.get("key") == "value"
    now = 111.0
    assert cache.get("key") is None


def test_market_service_does_not_cache_errors():
    provider = QuoteProvider()
    service = MarketService(provider=provider)

    provider.fail = True
    with pytest.raises(MarketProviderUnavailableError):
        service.get_quotes(["PETR4"])

    provider.fail = False
    response = service.get_quotes(["PETR4"])

    assert response.quotes[0].current_price == Decimal("10")
    assert provider.calls == 2


def test_market_service_falls_back_to_individual_quotes_when_batch_is_empty():
    provider = EmptyBatchProvider()
    service = MarketService(provider=provider)

    response = service.get_quotes(["ITSA4", "PETR4"])

    assert [quote.ticker for quote in response.quotes] == ["ITSA4", "PETR4"]
    assert response.unavailable_symbols == []
    assert provider.calls == 3


def test_market_service_falls_back_to_individual_quotes_when_batch_fails():
    provider = FailingBatchProvider()
    service = MarketService(provider=provider)

    response = service.get_quotes(["ITSA4", "PETR4"])

    assert [quote.ticker for quote in response.quotes] == ["ITSA4", "PETR4"]
    assert response.unavailable_symbols == []
    assert provider.calls == 3
