from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.engines.portfolio_engine import PortfolioEngine
from app.engines.scanner_engine import ScannerEngine
from app.schemas.market import QuoteResponse
from app.schemas.portfolio import PortfolioPosition


def make_quote(price: str) -> QuoteResponse:
    return QuoteResponse(
        ticker="PETR4",
        price=Decimal(price),
        source="test",
    )


def test_price_above_target():
    assert ScannerEngine.price_above(make_quote("11"), Decimal("10")) is True


def test_price_below_target():
    assert ScannerEngine.price_below(make_quote("9"), Decimal("10")) is True


def test_price_equal_target_is_not_above_or_below():
    quote = make_quote("10")

    assert ScannerEngine.price_above(quote, Decimal("10")) is False
    assert ScannerEngine.price_below(quote, Decimal("10")) is False


def test_scanner_reuses_portfolio_engine_data_for_concentration():
    position = PortfolioPosition(
        asset_id=uuid4(),
        ticker="PETR4",
        asset_name="Petrobras PN",
        quantity=Decimal("10"),
        average_price=Decimal("10"),
        invested_amount=Decimal("100"),
        market_value=Decimal("100"),
    )

    concentration = PortfolioEngine.concentration([position])

    assert concentration[0]["ticker"] == "PETR4"
    assert concentration[0]["allocation"] == Decimal("100.00")


def test_scanner_engine_does_not_expose_financial_calculation_methods():
    assert not hasattr(ScannerEngine, "portfolio_concentration")
    assert not hasattr(ScannerEngine, "total_market_value")
