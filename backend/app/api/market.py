from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_active_user
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

router = APIRouter(
    prefix="/market",
    tags=["Mercado"],
)


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
