from decimal import Decimal

from app.engines.portfolio_engine import PortfolioEngine
from app.engines.scanner_engine import ScannerEngine
from app.services.market_service import MarketService
from app.services.portfolio_service import PortfolioService


class ScannerService:

    def __init__(
        self,
        portfolio_service: PortfolioService,
        market_service: MarketService,
    ):
        self.portfolio_service = portfolio_service
        self.market_service = market_service

    def analyze_portfolio(
        self,
        user_id,
    ):

        portfolio = self.portfolio_service.calculate(user_id)

        concentration = PortfolioEngine.concentration(portfolio.positions)

        return {
            "total_invested": portfolio.total_invested,
            "total_market_value": portfolio.total_market_value,
            "positions": portfolio.positions,
            "concentration": concentration,
        }

    def check_price_above(
        self,
        ticker: str,
        target: Decimal,
    ) -> bool:

        quote = self.market_service.get_quote(ticker)

        return ScannerEngine.price_above(
            quote,
            target,
        )

    def check_price_below(
        self,
        ticker: str,
        target: Decimal,
    ) -> bool:

        quote = self.market_service.get_quote(ticker)

        return ScannerEngine.price_below(
            quote,
            target,
        )
