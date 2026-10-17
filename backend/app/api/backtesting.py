from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.backtesting import BacktestingRequest, BacktestingResult
from app.services.backtesting_service import BacktestingService
from app.schemas.portfolio_validation import WalkForwardRequest, WalkForwardResult
from app.engines.portfolio_walk_forward_engine import PortfolioWalkForwardEngine

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


@router.post(
    "/portfolio-walk-forward",
    response_model=WalkForwardResult,
    summary="Simulação histórica de carteira e benchmark, com barreiras anti-look-ahead",
)
def run_portfolio_walk_forward(
    request: WalkForwardRequest,
    current_user: User = Depends(get_current_active_user),
):
    # Endpoint autenticado, determinístico, sem alteração de carteira ou banco.
    # Os resultados são simulações porque a origem do histórico informado
    # no corpo NÃO pode ser auditada apenas por esta API.
    try:
        return PortfolioWalkForwardEngine.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
