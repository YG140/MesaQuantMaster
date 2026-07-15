from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.market import MarketAssetResponse, QuoteResponse
from app.services.market_service import MarketService

router = APIRouter(
    prefix="/market",
    tags=["Mercado"],
)


@router.get(
    "/quote/{ticker}",
    response_model=QuoteResponse,
    summary="Obtem a cotacao de um ativo",
)
def get_quote(
    ticker: str,
    current_user: User = Depends(get_current_active_user),
):
    service = MarketService()
    try:
        return service.get_quote(ticker)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provider de mercado indisponivel. Tente novamente ou cadastre manualmente.",
        ) from exc


@router.get(
    "/search",
    response_model=list[MarketAssetResponse],
    summary="Pesquisa ativos por codigo ou nome",
)
def search_assets(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=10, ge=1, le=20),
    current_user: User = Depends(get_current_active_user),
):
    service = MarketService()
    try:
        return service.search_assets(q, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provider de mercado indisponivel. Tente novamente ou cadastre manualmente.",
        ) from exc


@router.get(
    "/assets/{ticker}",
    response_model=MarketAssetResponse,
    summary="Obtem dados consolidados de mercado de um ativo",
)
def get_market_asset(
    ticker: str,
    current_user: User = Depends(get_current_active_user),
):
    service = MarketService()
    try:
        asset = service.get_asset(ticker)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Provider de mercado indisponivel. Tente novamente ou cadastre manualmente.",
        ) from exc
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ativo nao encontrado no provedor de mercado.",
        )
    return asset
