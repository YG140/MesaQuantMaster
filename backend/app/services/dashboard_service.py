from datetime import datetime, timezone
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
        valuation_basis = PortfolioEngine.valuation_basis(portfolio.positions)
        patrimonio_total = PortfolioEngine.total_valuation(
            portfolio.positions,
            valuation_basis or "invested_amount",
        )
        lucro_prejuizo = (
            portfolio.total_profit
            if valuation_basis in {"market_value", "mixed"}
            else Decimal("0")
        )
        rentabilidade = (
            PortfolioEngine.profitability(portfolio.positions)
            if valuation_basis in {"market_value", "mixed"}
            else Decimal("0")
        )

        return DashboardSummary(
            patrimonio_total=patrimonio_total,
            valor_investido=portfolio.total_invested,
            lucro_prejuizo=lucro_prejuizo,
            rentabilidade=rentabilidade,
            caixa=Decimal("0"),
            ativos=PortfolioEngine.total_positions(portfolio.positions),
            operacoes=len(operations),
            proventos=Decimal("0"),
            ultima_atualizacao=datetime.now(timezone.utc),
            market_data_status=portfolio.market_data_status,
            quote_updated_at=portfolio.quote_updated_at,
            unpriced_symbols=portfolio.unpriced_symbols,
        )
