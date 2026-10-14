from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import UUID

from app.schemas.intelligence import (
    BuildPortfolioAsset,
    BuildPortfolioClassAllocation,
    BuildPortfolioExclusion,
    BuildPortfolioIndicator,
    ExistingHoldingAssessment,
    BuildPortfolioPreflight,
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    BuildPortfolioSelection,
    ContributionPriority,
    PortfolioPolicyRead,
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
from app.engines.portfolio_holdings_context import limit_new_contributions, assess_holdings
from app.services.symbol_identity import B3_MARKET, resolve_symbol_identity


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
class PortfolioHolding:
    # Origem: operações autenticadas, nunca o JSON de montagem.
    symbol: str
    quantity: Decimal
    value: Decimal
    valuation_basis: str
    asset_class: str | None = None
    sector: str | None = None
    issuer: str | None = None


@dataclass(frozen=True)
class PortfolioCandidate:
    snapshot: AssetIntelligenceSnapshot
    sector: str | None = None
    issuer: str | None = None
    market_context: str | None = None


# Classe do envelope da PortfolioPolicy que não corresponde a nenhum ativo
# de mercado selecionável pelo SmartPortfolio (reserva de emergência é
# tratada pelo FinancialDiagnosisEngine/fase "protection" e pelo
# contribution_plan, nunca por um PortfolioCandidate) -- nunca incluída em
# PortfolioStrategy.class_targets.
RESERVE_CLASS_LABEL = "Reserva de emergência"

# Valor NEUTRO quanto à origem: PortfolioPolicy é gravada tanto pelo
# onboarding do Perfil do Investidor (InvestorProfileService.confirm())
# quanto diretamente por POST/PUT /intelligence/policy -- o modelo
# PortfolioPolicy não tem nenhum campo de provenance que permita
# distinguir qual caminho gravou uma policy específica. "policy_source"
# só pode afirmar honestamente que UMA PortfolioPolicy persistida foi
# aplicada, nunca de onde ela veio (nem inventar essa origem).
POLICY_SOURCE = "portfolio_policy"
LEGACY_SOURCE = "request_legacy"


@dataclass(frozen=True)
class ClassTarget:
    target_percentage: Decimal
    minimum_percentage: Decimal
    maximum_percentage: Decimal


@dataclass(frozen=True)
class PortfolioStrategy:
    """Envelope estratégico EFETIVO para uma execução de build_portfolio.

    Fonte de verdade (ver AGENTS.md/auditoria): quando existe uma
    PortfolioPolicy persistida para o usuário (`source == POLICY_SOURCE`),
    todo campo estratégico vem dela -- nunca do corpo da requisição, que
    não pode sobrescrever silenciosamente uma política já persistida. Um
    override operacional do request só pode ser MAIS restritivo que a
    política, nunca mais permissivo (ver from_policy). A PortfolioPolicy
    pode ter sido criada pelo onboarding do Perfil do Investidor OU
    diretamente via POST/PUT /intelligence/policy -- ambos igualmente
    autoritativos; o modelo não persiste essa origem, então nada aqui
    afirma qual dos dois caminhos gravou a policy em uso.

    Quando não existe política (`source == LEGACY_SOURCE`), o
    comportamento anterior a esta mudança é preservado integralmente:
    todo campo estratégico vem do próprio BuildPortfolioRequest,
    class_targets fica vazio (aciona a alocação legada por classes
    iguais em allocate()) e max_percentage_per_issuer fica None (sem
    limite de emissor, igual ao comportamento anterior).
    """

    source: str
    policy_id: UUID | None
    risk_profile: str
    objective: str
    horizon: str
    monthly_contribution: Decimal
    needs_income: bool
    needs_liquidity: bool
    max_percentage_per_asset: Decimal
    max_percentage_per_sector: Decimal
    max_percentage_per_issuer: Decimal | None
    allowed_classes: frozenset[str]
    prohibited_classes: frozenset[str]
    class_targets: dict[str, ClassTarget] = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: BuildPortfolioRequest) -> "PortfolioStrategy":
        return cls(
            source=LEGACY_SOURCE,
            policy_id=None,
            risk_profile=request.risk_profile,
            objective=request.objective,
            horizon=request.horizon,
            monthly_contribution=request.monthly_contribution,
            needs_income=request.needs_income,
            needs_liquidity=request.needs_liquidity,
            max_percentage_per_asset=request.max_percentage_per_asset,
            max_percentage_per_sector=request.max_percentage_per_sector,
            max_percentage_per_issuer=None,
            allowed_classes=frozenset(request.allowed_classes),
            prohibited_classes=frozenset(request.prohibited_classes),
            class_targets={},
        )

    @classmethod
    def from_policy(
        cls, policy: PortfolioPolicyRead, request: BuildPortfolioRequest
    ) -> "PortfolioStrategy":
        enabled = [
            item
            for item in policy.allocations
            if item.enabled and item.asset_class != RESERVE_CLASS_LABEL
        ]
        class_targets = {
            item.asset_class: ClassTarget(
                target_percentage=item.target_percentage,
                minimum_percentage=item.minimum_percentage,
                maximum_percentage=item.maximum_percentage,
            )
            for item in enabled
        }
        # Classe proibida pelo perfil nunca pode ser reativada pelo
        # request (seção 14): o efetivo é a interseção com allowed_classes
        # do request quando informado, nunca a união. prohibited_classes
        # do request é sempre aditivo (só pode restringir mais).
        effective_allowed = set(class_targets.keys())
        if request.allowed_classes:
            effective_allowed &= set(request.allowed_classes)
        return cls(
            source=POLICY_SOURCE,
            policy_id=policy.id,
            risk_profile=policy.risk_profile,
            objective=policy.objective,
            horizon=policy.investment_horizon,
            monthly_contribution=policy.monthly_contribution,
            needs_income=policy.income_need,
            # liquidity_need é textual na política ("baixa"/"moderada"/
            # "alta"); needs_liquidity no scoring é binário -- "moderada"
            # e "alta" mapeiam para necessidade real de liquidez, só
            # "baixa" mapeia para False (ver auditoria, seção 16).
            needs_liquidity=policy.liquidity_need in {"moderada", "alta"},
            # Override operacional só pode ser MAIS restritivo que a
            # política, nunca mais permissivo (seção 11) -- min(), nunca
            # max().
            max_percentage_per_asset=min(
                policy.maximum_weight_per_asset, request.max_percentage_per_asset
            ),
            max_percentage_per_sector=min(
                policy.maximum_weight_per_sector, request.max_percentage_per_sector
            ),
            max_percentage_per_issuer=policy.maximum_weight_per_issuer,
            allowed_classes=frozenset(effective_allowed),
            prohibited_classes=frozenset(request.prohibited_classes),
            class_targets={
                asset_class: target
                for asset_class, target in class_targets.items()
                if asset_class in effective_allowed
            },
        )


class SmartPortfolioEngine:
    """Regras puras de elegibilidade, pontuação e alocação da carteira V1."""

    @classmethod
    def build(
        cls,
        request: BuildPortfolioRequest,
        candidates: list[PortfolioCandidate],
        *,
        policy: PortfolioPolicyRead | None = None,
        provider_errors: list[str] | None = None,
        universe_total: int | None = None,
        universe_considered: int | None = None,
        universe_truncated: bool = False,
        batch_size: int = 0,
        batch_count: int = 0,
        holdings: list[PortfolioHolding] | None = None,
    ) -> BuildPortfolioResponse:
        now = datetime.now(timezone.utc)
        strategy = (
            PortfolioStrategy.from_policy(policy, request)
            if policy is not None
            else PortfolioStrategy.from_request(request)
        )
        diagnosis = FinancialDiagnosisEngine.diagnose(request)
        projections = FinancialProjectionEngine.project(request)
        eligible, exclusions = cls.eligibility(strategy, candidates)
        ranked = cls.score(strategy, eligible)[: request.max_assets]
        percentages = cls.allocate(request, ranked, strategy)
        holding_notes: dict[str, str] = {}
        if holdings:
            percentages, holding_notes = limit_new_contributions(
                request, ranked, strategy, percentages, holdings, cls.class_label
            )

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
            recommended = cls.explain(request, candidate, score, percentage, diagnosis.phase)
            if holdings:
                existing = next(
                    (item for item in holdings if item.symbol == candidate.snapshot.symbol.upper()),
                    None,
                )
                previous_value = existing.value if existing else Decimal("0")
                portfolio_after = sum((item.value for item in holdings), Decimal("0")) + request.available_amount
                post_weight = (
                    (previous_value + recommended.executable_amount) / portfolio_after * HUNDRED
                ).quantize(CENT)
                note = holding_notes.get(candidate.snapshot.symbol)
                recommended = recommended.model_copy(update={
                    "existing_quantity": existing.quantity if existing else Decimal("0"),
                    "existing_value": previous_value,
                    "post_purchase_weight": post_weight,
                    "allocation_note": note,
                    "reasons": recommended.reasons + ([note] if note else []),
                })
            assets.append(recommended)

        class_totals: dict[str, Decimal] = defaultdict(Decimal)
        for asset in assets:
            class_totals[asset.asset_class] += asset.recommended_percentage
        class_allocations = cls._class_allocations(request, strategy, class_totals)
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
        holdings_warnings = []
        if holdings:
            fallback_count = sum(item.valuation_basis != "market" for item in holdings)
            if fallback_count:
                holdings_warnings.append(
                    f"{fallback_count} posição(ões) sem cotação: valor estimado pelo custo "
                    "registrado; limites de concentração são provisórios."
                )
                if confidence == ConfidenceLevel.HIGH.value:
                    confidence = ConfidenceLevel.MEDIUM.value
            if holding_notes:
                holdings_warnings.append(
                    "Aportes limitados pela concentração da carteira existente."
                )
        holding_assessments = (
            assess_holdings(holdings, candidates, strategy, cls._effective_score)
            if holdings else []
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
                f"Objetivo {strategy.objective}; perfil {strategy.risk_profile}; "
                f"horizonte {strategy.horizon}; até {request.max_assets} ativos."
                + (
                    # Nunca afirma que a origem é o onboarding do Perfil do
                    # Investidor: a policy pode ter sido criada por lá OU
                    # diretamente via POST/PUT /intelligence/policy, e o
                    # modelo não persiste qual dos dois caminhos foi usado.
                    " Estratégia definida pela política de carteira "
                    "(PortfolioPolicy) persistida do usuário."
                    if strategy.source == POLICY_SOURCE
                    else ""
                )
            ),
            policy_source=strategy.source,
            policy_id=strategy.policy_id,
            existing_portfolio_value=sum((item.value for item in holdings), Decimal("0")) if holdings else Decimal("0"),
            existing_positions_count=len(holdings) if holdings else 0,
            existing_holdings_assessments=holding_assessments,
            holdings_warnings=holdings_warnings,
            diagnosis=diagnosis,
            contribution_plan=cls.contribution_plan(request, strategy, assets, diagnosis.phase),
            projections=projections,
            freedom_goal=FinancialProjectionEngine.freedom_goal(request, projections),
            generated_at=now,
        )

    @classmethod
    def _class_allocations(
        cls,
        request: BuildPortfolioRequest,
        strategy: "PortfolioStrategy",
        class_totals: dict[str, Decimal],
    ) -> list[BuildPortfolioClassAllocation]:
        """Uma linha por classe com alocação efetiva OU meta da política --
        classes com meta na política mas sem nenhum candidato elegível
        aparecem com percentage=0 e gap_percentage=target_percentage
        (nunca omitidas silenciosamente: seção 24, transparência do gap)."""
        all_classes = set(class_totals) | set(strategy.class_targets)
        result = []
        for asset_class in sorted(all_classes):
            percentage = class_totals.get(asset_class, Decimal("0"))
            target = strategy.class_targets.get(asset_class)
            gap_percentage = None
            gap_reason = None
            if target is not None:
                gap_percentage = max(Decimal("0"), target.target_percentage - percentage)
                if gap_percentage > 0:
                    gap_reason = (
                        "Nenhum candidato elegível suficiente para atingir a meta "
                        "da política nesta classe."
                        if asset_class not in class_totals
                        else "Meta da política não totalmente atingida pelos candidatos "
                        "elegíveis disponíveis."
                    )
            result.append(
                BuildPortfolioClassAllocation(
                    asset_class=asset_class,
                    percentage=percentage.quantize(CENT),
                    amount=(request.available_amount * percentage / HUNDRED).quantize(CENT),
                    explanation=(
                        "Soma das alocações elegíveis da classe, dentro da meta definida "
                        "pela política de carteira (PortfolioPolicy) persistida do usuário."
                        if target is not None
                        else "Soma das alocações elegíveis da classe, limitada pelas "
                        "restrições informadas."
                    ),
                    target_percentage=target.target_percentage if target else None,
                    minimum_percentage=target.minimum_percentage if target else None,
                    maximum_percentage=target.maximum_percentage if target else None,
                    gap_percentage=gap_percentage,
                    gap_reason=gap_reason,
                )
            )
        return result

    @classmethod
    def eligibility(cls, strategy, candidates):
        """Elegibilidade estrutural (P2): usa o confidence já resolvido pelo P1
        (required completo + scoring real suficiente + sem anomalia crítica) em
        vez de reimplementar esses gates aqui. NÃO usa mais coverage_percentage
        legado, data_quality.recommendation_blocked ou overall_score is None
        como gates diretos — LOW/provider_coverage baixo/RECOMMENDED ou
        OPTIONAL ausentes nunca bloqueiam sozinhos.
        """
        eligible = []
        exclusions = []
        allowed = strategy.allowed_classes
        prohibited = strategy.prohibited_classes
        conservative = strategy.risk_profile.strip().lower() == "conservador"
        # Em modo de política, o envelope efetivo é sempre imposto --
        # inclusive quando a interseção política x request resultar
        # vazia (nenhuma classe efetivamente permitida), o que precisa
        # excluir TUDO, nunca ser tratado como "sem restrição" (bug real
        # encontrado nos testes: um frozenset() vazio é falsy em Python,
        # então `if allowed` sozinho tornaria essa borda equivalente a
        # "nenhuma restrição", quando na verdade a política + request
        # não deixaram nenhuma classe elegível). Em modo legado, mantém
        # exatamente o comportamento anterior: allowed_classes vazio
        # sempre significou "sem restrição".
        policy_mode = strategy.source == POLICY_SOURCE
        for candidate in sorted(candidates, key=lambda item: item.snapshot.symbol):
            snapshot = candidate.snapshot
            asset_class = cls.class_label(snapshot.asset_class)
            reasons = []
            if policy_mode:
                if asset_class not in allowed:
                    reasons.append(
                        "Classe fora do envelope da política de carteira "
                        "(PortfolioPolicy) persistida do usuário."
                    )
            elif allowed and asset_class not in allowed:
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
    def score(cls, strategy, candidates):
        ranked = []
        for candidate in candidates:
            snapshot = candidate.snapshot
            score = cls._effective_score(snapshot)
            if score is None:
                # Invariante estrutural (P4): eligibility() já excluiu todo
                # candidato com confidence == INSUFFICIENT, o que cobre
                # "nenhum score component real". Se mesmo assim chegar aqui
                # sem nenhum component, o candidato é excluído do ranking em
                # vez de receber um score inventado — nunca 0.
                continue
            if snapshot.strategy_fit_score is not None:
                score = score * Decimal("0.8") + snapshot.strategy_fit_score * Decimal(
                    "0.2"
                )
            if strategy.needs_income and snapshot.income_score is not None:
                score = score * Decimal("0.8") + snapshot.income_score * Decimal("0.2")
            if strategy.needs_liquidity and snapshot.liquidity_score is not None:
                score = score * Decimal("0.8") + snapshot.liquidity_score * Decimal(
                    "0.2"
                )
            ranked.append((candidate, score.quantize(CENT)))
        return sorted(ranked, key=lambda item: (-item[1], item[0].snapshot.symbol))

    @staticmethod
    def _effective_score(snapshot) -> Decimal | None:
        """Nunca fabrica score. Usa overall_score real quando existir; senão
        deriva a média SOMENTE dos score components realmente calculados
        (nunca preenche um component ausente com zero).

        Um candidato sem overall_score e sem nenhum component real não
        deveria chegar aqui — teria confidence == INSUFFICIENT e sido
        excluído em eligibility(). Se isso ocorrer mesmo assim (P4: violação
        de invariante, não caso real esperado), retorna None em vez de um
        score fabricado; o chamador (score()) exclui o candidato do ranking.
        """
        if snapshot.overall_score is not None:
            return snapshot.overall_score
        components = [
            value
            for value in (getattr(snapshot, field) for field in SCORE_COMPONENT_FIELDS)
            if value is not None
        ]
        if not components:
            return None
        return (sum(components, Decimal("0")) / Decimal(len(components))).quantize(CENT)

    @classmethod
    def allocate(cls, request, ranked, strategy=None):
        if not ranked:
            return {}
        class_members: dict[str, list[PortfolioCandidate]] = defaultdict(list)
        for candidate, _ in ranked:
            class_members[cls.class_label(candidate.snapshot.asset_class)].append(
                candidate
            )
        if strategy is not None and strategy.class_targets:
            return cls._allocate_with_policy_targets(class_members, strategy)
        return cls._allocate_equal_class_legacy(request, class_members)

    @staticmethod
    def _allocate_equal_class_legacy(request, class_members):
        """Comportamento ANTERIOR a esta mudança, preservado byte a byte:
        meta igualitária entre as classes que aparecem entre os elegíveis
        -- usado sempre que não há PortfolioPolicy (modo legado)."""
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

    @staticmethod
    def _allocate_with_policy_targets(class_members, strategy):
        """Cada classe habilitada da política tenta atingir seu próprio
        target_percentage (nunca excede maximum_percentage, pois
        target <= maximum por construção em InvestorProfileEngine) --
        nunca a meta igualitária legada. Dentro da classe, distribui pelo
        ranking real já calculado, respeitando limite por ativo, por
        setor e por emissor (maximum_weight_per_issuer, seção 13 --
        emissor ausente usa identidade isolada por símbolo, nunca
        agrupado com outros emissores ausentes). Classe sem nenhum
        candidato elegível fica com gap explícito (ver _class_allocations)
        -- nunca transfere a meta não preenchida para outra classe."""
        allocations: dict[str, Decimal] = {}
        sector_totals: dict[str, Decimal] = defaultdict(Decimal)
        issuer_totals: dict[str, Decimal] = defaultdict(Decimal)
        for asset_class in sorted(strategy.class_targets):
            members = class_members.get(asset_class)
            if not members:
                continue
            target = strategy.class_targets[asset_class]
            remaining_class = target.target_percentage
            for index, candidate in enumerate(members):
                if remaining_class <= 0:
                    break
                slots = Decimal(len(members) - index)
                share = min(strategy.max_percentage_per_asset, remaining_class / slots)
                sector = candidate.sector or f"sem-setor:{candidate.snapshot.symbol}"
                sector_room = strategy.max_percentage_per_sector - sector_totals[sector]
                share = min(share, max(Decimal("0"), sector_room))
                if strategy.max_percentage_per_issuer is not None:
                    issuer_key = candidate.issuer or f"sem-emissor:{candidate.snapshot.symbol}"
                    issuer_room = strategy.max_percentage_per_issuer - issuer_totals[issuer_key]
                    share = min(share, max(Decimal("0"), issuer_room))
                else:
                    issuer_key = None
                share = max(Decimal("0"), share).quantize(CENT, rounding=ROUND_DOWN)
                if share > 0:
                    allocations[candidate.snapshot.symbol] = share
                    remaining_class -= share
                    sector_totals[sector] += share
                    if issuer_key is not None:
                        issuer_totals[issuer_key] += share
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
                unit=item.unit,
                status=item.status.value,
                unavailable_reason=item.unavailable_reason,
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
        quantity = None
        quantity_step = None
        market_segment = None
        identity = resolve_symbol_identity(
            snapshot.symbol,
            market=candidate.market_context,
        )
        economic_identity = identity.canonical_symbol
        trading_symbol = identity.trading_symbol
        if phase == "protection":
            impediments.append(
                "Execução suspensa enquanto reserva ou dívidas prioritárias exigem proteção."
            )
        elif price and price > 0:
            quantity_step = (
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
            calculated_quantity = (target_amount / price / quantity_step).to_integral_value(
                rounding=ROUND_DOWN
            ) * quantity_step
            if calculated_quantity > 0:
                quantity = calculated_quantity
                if (
                    candidate.market_context == B3_MARKET
                    and snapshot.asset_class == InvestmentClass.STOCK
                ):
                    standard_lot = Decimal("100")
                    remainder = quantity % standard_lot
                    if quantity < standard_lot:
                        market_segment = "fractional"
                        trading_symbol = (
                            identity.trading_symbol
                            if identity.is_fractional
                            else f"{identity.canonical_symbol}F"
                        )
                    elif remainder:
                        market_segment = "mixed"
                        # Não há um único ticker operacional para lote e sobra.
                        trading_symbol = None
                    else:
                        market_segment = "standard_lot"
                        trading_symbol = identity.canonical_symbol
            else:
                impediments.append(
                    "Valor destinado menor que uma unidade negociável pelo preço de referência."
                )
        else:
            impediments.append(
                "Preço de referência indisponível para calcular quantidade."
            )
        executable_amount = (
            (quantity * price).quantize(CENT)
            if quantity is not None and price is not None
            else Decimal("0")
        )
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
            trading_symbol=trading_symbol,
            economic_identity=economic_identity,
            market_segment=market_segment,
            quantity_step=quantity_step,
        )

    @staticmethod
    def contribution_plan(request, strategy, assets, phase):
        # monthly_contribution é estratégico (vem da política quando
        # existir, ver PortfolioStrategy); reinvest_income é puramente
        # operacional (não existe em PortfolioPolicy) e continua vindo do
        # request.
        monthly_contribution = strategy.monthly_contribution
        if monthly_contribution <= 0:
            return []
        if phase == "protection":
            return [
                ContributionPriority(
                    priority=1,
                    symbol="RESERVA",
                    asset_class="Proteção financeira",
                    suggested_amount=monthly_contribution.quantize(CENT),
                    reason="Priorizar reserva de emergência e dívidas de alto custo antes de elevar o risco.",
                )
            ]
        remaining = monthly_contribution
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

        # Aditivo (P4): agrega o resolution_summary (P4) de cada snapshot —
        # puro diagnóstico de fontes/fallback, nunca usado como gate aqui.
        provider_failure_reason_counts: dict[str, int] = defaultdict(int)
        fallback_success_count = 0
        unresolved_after_fallback_count = 0
        stale_assets_count = 0
        for snapshot in snapshots:
            summary = snapshot.resolution_summary
            if summary is None:
                continue
            for reason, count in summary.failure_reason_counts.items():
                provider_failure_reason_counts[reason] += count
            fallback_success_count += summary.fallback_success_count
            unresolved_after_fallback_count += summary.unresolved_count
            if summary.stale_count > 0:
                stale_assets_count += 1

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
            provider_failure_reason_counts=dict(provider_failure_reason_counts),
            fallback_success_count=fallback_success_count,
            unresolved_after_fallback_count=unresolved_after_fallback_count,
            stale_assets_count=stale_assets_count,
        )
