"""Proteção da montagem de carteira: 'dados suficientes' não implica 'comprar'.

Este filtro aplica-se exclusivamente a NOVOS aportes em ações brasileiras.
Outras classes permanecem sob as regras específicas existentes. Não calcula
preço intrínseco, não garante retorno e não altera posições já registradas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot,
    ConfidenceLevel,
    RecommendationAction,
    ValuationStatus,
)

MAX_STOCK_REFERENCE_AGE = timedelta(days=7)
REQUIRED_RELATIVE_MARGIN = Decimal("0.20")
ACCEPTED_PURCHASE_SIGNALS = {RecommendationAction.ANALYZE_TO_BUY}
ACCEPTED_PRICE_STATUS = {ValuationStatus.ATTRACTIVE, ValuationStatus.VERY_ATTRACTIVE}
ACCEPTED_CONFIDENCE = {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _recent(observed: datetime | None, reference: datetime) -> bool:
    if observed is None:
        return False
    age = _aware(reference) - _aware(observed)
    return -timedelta(days=1) <= age <= MAX_STOCK_REFERENCE_AGE


def stock_purchase_exclusion_reason(snapshot: AssetIntelligenceSnapshot) -> str | None:
    """Motivo explícito para abster-se de sugerir NOVO aporte em ação.

    Valida novamente a evidência que deve ter sido construída pelo motor
    setorial: sinal de análise para compra, confiança suficiente, fonte
    relativa identificável, intervalo consistente, datas e margem de 20%.
    Não transforma um simples score alto em recomendação de compra.
    """
    if snapshot.confidence not in ACCEPTED_CONFIDENCE:
        return "Ação sem confiança de dados média ou alta para novo aporte."
    if snapshot.data_quality and snapshot.data_quality.recommendation_blocked:
        return "Ação com bloqueio explícito de qualidade dos dados."
    if snapshot.recommendation not in ACCEPTED_PURCHASE_SIGNALS:
        return "Ação sem sinal fundamentado de análise para compra; não sugerir novo aporte."
    valuation = snapshot.valuation
    if (
        snapshot.valuation_status not in ACCEPTED_PRICE_STATUS
        or valuation.status != snapshot.valuation_status
    ):
        return "Ação sem avaliação de preço atrativo coerente e validada."
    if valuation.confidence not in ACCEPTED_CONFIDENCE or not valuation.methods:
        return "Avaliação de preço sem método identificável e confiança suficiente."
    if not _recent(valuation.data_date, snapshot.calculated_at):
        return "Avaliação de preço desatualizada ou sem data verificável."
    if not _recent(snapshot.market_updated_at, snapshot.calculated_at):
        return "Cotação da ação desatualizada ou sem data verificável."
    low, high, price = (
        valuation.estimated_range_low,
        valuation.estimated_range_high,
        snapshot.current_price,
    )
    if any(value is None or not value.is_finite() for value in (low, high, price)):
        return "Faixa relativa de preço não verificável."
    if low <= 0 or high < low or price <= 0:
        return "Faixa relativa de preço inconsistente."
    if price > low * (Decimal("1") - REQUIRED_RELATIVE_MARGIN):
        return "Ação sem margem relativa mínima de 20% abaixo da faixa setorial."
    return None
