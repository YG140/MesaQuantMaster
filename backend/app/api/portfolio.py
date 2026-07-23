from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository
from app.schemas.portfolio import (
    InitialPortfolioImport,
    InitialPortfolioImportResponse,
    InvestmentCreate,
    InvestmentCreateResponse,
    PortfolioSummary,
    PositionDeleteRequest,
    PositionDeleteResponse,
)
from app.services.portfolio_service import PortfolioService
from app.services.operation_service import OperationService
from app.schemas.operation import OperationResponse

router = APIRouter(
    prefix="/portfolio",
    tags=["Carteira"],
)


@router.get(
    "/positions/{asset_id}/operations",
    response_model=list[OperationResponse],
)
def list_position_operations(
    asset_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OperationService(
        OperationRepository(db), AssetRepository(db), BrokerageRepository(db)
    )
    try:
        return service.list_position_operations(current_user.id, asset_id)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/positions/{asset_id}",
    response_model=PositionDeleteResponse,
    summary="Exclui somente as operações do usuário que formam uma posição",
)
def delete_position(
    asset_id: UUID,
    confirmation: PositionDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = OperationService(
        OperationRepository(db), AssetRepository(db), BrokerageRepository(db)
    )
    try:
        deleted = service.delete_position(
            current_user.id,
            asset_id,
            confirmation.expected_operations,
            confirmation.ticker,
        )
        return PositionDeleteResponse(
            asset_id=asset_id,
            ticker=confirmation.ticker.strip().upper(),
            operations_deleted=deleted,
            message="Posição excluída da carteira.",
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


def get_service(db: Session) -> PortfolioService:
    return PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
        brokerage_repository=BrokerageRepository(db),
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


@router.post(
    "/investments",
    response_model=InvestmentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona um investimento criando ativo e compra quando necessario",
)
def add_investment(
    investment: InvestmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    try:
        return service.add_investment(current_user.id, investment)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/import-initial",
    response_model=InitialPortfolioImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Importa uma carteira inicial consolidada",
)
def import_initial_portfolio(
    portfolio_import: InitialPortfolioImport,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    try:
        return service.import_initial_portfolio(current_user.id, portfolio_import)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
