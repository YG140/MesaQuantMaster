from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db

from app.models.user import User

from app.repositories.alert_repository import AlertRepository
from app.repositories.asset_repository import AssetRepository

from app.schemas.alert import (
    AlertCreate,
    AlertResponse,
    AlertUpdate,
)

from app.services.alert_service import AlertService

router = APIRouter(
    prefix="/alerts",
    tags=["Alertas"],
)


def get_service(db: Session) -> AlertService:
    return AlertService(
        repository=AlertRepository(db),
        asset_repository=AssetRepository(db),
    )


@router.post(
    "",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_alert(
    alert: AlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)

    try:
        return service.create(current_user, alert)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "",
    response_model=list[AlertResponse],
)
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.list(current_user)


@router.put(
    "/{alert_id}",
    response_model=AlertResponse,
)
def update_alert(
    alert_id: UUID,
    alert: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)

    try:
        current = service.get_by_id(alert_id)

        if current.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado.",
            )

        return service.update(alert_id, alert)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_alert(
    alert_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)

    try:
        current = service.get_by_id(alert_id)

        if current.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado.",
            )

        service.delete(alert_id)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
