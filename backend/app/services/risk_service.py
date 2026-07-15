from app.engines.portfolio_engine import PortfolioEngine
from app.engines.risk_engine import RiskEngine
from app.services.portfolio_service import PortfolioService


class RiskService:

    def __init__(
        self,
        portfolio_service: PortfolioService,
    ):
        self.portfolio_service = portfolio_service

    def analyze_portfolio(
        self,
        user_id,
    ):

        portfolio = self.portfolio_service.calculate(user_id)

        concentration = PortfolioEngine.concentration(portfolio.positions)

        alerts = RiskEngine.concentration_alerts(concentration)

        total_positions = PortfolioEngine.total_positions(portfolio.positions)

        return {
            "total_market_value": portfolio.total_market_value,
            "total_positions": total_positions,
            "portfolio_is_empty": RiskEngine.portfolio_is_empty(total_positions),
            "concentration": concentration,
            "alerts": alerts,
        }
