from fastapi import APIRouter, Depends

from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.market import QuoteResponse
from app.services.market_service import MarketService

router = APIRouter(
    prefix="/market",
    tags=["Mercado"],
)


@router.get(
    "/quote/{ticker}",
    response_model=QuoteResponse,
    summary="Obtém a cotação de um ativo",
)
def get_quote(
    ticker: str,
    current_user: User = Depends(get_current_active_user),
):
    service = MarketService()
    return service.get_quote(ticker)
