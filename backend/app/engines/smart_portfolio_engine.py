from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from app.schemas.intelligence import (
    BuildPortfolioAsset,
    BuildPortfolioClassAllocation,
    BuildPortfolioExclusion,
    BuildPortfolioIndicator,
    BuildPortfolioPreflight,
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    BuildPortfolioSelection,
    ContributionPriority,
)
from app.engines.financial_planning_engine import (
    FinancialDiagnosisEngine,
    FinancialProjectionEngine,
)
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot,
    ConfidenceLevel,
    IndicatorStatus,
    InvestmentClass,
)


HUNDRED = Decimal("100")
CENT = Decimal("0.01")

# Categorias reais de score já calculadas pelo motor P1 (market_intelligence_engine).
# Usadas para derivar um ranking sem overall_score legado, sem jamais
# preencher uma categoria ausente com zero.
SCORE_COMPONENT_FIELDS = (
    "quality_score",
    "valuation_score",
    "income_score",
    "growth_score",
    "debt_score",
    "risk_score",
    "liquidity_score",
)

CRITICAL_IDENTITY_ANOMALY_FLAGS = {"identifier_unresolved", "issuer_identity_unresolved"}
CRITICAL_CONFLICT_ANOMALY_FLAGS = {"conflicting_sources"}

CLASS_LABELS = {
    InvestmentClass.STOCK: "Ações",
    InvestmentClass.FII: "FIIs",
    InvestmentClass.ETF: "ETFs",
    InvestmentClass.TREASURY: "Tesouro Direto",
    InvestmentClass.CDB: "Renda fixa bancária",
    InvestmentClass.LCI: "Renda fixa bancária",
    InvestmentClass.LCA: "Renda fixa bancária",
    InvestmentClass.DEBENTURE: "Crédito privado",
    InvestmentClass.INVESTMENT_FUND: "Fundos de investimento",
    InvestmentClass.BDR: "BDRs",
    InvestmentClass.INTERNATIONAL: "Ativos internacionais",
    InvestmentClass.CRYPTO: "Criptomoedas",
    InvestmentClass.UNKNOWN: "Outros",
}


@dataclass(frozen=True)
class PortfolioCandidate:
    snapshot: AssetIntelligenceSnapshot
    sector: str | None = None
    issuer: str | None = None


class SmartPortfolioEngine:
    """Regras puras de elegibilidade, pontuação e alocação da carteira V1."""

    @classmethod
    def build(
        cls,
        request: BuildPortfolioRequest,
        candidates: list[PortfolioCandidate],
        *,
        provider_errors: list[str] | None = None,
        universe_total: int | None = None,
        universe_considered: int | None = None,
        universe_truncated: bool = False,
        batch_size: int = 0,
        batch_count: int = 0,
    ) -> BuildPortfolioResponse:
        now = datetime.now(timezone.utc)
        diagnosis = FinancialDiagnosisEngine.diagnose(request)
        projections = FinancialProjectionEngine.project(request)
        eligible, exclusions = cls.eligibility(request, candidates)
        ranked = cls.score(request, eligible)[: request.max_assets]
        percentages = cls.allocate(request, ranked)

        assets = []
        for candidate, score in ranked:
            percentage = percentages.get(candidate.snapshot.symbol, Decimal("0"))
            if percentage <= 0:
                exclusions.append(
                    BuildPortfolioExclusion(
                        symbol=candidate.snapshot.symbol,
                        asset_class=cls.class_label(candidate.snapshot.asset_class),
                        reasons=["Limites de concentração não permitiram alocação."],
                    )
                )
                continue
            assets.append(
                cls.explain(request, candidate, score, percentage, diagnosis.phase)
            )

        class_totals: dict[str, Decimal] = defaultdict(Decimal)
        for asset in assets:
            class_totals[asset.asset_class] += asset.recommended_percentage
        class_allocations = [
            BuildPortfolioClassAllocation(
                asset_class=asset_class,
                percentage=percentage.quantize(CENT),
                amount=(request.available_amount * percentage / HUNDRED).quantize(CENT),
                explanation="Soma das alocações elegíveis da classe, limitada pelas restrições informadas.",
            )
            for asset_class, percentage in sorted(class_totals.items())
        ]
        allocated_amount = sum(
            (item.executable_amount for item in assets), Decimal("0")
        ).quantize(CENT)
        allocated_percentage = (
            (allocated_amount / request.available_amount * HUNDRED).quantize(CENT)
            if request.available_amount
            else Decimal("0")
        )
        unallocated = (request.available_amount - allocated_amount).quantize(CENT)
        missing = sorted({item for asset in assets for item in asset.missing_data})
        if provider_errors:
            missing.append("Parte das fontes de mercado não respondeu.")
        confidence = cls.portfolio_confidence(
            assets, unallocated, request.available_amount
        )
        status = (
            "available"
            if assets and unallocated == 0
            else "partial" if assets else "unavailable"
        )
        selections = [
            BuildPortfolioSelection(
                asset_class=item.asset_class,
                message=f"{sum(1 for asset in assets if asset.asset_class == item.asset_class)} ativo(s) elegível(is).",
                data_status="disponível" if item.percentage > 0 else "indisponível",
            )
            for item in class_allocations
        ]
        sorted_exclusions = sorted(exclusions, key=lambda item: item.symbol)
        preflight = cls._preflight(
            candidates=candidates,
            eligible=eligible,
            exclusions=sorted_exclusions,
            provider_errors=provider_errors,
            universe_total=universe_total,
            universe_considered=universe_considered,
            universe_truncated=universe_truncated,
            batch_size=batch_size,
            batch_count=batch_count,
        )
        return BuildPortfolioResponse(
            class_allocations=class_allocations,
            selections=selections,
            assets=assets,
            exclusions=sorted_exclusions,
            total_allocated_percentage=allocated_percentage,
            total_allocated_amount=allocated_amount,
            unallocated_amount=unallocated,
            confidence=confidence,
            status=status,
            missing_data=missing,
            preflight=preflight,
            strategy_summary=(
                f"Objetivo {request.objective}; perfil {request.risk_profile}; "
                f"horizonte {request.horizon}; até {request.max_assets} ativos."
            ),
            diagnosis=diagnosis,
            contribution_plan=cls.contribution_plan(request, assets, diagnosis.phase),
            projections=projections,
            freedom_goal=FinancialProjectionEngine.freedom_goal(request, projections),
            generated_at=now,
        )

    @classmethod
    def eligibility(cls, request, candidates):
        """Elegibilidade estrutural (P2): usa o confidence já resolvido pelo P1
        (required completo + scoring real suficiente + sem anomalia crítica) em
        vez de reimplementar esses gates aqui. NÃO usa mais coverage_percentage
        legado, data_quality.recommendation_blocked ou overall_score is None
        como gates diretos — LOW/provider_coverage baixo/RECOMMENDED ou
        OPTIONAL ausentes nunca bloqueiam sozinhos.
        """
        eligible = []
        exclusions = []
        allowed = set(request.allowed_classes)
        prohibited = set(request.prohibited_classes)
        conservative = request.risk_profile.strip().lower() == "conservador"
        for candidate in sorted(candidates, key=lambda item: item.snapshot.symbol):
            snapshot = candidate.snapshot
            asset_class = cls.class_label(snapshot.asset_class)
            reasons = []
            if allowed and asset_class not in allowed:
                reasons.append("Classe fora da lista permitida.")
            if asset_class in prohibited:
                reasons.append("Classe explicitamente proibida.")
            if conservative and snapshot.asset_class == InvestmentClass.CRYPTO:
                reasons.append(
                    "Classe incompatível com o perfil conservador nesta versão."
                )
            if snapshot.current_price is None:
                reasons.append("Cotação atual indispensável não disponível.")
            elif snapshot.current_price <= 0:
                reasons.append("Cotação atual inválida (menor ou igual a zero).")
            if snapshot.confidence == ConfidenceLevel.INSUFFICIENT:
                reasons.append(cls._insufficiency_reason(snapshot))
            if reasons:
                exclusions.append(
                    BuildPortfolioExclusion(
                        symbol=snapshot.symbol, asset_class=asset_class, reasons=reasons
                    )
                )
            else:
                eligible.append(candidate)
        return eligible, exclusions

    @staticmethod
    def _insufficiency_reason(snapshot) -> str:
        """Traduz confidence == INSUFFICIENT numa causa específica e real,
        nunca uma mensagem genérica de "dados insuficientes"."""
        anomaly_flags = set(snapshot.anomaly_flags or [])
        if anomaly_flags & CRITICAL_IDENTITY_ANOMALY_FLAGS:
            return "Identidade do ativo não resolvida."
        if anomaly_flags & CRITICAL_CONFLICT_ANOMALY_FLAGS:
            return "Conflito crítico entre fontes de dados."
        breakdown = snapshot.coverage_breakdown
        if (
            breakdown is not None
            and breakdown.required_total
            and breakdown.required_satisfied < breakdown.required_total
        ):
            return "Pilar obrigatório aplicável não satisfeito."
        return "Categorias reais de scoring insuficientes para uma análise confiável."

    @classmethod
    def score(cls, request, candidates):
        ranked = []
        for candidate in candidates:
            snapshot = candidate.snapshot
            score = cls._effective_score(snapshot)
            if snapshot.strategy_fit_score is not None:
                score = score * Decimal("0.8") + snapshot.strategy_fit_score * Decimal(
                    "0.2"
                )
            if request.needs_income and snapshot.income_score is not None:
                score = score * Decimal("0.8") + snapshot.income_score * Decimal("0.2")
            if request.needs_liquidity and snapshot.liquidity_score is not None:
                score = score * Decimal("0.8") + snapshot.liquidity_score * Decimal(
                    "0.2"
                )
            ranked.append((candidate, score.quantize(CENT)))
        return sorted(ranked, key=lambda item: (-item[1], item[0].snapshot.symbol))

    @staticmethod
    def _effective_score(snapshot) -> Decimal:
        """Nunca fabrica score. Usa overall_score real quando existir; senão
        deriva a média SOMENTE dos score components realmente calculados
        (nunca preenche um component ausente com zero). Um candidato sem
        nenhum component real não deveria chegar aqui — teria
        confidence == INSUFFICIENT e sido excluído em eligibility(); o
        fallback para 0 abaixo é só uma rede de segurança determinística,
        nunca um valor fabricado para um caso real.
        """
        if snapshot.overall_score is not None:
            return snapshot.overall_score
        components = [
            value
            for value in (getattr(snapshot, field) for field in SCORE_COMPONENT_FIELDS)
            if value is not None
        ]
        if not components:
            return Decimal("0")
        return (sum(components, Decimal("0")) / Decimal(len(components))).quantize(CENT)

    @classmethod
    def allocate(cls, request, ranked):
        if not ranked:
            return {}
        class_members: dict[str, list[PortfolioCandidate]] = defaultdict(list)
        for candidate, _ in ranked:
            class_members[cls.class_label(candidate.snapshot.asset_class)].append(
                candidate
            )
        class_count = Decimal(len(class_members))
        equal_class_target = HUNDRED / class_count
        allocations = {}
        sector_totals: dict[str, Decimal] = defaultdict(Decimal)
        for asset_class in sorted(class_members):
            members = class_members[asset_class]
            class_cap = min(request.max_percentage_per_class, equal_class_target)
            remaining_class = class_cap
            for index, candidate in enumerate(members):
                slots = Decimal(len(members) - index)
                share = min(request.max_percentage_per_asset, remaining_class / slots)
                sector = candidate.sector or f"sem-setor:{candidate.snapshot.symbol}"
                sector_room = request.max_percentage_per_sector - sector_totals[sector]
                share = max(Decimal("0"), min(share, sector_room)).quantize(
                    CENT, rounding=ROUND_DOWN
                )
                if share > 0:
                    allocations[candidate.snapshot.symbol] = share
                    remaining_class -= share
                    sector_totals[sector] += share
        return allocations

    @classmethod
    def explain(cls, request, candidate, score, percentage, phase):
        snapshot = candidate.snapshot
        used = [
            BuildPortfolioIndicator(
                key=item.key,
                label=item.label,
                value=item.value,
                source=item.source,
                source_type=item.source_type,
                reference_date=item.reference_date,
                valid_until=item.valid_until,
                freshness_status=item.freshness_status,
            )
            for item in snapshot.indicators
            if item.status == IndicatorStatus.AVAILABLE
        ]
        reasons = list(snapshot.positive_reasons)
        reasons.append(
            f"Requisitos essenciais satisfeitos e scoring real suficiente "
            f"(confidence {snapshot.confidence.value})."
        )
        reasons.append(
            "Selecionado por pontuação determinística entre os ativos elegíveis."
        )
        risks = list(snapshot.warning_reasons)
        if candidate.sector is None:
            risks.append(
                "Setor não informado; controle setorial aplicado de forma conservadora por ativo."
            )
        target_amount = (request.available_amount * percentage / HUNDRED).quantize(CENT)
        price = snapshot.current_price
        impediments = []
        quantity = Decimal("0")
        if phase == "protection":
            impediments.append(
                "Execução suspensa enquanto reserva ou dívidas prioritárias exigem proteção."
            )
        elif price and price > 0:
            step = (
                Decimal("1")
                if snapshot.asset_class
                in {
                    InvestmentClass.STOCK,
                    InvestmentClass.FII,
                    InvestmentClass.ETF,
                    InvestmentClass.BDR,
                }
                else Decimal("0.01")
            )
            quantity = (target_amount / price / step).to_integral_value(
                rounding=ROUND_DOWN
            ) * step
        else:
            impediments.append(
                "Preço de referência indisponível para calcular quantidade."
            )
        executable_amount = (quantity * price).quantize(CENT) if price else Decimal("0")
        return BuildPortfolioAsset(
            symbol=snapshot.symbol,
            name=snapshot.name,
            asset_class=cls.class_label(snapshot.asset_class),
            sector=candidate.sector,
            issuer=candidate.issuer,
            recommended_percentage=percentage,
            recommended_amount=target_amount,
            score=score,
            reasons=reasons,
            risks=risks,
            indicators_used=used,
            missing_data=snapshot.missing_data,
            confidence=snapshot.confidence.value,
            reference_price=price,
            executable_quantity=quantity,
            executable_amount=executable_amount,
            effective_percentage=(
                executable_amount / request.available_amount * HUNDRED
            ).quantize(CENT),
            target_gap=(target_amount - executable_amount).quantize(CENT),
            execution_impediments=impediments,
        )

    @staticmethod
    def contribution_plan(request, assets, phase):
        if request.monthly_contribution <= 0:
            return []
        if phase == "protection":
            return [
                ContributionPriority(
                    priority=1,
                    symbol="RESERVA",
                    asset_class="Proteção financeira",
                    suggested_amount=request.monthly_contribution.quantize(CENT),
                    reason="Priorizar reserva de emergência e dívidas de alto custo antes de elevar o risco.",
                )
            ]
        remaining = request.monthly_contribution
        result = []
        for index, asset in enumerate(
            sorted(assets, key=lambda item: (-item.target_gap, item.symbol)), 1
        ):
            amount = min(remaining, max(Decimal("0"), asset.target_gap)).quantize(CENT)
            if amount <= 0:
                continue
            result.append(
                ContributionPriority(
                    priority=index,
                    symbol=asset.symbol,
                    asset_class=asset.asset_class,
                    suggested_amount=amount,
                    reason="Reduz a diferença entre a alocação alvo e a executável.",
                    uses_income=request.reinvest_income,
                )
            )
            remaining -= amount
            if remaining <= 0:
                break
        return result

    @staticmethod
    def class_label(asset_class: InvestmentClass) -> str:
        return CLASS_LABELS.get(asset_class, "Outros")

    @staticmethod
    def portfolio_confidence(assets, unallocated, available):
        if not assets:
            return ConfidenceLevel.INSUFFICIENT.value
        levels = {asset.confidence for asset in assets}
        ratio = unallocated / available if available else Decimal("1")
        if ratio > Decimal("0.25") or ConfidenceLevel.LOW.value in levels:
            return ConfidenceLevel.LOW.value
        if levels == {ConfidenceLevel.HIGH.value} and unallocated == 0:
            return ConfidenceLevel.HIGH.value
        return ConfidenceLevel.MEDIUM.value

    @classmethod
    def _preflight(
        cls,
        *,
        candidates,
        eligible,
        exclusions,
        provider_errors,
        universe_total,
        universe_considered,
        universe_truncated,
        batch_size,
        batch_count,
    ) -> BuildPortfolioPreflight:
        """Diagnóstico estrutural do universo/elegibilidade (P2).

        universe_total/universe_considered refletem o universo real quando
        informados pelo chamador (batches); caso contrário assumem o próprio
        conjunto de candidatos recebido, para engines-level callers que não
        fazem batching (ex.: testes diretos de SmartPortfolioEngine.build).
        """
        snapshots = [candidate.snapshot for candidate in candidates]
        assets_with_valid_price = sum(
            1
            for snapshot in snapshots
            if snapshot.current_price is not None and snapshot.current_price > 0
        )
        required_complete_count = sum(
            1
            for snapshot in snapshots
            if snapshot.coverage_breakdown.required_total == 0
            or snapshot.coverage_breakdown.required_satisfied
            == snapshot.coverage_breakdown.required_total
        )
        confidence_counts = Counter(snapshot.confidence.value for snapshot in snapshots)
        class_counts = Counter(cls.class_label(snapshot.asset_class) for snapshot in snapshots)
        exclusion_reason_counts: dict[str, int] = defaultdict(int)
        for exclusion in exclusions:
            for reason in exclusion.reasons:
                exclusion_reason_counts[reason] += 1

        return BuildPortfolioPreflight(
            universe_total=universe_total if universe_total is not None else len(candidates),
            universe_considered=(
                universe_considered if universe_considered is not None else len(candidates)
            ),
            universe_truncated=universe_truncated,
            batch_size=batch_size,
            batch_count=batch_count,
            snapshots_received=len(candidates),
            assets_with_valid_price=assets_with_valid_price,
            required_complete_count=required_complete_count,
            confidence_high_count=confidence_counts.get(ConfidenceLevel.HIGH.value, 0),
            confidence_medium_count=confidence_counts.get(ConfidenceLevel.MEDIUM.value, 0),
            confidence_low_count=confidence_counts.get(ConfidenceLevel.LOW.value, 0),
            confidence_insufficient_count=confidence_counts.get(
                ConfidenceLevel.INSUFFICIENT.value, 0
            ),
            eligible_count=len(eligible),
            excluded_count=len(exclusions),
            provider_error_count=len(provider_errors or []),
            class_counts=dict(class_counts),
            exclusion_reason_counts=dict(exclusion_reason_counts),
        )
