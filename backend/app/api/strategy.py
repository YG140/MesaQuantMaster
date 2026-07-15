from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_active_user

from app.models.user import User

from app.schemas.strategy import (
    StrategyRequest,
    StrategyResponse,
    StrategyScoreRequest,
    StrategyScoreResponse,
)

from app.services.strategy_service import StrategyService

router = APIRouter(
    prefix="/strategy",
    tags=["Strategy Engine"],
)


def get_service() -> StrategyService:
    return StrategyService()


@router.post(
    "/analyze",
    response_model=StrategyResponse,
)
def analyze_strategy(
    request: StrategyRequest,
    current_user: User = Depends(get_current_active_user),
):

    service = get_service()

    try:

        return service.analyze(
            strategy=request.strategy,
            indicators=request.indicators,
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.post(
    "/score",
    response_model=StrategyScoreResponse,
)
def calculate_score(
    request: StrategyScoreRequest,
    current_user: User = Depends(get_current_active_user),
):

    service = get_service()

    score = service.score(
        **request.criteria,
    )

    return StrategyScoreResponse(
        score=score,
    )
