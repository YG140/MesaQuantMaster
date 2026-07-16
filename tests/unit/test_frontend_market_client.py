import httpx

from services.api_client import ApiClient
from services.market_client import MarketClient


def test_market_client_search_encodes_query_and_sends_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/market/search"
        assert request.url.params["q"] == "petrobras energia"
        assert request.url.params["limit"] == "8"
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json=[{"ticker": "PETR4"}])

    client = MarketClient(
        ApiClient(
            base_url="http://testserver",
            token_getter=lambda: "secret",
            transport=httpx.MockTransport(handler),
        )
    )

    assert client.search_assets("petrobras energia") == [{"ticker": "PETR4"}]


def test_market_client_get_asset_uses_market_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/market/assets/PETR4"
        return httpx.Response(200, json={"ticker": "PETR4", "provider": "BRAPI"})

    client = MarketClient(
        ApiClient(
            base_url="http://testserver",
            transport=httpx.MockTransport(handler),
        )
    )

    assert client.get_asset("PETR4")["provider"] == "BRAPI"
