from decimal import Decimal

import httpx
import pytest

from app.providers.bcb_sgs_provider import BcbSgsProvider
from app.providers.brapi_provider import BrapiProvider
from app.providers.exceptions import MarketPermissionError


@pytest.mark.parametrize(
    ("dataset", "path"),
    [
        ("statistics", "/api/v2/stocks/statistics"),
        ("financial_data", "/api/v2/stocks/financial-data"),
        ("balance_sheet", "/api/v2/stocks/balance-sheet"),
        ("income_statement", "/api/v2/stocks/income-statement"),
        ("cash_flow", "/api/v2/stocks/cash-flow"),
        ("dividends", "/api/v2/stocks/dividends"),
        ("historical", "/api/v2/stocks/historical"),
    ],
)
def test_stock_datasets_use_official_endpoints(dataset, path):
    def handler(request):
        assert request.url.path == path
        assert request.url.params["symbols"] == "PETR4"
        return httpx.Response(
            200, json={"results": [{"symbol": "PETR4", "data": {"value": 1}}]}
        )

    provider = BrapiProvider(
        client=httpx.Client(
            base_url="https://brapi.dev", transport=httpx.MockTransport(handler)
        ),
        api_key="test",
    )
    assert provider.get_stock_dataset(dataset, ["PETR4"])["results"]


@pytest.mark.parametrize(
    "dataset", ["indicators", "properties", "portfolio", "reports", "dividends"]
)
def test_fii_datasets_use_fii_domain(dataset):
    def handler(request):
        assert request.url.path == f"/api/v2/fii/{dataset}"
        return httpx.Response(200, json={"fiis": [{"symbol": "HGLG11"}]})

    provider = BrapiProvider(
        client=httpx.Client(
            base_url="https://brapi.dev", transport=httpx.MockTransport(handler)
        ),
        api_key="test",
    )
    assert provider.get_fii_dataset(dataset, ["HGLG11"])["fiis"]


def test_restricted_plan_has_specific_exception():
    provider = BrapiProvider(
        client=httpx.Client(
            base_url="https://brapi.dev",
            transport=httpx.MockTransport(lambda request: httpx.Response(403)),
        ),
        api_key="test",
    )
    with pytest.raises(MarketPermissionError, match="plano"):
        provider.get_stock_dataset("statistics", ["PETR4"])


def test_treasury_and_macro_endpoints():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"results": []})

    provider = BrapiProvider(
        client=httpx.Client(
            base_url="https://brapi.dev", transport=httpx.MockTransport(handler)
        ),
        api_key="test",
    )
    provider.get_treasury("indicators", ["tesouro-selic-01032031"])
    provider.get_macro(["selic", "ipca"])
    assert seen == ["/api/v2/treasury/indicators", "/api/v2/macro"]


def test_bcb_sgs_normalizes_decimal_and_metadata():
    def handler(request):
        assert request.url.path.endswith("bcdata.sgs.433/dados")
        return httpx.Response(200, json=[{"data": "01/06/2026", "valor": "0,26"}])

    provider = BcbSgsProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = provider.get_series("ipca")
    assert result["series_code"] == 433
    assert result["values"][0]["value"] == Decimal("0.26")
