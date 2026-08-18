from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from unicodedata import normalize

from app.engines.indicator_catalog import (
    SECTOR_RULES,
    indicator_temporal_validity_days,
)
from app.schemas.market_intelligence import (
    DataQualityReport,
    IndicatorStatus,
    NormalizedIndicator,
    ProviderFailureReason,
)


class IndicatorValidationService:
    def validate(
        self,
        indicators: list[NormalizedIndicator],
        *,
        sector: str | None = None,
        segment: str | None = None,
        collected_at: datetime | None = None,
    ) -> tuple[list[NormalizedIndicator], DataQualityReport]:
        now = collected_at or datetime.now(timezone.utc)
        sector_profile = profile_for_sector(sector)
        fii_nature = classify_fii_nature(segment, sector)
        validated = []
        anomaly_flags = []
        indicator_map = {item.key: item for item in indicators}

        for indicator in indicators:
            item = indicator
            if sector_profile and indicator.key in sector_profile["blocked_indicators"]:
                item = indicator.model_copy(
                    update={
                        "status": IndicatorStatus.NOT_APPLICABLE,
                        "value": None,
                        "display_value": None,
                        "unavailable_reason": sector_profile["message"],
                        "explanation": sector_profile["message"],
                        "provider_failure_reason": ProviderFailureReason.NOT_APPLICABLE,
                    }
                )
            elif indicator.key == "price_earnings" and _negative_earnings_context(indicator_map):
                item = indicator.model_copy(
                    update={
                        "status": IndicatorStatus.NOT_APPLICABLE,
                        "value": None,
                        "display_value": None,
                        "unavailable_reason": "Lucro não positivo; o múltiplo P/L não é financeiramente significativo.",
                        "explanation": "Lucro não positivo; o múltiplo P/L não é financeiramente significativo.",
                        "provider_failure_reason": ProviderFailureReason.NOT_APPLICABLE,
                    }
                )
            elif indicator.key in _FII_BRICK_ONLY_INDICATORS and fii_nature == FiiNature.PAPER:
                item = indicator.model_copy(
                    update={
                        "status": IndicatorStatus.NOT_APPLICABLE,
                        "value": None,
                        "display_value": None,
                        "unavailable_reason": "Indicador de imóvel físico não se aplica a FII de papel.",
                        "explanation": "Indicador de imóvel físico não se aplica a FII de papel.",
                        "provider_failure_reason": ProviderFailureReason.NOT_APPLICABLE,
                    }
                )
            elif indicator.key in _FII_PAPER_ONLY_INDICATORS and fii_nature == FiiNature.BRICK:
                item = indicator.model_copy(
                    update={
                        "status": IndicatorStatus.NOT_APPLICABLE,
                        "value": None,
                        "display_value": None,
                        "unavailable_reason": "Indicadores de recebíveis e crédito não se aplicam a FII de tijolo.",
                        "explanation": "Indicadores de recebíveis e crédito não se aplicam a FII de tijolo.",
                        "provider_failure_reason": ProviderFailureReason.NOT_APPLICABLE,
                    }
                )
            else:
                if item.valid_until is not None and now > item.valid_until:
                    if item.status == IndicatorStatus.AVAILABLE:
                        item = item.model_copy(
                            update={
                                "status": IndicatorStatus.STALE,
                                "unavailable_reason": "Indicador expirou pela validade declarada do dado.",
                                "provider_failure_reason": ProviderFailureReason.STALE,
                            }
                        )
                elif item.reference_date is not None and item.key in _time_sensitive_indicators():
                    age_days = (now - item.reference_date).days
                    validity_days = indicator_temporal_validity_days(item.key)
                    if (
                        validity_days is not None
                        and item.status == IndicatorStatus.AVAILABLE
                        and age_days > validity_days
                    ):
                        item = item.model_copy(
                            update={
                                "status": IndicatorStatus.STALE,
                                "unavailable_reason": "Indicador desatualizado para uso em recomendação.",
                                "provider_failure_reason": ProviderFailureReason.STALE,
                            }
                        )

            flag = anomaly_for(item)
            if flag:
                anomaly_flags.append(flag)
                if item.status == IndicatorStatus.AVAILABLE:
                    item = item.model_copy(
                        update={"status": IndicatorStatus.POTENTIALLY_INCONSISTENT}
                    )
            validated.append(item)

        report = data_quality(validated, anomaly_flags)
        return validated, report


def data_quality(
    indicators: list[NormalizedIndicator],
    anomaly_flags: list[str],
) -> DataQualityReport:
    applicable = [
        item for item in indicators if item.status != IndicatorStatus.NOT_APPLICABLE
    ]
    if not applicable:
        return DataQualityReport(
            data_quality_score=Decimal("0"),
            data_completeness=Decimal("0"),
            data_freshness=Decimal("0"),
            anomaly_flags=anomaly_flags,
            non_applicable_indicators=[item.label for item in indicators],
            recommendation_blocked=True,
            blocking_reason="Não foi possível emitir uma avaliação confiável devido à qualidade ou à ausência dos dados.",
        )

    available = [
        item for item in applicable if item.status == IndicatorStatus.AVAILABLE
    ]
    fresh = [
        item
        for item in available
        if item.reference_date is not None and item.status != IndicatorStatus.STALE
    ]
    data_completeness = (
        Decimal(len(available)) / Decimal(len(applicable)) * Decimal("100")
    ).quantize(Decimal("0.01"))
    data_freshness = (
        Decimal(len(fresh)) / Decimal(len(applicable)) * Decimal("100")
    ).quantize(Decimal("0.01"))
    anomaly_penalty = Decimal(min(len(anomaly_flags) * 10, 40))
    quality_score = max(
        Decimal("0"),
        (
            data_completeness * Decimal("0.70")
            + data_freshness * Decimal("0.30")
            - anomaly_penalty
        ),
    ).quantize(Decimal("0.01"))
    blocked = quality_score < Decimal("40")
    return DataQualityReport(
        data_quality_score=quality_score,
        data_completeness=data_completeness,
        data_freshness=data_freshness,
        anomaly_flags=anomaly_flags,
        missing_indicators=[
            item.label
            for item in applicable
            if item.status
            in {
                IndicatorStatus.UNAVAILABLE,
                IndicatorStatus.INSUFFICIENT_DATA,
                IndicatorStatus.INVALID,
                IndicatorStatus.POTENTIALLY_INCONSISTENT,
            }
        ],
        non_applicable_indicators=[
            item.label
            for item in indicators
            if item.status == IndicatorStatus.NOT_APPLICABLE
        ],
        recommendation_blocked=blocked,
        blocking_reason=(
            "Não foi possível emitir uma avaliação confiável devido à qualidade ou à ausência dos dados."
            if blocked
            else None
        ),
    )


def anomaly_for(indicator: NormalizedIndicator) -> str | None:
    value = indicator.value
    if not isinstance(value, Decimal):
        return None
    if indicator.key == "dividend_yield" and value > Decimal("20"):
        return "Dividend Yield extraordinário; pode refletir evento não recorrente."
    if indicator.key == "price_book" and value > 0 and value < Decimal("0.25"):
        return "P/VP anormalmente baixo; exige validação com patrimônio e segmento."
    if indicator.key == "daily_change" and abs(value) > Decimal("30"):
        return "Variação diária extrema; pode refletir evento corporativo ou erro do provedor."
    if indicator.key == "rsi" and (value < Decimal("20") or value > Decimal("80")):
        return "RSI extremo; indicador técnico isolado não deve gerar recomendação automática."
    if indicator.key in {"volume", "liquidity"} and value <= 0:
        return (
            "Liquidez ausente ou nula; ativo não deve ser selecionado automaticamente."
        )
    return None


def _time_sensitive_indicators() -> set[str]:
    return {
        "current_price",
        "daily_change",
        "volume",
        "liquidity",
        "treasury_rate",
        "real_rate",
        "current_rate",
    }


def _negative_earnings_context(indicators: dict[str, NormalizedIndicator]) -> bool:
    for key in ("earnings_per_share", "net_margin", "roe", "roa"):
        indicator = indicators.get(key)
        if indicator is None or indicator.status != IndicatorStatus.AVAILABLE:
            continue
        value = indicator.value
        if isinstance(value, Decimal) and value <= 0:
            return True
    return False


# Indicadores que só fazem sentido para FII com imóveis físicos (tijolo) --
# NOT_APPLICABLE quando o fundo é comprovadamente de papel/recebíveis (ver
# classify_fii_nature). Nunca NOT_APPLICABLE para tijolo/híbrido/desconhecido.
_FII_BRICK_ONLY_INDICATORS = frozenset(
    {
        "physical_vacancy",
        "financial_vacancy",
        "property_concentration",
        "tenant_concentration",
        "contract_average_term",
        "property_quality",
    }
)

# Indicadores que só fazem sentido para FII de recebíveis/papel --
# NOT_APPLICABLE quando o fundo é comprovadamente de tijolo (ver
# classify_fii_nature). Nunca NOT_APPLICABLE para papel/híbrido/desconhecido.
_FII_PAPER_ONLY_INDICATORS = frozenset(
    {
        "receivable_quality",
        "debtor_concentration",
        "delinquency",
    }
)


class FiiNature(str, Enum):
    PAPER = "paper"
    BRICK = "brick"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


def classify_fii_nature(segment: str | None, sector: str | None = None) -> FiiNature:
    """Classifica a natureza real de um FII de forma determinística e
    MUTUAMENTE EXCLUSIVA -- nunca por ticker, nunca combinando papel e
    tijolo ao mesmo tempo por acidente de substring.

    Precedência ESTRITA: se `segment` tem valor não vazio, a classificação
    vem SOMENTE dele -- mesmo que o texto não seja reconhecido (ex.:
    segment="Logística" -> UNKNOWN), NUNCA cai para `sector` nesse caso
    (um segmento real e específico, mesmo que não mapeado pelo
    vocabulário conhecido, não deve ser "corrigido" por um campo genérico
    e menos confiável). `sector` só é consultado quando `segment` está
    genuinamente ausente/vazio.

    Mesmo vocabulário estrito nas duas fontes (papel/recebível vs.
    tijolo/brick explícitos). "Fundo Imobiliário"/"real estate" sozinho
    NUNCA é evidência de tijolo -- é apenas a categoria regulatória de
    TODO FII (inclusive os de papel), então por si só produz UNKNOWN,
    nunca BRICK.
    """
    if segment is not None and ascii_key(segment):
        return _classify_fii_text(segment)
    return _classify_fii_text(sector)


def _classify_fii_text(value: str | None) -> FiiNature:
    text = ascii_key(value)
    if not text:
        return FiiNature.UNKNOWN
    is_hybrid = "hibrid" in text or "hybrid" in text
    if is_hybrid:
        return FiiNature.HYBRID
    is_paper = "papel" in text or "paper" in text or "recebivel" in text or "receivable" in text
    is_brick = "tijolo" in text or "brick" in text
    if is_paper and is_brick:
        # Evidência textual contraditória -- nunca decide por um lado sem
        # comprovação clara; conservador (mesmo tratamento de híbrido sem
        # rótulo explícito: não elimina nenhum lado).
        return FiiNature.UNKNOWN
    if is_paper:
        return FiiNature.PAPER
    if is_brick:
        return FiiNature.BRICK
    return FiiNature.UNKNOWN


def profile_for_sector(sector: str | None) -> dict | None:
    key = ascii_key(sector)
    if not key:
        return None
    for profile in SECTOR_RULES.values():
        if any(label in key for label in profile["labels"]):
            return profile
    return None


def ascii_key(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
