from datetime import datetime
from decimal import Decimal

from app.engines.portfolio_engine import PortfolioEngine
from app.repositories.operation_repository import OperationRepository
from app.services.portfolio_service import PortfolioService
from app.schemas.dashboard import DashboardSummary


class DashboardService:
    def __init__(
        self,
        portfolio_service: PortfolioService,
        operation_repository: OperationRepository,
    ):
        self.portfolio_service = portfolio_service
        self.operation_repository = operation_repository

    def get_dashboard(self, user_id):
        portfolio = self.portfolio_service.calculate(user_id)

        operations = self.operation_repository.list_by_user(user_id)

        return DashboardSummary(
            patrimonio_total=portfolio.total_market_value,
            valor_investido=portfolio.total_invested,
            lucro_prejuizo=portfolio.total_profit,
            rentabilidade=PortfolioEngine.profitability(portfolio.positions),
            caixa=Decimal("0"),
            ativos=PortfolioEngine.total_positions(portfolio.positions),
            operacoes=len(operations),
            proventos=Decimal("0"),
            ultima_atualizacao=datetime.utcnow(),
        )
