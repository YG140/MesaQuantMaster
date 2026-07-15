from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository
from app.schemas.portfolio import PortfolioSummary
from app.services.portfolio_service import PortfolioService

router = APIRouter(
    prefix="/portfolio",
    tags=["Carteira"],
)


def get_service(db: Session) -> PortfolioService:
    return PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
    )


@router.get(
    "",
    response_model=PortfolioSummary,
    summary="Retorna a carteira consolidada do usuário",
)
def get_portfolio(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.calculate(current_user.id)
