from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.engines.portfolio_engine import PortfolioEngine


@dataclass
class FakeAsset:
    id: UUID
    ticker: str
    name: str


@dataclass
class FakeOperation:
    asset_id: UUID
    operation_type: str
    operation_date: date
    quantity: Decimal
    unit_price: Decimal
    fees: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")


def make_asset(ticker: str = "PETR4") -> FakeAsset:
    return FakeAsset(
        id=uuid4(),
        ticker=ticker,
        name=f"{ticker} SA",
    )


def make_operation(
    asset_id: UUID,
    operation_type: str,
    operation_date: date,
    quantity: str,
    unit_price: str,
    fees: str = "0",
    taxes: str = "0",
) -> FakeOperation:
    return FakeOperation(
        asset_id=asset_id,
        operation_type=operation_type,
        operation_date=operation_date,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        fees=Decimal(fees),
        taxes=Decimal(taxes),
    )


def calculate(asset: FakeAsset, operations: list[FakeOperation]):
    positions = PortfolioEngine.calculate_positions(
        operations=operations,
        assets_by_id={asset.id: asset},
    )
    return PortfolioEngine.summarize(positions)


def test_single_buy_consolidates_position():
    asset = make_asset()
    summary = calculate(
        asset,
        [
            make_operation(
                asset.id,
                "BUY",
                date(2026, 1, 1),
                "10",
                "20",
            )
        ],
    )

    assert summary.total_invested == Decimal("200")
    assert len(summary.positions) == 1
    assert summary.positions[0].quantity == Decimal("10")
    assert summary.positions[0].average_price == Decimal("20")
    assert summary.positions[0].invested_amount == Decimal("200")


def test_multiple_buys_recalculate_average_price_with_fees_and_taxes():
    asset = make_asset()
    summary = calculate(
        asset,
        [
            make_operation(asset.id, "BUY", date(2026, 1, 1), "10", "10", "1", "2"),
            make_operation(asset.id, "BUY", date(2026, 1, 2), "10", "20", "3", "4"),
        ],
    )

    position = summary.positions[0]

    assert position.quantity == Decimal("20")
    assert position.invested_amount == Decimal("310")
    assert position.average_price == Decimal("15.5")


def test_partial_sell_reduces_quantity_and_invested_cost_proportionally():
    asset = make_asset()
    summary = calculate(
        asset,
        [
            make_operation(asset.id, "BUY", date(2026, 1, 1), "10", "10"),
            make_operation(asset.id, "BUY", date(2026, 1, 2), "10", "20"),
            make_operation(asset.id, "SELL", date(2026, 1, 3), "5", "30"),
        ],
    )

    position = summary.positions[0]

    assert position.quantity == Decimal("15")
    assert position.average_price == Decimal("15")
    assert position.invested_amount == Decimal("225")


def test_total_sell_removes_position_from_portfolio():
    asset = make_asset()
    summary = calculate(
        asset,
        [
            make_operation(asset.id, "BUY", date(2026, 1, 1), "10", "10"),
            make_operation(asset.id, "SELL", date(2026, 1, 2), "10", "12"),
        ],
    )

    assert summary.positions == []
    assert summary.total_invested == Decimal("0")


def test_sell_above_position_raises_explicit_error():
    asset = make_asset()
    operations = [
        make_operation(asset.id, "BUY", date(2026, 1, 1), "10", "10"),
        make_operation(asset.id, "SELL", date(2026, 1, 2), "15", "12"),
    ]

    with pytest.raises(ValueError) as exc_info:
        calculate(asset, operations)

    message = str(exc_info.value)

    assert "Disponivel: 10" in message
    assert "Solicitada: 15" in message


def test_sell_above_position_does_not_change_valid_position_state():
    asset = make_asset()
    valid_summary = calculate(
        asset,
        [
            make_operation(asset.id, "BUY", date(2026, 1, 1), "10", "10"),
        ],
    )

    position = valid_summary.positions[0]

    assert position.quantity == Decimal("10")
    assert position.average_price == Decimal("10")
    assert position.invested_amount == Decimal("100")


def test_operations_are_processed_chronologically():
    asset = make_asset()
    summary = calculate(
        asset,
        [
            make_operation(asset.id, "SELL", date(2026, 1, 3), "5", "30"),
            make_operation(asset.id, "BUY", date(2026, 1, 1), "10", "10"),
            make_operation(asset.id, "BUY", date(2026, 1, 2), "10", "20"),
        ],
    )

    position = summary.positions[0]

    assert position.quantity == Decimal("15")
    assert position.average_price == Decimal("15")
    assert position.invested_amount == Decimal("225")


def test_fees_and_taxes_are_included_in_buy_cost():
    asset = make_asset()
    summary = calculate(
        asset,
        [
            make_operation(
                asset.id,
                "BUY",
                date(2026, 1, 1),
                "2",
                "50",
                "5",
                "7",
            )
        ],
    )

    position = summary.positions[0]

    assert position.invested_amount == Decimal("112")
    assert position.average_price == Decimal("56")


def test_multiple_assets_do_not_interfere_with_each_other():
    first_asset = make_asset("PETR4")
    second_asset = make_asset("VALE3")
    operations = [
        make_operation(first_asset.id, "BUY", date(2026, 1, 1), "10", "10"),
        make_operation(second_asset.id, "BUY", date(2026, 1, 1), "5", "20"),
    ]

    positions = PortfolioEngine.calculate_positions(
        operations=operations,
        assets_by_id={
            first_asset.id: first_asset,
            second_asset.id: second_asset,
        },
    )

    positions_by_ticker = {position.ticker: position for position in positions}

    assert positions_by_ticker["PETR4"].quantity == Decimal("10")
    assert positions_by_ticker["PETR4"].invested_amount == Decimal("100")
    assert positions_by_ticker["VALE3"].quantity == Decimal("5")
    assert positions_by_ticker["VALE3"].invested_amount == Decimal("100")


def test_empty_portfolio_returns_zeroes_and_empty_lists():
    summary = PortfolioEngine.summarize([])

    assert summary.total_invested == Decimal("0")
    assert summary.total_market_value == Decimal("0")
    assert summary.total_profit == Decimal("0")
    assert summary.profitability == Decimal("0")
    assert summary.allocation == []
    assert summary.positions == []
