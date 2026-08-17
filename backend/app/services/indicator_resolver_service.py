from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json

from app.core.config import settings
from app.engines.derived_indicator_engine import DerivedIndicatorEngine
from app.engines.indicator_catalog import indicator_temporal_validity_days
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
    ProviderFailureReason,
    ProviderResolutionAttempt,
    ResolutionOutcome,
    ResolutionSummary,
)
from app.services.indicator_normalization_service import (
    IndicatorNormalizationService,
    classify_provider_failure_reason,
    display_value,
    sanitize_failure_detail,
)
from app.services.market_service import MarketService


# Validade temporal de dado CVM por PERIODICIDADE REAL do documento — nunca
# uma única janela genérica para "qualquer dado CVM" (auditoria confirmou
# que CvmFinancialDocument.document_type chega intacto até este serviço via
# CvmFinancialRepository.latest_normalized(), sem inferência por nome/ticker;
# ver _cvm_valid_until()).
#
# DFP (Demonstrações Financeiras Padronizadas) é uma demonstração ANUAL —
# o próximo dado só é esperado ~1 ano depois do period_end. 100 dias
# expirava a validade meses antes da própria CVM publicar a próxima DFP
# (comprovado em sincronização real: dado de 2025-12-31 já aparecia STALE
# em 2026-08-17). 395 = ciclo anual (365) + margem para atraso de
# publicação, mesmo raciocínio já estabelecido no código para dado
# manual/cadastral anual (ver valid_until de 395 dias em _apply_manual).
CVM_DFP_VALIDITY_DAYS = 395

# ITR (Informações Trimestrais) é periódica — o próximo dado é esperado
# ~1 trimestre (91 dias) depois do period_end, mais a folga regulatória de
# entrega da CVM (45 dias corridos após o fim do trimestre) mais uma
# margem de processamentos/atraso. 91 + 45 ≈ 136; arredondado para 120 para
# não superestimar (mais conservador que o prazo regulatório completo).
# Nunca herda a janela anual da DFP — um ITR antigo não pode ficar
# artificialmente "current" por ~13 meses.
CVM_ITR_VALIDITY_DAYS = 120

# Fallback conservador para um document_type que não seja DFP nem ITR
# (não deveria ocorrer com os providers atuais, mas nunca estende a
# validade além do ciclo mais curto conhecido só por ausência de política).
CVM_DEFAULT_VALIDITY_DAYS = CVM_ITR_VALIDITY_DAYS


def _cvm_valid_until(reference_date: datetime, document_type: str | None) -> datetime:
    """Validade temporal de um valor oficial CVM, por tipo real do documento.

    Nunca infere o tipo pelo ticker/nome do indicador — recebe
    `document_type` diretamente de CvmFinancialDocument.document_type
    (DFP/ITR), propagado sem transformação desde o repository.
    """
    kind = (document_type or "").upper()
    if kind == "DFP":
        days = CVM_DFP_VALIDITY_DAYS
    elif kind == "ITR":
        days = CVM_ITR_VALIDITY_DAYS
    else:
        days = CVM_DEFAULT_VALIDITY_DAYS
    return reference_date + timedelta(days=days)

# Indicadores que DerivedIndicatorEngine sabe calcular a partir de
# componentes brutos CVM (seção 6 do resolver híbrido) — só tentados quando
# ainda pendentes após BRAPI/CVM direto, nunca substituindo um valor já
# resolvido por fonte de maior prioridade.
DERIVED_INDICATOR_KEYS = (
    "roe",
    "roa",
    "net_debt",
    "net_debt_equity",
    "liabilities_assets",
    "current_liquidity",
)


class IndicatorResolverService:
    """Resolve dados por validade e procedência, sem exigir BRAPI Pro.

    Cada estágio da cascata (snapshot -> BRAPI -> oficial -> snapshot stale ->
    manual) registra, para cada indicador ainda pendente, uma tentativa
    estruturada (`ProviderResolutionAttempt`) com a fonte, o resultado e o
    motivo classificado da falha — nunca engolindo a exceção original em
    silêncio e nunca convertendo ausência em zero.
    """

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
            pending = self._unresolved_keys(resolved)
            payloads, dataset_outcomes = self._load_brapi_free(symbol, asset_class)
            self._apply_payloads(
                resolved,
                payloads,
                collected_at,
                source="BRAPI",
                source_type="provider",
            )
            self._record_stage_attempts(
                resolved,
                pending_before=pending,
                provider="BRAPI",
                source_type="provider",
                dataset_outcomes=dataset_outcomes,
                attempted_at=collected_at,
            )

        if asset_class == InvestmentClass.TREASURY and self._has_unresolved(resolved):
            pending = self._unresolved_keys(resolved)
            rows, error, attempted = self._load_treasury_official(symbol)
            if attempted:
                self._apply_payloads(
                    resolved,
                    rows,
                    collected_at,
                    source="Tesouro Transparente",
                    source_type="official",
                )
                self._record_stage_attempts(
                    resolved,
                    pending_before=pending,
                    provider="Tesouro Transparente",
                    source_type="official",
                    dataset_outcomes=[("daily_dataset", error is None, error)],
                    attempted_at=collected_at,
                )

        if asset_id is not None and self._has_unresolved(resolved):
            self._apply_cvm(resolved, asset_id, collected_at, symbol=symbol)

        if self._has_unresolved(resolved):
            self._apply_stale_snapshot_fallback(resolved, symbol, collected_at)

        if asset_id is not None and self.manual_repository is not None:
            self._apply_manual(resolved, user_id, asset_id, collected_at)

        self._reconcile_failure_reasons(resolved)
        return list(resolved.values())

    @staticmethod
    def _reconcile_failure_reasons(resolved: dict[str, NormalizedIndicator]) -> None:
        """Após a cascata, reflete no indicador o motivo mais específico já apurado.

        Nunca inventa uma causa: escolhe entre os motivos já registrados em
        `resolution_attempts` (evidência real de cada tentativa), preferindo o
        mais específico (diferente de NOT_REPORTED) ao mais recente genérico.
        """
        for key, item in resolved.items():
            if item.status in (IndicatorStatus.AVAILABLE, IndicatorStatus.STALE):
                # STALE ja carrega seu proprio motivo definitivo (preservado
                # pelo estagio que o produziu); nao deve ser substituido por
                # uma falha anterior e menos especifica na cascata.
                continue
            failures = [
                attempt
                for attempt in item.resolution_attempts
                if attempt.outcome == ResolutionOutcome.FAILURE
                and attempt.provider_failure_reason is not None
            ]
            if not failures:
                continue
            specific = [
                attempt
                for attempt in failures
                if attempt.provider_failure_reason != ProviderFailureReason.NOT_REPORTED
            ]
            chosen = specific[-1] if specific else failures[-1]
            if chosen.provider_failure_reason == item.provider_failure_reason:
                continue
            resolved[key] = item.model_copy(
                update={"provider_failure_reason": chosen.provider_failure_reason}
            )

    def resolve_macro(
        self, definitions: list, collected_at: datetime
    ) -> list[MacroIndicatorSnapshot]:
        results = []
        for definition in definitions:
            latest = None
            payload = None
            attempts: list[ProviderResolutionAttempt] = []
            failure_reason: ProviderFailureReason | None = None

            if definition.key not in self.bcb_provider.series:
                failure_reason = ProviderFailureReason.NOT_SUPPORTED
            else:
                try:
                    payload = self.bcb_provider.get_series(definition.key)
                    latest = payload["values"][-1] if payload["values"] else None
                    if latest is None:
                        failure_reason = ProviderFailureReason.NOT_REPORTED
                    attempts.append(
                        ProviderResolutionAttempt(
                            provider=self.bcb_provider.provider_name,
                            source_type="official",
                            dataset=definition.key,
                            outcome=(
                                ResolutionOutcome.SUCCESS
                                if latest
                                else ResolutionOutcome.FAILURE
                            ),
                            provider_failure_reason=(
                                None if latest else failure_reason
                            ),
                            attempted_at=collected_at,
                        )
                    )
                except Exception as exc:
                    failure_reason = classify_provider_failure_reason(exc)
                    attempts.append(
                        ProviderResolutionAttempt(
                            provider=self.bcb_provider.provider_name,
                            source_type="official",
                            dataset=definition.key,
                            outcome=ResolutionOutcome.FAILURE,
                            provider_failure_reason=failure_reason,
                            attempted_at=collected_at,
                            detail=sanitize_failure_detail(str(exc)),
                        )
                    )

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
                    provider_failure_reason=None if latest else failure_reason,
                    resolution_attempts=attempts,
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
                    "provider_failure_reason": None,
                    "provenance": json.loads(
                        getattr(row, "provenance_json", None) or "{}"
                    ),
                }
            )

    def _load_brapi_free(
        self, symbol: str, asset_class: InvestmentClass
    ) -> tuple[list[dict], list[tuple[str, bool, Exception | None]]]:
        datasets = (
            ["indicators"]
            if asset_class == InvestmentClass.FII
            else ["statistics", "financial_data"]
        )
        payloads = []
        outcomes: list[tuple[str, bool, Exception | None]] = []
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
                outcomes.append((dataset, True, None))
            except Exception as exc:
                outcomes.append((dataset, False, exc))
        return payloads, outcomes

    def _load_treasury_official(
        self, symbol: str
    ) -> tuple[list[dict], Exception | None, bool]:
        if self.treasury_provider is None:
            return [], None, False
        try:
            rows = self.treasury_provider.fetch_daily_dataset()
        except Exception as exc:
            return [], exc, True
        normalized = symbol.lower().strip()
        matched = [
            row
            for row in rows
            if str(row.get("symbol", row.get("name", ""))).lower().strip()
            == normalized
        ][:1]
        return matched, None, True

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
            if current is None or current.status in self._RESOLVED_STATUSES:
                continue
            if (
                candidate.status == IndicatorStatus.AVAILABLE
                and candidate.value is not None
            ):
                resolved[candidate.key] = candidate.model_copy(
                    update={
                        "source": source,
                        "source_type": source_type,
                        "valid_until": self._valid_until(
                            candidate.key, collected_at, source_type=source_type
                        ),
                        "freshness_status": "current",
                    }
                )

    @staticmethod
    def _valid_until(
        key: str, collected_at: datetime, *, source_type: str
    ) -> datetime:
        """Validade temporal (P4): fonte única via indicator_temporal_validity_days.

        Usa a política do catálogo por indicador quando ela existe (ex.: preço
        expira em 2 dias, dado cadastral em 3650) em vez do fallback genérico
        por estágio — nunca estende artificialmente a validade de um dado.
        Preserva o fallback conservador (1 dia oficial / 30 dias provider)
        apenas para indicadores sem política declarada no catálogo.
        """
        validity_days = indicator_temporal_validity_days(key)
        if validity_days is not None:
            return collected_at + timedelta(days=validity_days)
        return collected_at + timedelta(days=1 if source_type == "official" else 30)

    def _record_stage_attempts(
        self,
        resolved: dict[str, NormalizedIndicator],
        *,
        pending_before: set[str],
        provider: str,
        source_type: str,
        dataset_outcomes: list[tuple[str, bool, Exception | None]],
        attempted_at: datetime,
    ) -> None:
        """Anexa uma tentativa estruturada por indicador ainda pendente antes do estágio.

        Indicadores resolvidos neste estágio recebem uma tentativa de sucesso;
        os que continuam pendentes recebem uma tentativa de falha com o motivo
        classificado a partir da exceção tipada real (nunca inventado).
        """
        if not pending_before or not dataset_outcomes:
            return
        still_pending = pending_before & self._unresolved_keys(resolved)
        resolved_now = pending_before - still_pending
        successful_datasets = [name for name, ok, _ in dataset_outcomes if ok]
        failed = [(name, exc) for name, ok, exc in dataset_outcomes if not ok]
        dataset_label = ", ".join(name for name, _, _ in dataset_outcomes)

        for key in resolved_now:
            item = resolved.get(key)
            if item is None:
                continue
            attempt = ProviderResolutionAttempt(
                provider=provider,
                source_type=source_type,
                dataset=dataset_label,
                outcome=ResolutionOutcome.SUCCESS,
                attempted_at=attempted_at,
                reference_date=item.reference_date,
            )
            resolved[key] = item.model_copy(
                update={"resolution_attempts": [*item.resolution_attempts, attempt]}
            )

        if not still_pending:
            return

        if successful_datasets:
            reason: ProviderFailureReason | None = ProviderFailureReason.NOT_REPORTED
            detail = None
        elif failed:
            _, last_exc = failed[-1]
            reason = classify_provider_failure_reason(last_exc)
            detail = sanitize_failure_detail(str(last_exc)) if last_exc else None
        else:
            reason = None
            detail = None

        for key in still_pending:
            item = resolved.get(key)
            if item is None:
                continue
            attempt = ProviderResolutionAttempt(
                provider=provider,
                source_type=source_type,
                dataset=dataset_label,
                outcome=ResolutionOutcome.FAILURE,
                provider_failure_reason=reason,
                attempted_at=attempted_at,
                detail=detail,
            )
            resolved[key] = item.model_copy(
                update={"resolution_attempts": [*item.resolution_attempts, attempt]}
            )

    def _apply_manual(self, resolved, user_id, asset_id, collected_at) -> None:
        pending = self._unresolved_keys(resolved)
        if not pending:
            return
        items_by_key = {
            item.indicator_key: item
            for item in self.manual_repository.list_for_asset(user_id, asset_id)
        }
        for key in pending:
            current = resolved.get(key)
            if current is None or current.status == IndicatorStatus.STALE:
                # Um valor stale ja preservado (snapshot local) tem
                # precedencia sobre o manual: manual e fallback, nao
                # autoridade universal — nao pode sobrescrever silenciosamente
                # um dado real de maior prioridade so porque esta desatualizado.
                continue
            item = items_by_key.get(key)
            if item is None:
                attempt = ProviderResolutionAttempt(
                    provider="Indicador manual",
                    source_type="manual",
                    outcome=ResolutionOutcome.FAILURE,
                    provider_failure_reason=ProviderFailureReason.NOT_REPORTED,
                    attempted_at=collected_at,
                )
                resolved[key] = current.model_copy(
                    update={
                        "resolution_attempts": [
                            *current.resolution_attempts,
                            attempt,
                        ]
                    }
                )
                continue
            reference = datetime.combine(
                item.reference_date, time.min, tzinfo=timezone.utc
            )
            stale = (date.today() - item.reference_date).days > 395
            value = Decimal(item.value)
            attempt = ProviderResolutionAttempt(
                provider=item.source_description,
                source_type="manual",
                outcome=ResolutionOutcome.SUCCESS,
                provider_failure_reason=(
                    ProviderFailureReason.STALE if stale else None
                ),
                attempted_at=collected_at,
                reference_date=reference,
            )
            resolved[key] = current.model_copy(
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
                    "provider_failure_reason": (
                        ProviderFailureReason.STALE if stale else None
                    ),
                    "impact": AnalysisImpact.INFORMATIONAL,
                    "resolution_attempts": [*current.resolution_attempts, attempt],
                }
            )

    def _apply_cvm(self, resolved, asset_id, collected_at, symbol=None) -> None:
        if self.cvm_repository is None:
            return
        pending = self._unresolved_keys(resolved)
        if not pending:
            return

        issuer = self.cvm_repository.linked_issuer(asset_id)
        if issuer is None and symbol is not None:
            issuer = self._auto_link_cvm_issuer(asset_id, symbol)
        if issuer is None:
            self._append_attempts(
                resolved,
                pending,
                provider="CVM Dados Abertos",
                source_type="official",
                dataset="issuer_link",
                reason=ProviderFailureReason.IDENTIFIER_UNRESOLVED,
                attempted_at=collected_at,
            )
            return

        grouped = {}
        for account, document, issuer_row in self.cvm_repository.latest_normalized(
            asset_id
        ):
            grouped.setdefault(account.normalized_key, []).append(
                (account, document, issuer_row)
            )

        if not grouped:
            self._append_attempts(
                resolved,
                pending,
                provider="CVM Dados Abertos",
                source_type="official",
                dataset="latest_normalized",
                reason=ProviderFailureReason.NOT_SYNCED,
                attempted_at=collected_at,
            )
            return

        resolved_keys: set[str] = set()
        for key, rows in grouped.items():
            current = resolved.get(key)
            if current is None or current.status in self._RESOLVED_STATUSES:
                continue
            value = sum(
                (Decimal(account.normalized_value) for account, _, _ in rows),
                Decimal("0"),
            )
            account, document, issuer_row = rows[0]
            reference = datetime.combine(
                document.period_end, time.min, tzinfo=timezone.utc
            )
            attempt = ProviderResolutionAttempt(
                provider="CVM Dados Abertos",
                source_type="official",
                dataset=document.document_type,
                outcome=ResolutionOutcome.SUCCESS,
                attempted_at=collected_at,
                reference_date=reference,
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
                    "valid_until": _cvm_valid_until(reference, document.document_type),
                    "freshness_status": "current",
                    "confidence": ConfidenceLevel.HIGH,
                    "period": document.period_kind,
                    "unavailable_reason": None,
                    "provider_failure_reason": None,
                    "provenance": {
                        "provider": "cvm",
                        "document_type": document.document_type,
                        "scope": document.scope,
                        "method": account.acquisition_method,
                        "cnpj": issuer_row.cnpj,
                        "cvm_code": issuer_row.cvm_code,
                        "accounts": [
                            {
                                "code": item.account_code,
                                "description": item.account_description,
                                "original_value": str(item.original_value),
                            }
                            for item, _, _ in rows
                        ],
                    },
                    "resolution_attempts": [*current.resolution_attempts, attempt],
                }
            )
            resolved_keys.add(key)

        still_pending = pending - resolved_keys
        derived_pending = still_pending & set(DERIVED_INDICATOR_KEYS)
        if derived_pending:
            derived_resolved = self._apply_cvm_derived_indicators(
                resolved, grouped, derived_pending, collected_at
            )
            still_pending -= derived_resolved

        if still_pending:
            self._append_attempts(
                resolved,
                still_pending,
                provider="CVM Dados Abertos",
                source_type="official",
                dataset="latest_normalized",
                reason=ProviderFailureReason.NOT_REPORTED,
                attempted_at=collected_at,
            )

    def _auto_link_cvm_issuer(self, asset_id, symbol: str):
        """Vincula automaticamente ativo<->emissor CVM por CNPJ EXATO.

        Nunca por nome (sem fuzzy matching silencioso — ver seção 7 do
        resolver híbrido): usa o CNPJ retornado pelo perfil do provedor de
        mercado e só vincula se houver correspondência exata e única com um
        CvmIssuer já sincronizado via DFP/ITR. Qualquer falha ao buscar o
        perfil (provider indisponível, ticker sem perfil etc.) é absorvida
        aqui e apenas resulta em "ainda não vinculado" — nunca interrompe a
        cascata de resolução.
        """
        if self.market_service is None:
            return None
        try:
            profile = self.market_service.get_profile(symbol)
        except Exception:
            return None
        cnpj = CvmOpenDataProvider.normalize_cnpj(getattr(profile, "cnpj", None) or "")
        if not cnpj:
            return None
        issuer = self.cvm_repository.find_issuer_by_cnpj(cnpj)
        if issuer is None:
            return None
        self.cvm_repository.link_asset(asset_id, issuer.id)
        return issuer

    def _apply_cvm_derived_indicators(
        self, resolved, grouped, pending: set[str], collected_at: datetime
    ) -> set[str]:
        """Calcula indicadores derivados (seção 6 do resolver híbrido) a
        partir de componentes brutos já apurados pelo CVM, quando todos os
        componentes necessários existem e são COMPATÍVEIS — mesmo period_end
        E mesmo document_type (DFP não se mistura com ITR: são periodicidades
        diferentes, mesmo quando coincidem em period_end) — nunca divide por
        zero, nunca converte ausência em zero. O document_type vencedor é
        propagado para a política de validade temporal (_cvm_valid_until) e
        para o provenance — um indicador derivado de ITR nunca herda a
        janela de validade anual da DFP.
        """
        components: dict[str, Decimal] = {}
        source: dict[str, tuple] = {}  # raw_key -> (period_end, document_type, period_kind)
        for raw_key in (
            "net_income",
            "equity",
            "assets",
            "net_debt",
            "total_liabilities",
            "current_assets",
            "current_liabilities",
            "gross_debt",
            "cash_and_equivalents",
        ):
            rows = grouped.get(raw_key)
            if not rows:
                continue
            components[raw_key] = sum(
                (Decimal(account.normalized_value) for account, _, _ in rows),
                Decimal("0"),
            )
            document = rows[0][1]
            source[raw_key] = (document.period_end, document.document_type, document.period_kind)

        def _compatible(*keys: str) -> bool:
            values = {source[k] for k in keys if k in source}
            return len(values) == 1

        net_debt_value = components.get("net_debt")
        net_debt_source = source.get("net_debt")
        calculations: list[tuple] = []
        if (
            net_debt_value is None
            and "gross_debt" in components
            and "cash_and_equivalents" in components
            and _compatible("gross_debt", "cash_and_equivalents")
        ):
            net_debt_result = DerivedIndicatorEngine.net_debt(
                gross_debt=components["gross_debt"],
                cash_and_equivalents=components["cash_and_equivalents"],
            )
            if net_debt_result is not None:
                net_debt_value = net_debt_result.value
                net_debt_source = source["gross_debt"]
                calculations.append((net_debt_result, net_debt_source))

        if "net_income" in components and "equity" in components and _compatible(
            "net_income", "equity"
        ):
            calculations.append(
                (
                    DerivedIndicatorEngine.roe(
                        net_income=components["net_income"], equity=components["equity"]
                    ),
                    source["equity"],
                )
            )
        if "net_income" in components and "assets" in components and _compatible(
            "net_income", "assets"
        ):
            calculations.append(
                (
                    DerivedIndicatorEngine.roa(
                        net_income=components["net_income"], assets=components["assets"]
                    ),
                    source["assets"],
                )
            )
        if (
            net_debt_value is not None
            and "equity" in components
            and net_debt_source == source["equity"]
        ):
            calculations.append(
                (
                    DerivedIndicatorEngine.net_debt_equity(
                        net_debt=net_debt_value, equity=components["equity"]
                    ),
                    source["equity"],
                )
            )
        if (
            "total_liabilities" in components
            and "assets" in components
            and _compatible("total_liabilities", "assets")
        ):
            calculations.append(
                (
                    DerivedIndicatorEngine.liabilities_assets(
                        total_liabilities=components["total_liabilities"],
                        assets=components["assets"],
                    ),
                    source["assets"],
                )
            )
        if (
            "current_assets" in components
            and "current_liabilities" in components
            and _compatible("current_assets", "current_liabilities")
        ):
            calculations.append(
                (
                    DerivedIndicatorEngine.current_liquidity(
                        current_assets=components["current_assets"],
                        current_liabilities=components["current_liabilities"],
                    ),
                    source["current_assets"],
                )
            )

        resolved_keys: set[str] = set()
        for result, (period_end, document_type, period_kind) in calculations:
            if result is None or result.key not in pending:
                continue
            current = resolved.get(result.key)
            if current is None or current.status in self._RESOLVED_STATUSES:
                continue
            reference = datetime.combine(period_end, time.min, tzinfo=timezone.utc)
            attempt = ProviderResolutionAttempt(
                provider="CVM Dados Abertos (derivado)",
                source_type="derived",
                dataset=document_type,
                outcome=ResolutionOutcome.SUCCESS,
                attempted_at=collected_at,
                reference_date=reference,
            )
            resolved[result.key] = current.model_copy(
                update={
                    "value": result.value,
                    "display_value": display_value(result.value, result.unit, None),
                    "unit": result.unit,
                    "status": IndicatorStatus.AVAILABLE,
                    "source": "CVM Dados Abertos (derivado)",
                    "source_type": "derived",
                    "reference_date": reference,
                    "collected_at": collected_at,
                    "valid_until": _cvm_valid_until(reference, document_type),
                    "freshness_status": "current",
                    "confidence": ConfidenceLevel.HIGH,
                    "period": period_kind,
                    "unavailable_reason": None,
                    "provider_failure_reason": None,
                    "provenance": {
                        "provider": "cvm_derived",
                        "document_type": document_type,
                        "period_kind": period_kind,
                        "reference_date": period_end.isoformat(),
                        "formula": result.formula,
                        "components": {
                            key: str(value) for key, value in result.components.items()
                        },
                    },
                    "resolution_attempts": [*current.resolution_attempts, attempt],
                }
            )
            resolved_keys.add(result.key)
        return resolved_keys

    def _apply_stale_snapshot_fallback(
        self, resolved: dict[str, NormalizedIndicator], symbol: str, collected_at: datetime
    ) -> None:
        """Último recurso antes do manual: preserva um valor stale, nunca zero.

        Só é aplicado a indicadores que continuam sem resolução depois de
        snapshot válido, BRAPI, oficial e CVM terem sido tentados — nunca
        sobrescreve um valor já disponível de maior prioridade.
        """
        if self.snapshot_repository is None:
            return
        pending = self._unresolved_keys(resolved)
        if not pending:
            return
        fetch = getattr(self.snapshot_repository, "latest_for_symbol", None)
        if fetch is None:
            return
        rows = fetch(symbol, collected_at)
        for row in rows:
            key = row.indicator_key
            if key not in pending:
                continue
            template = resolved.get(key)
            if template is None or template.status in self._RESOLVED_STATUSES:
                continue
            if row.value is None:
                continue
            value = Decimal(row.value)
            attempt = ProviderResolutionAttempt(
                provider=row.source,
                source_type=row.source_type,
                dataset="stale_snapshot",
                outcome=ResolutionOutcome.SUCCESS,
                provider_failure_reason=ProviderFailureReason.STALE,
                attempted_at=collected_at,
                reference_date=self._aware(row.reference_date),
            )
            resolved[key] = template.model_copy(
                update={
                    "value": value,
                    "display_value": display_value(value, row.unit, None),
                    "unit": row.unit,
                    "status": IndicatorStatus.STALE,
                    "source": row.source,
                    "source_type": row.source_type,
                    "reference_date": self._aware(row.reference_date),
                    "collected_at": self._aware(row.collected_at) or collected_at,
                    "valid_until": self._aware(row.valid_until),
                    "freshness_status": "stale",
                    "confidence": ConfidenceLevel.LOW,
                    "period": row.period,
                    "unavailable_reason": None,
                    "provider_failure_reason": ProviderFailureReason.STALE,
                    "provenance": json.loads(
                        getattr(row, "provenance_json", None) or "{}"
                    ),
                    "resolution_attempts": [
                        *template.resolution_attempts,
                        attempt,
                    ],
                }
            )

    def _append_attempts(
        self,
        resolved: dict[str, NormalizedIndicator],
        keys: set[str],
        *,
        provider: str,
        source_type: str,
        dataset: str | None,
        reason: ProviderFailureReason | None,
        attempted_at: datetime,
        detail: str | None = None,
    ) -> None:
        for key in keys:
            item = resolved.get(key)
            if item is None:
                continue
            attempt = ProviderResolutionAttempt(
                provider=provider,
                source_type=source_type,
                dataset=dataset,
                outcome=ResolutionOutcome.FAILURE,
                provider_failure_reason=reason,
                attempted_at=attempted_at,
                detail=detail,
            )
            resolved[key] = item.model_copy(
                update={"resolution_attempts": [*item.resolution_attempts, attempt]}
            )

    _RESOLVED_STATUSES = (IndicatorStatus.AVAILABLE, IndicatorStatus.NOT_APPLICABLE)

    @classmethod
    def _has_unresolved(cls, resolved) -> bool:
        return any(
            item.status not in cls._RESOLVED_STATUSES for item in resolved.values()
        )

    @classmethod
    def _unresolved_keys(
        cls, resolved: dict[str, NormalizedIndicator]
    ) -> set[str]:
        return {
            key
            for key, item in resolved.items()
            if item.status not in cls._RESOLVED_STATUSES
        }

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


def build_resolution_summary(
    indicators: list[NormalizedIndicator],
) -> ResolutionSummary:
    """Agrega os resolution_attempts (P3) já existentes por indicador (P4).

    Puramente derivado — não influencia confidence/coverage/elegibilidade,
    apenas resume o que o resolver já registrou: quantas tentativas reais
    ocorreram, quantas tiveram sucesso/falha, quantas foram um fallback bem
    sucedido após pelo menos uma falha anterior no mesmo indicador, quantas
    fontes distintas contribuíram, e a contagem por provider_failure_reason.
    """
    attempt_count = 0
    success_count = 0
    failure_count = 0
    fallback_success_count = 0
    unresolved_count = 0
    stale_count = 0
    sources: set[str] = set()
    failure_reason_counts: dict[str, int] = {}

    for indicator in indicators:
        attempts = indicator.resolution_attempts
        attempt_count += len(attempts)
        seen_failure = False
        for attempt in attempts:
            if attempt.outcome == ResolutionOutcome.SUCCESS:
                success_count += 1
                sources.add(attempt.provider)
                if seen_failure:
                    fallback_success_count += 1
            else:
                failure_count += 1
                seen_failure = True
                if attempt.provider_failure_reason is not None:
                    reason_key = attempt.provider_failure_reason.value
                    failure_reason_counts[reason_key] = (
                        failure_reason_counts.get(reason_key, 0) + 1
                    )
        if indicator.status == IndicatorStatus.STALE:
            stale_count += 1
        elif indicator.status not in (
            IndicatorStatus.AVAILABLE,
            IndicatorStatus.NOT_APPLICABLE,
        ):
            unresolved_count += 1

    return ResolutionSummary(
        attempt_count=attempt_count,
        success_count=success_count,
        failure_count=failure_count,
        fallback_success_count=fallback_success_count,
        unresolved_count=unresolved_count,
        stale_count=stale_count,
        sources_used=sorted(sources),
        failure_reason_counts=failure_reason_counts,
    )
