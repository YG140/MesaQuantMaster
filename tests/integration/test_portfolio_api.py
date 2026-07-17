from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.market import QuoteResponse, QuotesResponse
from app.providers.provider_factory import ProviderFactory
from app.services.market_service import MarketService


def as_decimal(value) -> Decimal:
    return Decimal(str(value))


@pytest.fixture(autouse=True)
def isolate_market_service(monkeypatch):
    MarketService.clear_caches()
    monkeypatch.setattr(ProviderFactory, "get_provider", lambda: object())
    yield
    MarketService.clear_caches()


def test_get_portfolio_returns_consolidated_position(
    client,
    asset_factory,
    operation_factory,
    monkeypatch,
):
    def no_quotes(self, symbols: list[str]) -> QuotesResponse:
        return QuotesResponse(
            quotes=[],
            unavailable_symbols=[symbol.upper() for symbol in symbols],
        )

    monkeypatch.setattr(MarketService, "get_quotes", no_quotes)

    asset = asset_factory(
        ticker="PETR4",
        name="Petrobras PN",
    )
    operation_factory(
        asset=asset,
        operation_type="BUY",
        operation_date=date(2026, 1, 1),
        quantity=Decimal("10"),
        unit_price=Decimal("20"),
        fees=Decimal("1"),
        taxes=Decimal("2"),
    )

    response = client.get("/portfolio")

    assert response.status_code == 200

    data = response.json()
    position = data["positions"][0]

    assert as_decimal(data["total_invested"]) == Decimal("203")
    assert as_decimal(data["total_market_value"]) == Decimal("0")
    assert as_decimal(data["total_profit"]) == Decimal("0")
    assert data["valuation_basis"] == "invested_amount"
    assert data["market_data_status"] == "unavailable"
    assert data["unpriced_symbols"] == ["PETR4"]
    assert as_decimal(data["allocation"][0]["allocation"]) == Decimal("100.00")
    assert data["allocation"][0]["valuation_basis"] == "invested_amount"

    assert len(data["positions"]) == 1
    assert position["ticker"] == "PETR4"
    assert as_decimal(position["quantity"]) == Decimal("10")
    assert as_decimal(position["average_price"]) == Decimal("20.3")
    assert as_decimal(position["invested_amount"]) == Decimal("203")
    assert position["current_price"] is None
    assert position["market_value"] is None
    assert position["valuation_status"] == "unpriced"
    assert as_decimal(position["allocation"]) == Decimal("100.00")
    assert "asset_id" in position
    assert "asset_name" in position


def test_get_portfolio_applies_controlled_quote(
    client,
    asset_factory,
    operation_factory,
    monkeypatch,
):
    def controlled_quotes(self, symbols: list[str]) -> QuotesResponse:
        assert symbols == ["PETR4"]
        return QuotesResponse(
            quotes=[
                QuoteResponse(
                    ticker="PETR4",
                    symbol="PETR4",
                    requested_symbol="PETR4",
                    price=Decimal("39.89"),
                    current_price=Decimal("39.89"),
                    currency="BRL",
                    source="TEST",
                    provider="TEST",
                )
            ],
        )

    monkeypatch.setattr(MarketService, "get_quotes", controlled_quotes)

    asset = asset_factory(
        ticker="PETR4",
        name="Petrobras PN",
    )
    operation_factory(
        asset=asset,
        operation_type="BUY",
        operation_date=date(2026, 1, 1),
        quantity=Decimal("10"),
        unit_price=Decimal("20"),
        fees=Decimal("1"),
        taxes=Decimal("2"),
    )

    response = client.get("/portfolio")

    assert response.status_code == 200

    data = response.json()
    position = data["positions"][0]

    assert as_decimal(data["total_invested"]) == Decimal("203")
    assert as_decimal(data["total_market_value"]) == Decimal("398.90")
    assert as_decimal(data["total_profit"]) == Decimal("195.90")
    assert as_decimal(data["profitability"]) == Decimal("96.50")
    assert data["valuation_basis"] == "market_value"
    assert data["market_data_status"] == "live"
    assert data["unpriced_symbols"] == []

    assert position["ticker"] == "PETR4"
    assert as_decimal(position["current_price"]) == Decimal("39.89")
    assert as_decimal(position["market_value"]) == Decimal("398.90")
    assert as_decimal(position["unrealized_profit"]) == Decimal("195.90")
    assert as_decimal(position["unrealized_profit_percent"]) == Decimal("96.50")
    assert position["valuation_status"] == "live"
