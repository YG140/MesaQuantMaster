from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json

from app.core.config import settings
from app.providers.bcb_sgs_provider import BcbSgsProvider
from app.providers.cvm_open_data_provider import CvmOpenDataProvider
from app.providers.tesouro_transparente_provider import TesouroTransparenteProvider
from app.repositories.indicator_snapshot_repository import IndicatorSnapshotRepository
from app.repositories.manual_indicator_repository import ManualIndicatorRepository
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.schemas.market_intelligence import (
    AnalysisImpact,
    ConfidenceLevel,
    IndicatorStatus,
    InvestmentClass,
    MacroIndicatorSnapshot,
    NormalizedIndicator,
)
from app.services.indicator_normalization_service import (
    IndicatorNormalizationService,
    display_value,
)
from app.services.market_service import MarketService


class IndicatorResolverService:
    """Resolve dados por validade e procedência, sem exigir BRAPI Pro."""

    def __init__(
        self,
        *,
        market_service: MarketService,
        normalizer: IndicatorNormalizationService,
        snapshot_repository: IndicatorSnapshotRepository | None = None,
        manual_repository: ManualIndicatorRepository | None = None,
        bcb_provider: BcbSgsProvider | None = None,
        treasury_provider: TesouroTransparenteProvider | None = None,
        cvm_provider: CvmOpenDataProvider | None = None,
        cvm_repository: CvmFinancialRepository | None = None,
    ):
        self.market_service = market_service
        self.normalizer = normalizer
        self.snapshot_repository = snapshot_repository
        self.manual_repository = manual_repository
        self.bcb_provider = bcb_provider or BcbSgsProvider()
        self.treasury_provider = treasury_provider or self._default_treasury_provider()
        self.cvm_provider = cvm_provider or CvmOpenDataProvider()
        self.cvm_repository = cvm_repository

    def resolve_asset(
        self,
        *,
        symbol: str,
        asset_class: InvestmentClass,
        asset_id,
        user_id,
        baseline: list[NormalizedIndicator],
        collected_at: datetime,
    ) -> list[NormalizedIndicator]:
        resolved = {item.key: item for item in baseline}
        self._apply_snapshots(resolved, symbol, collected_at)
        if self._has_unresolved(resolved):
            self._apply_payloads(
                resolved,
                self._load_brapi_free(symbol, asset_class),
                collected_at,
                source="BRAPI",
                source_type="provider",
            )
        if asset_class == InvestmentClass.TREASURY and self._has_unresolved(resolved):
            self._apply_payloads(
                resolved,
                self._load_treasury_official(symbol),
                collected_at,
                source="Tesouro Transparente",
                source_type="official",
            )

        if asset_id is not None and self._has_unresolved(resolved):
            self._apply_cvm(resolved, asset_id, collected_at)
        if asset_id is not None and self.manual_repository is not None:
            self._apply_manual(resolved, user_id, asset_id, collected_at)
        return list(resolved.values())

    def resolve_macro(
        self, definitions: list, collected_at: datetime
    ) -> list[MacroIndicatorSnapshot]:
        results = []
        for definition in definitions:
            latest = None
            payload = None
            if definition.key in self.bcb_provider.series:
                try:
                    payload = self.bcb_provider.get_series(definition.key)
                    latest = payload["values"][-1] if payload["values"] else None
                except Exception:
                    pass
            results.append(
                MacroIndicatorSnapshot(
                    key=definition.key,
                    label=definition.label,
                    value=latest["value"] if latest else None,
                    period=latest["reference_date"] if latest else None,
                    source=(
                        payload["source"]
                        if payload
                        else (
                            self.bcb_provider.provider_name
                            if definition.key in self.bcb_provider.series
                            else definition.source
                        )
                    ),
                    updated_at=collected_at if latest else None,
                    frequency=(
                        payload.get("frequency", definition.frequency)
                        if payload
                        else definition.frequency
                    ),
                    history_available=bool(latest),
                    state=(
                        IndicatorStatus.AVAILABLE
                        if latest
                        else IndicatorStatus.UNAVAILABLE
                    ),
                )
            )
        return results

    def _apply_snapshots(
        self, resolved: dict[str, NormalizedIndicator], symbol: str, now: datetime
    ) -> None:
        if self.snapshot_repository is None:
            return
        for row in self.snapshot_repository.valid_for_symbol(symbol, now):
            template = resolved.get(row.indicator_key)
            if template is None or row.value is None:
                continue
            value = Decimal(row.value)
            resolved[row.indicator_key] = template.model_copy(
                update={
                    "value": value,
                    "display_value": display_value(value, row.unit, None),
                    "unit": row.unit,
                    "status": IndicatorStatus.AVAILABLE,
                    "source": row.source,
                    "source_type": row.source_type,
                    "reference_date": self._aware(row.reference_date),
                    "collected_at": self._aware(row.collected_at) or now,
                    "valid_until": self._aware(row.valid_until),
                    "freshness_status": "current",
                    "confidence": ConfidenceLevel.HIGH,
                    "period": row.period,
                    "unavailable_reason": None,
                    "provenance": json.loads(
                        getattr(row, "provenance_json", None) or "{}"
                    ),
                }
            )

    def _load_brapi_free(self, symbol: str, asset_class: InvestmentClass) -> list[dict]:
        datasets = (
            ["indicators"]
            if asset_class == InvestmentClass.FII
            else ["statistics", "financial_data"]
        )
        payloads = []
        for dataset in datasets:
            try:
                payload = (
                    self.market_service.get_fii_dataset(dataset, [symbol])
                    if asset_class == InvestmentClass.FII
                    else self.market_service.get_stock_dataset(
                        dataset, [symbol], mode="current"
                    )
                )
                payloads.append(payload)
            except Exception:
                continue
        return payloads

    def _load_treasury_official(self, symbol: str) -> list[dict]:
        if self.treasury_provider is None:
            return []
        try:
            rows = self.treasury_provider.fetch_daily_dataset()
        except Exception:
            return []
        normalized = symbol.lower().strip()
        return [
            row
            for row in rows
            if str(row.get("symbol", row.get("name", ""))).lower().strip() == normalized
        ][:1]

    def _apply_payloads(
        self, resolved, payloads, collected_at, *, source: str, source_type: str
    ) -> None:
        if not payloads:
            return
        candidates = self.normalizer.merge_provider_payloads(
            list(resolved.values()), payloads, collected_at=collected_at
        )
        for candidate in candidates:
            current = resolved.get(candidate.key)
            if current is None or current.status == IndicatorStatus.AVAILABLE:
                continue
            if (
                candidate.status == IndicatorStatus.AVAILABLE
                and candidate.value is not None
            ):
                resolved[candidate.key] = candidate.model_copy(
                    update={
                        "source": source,
                        "source_type": source_type,
                        "valid_until": collected_at
                        + timedelta(days=1 if source_type == "official" else 30),
                        "freshness_status": "current",
                    }
                )

    def _apply_manual(self, resolved, user_id, asset_id, collected_at) -> None:
        for item in self.manual_repository.list_for_asset(user_id, asset_id):
            current = resolved.get(item.indicator_key)
            if current is None or current.status == IndicatorStatus.AVAILABLE:
                continue
            reference = datetime.combine(
                item.reference_date, time.min, tzinfo=timezone.utc
            )
            stale = (date.today() - item.reference_date).days > 395
            value = Decimal(item.value)
            resolved[item.indicator_key] = current.model_copy(
                update={
                    "value": value,
                    "display_value": display_value(value, item.unit, None),
                    "unit": item.unit,
                    "status": (
                        IndicatorStatus.STALE if stale else IndicatorStatus.AVAILABLE
                    ),
                    "source": item.source_description,
                    "source_type": "manual",
                    "reference_date": reference,
                    "collected_at": self._aware(item.updated_at) or collected_at,
                    "valid_until": reference + timedelta(days=395),
                    "freshness_status": "stale" if stale else "current",
                    "confidence": ConfidenceLevel.LOW,
                    "period": "informado pelo usuário",
                    "unavailable_reason": None,
                    "impact": AnalysisImpact.INFORMATIONAL,
                }
            )

    def _apply_cvm(self, resolved, asset_id, collected_at) -> None:
        if self.cvm_repository is None:
            return
        grouped = {}
        for account, document, issuer in self.cvm_repository.latest_normalized(
            asset_id
        ):
            grouped.setdefault(account.normalized_key, []).append(
                (account, document, issuer)
            )
        for key, rows in grouped.items():
            current = resolved.get(key)
            if current is None or current.status == IndicatorStatus.AVAILABLE:
                continue
            value = sum(
                (Decimal(account.normalized_value) for account, _, _ in rows),
                Decimal("0"),
            )
            account, document, issuer = rows[0]
            reference = datetime.combine(
                document.period_end, time.min, tzinfo=timezone.utc
            )
            resolved[key] = current.model_copy(
                update={
                    "value": value,
                    "display_value": display_value(value, "currency", None),
                    "unit": "currency",
                    "status": IndicatorStatus.AVAILABLE,
                    "source": "CVM Dados Abertos",
                    "source_type": "official",
                    "reference_date": reference,
                    "collected_at": self._aware(document.collected_at) or collected_at,
                    "valid_until": reference + timedelta(days=100),
                    "freshness_status": "current",
                    "confidence": ConfidenceLevel.HIGH,
                    "period": document.period_kind,
                    "unavailable_reason": None,
                    "provenance": {
                        "provider": "cvm",
                        "document_type": document.document_type,
                        "scope": document.scope,
                        "method": account.acquisition_method,
                        "cnpj": issuer.cnpj,
                        "cvm_code": issuer.cvm_code,
                        "accounts": [
                            {
                                "code": item.account_code,
                                "description": item.account_description,
                                "original_value": str(item.original_value),
                            }
                            for item, _, _ in rows
                        ],
                    },
                }
            )

    @staticmethod
    def _has_unresolved(resolved) -> bool:
        return any(
            item.status != IndicatorStatus.AVAILABLE for item in resolved.values()
        )

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _default_treasury_provider():
        if not settings.TESOURO_TRANSPARENTE_DATASET_URL:
            return None
        return TesouroTransparenteProvider(settings.TESOURO_TRANSPARENTE_DATASET_URL)
