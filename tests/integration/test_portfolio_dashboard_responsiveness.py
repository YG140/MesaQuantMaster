from __future__ import annotations

from datetime import date
from decimal import Decimal
from time import perf_counter

import pytest


MAX_ENDPOINT_SECONDS = 2


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
    path,
):
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


@pytest.mark.parametrize("path", ["/portfolio", "/dashboard"])
def test_portfolio_and_dashboard_do_not_call_market_provider(
    client,
    asset_factory,
    operation_factory,
    monkeypatch,
    path,
):
    def fail_if_called():
        raise AssertionError("market provider should not be called")

    monkeypatch.setattr(
        "app.providers.provider_factory.ProviderFactory.get_provider",
        fail_if_called,
    )

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
