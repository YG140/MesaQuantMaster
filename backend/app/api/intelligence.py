from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.asset_repository import AssetRepository
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.operation_repository import OperationRepository
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    PortfolioDiagnosis,
    PortfolioIntelligenceResponse,
    PortfolioPolicyRead,
    PortfolioPolicyUpsert,
)
from app.services.intelligence_service import PortfolioIntelligenceService
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/intelligence", tags=["Inteligência"])


def get_service(db: Session) -> PortfolioIntelligenceService:
    portfolio_service = PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
        brokerage_repository=BrokerageRepository(db),
    )
    return PortfolioIntelligenceService(
        portfolio_service=portfolio_service,
        policy_repository=PortfolioPolicyRepository(db),
    )


@router.get("/portfolio", response_model=PortfolioIntelligenceResponse)
def get_portfolio_intelligence(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.get_portfolio_intelligence(current_user.id)


@router.get("/diagnosis", response_model=PortfolioDiagnosis)
def get_portfolio_diagnosis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.get_portfolio_intelligence(current_user.id).diagnosis


@router.get("/policy", response_model=PortfolioPolicyRead | None)
def get_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.get_policy(current_user.id)


@router.post("/policy", response_model=PortfolioPolicyRead, status_code=201)
def create_policy(
    data: PortfolioPolicyUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.save_policy(current_user.id, data)


@router.put("/policy", response_model=PortfolioPolicyRead)
def update_policy(
    data: PortfolioPolicyUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.save_policy(current_user.id, data)


@router.post("/build-portfolio", response_model=BuildPortfolioResponse)
def build_portfolio(
    data: BuildPortfolioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.build_portfolio(current_user.id, data)
