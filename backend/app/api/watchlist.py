from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db

from app.models.user import User

from app.repositories.asset_repository import AssetRepository
from app.repositories.watchlist_repository import WatchlistRepository

from app.schemas.watchlist import (
    WatchlistCreate,
    WatchlistResponse,
)

from app.services.watchlist_service import WatchlistService

router = APIRouter(
    prefix="/watchlist",
    tags=["Watchlist"],
)


def get_service(db: Session):

    return WatchlistService(
        repository=WatchlistRepository(db),
        asset_repository=AssetRepository(db),
    )


@router.post(
    "",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_watchlist(
    data: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    try:
        return service.create(current_user, data)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get(
    "",
    response_model=list[WatchlistResponse],
)
def list_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    return service.list(current_user)


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_watchlist(
    asset_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    try:
        service.delete(current_user, asset_id)

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )
