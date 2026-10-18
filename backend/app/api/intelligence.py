from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.engines.indicator_catalog import MACRO_INDICATOR_REGISTRY
from app.models.user import User
from app.repositories.asset_repository import AssetRepository
from app.repositories.investor_profile_repository import InvestorProfileRepository
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.operation_repository import OperationRepository
from app.repositories.manual_indicator_repository import ManualIndicatorRepository
from app.repositories.indicator_snapshot_repository import IndicatorSnapshotRepository
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.repositories.portfolio_recommendation_history_repository import PortfolioRecommendationHistoryRepository
from app.schemas.portfolio_recommendation_history import RecommendationHistorySummary, RecommendationHistoryDetail
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.repositories.cvm_fii_repository import CvmFiiRepository
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    WealthGoalSetting,
    FinancialFutureResponse,
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
from app.services.official_source_verification_service import OfficialSourceVerificationService
from app.services.pre_purchase_audit_service import PrePurchaseAuditService
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
    market_service = MarketService()
    asset_repository = AssetRepository(db)
    portfolio_service = PortfolioService(
        operation_repository=OperationRepository(db),
        asset_repository=asset_repository,
        brokerage_repository=BrokerageRepository(db),
        market_service=market_service,
    )
    policy_repository = PortfolioPolicyRepository(db)
    market_intelligence = MarketIntelligenceService(
        market_service=market_service,
        asset_repository=asset_repository,
        portfolio_service=portfolio_service,
        policy_repository=policy_repository,
        snapshot_repository=IndicatorSnapshotRepository(db),
        manual_repository=ManualIndicatorRepository(db),
        cvm_repository=CvmFinancialRepository(db),
        cvm_fii_repository=CvmFiiRepository(db),
    )
    return PortfolioIntelligenceService(
        portfolio_service=portfolio_service,
        policy_repository=policy_repository,
        asset_repository=asset_repository,
        market_intelligence_service=market_intelligence,
        investor_profile_repository=InvestorProfileRepository(db),
        pre_purchase_audit_service=PrePurchaseAuditService(
            OfficialSourceVerificationService(CvmFinancialRepository(db))
        ),
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
        manual_repository=ManualIndicatorRepository(db),
        cvm_repository=CvmFinancialRepository(db),
        cvm_fii_repository=CvmFiiRepository(db),
    )


def get_manual_indicator_service(db: Session) -> ManualIndicatorService:
    return ManualIndicatorService(ManualIndicatorRepository(db), AssetRepository(db))


def manual_response(item) -> ManualIndicatorResponse:
    return ManualIndicatorResponse.model_validate(
        {
            "id": item.id,
            "asset_id": item.asset_id,
            "indicator_key": item.indicator_key,
            "value": item.value,
            "unit": item.unit,
            "reference_date": item.reference_date,
            "source_type": item.source_type,
            "source_description": item.source_description,
            "notes": item.notes,
            "freshness_status": ManualIndicatorService.freshness(item),
            "created_at": _aware_datetime(item.created_at),
            "updated_at": _aware_datetime(item.updated_at),
        }
    )


def _aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@router.get("/portfolio", response_model=PortfolioIntelligenceResponse)
def get_portfolio_intelligence(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    try:
        return service.get_portfolio_intelligence(current_user.id)
    except ValueError as exc:
        # Inconsistencia de dominio na carteira (ex.: venda registrada acima
        # da quantidade acumulada comprada) -- nunca deve chegar como 500
        # generico. A mensagem do ValueError ja e de dominio (ver
        # PortfolioEngine.calculate_positions), sem stack trace/SQL/detalhe
        # interno, entao e reaproveitada diretamente.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/diagnosis", response_model=PortfolioDiagnosis)
def get_portfolio_diagnosis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    try:
        return service.get_portfolio_intelligence(current_user.id).diagnosis
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


@router.get("/financial-goal", response_model=WealthGoalSetting | None)
def get_financial_goal(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return get_service(db).get_wealth_goal(current_user.id)


@router.put("/financial-goal", response_model=WealthGoalSetting)
def save_financial_goal(
    goal: WealthGoalSetting,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return get_service(db).save_wealth_goal(current_user.id, goal)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/financial-future", response_model=FinancialFutureResponse | None)
def get_financial_future(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return get_service(db).get_financial_future(current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/build-portfolio", response_model=BuildPortfolioResponse)
def build_portfolio(
    data: BuildPortfolioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = get_service(db)
    response = service.build_portfolio(current_user.id, data)
    # Append exactly one user-scoped decision for every successful explicit
    # build, even with an empty selection. If storage fails, do not claim
    # that the recommendation was saved.
    entry = PortfolioRecommendationHistoryRepository(db).save(
        current_user.id, data, response
    )
    return response.model_copy(update={"history_id": entry.id})


@router.get(
    "/recommendation-history",
    response_model=list[RecommendationHistorySummary],
)
def list_recommendation_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Paginação inválida.")
    repo = PortfolioRecommendationHistoryRepository(db)
    return [
        RecommendationHistorySummary(
            id=item.id,
            generated_at=_aware_datetime(item.generated_at),
            created_at=_aware_datetime(item.created_at),
            engine_version=item.engine_version,
            status=item.status,
            selected_count=item.selected_count,
            considered_count=item.considered_count,
            content_sha256=item.content_sha256,
        )
        for item in repo.list_for_user(current_user.id, limit=limit, offset=offset)
    ]


@router.get(
    "/recommendation-history/{run_id}",
    response_model=RecommendationHistoryDetail,
)
def get_recommendation_history(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    repo = PortfolioRecommendationHistoryRepository(db)
    item = repo.get_for_user(current_user.id, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    try:
        evidence = repo.verify(item)
    except ValueError:
        raise HTTPException(
            status_code=409, detail="Registro histórico com integridade comprometida."
        )
    return RecommendationHistoryDetail(
        id=item.id,
        generated_at=_aware_datetime(item.generated_at),
        created_at=_aware_datetime(item.created_at),
        engine_version=item.engine_version,
        status=item.status,
        selected_count=item.selected_count,
        considered_count=item.considered_count,
        content_sha256=item.content_sha256,
        record=evidence,
    )


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
        items = get_manual_indicator_service(db).list(current_user.id, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [manual_response(item) for item in items]


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
        item = get_manual_indicator_service(db).create(current_user.id, symbol, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return manual_response(item)


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
        item = service.update(current_user.id, indicator_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return manual_response(item)


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
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    service = get_market_intelligence_service(db)
    return service.resolver.resolve_macro(
        MACRO_INDICATOR_REGISTRY, datetime.now(timezone.utc)
    )
