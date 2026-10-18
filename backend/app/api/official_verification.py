"""Endpoint apenas de consulta a documentos oficiais, sem efeito em ordens.

SEC = filings de empresa americana listada (CIK + ticker + bolsa).
Brasil = CVM oficial previamente sincronizada (não preço intraday B3).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.asset_repository import AssetRepository
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.repositories.cvm_fii_repository import CvmFiiRepository
from app.services.official_source_verification_service import (
    OfficialSourceVerificationService, OfficialVerification
)

router = APIRouter(prefix="/intelligence", tags=["Inteligência"])


@router.get("/official-verification/{symbol}", response_model=OfficialVerification)
def verify_official_financial_data(
    symbol: str,
    cik: str | None = Query(default=None, min_length=1, max_length=10, pattern=r"^[0-9]+$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """CIK opcional somente para ações dos EUA; nunca registrar dados do usuário."""
    if not 1 <= len(symbol) <= 20:
        raise HTTPException(status_code=422, detail="Símbolo inválido.")
    asset = AssetRepository(db).get_by_ticker(symbol.upper().strip())
    if asset is None:
        raise HTTPException(status_code=404, detail="Ativo não cadastrado.")
    kind = asset.asset_type.lower().strip()
    service = OfficialSourceVerificationService(
        CvmFinancialRepository(db), fii_repository=CvmFiiRepository(db)
    )
    if kind in {"stock", "acao", "ação", "ações"} and asset.currency.upper() == "BRL":
        return service.verify_brazil(asset)
    if kind in {"fii", "fundos imobiliários"} and asset.currency.upper() == "BRL":
        return service.verify_fii(asset)
    if kind in {"international", "ativo internacional", "ativos internacionais"} and asset.currency.upper() == "USD":
        return service.verify_sec(asset, cik)
    raise HTTPException(status_code=422, detail=(
        "Primeira etapa de verificação oficial cobre ações e FIIs da CVM "
        "e ações americanas com SEC/CIK; demais ativos sem confirmação oficial nesta rota."
    ))
