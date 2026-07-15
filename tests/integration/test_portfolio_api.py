from __future__ import annotations

from datetime import date
from decimal import Decimal


def as_decimal(value) -> Decimal:
    return Decimal(str(value))


def test_get_portfolio_returns_consolidated_position(
    client,
    asset_factory,
    operation_factory,
):
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
    assert as_decimal(data["total_profit"]) == Decimal("-203")
    assert data["valuation_basis"] == "invested_amount"
    assert as_decimal(data["allocation"][0]["allocation"]) == Decimal("100.00")
    assert data["allocation"][0]["valuation_basis"] == "invested_amount"

    assert len(data["positions"]) == 1
    assert position["ticker"] == "PETR4"
    assert as_decimal(position["quantity"]) == Decimal("10")
    assert as_decimal(position["average_price"]) == Decimal("20.3")
    assert as_decimal(position["invested_amount"]) == Decimal("203")
    assert as_decimal(position["allocation"]) == Decimal("100.00")
    assert "asset_id" in position
    assert "asset_name" in position
