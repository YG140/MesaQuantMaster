"""Auditoria de pré-compra: barata, determinística e sem efeitos colaterais.

Apenas a seleção de *novos aportes* é afetada; posições, ordens,
cotações e classificação histórica não são alteradas. Não faz scraping
ou consultas à SEC por ticker (CIK ainda não faz parte do cadastro).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from app.schemas.market_intelligence import IndicatorStatus, InvestmentClass

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.schemas.market_intelligence import AssetIntelligenceSnapshot
    from app.services.official_source_verification_service import (
        OfficialSourceVerificationService,
    )


BLOCKED_ANOMALIES = {
    "identifier_unresolved",
    "issuer_identity_unresolved",
    "conflicting_sources",
}
BALANCE_METRICS = {"assets", "equity"}
COMPARISON_TOLERANCE = Decimal("0.01")
ABSOLUTE_TOLERANCE_BRL = Decimal("1")


@dataclass(frozen=True)
class PurchaseAuditResult:
    blocking_reasons: tuple[str, ...] = ()
    official_comparisons: int = 0


class PrePurchaseAuditService:
    """Não cria novas fontes nem reavalia a carteira já existente.

    Apenas CONFLITOS COMPROVADOS e vencimento de cotação explicitamente
    datada geram veto de compra. Falta de documento/CNPJ ou erro no
    repositório CVM não é prova de conflito, e portanto não bloqueia.
    """

    def __init__(self, official_service: "OfficialSourceVerificationService | None" = None):
        self.official_service = official_service

    def check(
        self,
        snapshot: "AssetIntelligenceSnapshot",
        asset: "Asset | None",
        *,
        now: datetime | None = None,
    ) -> PurchaseAuditResult:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            current = current.replace(tzinfo=timezone.utc)
        reasons = []
        flags = set(snapshot.anomaly_flags or [])
        if flags & {"identifier_unresolved", "issuer_identity_unresolved"}:
            reasons.append("Identidade do ativo em conflito na análise; novo aporte suspenso.")
        if "conflicting_sources" in flags:
            reasons.append("Fontes de mercado em conflito; novo aporte suspenso.")

        observed = snapshot.market_updated_at
        if observed is not None:
            if observed.tzinfo is None or observed.utcoffset() is None:
                observed = observed.replace(tzinfo=timezone.utc)
            if observed > current + timedelta(minutes=5):
                reasons.append("Cotação datada no futuro; novo aporte suspenso.")
            elif (
                snapshot.asset_class in {
                    InvestmentClass.STOCK, InvestmentClass.FII,
                    InvestmentClass.ETF, InvestmentClass.BDR,
                    InvestmentClass.INTERNATIONAL,
                }
                and current - observed > timedelta(days=7)
            ):
                reasons.append("Cotação com mais de sete dias; novo aporte suspenso.")
            elif (
                snapshot.asset_class == InvestmentClass.CRYPTO
                and current - observed > timedelta(hours=48)
            ):
                reasons.append("Cotação de criptomoeda desatualizada; novo aporte suspenso.")

        # Evita consulta SQL se não há nenhum indicador comparável.
        # Jamais liga USD a dados BRL; SEC exige CIK exato e não é inferida.
        if (
            self.official_service is None
            or asset is None
            or not getattr(asset, "id", None)
            or snapshot.asset_class != InvestmentClass.STOCK
            or (getattr(asset, "asset_type", "") or "").lower() not in {
                "stock", "acao", "ação", "ações"
            }
            or (getattr(asset, "currency", "") or "").upper() != "BRL"
            or (getattr(asset, "exchange", "") or "").upper() not in {
                "", "B3", "BOVESPA", "SAO PAULO"
            }
        ):
            return PurchaseAuditResult(tuple(reasons))
        usable = [
            ind for ind in snapshot.indicators
            if ind.key in BALANCE_METRICS
            and ind.status == IndicatorStatus.AVAILABLE
            and ind.source_type in {"official", "provider"}
            and ind.unit == "currency"
            and ind.reference_date is not None
            and isinstance(ind.provenance, dict)
            and (ind.provenance.get("scope") == "consolidated"
                 or (ind.source_type == "official" and ind.provenance.get("provider") == "cvm"))
            and isinstance(ind.value, Decimal) and ind.value.is_finite()
        ]
        if not usable:
            return PurchaseAuditResult(tuple(reasons))
        try:
            filing = self.official_service.verify_brazil(asset)
        except Exception:
            # Erro operacional (banco temporariamente indisponível) não
            # é evidência de fraude ou conflito. Não bloqueia outros ativos.
            return PurchaseAuditResult(tuple(reasons))
        if filing.status != "verified_filing":
            return PurchaseAuditResult(tuple(reasons))

        official_by_key: dict[tuple[str, object], list] = {}
        for fact in filing.facts:
            if fact.metric in BALANCE_METRICS and fact.unit == "BRL":
                official_by_key.setdefault((fact.metric, fact.period_end), []).append(fact)
        comparisons = 0
        expected_cnpj = (
            filing.issuer_id.removeprefix("CNPJ:")
            if filing.issuer_id and filing.issuer_id.startswith("CNPJ:")
            else None
        )
        for ind in usable:
            provenance = ind.provenance if isinstance(ind.provenance, dict) else {}
            claimed_cnpj = provenance.get("cnpj")
            if (
                ind.source_type == "official"
                and provenance.get("provider") == "cvm"
                and expected_cnpj
                and claimed_cnpj is not None
                and str(claimed_cnpj) != expected_cnpj
            ):
                reasons.append(
                    f"Identidade CVM divergente no indicador {ind.key}; novo aporte suspenso."
                )
                continue

            # Comparar balanços de escopos distintos (individual x
            # consolidado) geraria falsos alarmes. CVM de referência é
            # consolidada; a outra fonte precisa DECLARAR mesmo escopo.
            if provenance.get("scope") != "consolidated":
                continue
            same_period = official_by_key.get((ind.key, ind.reference_date.date()), [])
            # Várias observações da própria fonte para a mesma data não
            # permitem presumir qual delas seria comparável. Não misturar.
            if len(same_period) != 1:
                continue
            fact = same_period[0]
            comparisons += 1
            discrepancy = abs(ind.value - fact.value)
            tolerance = max(
                ABSOLUTE_TOLERANCE_BRL, abs(fact.value) * COMPARISON_TOLERANCE
            )
            if discrepancy > tolerance:
                reasons.append(
                    f"Indicador {ind.key} diverge da CVM no mesmo período; "
                    "novo aporte suspenso."
                )
        return PurchaseAuditResult(tuple(dict.fromkeys(reasons)), comparisons)
