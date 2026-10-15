from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_superuser
from app.core.database import get_db
from app.models.user import User
from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketAuthenticationError,
    MarketInvalidResponseError,
    MarketPermissionError,
    MarketProviderUnavailableError,
    MarketRateLimitError,
)
from app.schemas.market import (
    MarketAssetResponse,
    MarketProfileResponse,
    QuoteResponse,
    QuotesRequest,
    QuotesResponse,
    ProviderCapabilitiesResponse,
)
from app.services.market_service import MarketService
from app.services.bcb_fx_service import BcbPtaxFxService, FxUnavailableError, FxReference
from app.repositories.asset_repository import AssetRepository
from app.repositories.market_sync_repository import MarketSyncRepository
from app.schemas.market_sync import MarketSyncReport, MarketSyncRequest
from app.services.market_sync_service import MarketSyncService

router = APIRouter(
    prefix="/market",
    tags=["Mercado"],
)


def get_market_sync_service(db: Session = Depends(get_db)) -> MarketSyncService:
    return MarketSyncService(
        asset_repository=AssetRepository(db),
        sync_repository=MarketSyncRepository(db),
        provider=MarketService(),
    )


@router.post("/sync", response_model=MarketSyncReport)
def dry_run_market_sync(
    request: MarketSyncRequest,
    _user: User = Depends(get_current_superuser),
    service: MarketSyncService = Depends(get_market_sync_service),
):
    """Preview administrativo; apply é permitido somente pelo comando local."""
    return service.run(request, apply=False)


@router.get("/fx/usd-brl", response_model=FxReference)
def get_usd_brl_reference(_user: User = Depends(get_current_active_user)):
    """PTAX venda oficial para leitura, jamais taxa executável de compra."""
    try:
        return BcbPtaxFxService().latest_usd_brl()
    except FxUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/provider-capabilities", response_model=ProviderCapabilitiesResponse)
def get_provider_capabilities(current_user: User = Depends(get_current_active_user)):
    return MarketService().provider_capabilities()


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
        raise _market_http_error(exc) from exc


@router.post(
    "/quotes",
    response_model=QuotesResponse,
    summary="Obtem cotacoes em lote",
)
def get_quotes(
    payload: QuotesRequest,
    current_user: User = Depends(get_current_active_user),
):
    service = MarketService()
    try:
        return service.get_quotes(payload.symbols)
    except Exception as exc:
        raise _market_http_error(exc) from exc


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
        raise _market_http_error(exc) from exc


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
        raise _market_http_error(exc) from exc
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ativo nao encontrado no provedor de mercado.",
        )
    return asset


@router.get(
    "/profile/{ticker}",
    response_model=MarketProfileResponse,
    summary="Obtem perfil de um ativo",
)
def get_profile(
    ticker: str,
    current_user: User = Depends(get_current_active_user),
):
    service = MarketService()
    try:
        return service.get_profile(ticker)
    except Exception as exc:
        raise _market_http_error(exc) from exc


def _market_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MarketAssetNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ativo nao encontrado no provedor de mercado.",
        )
    if isinstance(exc, MarketAuthenticationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BRAPI_API_KEY ausente ou invalida. Configure a chave no backend.",
        )
    if isinstance(exc, MarketPermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recurso de mercado nao permitido pelo plano configurado.",
        )
    if isinstance(exc, MarketRateLimitError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de consultas ao mercado atingido. Tente novamente mais tarde.",
        )
    if isinstance(exc, MarketProviderUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nao foi possivel consultar o mercado agora.",
        )
    if isinstance(exc, MarketInvalidResponseError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta invalida do provedor de mercado.",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Provider de mercado indisponivel. Tente novamente ou cadastre manualmente.",
    )
