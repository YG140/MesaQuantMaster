from decimal import Decimal

import pytest

from app.providers.exceptions import MarketPermissionError, MarketProviderUnavailableError
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


# --- Restrição de plano BRAPI: nunca vaza entre tickers nem entre instâncias.
#
# Bug corrigido: _restricted_domains era um set de CLASSE (compartilhado por
# todas as instâncias/requisições, nunca limpo em produção) e a chave de
# cache era só "fii:{dataset}", sem o símbolo — um único ticker restrito
# (ex.: um FII fora do plano gratuito) derrubava permanentemente o acesso
# àquele dataset para TODOS os outros ativos, pelo resto do processo.


class SelectiveFiiProvider:
    """Restringe apenas símbolos específicos, como o BRAPI real faz por FII
    (ex.: MXRF11 liberado, ALZR11 fora do plano) — não por dataset inteiro."""

    def __init__(self, restricted_symbols):
        self.restricted_symbols = set(restricted_symbols)
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def get_fii_dataset(self, dataset: str, symbols: list[str], **params):
        self.calls.append((dataset, tuple(symbols)))
        if any(symbol in self.restricted_symbols for symbol in symbols):
            raise MarketPermissionError("plano")
        return {"results": [{"symbol": symbol} for symbol in symbols]}

    def get_stock_dataset(self, dataset: str, symbols: list[str], **params):
        return self.get_fii_dataset(dataset, symbols, **params)


def test_one_restricted_ticker_does_not_block_another_ticker_same_dataset():
    provider = SelectiveFiiProvider(restricted_symbols={"ALZR11"})
    service = MarketService(provider=provider)

    with pytest.raises(MarketPermissionError):
        service.get_fii_dataset("indicators", ["ALZR11"])

    # MXRF11 nunca foi tentado antes — não pode herdar a restrição de ALZR11.
    result = service.get_fii_dataset("indicators", ["MXRF11"])
    assert result == {"results": [{"symbol": "MXRF11"}]}
    assert provider.calls == [("indicators", ("ALZR11",)), ("indicators", ("MXRF11",))]


def test_same_restricted_ticker_is_not_retried_on_the_same_instance():
    provider = SelectiveFiiProvider(restricted_symbols={"ALZR11"})
    service = MarketService(provider=provider)

    with pytest.raises(MarketPermissionError):
        service.get_fii_dataset("indicators", ["ALZR11"])
    with pytest.raises(MarketPermissionError):
        service.get_fii_dataset("indicators", ["ALZR11"])

    assert provider.calls == [("indicators", ("ALZR11",))]


def test_restriction_cache_does_not_leak_across_instances():
    provider = SelectiveFiiProvider(restricted_symbols={"ALZR11"})
    first_service = MarketService(provider=provider)
    with pytest.raises(MarketPermissionError):
        first_service.get_fii_dataset("indicators", ["ALZR11"])

    # Uma NOVA instância (ex.: nova requisição) não herda o estado da
    # anterior — precisa poder tentar de novo (a restrição real do BRAPI
    # pode ter mudado, e o processo não deve travar permanentemente).
    second_service = MarketService(provider=provider)
    with pytest.raises(MarketPermissionError):
        second_service.get_fii_dataset("indicators", ["ALZR11"])

    assert provider.calls == [
        ("indicators", ("ALZR11",)),
        ("indicators", ("ALZR11",)),
    ]
