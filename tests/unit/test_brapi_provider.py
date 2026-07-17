from decimal import Decimal

import httpx
import pytest

from app.providers.brapi_provider import BrapiProvider
from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketAuthenticationError,
    MarketInvalidResponseError,
    MarketPermissionError,
    MarketProviderUnavailableError,
    MarketRateLimitError,
)


def make_provider(handler, api_key: str = "test-token") -> BrapiProvider:
    client = httpx.Client(
        base_url="https://brapi.dev",
        transport=httpx.MockTransport(handler),
    )
    return BrapiProvider(client=client, api_key=api_key, timeout_seconds=1)


def test_search_assets_maps_brapi_tickers_and_authorization_header():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        assert request.url.path == "/api/v2/tickers"
        assert request.url.params["search"] == "PETR4"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "data": {
                            "symbol": "PETR4",
                            "name": "Petrobras PN",
                            "longName": "Petroleo Brasileiro S.A.",
                            "type": "STOCK",
                            "subType": "preferred",
                            "exchange": "B3",
                            "currency": "BRL",
                            "sectorName": "Energia",
                            "subsector": "Petroleo",
                            "logo": "https://example.com/logo.png",
                            "regularMarketPrice": 38.42,
                            "regularMarketChange": 0.3,
                            "regularMarketChangePercent": 0.78,
                        }
                    }
                ]
            },
        )

    provider = make_provider(handler)

    result = provider.search_assets("PETR4")

    assert seen_headers["authorization"] == "Bearer test-token"
    assert result[0].ticker == "PETR4"
    assert result[0].long_name == "Petroleo Brasileiro S.A."
    assert result[0].asset_type == "Ação"
    assert result[0].asset_subtype == "Preferencial"
    assert result[0].country == "Brasil"
    assert result[0].sector == "Energia"
    assert result[0].subsector == "Petroleo"
    assert result[0].current_price == Decimal("38.42")
    assert result[0].change_value == Decimal("0.3")
    assert result[0].change_percent == Decimal("0.78")


def test_get_quotes_maps_batch_and_symbol_change():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/stocks/quote"
        assert request.url.params["symbols"] == "PETR4,VALE3"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "data": {
                            "symbol": "PETR4",
                            "regularMarketPrice": 38.42,
                            "regularMarketPreviousClose": 38,
                            "regularMarketChange": -0.3,
                            "regularMarketChangePercent": -0.78,
                            "type": "stock",
                            "subType": "stock",
                            "exchange": "B3",
                        }
                    },
                    {
                        "data": {
                            "symbol": "VALE3",
                            "regularMarketPrice": 60.5,
                            "regularMarketChange": 0,
                            "regularMarketChangePercent": 0,
                            "type": "stock",
                        }
                    },
                ]
            },
        )

    provider = make_provider(handler)

    quotes = provider.get_quotes(["petr4", "VALE3"])

    assert [quote.ticker for quote in quotes] == ["PETR4", "VALE3"]
    assert quotes[0].current_price == Decimal("38.42")
    assert quotes[0].change_value == Decimal("-0.3")
    assert quotes[0].change_percent == Decimal("-0.78")
    assert quotes[0].asset_type == "Ação"
    assert quotes[0].asset_subtype is None
    assert quotes[1].change_value == Decimal("0")
    assert quotes[1].change_percent == Decimal("0")
    assert quotes[0].requested_symbol == "PETR4"


def test_get_profile_maps_normalized_profile():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/stocks/profile"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "data": {
                            "symbol": "PETR4",
                            "name": "Petrobras",
                            "summaryProfile": {
                                "sector": "Energia",
                                "industry": "Petroleo",
                                "longBusinessSummary": "Energia.",
                            },
                            "country": "Brasil",
                            "website": "https://petrobras.com.br",
                            "cnpj": "33.000.167/0001-01",
                        }
                    }
                ]
            },
        )

    profile = make_provider(handler).get_profile("petr4")

    assert profile.symbol == "PETR4"
    assert profile.industry == "Petroleo"
    assert profile.provider == "BRAPI"


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, MarketAuthenticationError),
        (403, MarketPermissionError),
        (404, MarketAssetNotFoundError),
        (429, MarketRateLimitError),
        (500, MarketProviderUnavailableError),
    ],
)
def test_provider_maps_http_errors(status_code, expected_error):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "failure"})

    with pytest.raises(expected_error):
        make_provider(handler).get_quote("PETR4")


def test_provider_maps_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    with pytest.raises(MarketInvalidResponseError):
        make_provider(handler).get_quote("PETR4")


def test_provider_maps_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(MarketProviderUnavailableError):
        make_provider(handler).get_quote("PETR4")


def test_provider_rejects_quote_without_price():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"symbol": "PETR4"}]})

    with pytest.raises(MarketInvalidResponseError):
        make_provider(handler).get_quote("PETR4")


def test_provider_marks_limited_mode_without_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            json={"results": [{"symbol": "PETR4", "regularMarketPrice": 38.42}]},
        )

    quote = make_provider(handler, api_key="").get_quote("PETR4")

    assert quote.limited_mode is True
