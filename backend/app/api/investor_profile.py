from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.api.intelligence import get_service as get_intelligence_service
from app.core.database import get_db
from app.models.user import User
from app.repositories.investor_profile_repository import InvestorProfileRepository
from app.schemas.investor_profile import (
    InvestorProfileAnswers,
    InvestorProfileEvaluationResponse,
    InvestorProfileRead,
    InvestorProfileStatusResponse,
)
from app.services.investor_profile_service import InvestorProfileService

router = APIRouter(prefix="/investor-profile", tags=["Perfil do Investidor"])


def get_service(db: Session) -> InvestorProfileService:
    return InvestorProfileService(
        repository=InvestorProfileRepository(db),
        policy_service=get_intelligence_service(db),
    )


@router.get("/status", response_model=InvestorProfileStatusResponse)
def get_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return get_service(db).get_status(current_user.id)


@router.get("", response_model=InvestorProfileRead)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return get_service(db).get_profile(current_user.id)


@router.put("/answers", response_model=InvestorProfileRead)
def save_answers(
    data: InvestorProfileAnswers,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return get_service(db).save_answers(current_user.id, data)


@router.post("/evaluate", response_model=InvestorProfileEvaluationResponse)
def evaluate(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return get_service(db).evaluate(current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/confirm", response_model=InvestorProfileRead)
def confirm(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return get_service(db).confirm(current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/review", response_model=InvestorProfileRead)
def review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return get_service(db).review(current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
