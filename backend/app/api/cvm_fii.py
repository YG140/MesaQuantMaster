from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_superuser
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models.user import User
from app.providers.cvm_fii_open_data_provider import CvmFiiOpenDataProvider
from app.repositories.cvm_fii_repository import CvmFiiRepository
from app.schemas.cvm_fii import CvmFiiSyncAccepted, CvmFiiSyncRequest, CvmFiiSyncStatus
from app.services.cvm_fii_service import CvmFiiService

router = APIRouter(prefix="/intelligence/cvm-fii", tags=["CVM FII"])


def cvm_fii_service(db: Session) -> CvmFiiService:
    provider = CvmFiiOpenDataProvider(
        cache_dir=Path(settings.CVM_FII_CACHE_DIR),
        timeout_seconds=settings.CVM_FII_TIMEOUT_SECONDS,
        max_download_bytes=settings.CVM_FII_MAX_DOWNLOAD_BYTES,
        max_uncompressed_bytes=settings.CVM_FII_MAX_UNCOMPRESSED_BYTES,
        cache_ttl_hours=settings.CVM_FII_CACHE_TTL_HOURS,
    )
    return CvmFiiService(CvmFiiRepository(db), provider)


def run_sync(year: int) -> None:
    db = SessionLocal()
    try:
        cvm_fii_service(db).synchronize(year)
    finally:
        db.close()


@router.post(
    "/sync", response_model=CvmFiiSyncAccepted, status_code=status.HTTP_202_ACCEPTED
)
def start_sync(
    request: CvmFiiSyncRequest,
    tasks: BackgroundTasks,
    current_user: User = Depends(get_current_superuser),
):
    tasks.add_task(run_sync, request.year)
    return CvmFiiSyncAccepted(
        status="accepted",
        message="Sincronização do Informe Trimestral de FII agendada no processo da API.",
        year=request.year,
    )


@router.get("/sync/status", response_model=list[CvmFiiSyncStatus])
def sync_status(
    db: Session = Depends(get_db), _user: User = Depends(get_current_active_user)
):
    return CvmFiiRepository(db).list_runs()
