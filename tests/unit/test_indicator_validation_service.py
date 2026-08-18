from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.market_intelligence import (
    ConfidenceLevel,
    IndicatorLayer,
    IndicatorStatus,
    NormalizedIndicator,
)
from app.services.indicator_validation_service import (
    FiiNature,
    IndicatorValidationService,
    classify_fii_nature,
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


# --- classify_fii_nature: canônica e mutuamente exclusiva -------------------


def test_classify_fii_nature_from_explicit_segment():
    assert classify_fii_nature("papel", None) == FiiNature.PAPER
    assert classify_fii_nature("Papel", None) == FiiNature.PAPER
    assert classify_fii_nature("tijolo", None) == FiiNature.BRICK
    assert classify_fii_nature("híbrido", None) == FiiNature.HYBRID
    assert classify_fii_nature(None, None) == FiiNature.UNKNOWN


def test_classify_fii_nature_generic_real_estate_sector_alone_is_unknown_not_brick():
    """'Fundo Imobiliário' sozinho é só a categoria regulatória de TODO
    FII (inclusive os de papel) -- nunca evidência de tijolo por si só."""
    assert classify_fii_nature(None, "Fundos Imobiliários") == FiiNature.UNKNOWN


def test_classify_fii_nature_paper_suffix_in_generic_sector_is_paper_not_brick():
    """'Fundos Imobiliários - papel' contém 'imobili' (que antes causava
    falso-positivo de tijolo) E 'papel' -- deve resolver como PAPER,
    nunca simultaneamente BRICK."""
    result = classify_fii_nature(None, "Fundos Imobiliários - papel")
    assert result == FiiNature.PAPER
    assert result != FiiNature.BRICK


def test_classify_fii_nature_explicit_segment_prevails_over_contradictory_sector():
    result = classify_fii_nature("papel", "Fundos Imobiliários - tijolo")
    assert result == FiiNature.PAPER


def test_classify_fii_nature_hybrid_segment_with_generic_sector():
    assert (
        classify_fii_nature("híbrido", "Fundos Imobiliários") == FiiNature.HYBRID
    )


def test_classify_fii_nature_contradictory_text_is_conservatively_unknown():
    assert classify_fii_nature(None, "papel e tijolo") == FiiNature.UNKNOWN


# --- Aplicabilidade dinâmica a partir da classificação -----------------------


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


def test_generic_real_estate_sector_alone_never_excludes_paper_side():
    """segment=None, sector='Fundos Imobiliários' (sem 'papel'/'tijolo')
    => UNKNOWN => nenhum dos dois lados é eliminado."""
    keys = ["physical_vacancy", "debtor_concentration"]
    baseline = [indicator(key) for key in keys]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment=None, sector="Fundos Imobiliários", collected_at=NOW
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
    """segment=None, sector='Fundos Imobiliários - papel' => PAPER (nunca
    BRICK, apesar de 'imobili' aparecer no texto) => physical_vacancy
    NOT_APPLICABLE, debtor_concentration continua disponível."""
    baseline = [
        indicator("physical_vacancy"),
        indicator("debtor_concentration"),
    ]
    validated, _ = IndicatorValidationService().validate(
        baseline, segment=None, sector="Fundos Imobiliários - papel", collected_at=NOW
    )
    by_key = {item.key: item for item in validated}
    assert by_key["physical_vacancy"].status == IndicatorStatus.NOT_APPLICABLE
    assert by_key["debtor_concentration"].status == IndicatorStatus.AVAILABLE
