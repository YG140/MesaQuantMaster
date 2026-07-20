from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unicodedata import normalize

from app.engines.indicator_catalog import SECTOR_RULES
from app.schemas.market_intelligence import (
    DataQualityReport,
    IndicatorStatus,
    NormalizedIndicator,
)


class IndicatorValidationService:
    def validate(
        self,
        indicators: list[NormalizedIndicator],
        *,
        sector: str | None = None,
        collected_at: datetime | None = None,
    ) -> tuple[list[NormalizedIndicator], DataQualityReport]:
        now = collected_at or datetime.now(timezone.utc)
        sector_profile = profile_for_sector(sector)
        validated = []
        anomaly_flags = []

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
                    }
                )
            elif indicator.reference_date is not None:
                age_days = (now - indicator.reference_date).days
                if age_days > 2 and indicator.status == IndicatorStatus.AVAILABLE:
                    item = indicator.model_copy(
                        update={
                            "status": IndicatorStatus.STALE,
                            "unavailable_reason": "Indicador desatualizado para uso em recomendação.",
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
