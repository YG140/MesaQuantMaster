from datetime import datetime, timezone
from decimal import Decimal

from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketProviderUnavailableError,
    MarketRateLimitError,
)
from app.providers.provider_factory import ProviderFactory
from app.schemas.market import MarketAssetResponse, MarketProfileResponse, QuoteResponse
from app.services.market_service import MarketService


class FakeMarketProvider:
    provider_name = "BRAPI"
    limited_mode = False

    def search_assets(self, query: str, limit: int = 10):
        items = [
            self._asset("PETR4", "Petrobras PN"),
            self._asset("PETR3", "Petrobras ON"),
            self._asset("VALE3", "Vale ON"),
            self._asset("PETR4", "Petrobras PN duplicado"),
        ]
        normalized = query.upper()
        matches = [
            item
            for item in items
            if normalized in item.ticker or normalized in (item.name or "").upper()
        ]
        return sorted(
            matches, key=lambda item: (item.ticker != normalized, item.ticker)
        )[:limit]

    def get_asset(self, ticker: str):
        symbol = ticker.upper()
        if symbol == "XXXX99":
            return None
        quote = self.get_quote(symbol)
        return MarketAssetResponse(
            ticker=quote.ticker,
            symbol=quote.ticker,
            name=quote.name,
            long_name=quote.name,
            asset_type=quote.asset_type,
            asset_subtype=quote.asset_subtype,
            sector=quote.sector,
            subsector=quote.subsector,
            country=quote.country,
            exchange=quote.exchange,
            currency=quote.currency,
            logo_url=quote.logo_url,
            current_price=quote.current_price,
            change_percent=quote.change_percent,
            last_updated=quote.market_time,
            updated_at=quote.market_time,
            provider="BRAPI",
        )

    def get_quote(self, ticker: str):
        quotes = self.get_quotes([ticker])
        if not quotes:
            raise MarketAssetNotFoundError("not found")
        return quotes[0]

    def get_quotes(self, tickers: list[str]):
        quotes = []
        for ticker in tickers:
            symbol = ticker.upper()
            if symbol == "XXXX99":
                continue
            quotes.append(
                QuoteResponse(
                    ticker=symbol,
                    symbol=symbol,
                    requested_symbol=symbol,
                    price=Decimal("38.42"),
                    current_price=Decimal("38.42"),
                    previous_close=Decimal("38.00"),
                    change=Decimal("0.42"),
                    change_percent=Decimal("1.10"),
                    currency="BRL",
                    market_time=datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc),
                    source="BRAPI",
                    name="Petrobras PN" if symbol.startswith("PETR") else symbol,
                    asset_type="Acao",
                    asset_subtype="ON",
                    sector="Energia",
                    subsector="Petroleo",
                    country="Brasil",
                    exchange="B3",
                    logo_url="https://example.com/logo.png",
                    provider="BRAPI",
                )
            )
        return quotes

    def get_profile(self, ticker: str):
        return MarketProfileResponse(
            symbol=ticker.upper(),
            name="Petrobras",
            sector="Energia",
            industry="Petroleo",
            country="Brasil",
            website="https://petrobras.com.br",
            description="Empresa brasileira de energia.",
            cnpj="33.000.167/0001-01",
            logo_url="https://example.com/logo.png",
            provider="BRAPI",
        )

    @staticmethod
    def _asset(ticker: str, name: str):
        return MarketAssetResponse(
            ticker=ticker,
            symbol=ticker,
            name=name,
            long_name=name,
            asset_type="Acao",
            asset_subtype="PN",
            sector="Energia",
            subsector="Petroleo",
            country="Brasil",
            exchange="B3",
            currency="BRL",
            logo_url="https://example.com/logo.png",
            current_price=Decimal("38.42"),
            change_percent=Decimal("1.10"),
            last_updated=datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc),
            provider="BRAPI",
        )


def setup_function():
    MarketService.clear_caches()


def test_market_search_by_ticker_prioritizes_exact_match(client, monkeypatch):
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: FakeMarketProvider())

    response = client.get("/market/search?q=PETR4")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["ticker"] == "PETR4"
    assert data[0]["name"] == "Petrobras PN"
    assert data[0]["provider"] == "BRAPI"


def test_market_search_by_company_name_without_duplicates(client, monkeypatch):
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: FakeMarketProvider())

    response = client.get("/market/search?q=petrobras")

    assert response.status_code == 200
    tickers = [item["ticker"] for item in response.json()]
    assert "PETR4" in tickers
    assert "PETR3" in tickers
    assert tickers.count("PETR4") == 1


def test_market_asset_contract_contains_consolidated_fields(client, monkeypatch):
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: FakeMarketProvider())

    response = client.get("/market/assets/PETR4")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "PETR4"
    assert data["symbol"] == "PETR4"
    assert data["name"] == "Petrobras PN"
    assert data["asset_type"] == "Acao"
    assert data["asset_subtype"] == "ON"
    assert data["sector"] == "Energia"
    assert data["subsector"] == "Petroleo"
    assert data["country"] == "Brasil"
    assert data["exchange"] == "B3"
    assert data["currency"] == "BRL"
    assert data["current_price"] == "38.42"
    assert data["updated_at"] is not None
    assert data["provider"] == "BRAPI"
    assert "BRAPI_API_KEY" not in str(data)


def test_market_quote_keeps_legacy_and_new_price_fields(client, monkeypatch):
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: FakeMarketProvider())

    response = client.get("/market/quote/PETR4")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "PETR4"
    assert data["symbol"] == "PETR4"
    assert data["price"] == "38.42"
    assert data["current_price"] == "38.42"
    assert data["source"] == "BRAPI"
    assert data["provider"] == "BRAPI"


def test_market_quotes_batch(client, monkeypatch):
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: FakeMarketProvider())

    response = client.post("/market/quotes", json={"symbols": ["PETR4", "VALE3"]})

    assert response.status_code == 200
    data = response.json()
    assert [item["ticker"] for item in data["quotes"]] == ["PETR4", "VALE3"]
    assert data["provider"] == "BRAPI"
    assert data["limited_mode"] is False


def test_market_profile(client, monkeypatch):
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: FakeMarketProvider())

    response = client.get("/market/profile/PETR4")

    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "PETR4"
    assert data["cnpj"] == "33.000.167/0001-01"


def test_market_asset_not_found(client, monkeypatch):
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: FakeMarketProvider())

    response = client.get("/market/assets/XXXX99")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ativo nao encontrado no provedor de mercado."


def test_market_rate_limit_returns_readable_error(client, monkeypatch):
    class RateLimitedProvider(FakeMarketProvider):
        def search_assets(self, query: str, limit: int = 10):
            raise MarketRateLimitError("secret header should not leak")

    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: RateLimitedProvider())

    response = client.get("/market/search?q=PETR4")

    assert response.status_code == 429
    assert response.json()["detail"] == (
        "Limite de consultas ao mercado atingido. Tente novamente mais tarde."
    )
    assert "secret" not in response.text


def test_market_provider_unavailable_returns_readable_error(client, monkeypatch):
    class UnavailableProvider(FakeMarketProvider):
        def search_assets(self, query: str, limit: int = 10):
            raise MarketProviderUnavailableError("provider down")

    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: UnavailableProvider())

    response = client.get("/market/search?q=PETR4")

    assert response.status_code == 503
    assert response.json()["detail"] == "Nao foi possivel consultar o mercado agora."


def test_market_endpoints_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/market/search?q=PETR4")

    assert response.status_code == 401
