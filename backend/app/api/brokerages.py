from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.brokerage_repository import BrokerageRepository
from app.schemas.brokerage import BrokerageCreate, BrokerageResponse
from app.services.brokerage_service import BrokerageService

router = APIRouter(
    prefix="/brokerages",
    tags=["Corretoras"],
)


def get_service(db: Session) -> BrokerageService:
    return BrokerageService(BrokerageRepository(db))


@router.post(
    "",
    response_model=BrokerageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_brokerage(
    brokerage: BrokerageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    try:
        return service.create(current_user.id, brokerage.name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[BrokerageResponse],
)
def list_brokerages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.list_by_user(current_user.id)
