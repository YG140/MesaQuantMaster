from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models.user import User
from app.providers.cvm_open_data_provider import CvmOpenDataProvider
from app.repositories.asset_repository import AssetRepository
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.schemas.cvm_financial import (
    AssetCvmLinkResponse,
    AssetCvmLinkUpdate,
    CvmAvailableDocument,
    CvmIssuerResponse,
    CvmSyncAccepted,
    CvmSyncRequest,
    CvmSyncStatus,
)
from app.services.cvm_financial_service import CvmFinancialService

router = APIRouter(prefix="/intelligence/cvm", tags=["CVM"])


def cvm_service(db: Session) -> CvmFinancialService:
    provider = CvmOpenDataProvider(
        cache_dir=Path(settings.CVM_CACHE_DIR),
        timeout_seconds=settings.CVM_TIMEOUT_SECONDS,
        max_download_bytes=settings.CVM_MAX_DOWNLOAD_BYTES,
        max_uncompressed_bytes=settings.CVM_MAX_UNCOMPRESSED_BYTES,
        cache_ttl_hours=settings.CVM_CACHE_TTL_HOURS,
    )
    return CvmFinancialService(
        CvmFinancialRepository(db), AssetRepository(db), provider
    )


def run_sync(document_type: str, year: int) -> None:
    db = SessionLocal()
    try:
        cvm_service(db).synchronize(document_type, year)
    finally:
        db.close()


@router.post(
    "/sync", response_model=CvmSyncAccepted, status_code=status.HTTP_202_ACCEPTED
)
def start_sync(
    request: CvmSyncRequest,
    tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores podem iniciar a sincronização CVM.",
        )
    tasks.add_task(run_sync, request.document_type, request.year)
    return CvmSyncAccepted(
        status="accepted",
        message="Sincronização CVM agendada no processo da API.",
        document_type=request.document_type,
        year=request.year,
    )


@router.get("/sync/status", response_model=list[CvmSyncStatus])
def sync_status(
    db: Session = Depends(get_db), _user: User = Depends(get_current_active_user)
):
    return CvmFinancialRepository(db).list_runs()


@router.get("/documents", response_model=list[CvmAvailableDocument])
def available_documents(
    db: Session = Depends(get_db), _user: User = Depends(get_current_active_user)
):
    return [
        CvmAvailableDocument(document_type=kind, year=year)
        for kind, year in CvmFinancialRepository(db).available_documents()
    ]


@router.get("/issuers", response_model=list[CvmIssuerResponse])
def list_issuers(
    db: Session = Depends(get_db), _user: User = Depends(get_current_active_user)
):
    return CvmFinancialRepository(db).list_issuers()


@router.get("/assets/{asset_id}/issuer", response_model=AssetCvmLinkResponse)
def asset_issuer(
    asset_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    try:
        return cvm_service(db).asset_link(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/assets/{asset_id}/issuer", response_model=AssetCvmLinkResponse)
def link_asset_issuer(
    asset_id: UUID,
    payload: AssetCvmLinkUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_active_user),
):
    service = cvm_service(db)
    try:
        service.link_asset(asset_id, payload.issuer_id)
        return service.asset_link(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
