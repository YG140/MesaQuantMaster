from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.engines.indicator_catalog import MACRO_INDICATOR_REGISTRY
from app.models.user import User
from app.repositories.asset_repository import AssetRepository
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.operation_repository import OperationRepository
from app.repositories.manual_indicator_repository import ManualIndicatorRepository
from app.repositories.indicator_snapshot_repository import IndicatorSnapshotRepository
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    PortfolioDiagnosis,
    PortfolioIntelligenceResponse,
    PortfolioPolicyRead,
    PortfolioPolicyUpsert,
)
from app.schemas.market_intelligence import (
    AnalyzeAssetsRequest,
    AssetIntelligenceHistoryResponse,
    AssetIntelligenceSnapshot,
    BatchAssetAnalysisResponse,
    MacroIndicatorSnapshot,
    NormalizedIndicator,
)
from app.services.intelligence_service import PortfolioIntelligenceService
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.manual_indicator_service import ManualIndicatorService
from app.schemas.manual_indicator import (
    ManualIndicatorCreate,
    ManualIndicatorResponse,
    ManualIndicatorUpdate,
)
from app.services.market_service import MarketService
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/intelligence", tags=["Inteligência"])


def get_service(db: Session) -> PortfolioIntelligenceService:
    portfolio_service = PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
        brokerage_repository=BrokerageRepository(db),
    )
    return PortfolioIntelligenceService(
        portfolio_service=portfolio_service,
        policy_repository=PortfolioPolicyRepository(db),
    )


def get_market_intelligence_service(db: Session) -> MarketIntelligenceService:
    portfolio_service = PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=AssetRepository(db),
        brokerage_repository=BrokerageRepository(db),
        market_service=MarketService(),
    )
    return MarketIntelligenceService(
        market_service=MarketService(),
        asset_repository=AssetRepository(db),
        portfolio_service=portfolio_service,
        policy_repository=PortfolioPolicyRepository(db),
        snapshot_repository=IndicatorSnapshotRepository(db),
    )


def get_manual_indicator_service(db: Session) -> ManualIndicatorService:
    return ManualIndicatorService(ManualIndicatorRepository(db), AssetRepository(db))


def manual_response(item) -> ManualIndicatorResponse:
    return ManualIndicatorResponse.model_validate(item).model_copy(
        update={"freshness_status": ManualIndicatorService.freshness(item)}
    )


@router.get("/portfolio", response_model=PortfolioIntelligenceResponse)
def get_portfolio_intelligence(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.get_portfolio_intelligence(current_user.id)


@router.get("/diagnosis", response_model=PortfolioDiagnosis)
def get_portfolio_diagnosis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.get_portfolio_intelligence(current_user.id).diagnosis


@router.get("/policy", response_model=PortfolioPolicyRead | None)
def get_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.get_policy(current_user.id)


@router.post("/policy", response_model=PortfolioPolicyRead, status_code=201)
def create_policy(
    data: PortfolioPolicyUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.save_policy(current_user.id, data)


@router.put("/policy", response_model=PortfolioPolicyRead)
def update_policy(
    data: PortfolioPolicyUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.save_policy(current_user.id, data)


@router.post("/build-portfolio", response_model=BuildPortfolioResponse)
def build_portfolio(
    data: BuildPortfolioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    return service.build_portfolio(current_user.id, data)


@router.post("/assets/analyze", response_model=BatchAssetAnalysisResponse)
def analyze_assets(
    data: AnalyzeAssetsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_market_intelligence_service(db)
    return service.analyze_assets(data, current_user.id)


@router.get("/assets/{symbol}", response_model=AssetIntelligenceSnapshot)
def get_asset_intelligence(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_market_intelligence_service(db)
    return service.analyze_asset(symbol, current_user.id)


@router.get("/assets/{symbol}/indicators", response_model=list[NormalizedIndicator])
def get_asset_indicators(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_market_intelligence_service(db)
    return service.indicators_for_asset(symbol, current_user.id)


@router.get(
    "/assets/{symbol}/manual-indicators", response_model=list[ManualIndicatorResponse]
)
def list_manual_indicators(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return [
            manual_response(item)
            for item in get_manual_indicator_service(db).list(current_user.id, symbol)
        ]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/assets/{symbol}/manual-indicators",
    response_model=ManualIndicatorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_indicator(
    symbol: str,
    data: ManualIndicatorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return manual_response(
            get_manual_indicator_service(db).create(current_user.id, symbol, data)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/assets/{symbol}/manual-indicators/{indicator_id}",
    response_model=ManualIndicatorResponse,
)
def update_manual_indicator(
    symbol: str,
    indicator_id: UUID,
    data: ManualIndicatorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_manual_indicator_service(db)
    service.asset_for_symbol(symbol)
    try:
        return manual_response(service.update(current_user.id, indicator_id, data))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/assets/{symbol}/manual-indicators/{indicator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_manual_indicator(
    symbol: str,
    indicator_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_manual_indicator_service(db)
    service.asset_for_symbol(symbol)
    try:
        service.delete(current_user.id, indicator_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/assets/{symbol}/history",
    response_model=AssetIntelligenceHistoryResponse,
)
def get_asset_intelligence_history(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_market_intelligence_service(db)
    return service.history_for_asset(symbol)


@router.get("/portfolio/recommendations", response_model=BatchAssetAnalysisResponse)
def get_portfolio_market_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_market_intelligence_service(db)
    return service.portfolio_recommendations(current_user.id)


@router.get("/macro", response_model=list[MacroIndicatorSnapshot])
def get_macro_context(
    _current_user: User = Depends(get_current_active_user),
):
    return [
        MacroIndicatorSnapshot(
            key=item.key,
            label=item.label,
            source=item.source,
            frequency=item.frequency,
            state=item.state,
        )
        for item in MACRO_INDICATOR_REGISTRY
    ]
