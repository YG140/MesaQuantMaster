from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user

from app.core.database import get_db

from app.models.user import User

from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository

from app.schemas.risk import RiskSummary

from app.services.portfolio_service import PortfolioService
from app.services.risk_service import RiskService

router = APIRouter(
    prefix="/risk",
    tags=["Risk Engine"],
)


def get_service(db: Session):

    portfolio_service = PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
    )

    return RiskService(
        portfolio_service=portfolio_service,
    )


@router.get(
    "",
    response_model=RiskSummary,
)
def analyze_risk(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    return service.analyze_portfolio(current_user.id)
