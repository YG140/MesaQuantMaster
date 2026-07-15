from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.backtesting import BacktestingRequest, BacktestingResult
from app.services.backtesting_service import BacktestingService

router = APIRouter(
    prefix="/backtesting",
    tags=["Backtesting"],
)


def get_service() -> BacktestingService:
    return BacktestingService()


@router.post(
    "/run",
    response_model=BacktestingResult,
    summary="Executa um backtest long-only de um unico ativo",
)
def run_backtest(
    request: BacktestingRequest,
    current_user: User = Depends(get_current_active_user),
):
    service = get_service()

    try:
        return service.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
