from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from time import perf_counter

import pytest

from app.providers.exceptions import MarketProviderUnavailableError
from app.providers.provider_factory import ProviderFactory
from app.schemas.market import QuoteResponse
from app.services.market_service import MarketService


MAX_ENDPOINT_SECONDS = 2


class BatchQuoteProvider:
    limited_mode = False

    def __init__(self, fail: bool = False, partial: bool = False):
        self.fail = fail
        self.partial = partial
        self.calls = 0
        self.requested_batches: list[list[str]] = []

    def get_quotes(self, tickers: list[str]):
        self.calls += 1
        self.requested_batches.append(tickers)
        if self.fail:
            raise MarketProviderUnavailableError("down")
        quotes = []
        for ticker in tickers:
            symbol = ticker.upper()
            if self.partial and symbol == "VALE3":
                continue
            quotes.append(
                QuoteResponse(
                    ticker=symbol,
                    symbol=symbol,
                    requested_symbol=symbol,
                    price=Decimal("30"),
                    current_price=Decimal("30"),
                    currency="BRL",
                    market_time=datetime(2026, 7, 16, 18, 30, tzinfo=timezone.utc),
                    source="BRAPI",
                    provider="BRAPI",
                )
            )
        return quotes

    def get_quote(self, ticker: str):
        return self.get_quotes([ticker])[0]

    def search_assets(self, query: str, limit: int = 10):
        return []

    def get_asset(self, ticker: str):
        return None

    def get_profile(self, ticker: str):
        raise AssertionError("not used")


def setup_function():
    MarketService.clear_caches()


def timed_get(client, path: str):
    start = perf_counter()
    response = client.get(path)
    elapsed = perf_counter() - start
    return response, elapsed


@pytest.mark.parametrize("path", ["/portfolio", "/dashboard"])
def test_portfolio_and_dashboard_return_quickly_with_empty_portfolio(client, path):
    response, elapsed = timed_get(client, path)

    assert response.status_code == 200
    assert elapsed < MAX_ENDPOINT_SECONDS


@pytest.mark.parametrize("path", ["/portfolio", "/dashboard"])
def test_portfolio_and_dashboard_return_quickly_with_multiple_positions(
    client,
    asset_factory,
    operation_factory,
    monkeypatch,
    path,
):
    provider = BatchQuoteProvider()
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: provider)

    for index in range(5):
        asset = asset_factory(
            ticker=f"MQ{index}",
            name=f"Mesa Quant {index}",
        )
        operation_factory(
            asset=asset,
            operation_type="BUY",
            operation_date=date(2026, 1, index + 1),
            quantity=Decimal("10"),
            unit_price=Decimal("20"),
        )

    response, elapsed = timed_get(client, path)

    assert response.status_code == 200
    assert elapsed < MAX_ENDPOINT_SECONDS


def test_portfolio_uses_single_batch_quote_call(
    client,
    asset_factory,
    operation_factory,
    monkeypatch,
):
    provider = BatchQuoteProvider()
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: provider)

    for ticker in ["PETR4", "VALE3", "ITUB4"]:
        asset = asset_factory(ticker=ticker, name=ticker)
        operation_factory(
            asset=asset,
            operation_type="BUY",
            operation_date=date(2026, 1, 1),
            quantity=Decimal("10"),
            unit_price=Decimal("20"),
        )

    response = client.get("/portfolio")

    assert response.status_code == 200
    assert provider.calls == 1
    assert provider.requested_batches == [["ITUB4", "PETR4", "VALE3"]]
    data = response.json()
    assert data["market_data_status"] == "live"
    assert data["unpriced_symbols"] == []
    assert data["positions"][0]["current_price"] == "30"


def test_portfolio_partial_quotes_keep_unpriced_position(
    client,
    asset_factory,
    operation_factory,
    monkeypatch,
):
    provider = BatchQuoteProvider(partial=True)
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: provider)

    for ticker in ["PETR4", "VALE3"]:
        asset = asset_factory(ticker=ticker, name=ticker)
        operation_factory(
            asset=asset,
            operation_type="BUY",
            operation_date=date(2026, 1, 1),
            quantity=Decimal("10"),
            unit_price=Decimal("20"),
        )

    response = client.get("/portfolio")

    assert response.status_code == 200
    data = response.json()
    assert data["market_data_status"] == "partial"
    assert data["unpriced_symbols"] == ["VALE3"]
    vale = next(item for item in data["positions"] if item["ticker"] == "VALE3")
    assert vale["current_price"] is None
    assert vale["market_value"] is None
    assert vale["valuation_status"] == "unpriced"


@pytest.mark.parametrize("path", ["/portfolio", "/dashboard"])
def test_portfolio_and_dashboard_continue_when_provider_fails(
    client,
    asset_factory,
    operation_factory,
    monkeypatch,
    path,
):
    provider = BatchQuoteProvider(fail=True)
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: provider)

    asset = asset_factory(ticker="PETR4", name="Petrobras PN")
    operation_factory(
        asset=asset,
        operation_type="BUY",
        operation_date=date(2026, 1, 1),
        quantity=Decimal("10"),
        unit_price=Decimal("20"),
    )

    response, elapsed = timed_get(client, path)

    assert response.status_code == 200
    assert elapsed < MAX_ENDPOINT_SECONDS
    assert response.json()["market_data_status"] == "unavailable"
