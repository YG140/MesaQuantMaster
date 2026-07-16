from decimal import Decimal

from app.providers.provider_factory import ProviderFactory
from app.schemas.market import MarketAssetResponse


def test_market_search_by_ticker_prioritizes_exact_match(client):
    response = client.get("/market/search?q=PETR4")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["ticker"] == "PETR4"
    assert data[0]["name"] == "Petrobras PN"
    assert data[0]["provider"] == "BRAPI"


def test_market_search_by_company_name(client):
    response = client.get("/market/search?q=petrobras")

    assert response.status_code == 200
    tickers = [item["ticker"] for item in response.json()]
    assert "PETR4" in tickers
    assert "PETR3" in tickers


def test_market_asset_contract_contains_consolidated_fields(client):
    response = client.get("/market/assets/PETR4")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "PETR4"
    assert data["name"] == "Petrobras PN"
    assert data["asset_type"] == "Acao"
    assert data["sector"] == "Energia"
    assert data["country"] == "Brasil"
    assert data["exchange"] == "B3"
    assert data["currency"] == "BRL"
    assert data["current_price"] == "38.42"
    assert data["last_updated"] is not None
    assert data["provider"] == "BRAPI"


def test_market_quote_keeps_legacy_and_new_price_fields(client):
    response = client.get("/market/quote/PETR4")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "PETR4"
    assert data["price"] == "38.42"
    assert data["current_price"] == "38.42"
    assert data["source"] == "BRAPI"
    assert data["provider"] == "BRAPI"


def test_market_asset_not_found(client):
    response = client.get("/market/assets/XXXX99")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ativo nao encontrado no provedor de mercado."


def test_market_search_supports_partial_provider_data(client, monkeypatch):
    class PartialProvider:
        def search_assets(self, query: str, limit: int = 10):
            return [
                MarketAssetResponse(
                    ticker="PARC3",
                    name=None,
                    asset_type=None,
                    current_price=Decimal("10.00"),
                    provider="TEST",
                )
            ]

        def get_asset(self, ticker: str):
            return None

        def get_quote(self, ticker: str):
            raise AssertionError("not used")

    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: PartialProvider())

    response = client.get("/market/search?q=PAR")

    assert response.status_code == 200
    data = response.json()[0]
    assert data["ticker"] == "PARC3"
    assert data["name"] is None
    assert data["asset_type"] is None
    assert data["current_price"] == "10.00"


def test_market_provider_unavailable_returns_readable_error(client, monkeypatch):
    class UnavailableProvider:
        def search_assets(self, query: str, limit: int = 10):
            raise RuntimeError("provider down")

        def get_asset(self, ticker: str):
            raise RuntimeError("provider down")

        def get_quote(self, ticker: str):
            raise RuntimeError("provider down")

    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: UnavailableProvider())

    response = client.get("/market/search?q=PETR4")

    assert response.status_code == 503
    assert "Provider de mercado indisponivel" in response.json()["detail"]


def test_market_endpoints_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/market/search?q=PETR4")

    assert response.status_code == 401
