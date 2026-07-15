from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user

from app.core.database import get_db

from app.models.user import User

from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository

from app.schemas.scanner import (
    PriceCheckRequest,
    PriceCheckResponse,
    PortfolioAnalysisResponse,
)

from app.services.market_service import MarketService
from app.services.portfolio_service import PortfolioService
from app.services.scanner_service import ScannerService

router = APIRouter(
    prefix="/scanner",
    tags=["Scanner Quantitativo"],
)


def get_service(db: Session):

    portfolio_service = PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
    )

    market_service = MarketService()

    return ScannerService(
        portfolio_service=portfolio_service,
        market_service=market_service,
    )


@router.get(
    "/portfolio",
    response_model=PortfolioAnalysisResponse,
)
def analyze_portfolio(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    return service.analyze_portfolio(current_user.id)


@router.post(
    "/price-above",
    response_model=PriceCheckResponse,
)
def price_above(
    data: PriceCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    return PriceCheckResponse(
        ticker=data.ticker,
        target_price=data.target_price,
        triggered=service.check_price_above(
            data.ticker,
            data.target_price,
        ),
    )


@router.post(
    "/price-below",
    response_model=PriceCheckResponse,
)
def price_below(
    data: PriceCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):

    service = get_service(db)

    return PriceCheckResponse(
        ticker=data.ticker,
        target_price=data.target_price,
        triggered=service.check_price_below(
            data.ticker,
            data.target_price,
        ),
    )
