from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from app.schemas.intelligence import (
    BuildPortfolioAsset,
    BuildPortfolioClassAllocation,
    BuildPortfolioExclusion,
    BuildPortfolioIndicator,
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


MINIMUM_COVERAGE = Decimal("40")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")

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
        return BuildPortfolioResponse(
            class_allocations=class_allocations,
            selections=selections,
            assets=assets,
            exclusions=sorted(exclusions, key=lambda item: item.symbol),
            total_allocated_percentage=allocated_percentage,
            total_allocated_amount=allocated_amount,
            unallocated_amount=unallocated,
            confidence=confidence,
            status=status,
            missing_data=missing,
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
                reasons.append("Cotação atual indisponível.")
            if snapshot.coverage_percentage < MINIMUM_COVERAGE:
                reasons.append(
                    f"Cobertura de {snapshot.coverage_percentage}% abaixo do mínimo de {MINIMUM_COVERAGE}%."
                )
            if snapshot.data_quality and snapshot.data_quality.recommendation_blocked:
                reasons.append(
                    snapshot.data_quality.blocking_reason
                    or "Qualidade dos dados bloqueia recomendação."
                )
            if snapshot.overall_score is None:
                reasons.append("Pontuação indisponível por cobertura insuficiente.")
            if reasons:
                exclusions.append(
                    BuildPortfolioExclusion(
                        symbol=snapshot.symbol, asset_class=asset_class, reasons=reasons
                    )
                )
            else:
                eligible.append(candidate)
        return eligible, exclusions

    @classmethod
    def score(cls, request, candidates):
        ranked = []
        for candidate in candidates:
            snapshot = candidate.snapshot
            score = snapshot.overall_score or Decimal("0")
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
        reasons.append(f"Cobertura mínima atendida ({snapshot.coverage_percentage}%).")
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
