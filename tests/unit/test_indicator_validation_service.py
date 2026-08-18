from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.market_intelligence import (
    ConfidenceLevel,
    IndicatorLayer,
    IndicatorStatus,
    NormalizedIndicator,
)
from app.services.indicator_validation_service import (
    IndicatorValidationService,
    is_fii_brick,
    is_fii_paper,
)


NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


def indicator(key: str, status=IndicatorStatus.AVAILABLE) -> NormalizedIndicator:
    return NormalizedIndicator(
        key=key,
        label=key,
        layer=IndicatorLayer.FUNDAMENTAL,
        value=None,
        unit="percent",
        status=status,
        source="BRAPI",
        collected_at=NOW,
        confidence=ConfidenceLevel.HIGH,
    )


def test_is_fii_paper_and_brick_are_evidence_based_not_ticker_based():
    assert is_fii_paper("papel") is True
    assert is_fii_paper("Papel") is True
    assert is_fii_paper("tijolo") is False
    assert is_fii_brick("tijolo") is True
    assert is_fii_brick(None) is False
    assert is_fii_paper(None) is False


def test_brick_only_indicators_are_not_applicable_for_paper_fund():
    keys = [
        "physical_vacancy",
        "financial_vacancy",
        "property_concentration",
        "tenant_concentration",
        "contract_average_term",
        "property_quality",
    ]
    baseline = [indicator(key) for key in keys]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment="papel", collected_at=NOW
    )
    for item in validated:
        assert item.status == IndicatorStatus.NOT_APPLICABLE, item.key


def test_brick_only_indicators_remain_available_for_brick_fund():
    keys = ["physical_vacancy", "tenant_concentration"]
    baseline = [indicator(key) for key in keys]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment="tijolo", collected_at=NOW
    )
    for item in validated:
        assert item.status == IndicatorStatus.AVAILABLE, item.key


def test_paper_only_indicators_are_not_applicable_for_brick_fund():
    keys = ["receivable_quality", "debtor_concentration", "delinquency"]
    baseline = [indicator(key) for key in keys]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment="tijolo", collected_at=NOW
    )
    for item in validated:
        assert item.status == IndicatorStatus.NOT_APPLICABLE, item.key


def test_paper_only_indicators_remain_available_for_paper_fund():
    keys = ["debtor_concentration"]
    baseline = [indicator(key) for key in keys]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment="papel", collected_at=NOW
    )
    assert validated[0].status == IndicatorStatus.AVAILABLE


def test_unknown_segment_never_marks_anything_not_applicable():
    """Natureza desconhecida: nunca inventa classificação, mantém
    diagnóstico conservador (nenhum indicador é marcado NOT_APPLICABLE
    só por falta de segmento)."""
    keys = [
        "physical_vacancy",
        "debtor_concentration",
        "tenant_concentration",
        "receivable_quality",
    ]
    baseline = [indicator(key) for key in keys]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment=None, sector=None, collected_at=NOW
    )
    for item in validated:
        assert item.status == IndicatorStatus.AVAILABLE, item.key


def test_hybrid_segment_does_not_exclude_either_side():
    """Fundo híbrido: nem 'papel' nem 'tijolo' aparecem no texto do
    segmento -- nenhum lado deve ser eliminado sem evidência."""
    keys = ["physical_vacancy", "debtor_concentration"]
    baseline = [indicator(key) for key in keys]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment="híbrido", collected_at=NOW
    )
    for item in validated:
        assert item.status == IndicatorStatus.AVAILABLE, item.key


def test_segment_falls_back_to_sector_when_segment_is_none():
    baseline = [indicator("physical_vacancy")]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment=None, sector="Fundos Imobiliários - papel", collected_at=NOW
    )
    assert validated[0].status == IndicatorStatus.NOT_APPLICABLE
