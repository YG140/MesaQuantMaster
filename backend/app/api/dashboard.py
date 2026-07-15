from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User

from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository

from app.schemas.dashboard import DashboardSummary

from app.services.dashboard_service import DashboardService
from app.services.portfolio_service import PortfolioService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


def get_dashboard_service(db: Session) -> DashboardService:
    portfolio_service = PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
    )

    return DashboardService(
        portfolio_service=portfolio_service,
        operation_repository=OperationRepository(db),
    )


@router.get(
    "",
    response_model=DashboardSummary,
    summary="Resumo do Dashboard",
)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_dashboard_service(db)
    return service.get_dashboard(current_user.id)
