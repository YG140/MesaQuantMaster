from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.engines.portfolio_engine import PortfolioEngine
from app.engines.risk_engine import RiskEngine
from app.schemas.portfolio import PortfolioPosition


def make_position(
    ticker: str,
    market_value: str,
    quantity: str = "1",
) -> PortfolioPosition:
    return PortfolioPosition(
        asset_id=uuid4(),
        ticker=ticker,
        asset_name=ticker,
        quantity=Decimal(quantity),
        average_price=Decimal("10"),
        invested_amount=Decimal("10"),
        market_value=Decimal(market_value),
    )


def test_concentration_is_calculated_by_portfolio_engine():
    positions = [
        make_position("AAA", "80"),
        make_position("BBB", "20"),
    ]

    concentration = PortfolioEngine.concentration(positions)

    assert concentration[0]["ticker"] == "AAA"
    assert concentration[0]["allocation"] == Decimal("80.00")
    assert concentration[1]["allocation"] == Decimal("20.00")


def test_alert_is_created_when_concentration_reaches_limit():
    concentration = [
        {
            "ticker": "AAA",
            "allocation": Decimal("20.00"),
            "market_value": Decimal("20"),
        }
    ]

    alerts = RiskEngine.concentration_alerts(concentration)

    assert alerts == [
        {
            "ticker": "AAA",
            "allocation": Decimal("20.00"),
            "message": "Concentracao acima do limite recomendado.",
        }
    ]


def test_empty_portfolio_risk_state_uses_position_count():
    assert RiskEngine.portfolio_is_empty(0) is True
    assert RiskEngine.portfolio_is_empty(1) is False


def test_total_positions_and_market_value_come_from_portfolio_engine():
    positions = [
        make_position("AAA", "80"),
        make_position("BBB", "20", quantity="0"),
    ]

    assert PortfolioEngine.total_positions(positions) == 1
    assert PortfolioEngine.total_market_value(positions) == Decimal("100")
