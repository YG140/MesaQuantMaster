from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionLocal
from app.engines.derived_indicator_engine import DerivedIndicatorEngine
from app.engines.indicator_catalog import indicator_temporal_validity_days
from app.providers.bcb_sgs_provider import BcbSgsProvider
from app.providers.cvm_open_data_provider import CvmOpenDataProvider
from app.providers.tesouro_transparente_provider import TesouroTransparenteProvider
from app.repositories.indicator_snapshot_repository import IndicatorSnapshotRepository
from app.repositories.manual_indicator_repository import ManualIndicatorRepository
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.repositories.cvm_fii_repository import CvmFiiRepository
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


# Validade temporal de dado CVM = prazo esperado para o PRÓXIMO reporte
# financeiro periódico que substituiria economicamente este documento —
# nunca uma janela fixa por tipo de documento sozinho. Regras oficiais
# (CVM): ITR entregue em até 45 dias corridos após o fim de cada trimestre;
# não existe ITR referente ao último trimestre (ele é incorporado à DFP);
# DFP entregue em até 3 MESES (calendáricos, não "90 dias" — meses têm
# tamanhos diferentes) após o encerramento do exercício social. Ver
# _cvm_valid_until() e _next_cvm_report_deadline().
CVM_QUARTERLY_FILING_DEADLINE_DAYS = 45
CVM_ANNUAL_FILING_DEADLINE_MONTHS = 3

# Fallback conservador quando o encerramento do exercício social do emissor
# é DESCONHECIDO (nenhuma DFP sincronizada ainda para ele — só ITR
# disponível): nunca inventa um calendário fiscal, apenas assume o ciclo
# mínimo conhecido (1 trimestre + prazo regulatório de entrega), o mesmo
# usado para um ITR que não é o último do exercício. Mantém o dado
# conservadoramente mais curto em vez de estender por incerteza.
CVM_UNKNOWN_FISCAL_CALENDAR_FALLBACK_DAYS = 91 + CVM_QUARTERLY_FILING_DEADLINE_DAYS


def _add_months(value: date, months: int) -> date:
    """Soma meses a uma data, ajustando para o último dia do mês resultante
    quando necessário (ex.: 31/01 + 1 mês -> 28/02 ou 29/02)."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_days(value: date, days: int) -> date:
    return value + timedelta(days=days)


def _fiscal_year_end_for_period(period_end: date, observed_fiscal_year_end: date) -> date:
    """Projeta o encerramento fiscal OBSERVADO (mês/dia, real, do próprio
    emissor) para o ciclo fiscal ao qual `period_end` efetivamente
    pertence — nunca reutiliza o ANO histórico da DFP mais recente como se
    fosse o do exercício corrente.

    Um period_end pertence ao ciclo fiscal cujo encerramento (no mesmo mês/
    dia observado) é o primeiro que ocorre em ou após ele. Ex.: encerramento
    observado 31/12, period_end 2026-09-30 -> pertence ao ciclo que fecha em
    2026-12-31 (não 2025-12-31, que já passou).
    """
    candidate = date(
        period_end.year,
        observed_fiscal_year_end.month,
        min(
            observed_fiscal_year_end.day,
            calendar.monthrange(period_end.year, observed_fiscal_year_end.month)[1],
        ),
    )
    if period_end <= candidate:
        return candidate
    return date(
        period_end.year + 1,
        observed_fiscal_year_end.month,
        min(
            observed_fiscal_year_end.day,
            calendar.monthrange(period_end.year + 1, observed_fiscal_year_end.month)[1],
        ),
    )


def _next_cvm_report_deadline(
    period_end: date, document_type: str, observed_fiscal_year_end: date | None
) -> date:
    """Data-limite regulatória do PRÓXIMO reporte periódico esperado que
    substituiria economicamente este documento.

    - DFP: o próximo reporte esperado é o primeiro ITR do exercício
      seguinte (period_end + 1 trimestre), com prazo de entrega de 45 dias.
    - ITR que NÃO é o último trimestre antes do fechamento do exercício:
      o próximo reporte esperado é o próximo ITR (period_end + 1
      trimestre + 45 dias).
    - ITR que É o último trimestre antes do fechamento (ou, por segurança,
      qualquer ITR cujo period_end coincida com o próprio fechamento):
      o próximo reporte esperado é a DFP do exercício corrente
      (encerramento fiscal RELEVANTE para este period_end + 3 meses
      calendáricos) — nunca herda a janela de um ITR seguinte que não
      existirá (não há ITR do último trimestre), e nunca usa o ANO
      histórico da DFP mais recente cegamente: o mês/dia observado é
      projetado para o ciclo fiscal ao qual este period_end pertence via
      _fiscal_year_end_for_period().
    - fiscal_year_end desconhecido: usa o fallback conservador (nunca
      inventa calendário fiscal).

    Invariante: o prazo nunca pode anteceder o próprio period_end — se a
    aritmética de calendário resultasse nisso (não deveria, dado o
    rollover acima), o resultado é travado no próprio period_end como
    salvaguarda de última linha.
    """
    kind = (document_type or "").upper()

    if kind == "DFP":
        # period_end de uma DFP É o encerramento do exercício, por
        # definição regulatória — não é uma suposição.
        next_quarter_end = _add_months(period_end, 3)
        deadline = _add_days(next_quarter_end, CVM_QUARTERLY_FILING_DEADLINE_DAYS)
        return max(deadline, period_end)

    if observed_fiscal_year_end is None:
        deadline = _add_days(period_end, CVM_UNKNOWN_FISCAL_CALENDAR_FALLBACK_DAYS)
        return max(deadline, period_end)

    relevant_fiscal_year_end = _fiscal_year_end_for_period(period_end, observed_fiscal_year_end)
    months_to_fye = (relevant_fiscal_year_end.month - period_end.month) % 12
    if months_to_fye in (0, 3):
        # Último trimestre antes do fechamento (ou o próprio fechamento,
        # por segurança) -> o próximo reporte esperado é a DFP do
        # exercício corrente, entregue em até 3 MESES calendáricos após o
        # encerramento — nunca aproximado como "90 dias".
        deadline = _add_months(relevant_fiscal_year_end, CVM_ANNUAL_FILING_DEADLINE_MONTHS)
        return max(deadline, period_end)

    next_quarter_end = _add_months(period_end, 3)
    deadline = _add_days(next_quarter_end, CVM_QUARTERLY_FILING_DEADLINE_DAYS)
    return max(deadline, period_end)


def _cvm_valid_until(
    reference_date: datetime, document_type: str | None, fiscal_year_end: date | None
) -> datetime:
    """Validade temporal de um valor oficial CVM = prazo-limite esperado
    para o PRÓXIMO reporte financeiro periódico que o substituiria.

    Nunca infere o tipo pelo ticker/nome do indicador — recebe
    `document_type` diretamente de CvmFinancialDocument.document_type
    (DFP/ITR), propagado sem transformação desde o repository, e
    `fiscal_year_end` observado no histórico real de DFP do próprio
    emissor (CvmFinancialRepository.fiscal_year_end) — nunca assumido como
    31/12 para todas as companhias.
    """
    deadline = _next_cvm_report_deadline(
        reference_date.date(), document_type or "", fiscal_year_end
    )
    return datetime.combine(deadline, time.min, tzinfo=timezone.utc)


# A CADÊNCIA trimestral do Informe Trimestral de FII é um fato comprovado
# (é o próprio nome do dataset oficial da CVM -- fii-doc-inf_trimestral --
# e todos os Data_Referencia observados nos dados reais sincronizados
# correspondem a fins de trimestre). O PRAZO REGULATÓRIO exato de entrega
# deste informe específico à CVM (ANEXO 39-II da Instrução CVM 571/2015),
# porém, NÃO PÔDE ser confirmado no texto oficial dentro do escopo desta
# correção (as páginas de legislação consultadas em conteudo.cvm.gov.br
# não expuseram o texto do anexo em HTML plano acessível a este agente).
#
# Por isso, o valor abaixo NUNCA deve ser apresentado como uma obrigação
# da CVM -- é uma POLÍTICA TÉCNICA CONSERVADORA PRÓPRIA DO MESAQUANTMASTER
# para decidir quando um dado trimestral já sincronizado deixa de ser
# tratado como "atual" na ausência de um trimestre mais recente. Escolhida
# deliberadamente MENOR que o prazo de 45 dias do ITR corporativo (esse
# sim uma regra regulatória já confirmada -- ver CVM_QUARTERLY_FILING_
# DEADLINE_DAYS) para nunca ser confundida com ele, e para errar sempre
# no sentido de marcar STALE mais cedo, nunca de estender validade além
# do comprovado.
FII_QUARTERLY_TECHNICAL_FRESHNESS_WINDOW_DAYS = 30


def _fii_vacancy_valid_until(reference_date: date) -> datetime:
    """Validade TÉCNICA (não regulatória -- ver constante acima) do dado
    oficial de vacância de FII: cadência trimestral real do documento +
    janela de segurança própria do MesaQuantMaster.
    """
    next_quarter_end = _add_months(reference_date, 3)
    deadline = _add_days(next_quarter_end, FII_QUARTERLY_TECHNICAL_FRESHNESS_WINDOW_DAYS)
    return datetime.combine(deadline, time.min, tzinfo=timezone.utc)


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
        cvm_link_session_factory=None,
        cvm_fii_repository: CvmFiiRepository | None = None,
        fii_link_session_factory=None,
    ):
        self.market_service = market_service
        self.normalizer = normalizer
        self.snapshot_repository = snapshot_repository
        self.manual_repository = manual_repository
        self.bcb_provider = bcb_provider or BcbSgsProvider()
        self.treasury_provider = treasury_provider or self._default_treasury_provider()
        self.cvm_provider = cvm_provider or CvmOpenDataProvider()
        self.cvm_repository = cvm_repository
        # Fábrica de sessão usada SOMENTE para persistir o vínculo automático
        # ativo<->emissor CVM (ver _persist_cvm_link_isolated) — nunca para
        # nada relacionado à resolução de indicadores em si, que continua
        # usando exclusivamente self.cvm_repository/sua sessão compartilhada.
        self.cvm_link_session_factory = cvm_link_session_factory or SessionLocal
        self.cvm_fii_repository = cvm_fii_repository
        # Mesma filosofia de isolamento acima, aplicada ao vínculo
        # automático ativo<->fundo FII (ver _persist_fii_link_isolated).
        self.fii_link_session_factory = fii_link_session_factory or SessionLocal

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
            if asset_class == InvestmentClass.FII:
                self._apply_fii_brapi_derived(resolved, payloads, collected_at)
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

        if (
            asset_class == InvestmentClass.FII
            and asset_id is not None
            and self._has_unresolved(resolved)
        ):
            self._apply_fii_official_risk(resolved, asset_id, collected_at, symbol=symbol)

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
            # "indicators" traz o segmentType real (papel/tijolo) e dados
            # financeiros; "properties"/"portfolio" trazem vacância física
            # agregada e a composição de ativos (financialAssets) usada
            # para concentração de devedores em FII de papel -- cada
            # dataset é tentado isoladamente (ver loop abaixo), então uma
            # falha de plano em um deles nunca invalida os outros.
            ["indicators", "properties", "portfolio"]
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

    def _apply_fii_brapi_derived(self, resolved, payloads, collected_at) -> None:
        """Indicadores de FII resolvidos a partir de estruturas brutas da
        BRAPI (listas/objetos aninhados, não um único campo escalar --
        merge_provider_payloads via alias não alcança nem escala esses
        casos corretamente).

        CONTRATO INTERNO de indicadores unit="percent" (ver display_value):
        o `value` armazenado é em PONTOS PERCENTUAIS (70 para 70%, 2.4133
        para 2,4133%) -- nunca uma fração (0.70, 0.024133). A BRAPI expõe
        vacancyRate e a participação de devedores como FRAÇÃO (0-1); a
        conversão para pontos percentuais acontece exatamente aqui, no
        boundary de construção do indicador, nunca dentro de
        merge_provider_payloads (que é genérico para todo o sistema e não
        deve ganhar uma multiplicação global por campo "percent").
        """
        self._apply_physical_vacancy_from_brapi(resolved, payloads, collected_at)
        self._apply_debtor_concentration_from_brapi(resolved, payloads, collected_at)

    def _apply_physical_vacancy_from_brapi(self, resolved, payloads, collected_at) -> None:
        """physical_vacancy a partir do resumo agregado de vacância da
        BRAPI -- fii/properties.summary.vacancyRate (direto) ou
        fii/portfolio.summary.properties.vacancyRate (mesmo dado, um nível
        a mais de aninhamento). Nunca usa o valor por imóvel individual.
        """
        current = resolved.get("physical_vacancy")
        if current is None or current.status in self._RESOLVED_STATUSES:
            return
        found = self._find_fii_vacancy_summary(payloads)
        if found is None:
            return
        summary, dataset, reference_raw = found
        raw = summary.get("vacancyRate")
        if raw is None:
            return
        try:
            fraction = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return
        value = fraction * Decimal("100")
        reference = self._parse_brapi_date(reference_raw) or collected_at
        resolved["physical_vacancy"] = current.model_copy(
            update={
                "value": value,
                "display_value": display_value(value, "percent", None),
                "status": IndicatorStatus.AVAILABLE,
                "source": "BRAPI",
                "source_type": "provider",
                "reference_date": reference,
                "collected_at": collected_at,
                "valid_until": self._valid_until(
                    "physical_vacancy", collected_at, source_type="provider"
                ),
                "freshness_status": "current",
                "confidence": ConfidenceLevel.HIGH,
                "period": "período informado pelo provedor",
                "unavailable_reason": None,
                "provider_failure_reason": None,
                "provenance": {
                    "provider": "brapi",
                    "dataset": dataset,
                    "field": "summary.vacancyRate",
                    "method": "fração da BRAPI convertida para pontos percentuais (fração * 100)",
                    "reference_date": str(reference_raw) if reference_raw else None,
                },
            }
        )

    def _apply_debtor_concentration_from_brapi(self, resolved, payloads, collected_at) -> None:
        """debtor_concentration a partir da lista financialAssets do
        dataset fii/portfolio.

        Concentração = participação do MAIOR emissor único sobre o total
        de ativos financeiros do fundo -- só calculado quando a lista real
        tem pelo menos um item com valor informado; nunca inventa 0%
        quando a lista está ausente/vazia (fundo de tijolo sem carteira de
        papel simplesmente não tem este dado, o que é diferente de "0%
        concentrado").
        """
        current = resolved.get("debtor_concentration")
        if current is None or current.status in self._RESOLVED_STATUSES:
            return
        portfolio_payload = self._find_fii_payload(payloads, "financialAssets")
        if portfolio_payload is None:
            return
        financial_assets = portfolio_payload.get("financialAssets") or []
        fraction = self._largest_issuer_share(financial_assets)
        if fraction is None:
            return
        value = fraction * Decimal("100")
        reference_raw = portfolio_payload.get("referenceDate")
        reference = self._parse_brapi_date(reference_raw) or collected_at
        resolved["debtor_concentration"] = current.model_copy(
            update={
                "value": value,
                "display_value": display_value(value, "percent", None),
                "status": IndicatorStatus.AVAILABLE,
                "source": "BRAPI",
                "source_type": "provider",
                "reference_date": reference,
                "collected_at": collected_at,
                "valid_until": self._valid_until(
                    "debtor_concentration", collected_at, source_type="provider"
                ),
                "freshness_status": "current",
                "confidence": ConfidenceLevel.HIGH,
                "period": "período informado pelo provedor",
                "unavailable_reason": None,
                "provider_failure_reason": None,
                "provenance": {
                    "provider": "brapi",
                    "dataset": "fii/portfolio",
                    "field": "financialAssets",
                    "method": (
                        "maior valor de um único emissor (issuerCnpj) dividido "
                        "pelo total de financialAssets, convertido para pontos "
                        "percentuais (fração * 100)"
                    ),
                    "reference_date": str(reference_raw) if reference_raw else None,
                },
            }
        )

    @staticmethod
    def _find_fii_payload(payloads: list[dict], required_key: str) -> dict | None:
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            fiis = payload.get("fiis")
            if not isinstance(fiis, list) or not fiis:
                continue
            first = fiis[0]
            if isinstance(first, dict) and first.get(required_key):
                return first
        return None

    @staticmethod
    def _find_fii_vacancy_summary(payloads: list[dict]) -> tuple[dict, str, str | None] | None:
        """Localiza o resumo agregado de vacância em qualquer payload FII
        já obtido -- fii/properties.summary (direto) ou
        fii/portfolio.summary.properties (mesmo dado, aninhado um nível a
        mais). `payloads` é uma lista simples (sem o nome do dataset
        anexado -- ver _load_brapi_free), então o dataset de origem é
        inferido pela FORMA estrutural encontrada, não por um rótulo
        recebido de fora. Retorna (summary_dict, dataset_label, referenceDate).
        """
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            fiis = payload.get("fiis")
            if not isinstance(fiis, list) or not fiis:
                continue
            first = fiis[0]
            if not isinstance(first, dict):
                continue
            summary = first.get("summary")
            if not isinstance(summary, dict):
                continue
            reference = first.get("referenceDate")
            if "vacancyRate" in summary:
                return summary, "fii/properties", reference
            nested = summary.get("properties")
            if isinstance(nested, dict) and "vacancyRate" in nested:
                return nested, "fii/portfolio", reference
        return None

    @staticmethod
    def _largest_issuer_share(financial_assets: list[dict]) -> Decimal | None:
        by_issuer: dict[str, Decimal] = {}
        total = Decimal("0")
        for item in financial_assets:
            if not isinstance(item, dict) or item.get("value") is None:
                continue
            try:
                amount = Decimal(str(item["value"]))
            except (InvalidOperation, ValueError):
                continue
            issuer_key = str(
                item.get("issuerCnpj") or item.get("issuer") or item.get("name") or ""
            ).strip()
            if not issuer_key:
                continue
            total += amount
            by_issuer[issuer_key] = by_issuer.get(issuer_key, Decimal("0")) + amount
        if not by_issuer or total <= 0:
            return None
        return max(by_issuer.values()) / total

    @staticmethod
    def _parse_brapi_date(value) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

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

        # Encerramento do exercício social OBSERVADO no histórico real de
        # DFP deste emissor — nunca assumido como 31/12 para todos (ver
        # CvmFinancialRepository.fiscal_year_end e _cvm_valid_until).
        # Buscado uma única vez por ativo, reaproveitado para todas as
        # contas brutas e para os indicadores derivados abaixo.
        fiscal_year_end = self.cvm_repository.fiscal_year_end(issuer.id)

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
                    "valid_until": _cvm_valid_until(
                        reference, document.document_type, fiscal_year_end
                    ),
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
                resolved, grouped, derived_pending, collected_at, fiscal_year_end
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
        persisted = self._persist_cvm_link_isolated(asset_id, issuer.id)
        # Nunca retorna o issuer como vínculo utilizável se a transação
        # isolada não confirmou (nem por sucesso direto, nem por corrida
        # concorrente idempotente) que o vínculo realmente existe no banco
        # -- o chamador não pode acreditar em uma persistência que falhou.
        # A cascata de resolução trata isso exatamente como "identificador
        # ainda não resolvido" (mesmo diagnóstico conservador já usado
        # quando não há CNPJ ou não há emissor correspondente).
        return issuer if persisted else None

    def _persist_cvm_link_isolated(self, asset_id, issuer_id) -> bool:
        """Persiste o vínculo ativo<->emissor CVM em uma transação CURTA e
        ISOLADA, própria — nunca na sessão compartilhada usada para resolver
        indicadores (self.cvm_repository).

        Isto evita que este pequeno fato de identidade, criado como efeito
        colateral automático de uma resolução maior, comite (ou dependa de)
        qualquer outro trabalho pendente e não relacionado na sessão do
        chamador. Abre sua própria sessão via cvm_link_session_factory,
        comita/reverte/fecha essa sessão isolada, e nunca toca na sessão de
        resolução.

        Retorna True somente se o vínculo asset_id -> issuer_id está
        confirmadamente persistido (por esta transação ou por uma
        concorrente equivalente -- ver _resolve_concurrent_link_race).
        Retorna False em qualquer falha real, incluindo quando já existe
        um vínculo (seja lido diretamente aqui, seja detectado por uma
        corrida concorrente) apontando para um emissor DIFERENTE -- o
        auto-link NUNCA substitui silenciosamente a identidade de um
        emissor já vinculado; isso é uma ação exclusiva do fluxo manual
        (CvmFinancialService.link_asset, via CvmFinancialRepository.
        link_asset, que é create-or-update deliberado). Uma falha aqui
        nunca lança exceção para o chamador (mesma filosofia do restante
        de _auto_link_cvm_issuer: o pior caso é "ainda não vinculado nesta
        tentativa", nunca uma cascata de resolução interrompida) -- mas
        também nunca finge sucesso que não aconteceu.
        """
        db = self.cvm_link_session_factory()
        try:
            try:
                link = CvmFinancialRepository(db).ensure_asset_link(asset_id, issuer_id)
                if link is None:
                    # Já existia vínculo para um issuer DIFERENTE -- nada
                    # foi alterado (ensure_asset_link não muta neste caso).
                    # Conflito real, nunca sobrescrito silenciosamente.
                    db.rollback()
                    return False
                db.commit()
                return True
            except IntegrityError:
                # asset_cvm_issuers.asset_id é unique: duas transações
                # podem ter lido "sem vínculo" e tentado inserir ao mesmo
                # tempo. Não é necessariamente um erro real -- relê em
                # transação limpa antes de decidir.
                db.rollback()
                return self._resolve_concurrent_link_race(db, asset_id, issuer_id)
            except Exception:
                db.rollback()
                return False
        finally:
            db.close()

    def _resolve_concurrent_link_race(self, db, asset_id, issuer_id) -> bool:
        """Decide o resultado de uma corrida concorrente em asset_cvm_issuers
        após um IntegrityError + rollback, relendo o estado real do banco em
        transação limpa (mesma sessão isolada, já revertida).

        Se a transação concorrente vinculou o asset ao MESMO issuer que
        esta tentativa pretendia, trata como sucesso idempotente (o efeito
        desejado já existe, não é um erro). Se apontar para um issuer
        DIFERENTE, é um conflito de identidade real -- nunca sobrescreve
        silenciosamente; retorna False para que o chamador trate como
        "ainda não vinculado por esta tentativa", preservando o vínculo já
        existente intacto.

        Compara o issuer_id BRUTO da linha (find_link), não o CvmIssuer
        relacionado (linked_issuer) -- esta checagem não precisa carregar o
        emissor, só confirmar a que issuer_id o vínculo aponta.
        """
        existing_link = CvmFinancialRepository(db).find_link(asset_id)
        return existing_link is not None and existing_link.issuer_id == issuer_id

    def _apply_fii_official_risk(self, resolved, asset_id, collected_at, symbol) -> None:
        """Vacância física oficial de FII, via CVM Dados Abertos (Informe
        Trimestral) -- fallback usado quando BRAPI não resolveu
        physical_vacancy (indisponível pelo plano, ou fundo de papel sem
        dado a resolver por essa via). Segue a MESMA prioridade/filosofia
        de _apply_cvm: só roda se ainda houver algo pendente, nunca
        sobrescreve algo já resolvido, nunca inventa dado ausente.
        """
        if self.cvm_fii_repository is None:
            return
        current = resolved.get("physical_vacancy")
        if current is None or current.status in self._RESOLVED_STATUSES:
            return
        issuer = self.cvm_fii_repository.linked_issuer(asset_id)
        if issuer is None:
            issuer = self._auto_link_fii_issuer(asset_id, symbol)
        if issuer is None:
            return
        document = self.cvm_fii_repository.latest_vacancy_document(issuer.id)
        if document is None:
            return
        reference = datetime.combine(
            document.reference_date, time.min, tzinfo=timezone.utc
        )
        valid_until = _fii_vacancy_valid_until(document.reference_date)
        if collected_at > valid_until:
            # Documento oficial mais recente já expirou pela própria
            # cadência trimestral -- não finge que ainda é atual.
            return
        # document.area_weighted_vacancy_rate é uma FRAÇÃO (0-1, mesma
        # escala do campo oficial Percentual_Vacancia da CVM) -- o
        # contrato interno de indicadores "percent" espera pontos
        # percentuais (ver display_value), conversão explícita aqui.
        value = Decimal(document.area_weighted_vacancy_rate) * Decimal("100")
        resolved["physical_vacancy"] = current.model_copy(
            update={
                "value": value,
                "display_value": display_value(value, "percent", None),
                "unit": "percent",
                "status": IndicatorStatus.AVAILABLE,
                "source": "CVM Dados Abertos (FII)",
                "source_type": "official",
                "reference_date": reference,
                # collected_at é quando o documento oficial foi de fato
                # coletado/sincronizado (FiiPropertyVacancyDocument.
                # collected_at) -- nunca o horário desta análise, que é
                # uma informação totalmente diferente (ver _aware, mesmo
                # padrão já usado por _apply_cvm para CvmFinancialDocument).
                "collected_at": self._aware(document.collected_at) or collected_at,
                "valid_until": valid_until,
                "freshness_status": "current",
                "confidence": ConfidenceLevel.HIGH,
                "period": "trimestral",
                "unavailable_reason": None,
                "provider_failure_reason": None,
                "provenance": {
                    "provider": "cvm",
                    "dataset": "fii-doc-inf_trimestral",
                    "resource": document.source_resource,
                    "document_type": "INF_TRIMESTRAL",
                    "reference_date": str(document.reference_date),
                    "version": document.version,
                    "cnpj_fundo_classe": issuer.cnpj,
                    "property_count": document.property_count,
                    "method": document.aggregation_method,
                },
            }
        )

    def _auto_link_fii_issuer(self, asset_id, symbol: str):
        """Vincula automaticamente ativo<->fundo FII por CNPJ EXATO -- mesma
        regra do auto-link corporativo (nunca por nome). Usa o CNPJ do
        perfil do provedor de mercado; só vincula se houver correspondência
        exata com um FiiIssuer já sincronizado via Informe Trimestral.
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
        issuer = self.cvm_fii_repository.find_issuer_by_cnpj(cnpj)
        if issuer is None:
            return None
        persisted = self._persist_fii_link_isolated(asset_id, issuer.id)
        return issuer if persisted else None

    def _persist_fii_link_isolated(self, asset_id, issuer_id) -> bool:
        """Persiste o vínculo ativo<->fundo FII em transação curta e
        isolada, própria -- nunca na sessão compartilhada de resolução.
        Mesma arquitetura de _persist_cvm_link_isolated (ver essa
        docstring para a motivação completa): retorna True somente com
        persistência confirmada (direta ou por corrida concorrente
        idempotente), nunca sobrescreve um vínculo existente para um
        fundo diferente, nunca lança exceção para o chamador.
        """
        db = self.fii_link_session_factory()
        try:
            try:
                link = CvmFiiRepository(db).ensure_asset_link(asset_id, issuer_id)
                if link is None:
                    db.rollback()
                    return False
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                existing_link = CvmFiiRepository(db).find_link(asset_id)
                return existing_link is not None and existing_link.issuer_id == issuer_id
            except Exception:
                db.rollback()
                return False
        finally:
            db.close()

    def _apply_cvm_derived_indicators(
        self,
        resolved,
        grouped,
        pending: set[str],
        collected_at: datetime,
        fiscal_year_end: date | None,
    ) -> set[str]:
        """Calcula indicadores derivados (seção 6 do resolver híbrido) a
        partir de componentes brutos já apurados pelo CVM, quando todos os
        componentes necessários existem e são COMPATÍVEIS — mesmo period_end
        E mesmo document_type (DFP não se mistura com ITR: são periodicidades
        diferentes, mesmo quando coincidem em period_end) — nunca divide por
        zero, nunca converte ausência em zero. O document_type e o
        period_end vencedores são propagados para a política de validade
        temporal por próximo reporte esperado (_cvm_valid_until) e para o
        provenance.
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
                    "valid_until": _cvm_valid_until(
                        reference, document_type, fiscal_year_end
                    ),
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
