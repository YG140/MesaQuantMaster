from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.asset_repository import AssetRepository
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.operation_repository import OperationRepository
from app.schemas.operation import (
    OperationCreate,
    OperationResponse,
    OperationUpdate,
)
from app.services.operation_service import OperationService

router = APIRouter(
    prefix="/operations",
    tags=["Operações"],
)


def get_service(db: Session) -> OperationService:
    return OperationService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
        brokerage_repository=BrokerageRepository(db),
    )


@router.post(
    "",
    response_model=OperationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_operation(
    operation: OperationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)

    try:
        return service.create(current_user, operation)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "",
    response_model=list[OperationResponse],
)
def list_operations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.list_by_user(current_user.id)


@router.get(
    "/{operation_id}",
    response_model=OperationResponse,
)
def get_operation(
    operation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)

    try:
        operation = service.get_by_id(operation_id)

        if operation.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado.",
            )

        return operation

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put(
    "/{operation_id}",
    response_model=OperationResponse,
)
def update_operation(
    operation_id: UUID,
    operation: OperationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)

    try:
        current = service.get_by_id(operation_id)

        if current.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado.",
            )

        return service.update(operation_id, operation)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete(
    "/{operation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_operation(
    operation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)

    try:
        current = service.get_by_id(operation_id)

        if current.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado.",
            )

        service.delete(operation_id)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
