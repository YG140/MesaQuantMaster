from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.intelligence import (
    AllocationSuggestion,
    BuildPortfolioClassAllocation,
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    BuildPortfolioSelection,
    ClassAllocationDiagnosis,
    IndicatorStatus,
    Opportunity,
    PortfolioDiagnosis,
    PortfolioIntelligenceResponse,
    PortfolioOverview,
    PortfolioPolicyRead,
    Recommendation,
)
from app.schemas.portfolio import PortfolioPosition, PortfolioSummary


UNIDENTIFIED_CLASS = "Classe não identificada"

INDICATORS_BY_CLASS = {
    "Ações": ["P/L", "P/VP", "ROE", "Dividend yield", "Liquidez", "Volatilidade"],
    "FIIs": ["P/VP", "Dividend yield", "Vacância", "Liquidez", "Endividamento"],
    "ETFs": [
        "Índice acompanhado",
        "Taxa de administração",
        "Liquidez",
        "Diversificação",
    ],
    "Tesouro Direto": ["Tipo do título", "Indexador", "Vencimento", "Liquidez"],
    "Renda fixa bancária": ["Emissor", "Indexador", "Liquidez", "Cobertura do FGC"],
    "Criptomoedas": ["Capitalização", "Liquidez", "Volatilidade", "Risco"],
}

ASSET_TYPE_TO_CLASS = {
    "ACAO": "Ações",
    "AÇÃO": "Ações",
    "ACOES": "Ações",
    "AÇÕES": "Ações",
    "STOCK": "Ações",
    "EQUITY": "Ações",
    "FII": "FIIs",
    "REAL_ESTATE_FUND": "FIIs",
    "ETF": "ETFs",
    "BDR": "BDRs",
    "CRYPTO": "Criptomoedas",
    "CRIPTO": "Criptomoedas",
    "CASH": "Caixa",
    "CAIXA": "Caixa",
    "TREASURY": "Tesouro Direto",
    "TESOURO_DIRETO": "Tesouro Direto",
    "CDB": "Renda fixa bancária",
    "LCI": "Renda fixa bancária",
    "LCA": "Renda fixa bancária",
    "BANK_FIXED_INCOME": "Renda fixa bancária",
    "DEBENTURE": "Crédito privado",
    "DEBÊNTURE": "Crédito privado",
    "PRIVATE_CREDIT": "Crédito privado",
    "FUND": "Fundos de investimento",
    "FUNDO": "Fundos de investimento",
    "INTERNATIONAL": "Ativos internacionais",
    "OUTROS": "Outros",
    "OTHER": "Outros",
}


class PortfolioIntelligenceEngine:
    @classmethod
    def build(
        cls,
        portfolio: PortfolioSummary,
        policy: PortfolioPolicyRead | None = None,
    ) -> PortfolioIntelligenceResponse:
        now = datetime.now(timezone.utc)
        overview = cls.overview(portfolio, policy, now)
        diagnosis = cls.diagnosis(portfolio, policy, now)
        recommendations = RecommendationEngine.recommend(
            portfolio, policy, diagnosis, now
        )
        rebalancing = AllocationEngine.rebalance(portfolio, policy)
        opportunities = OpportunityScanner.scan(now)
        return PortfolioIntelligenceResponse(
            overview=overview,
            diagnosis=diagnosis,
            recommendations=recommendations,
            rebalancing=rebalancing,
            opportunities=opportunities,
            policy=policy,
            available_indicators={
                key: values[:2] for key, values in INDICATORS_BY_CLASS.items()
            },
            unavailable_indicators={
                key: values[2:] for key, values in INDICATORS_BY_CLASS.items()
            },
            generated_at=now,
        )

    @staticmethod
    def overview(
        portfolio: PortfolioSummary,
        policy: PortfolioPolicyRead | None,
        now: datetime,
    ) -> PortfolioOverview:
        positions = portfolio.positions
        has_positions = bool(positions)
        has_market_data = portfolio.market_data_status in {"live", "partial"}
        class_distribution = AllocationEngine.current_distribution(portfolio)
        fixed_income = sum(
            (
                item["percentage"]
                for item in class_distribution
                if item["asset_class"]
                in {
                    "Caixa",
                    "Reserva de emergência",
                    "Tesouro Direto",
                    "Renda fixa bancária",
                    "Crédito privado",
                }
            ),
            Decimal("0"),
        )
        variable_income = sum(
            (
                item["percentage"]
                for item in class_distribution
                if item["asset_class"]
                in {
                    "Ações",
                    "FIIs",
                    "ETFs",
                    "BDRs",
                    "Ativos internacionais",
                    "Criptomoedas",
                }
            ),
            Decimal("0"),
        )

        return PortfolioOverview(
            current_equity=(
                portfolio.total_market_value
                if has_market_data and portfolio.total_market_value > 0
                else None
            ),
            total_invested=portfolio.total_invested if has_positions else None,
            profit_loss=portfolio.total_profit if has_market_data else None,
            profitability=portfolio.profitability if has_market_data else None,
            received_income=None,
            investments_count=len(positions),
            fixed_income_percentage=fixed_income if has_positions else None,
            variable_income_percentage=variable_income if has_positions else None,
            portfolio_classification=(
                "Estratégia não configurada"
                if policy is None
                else (
                    "Carteira em formação"
                    if len(positions) < 5
                    else "Carteira diversificada"
                )
            ),
            risk_level=PortfolioIntelligenceEngine._risk_level(positions),
            data_quality=PortfolioIntelligenceEngine._data_quality(portfolio, policy),
            last_updated_at=portfolio.quote_updated_at or now,
            market_data_status=portfolio.market_data_status,
        )

    @staticmethod
    def diagnosis(
        portfolio: PortfolioSummary,
        policy: PortfolioPolicyRead | None,
        now: datetime,
    ) -> PortfolioDiagnosis:
        positions = portfolio.positions
        unclassified = [
            position.ticker
            for position in positions
            if classify_position(position) == UNIDENTIFIED_CLASS
        ]
        warnings = []
        if policy is None:
            warnings.append(
                "Configure sua estratégia para receber análises e sugestões personalizadas."
            )
        if unclassified:
            warnings.append("Existem investimentos sem classe identificada.")
        if portfolio.unpriced_symbols:
            warnings.append("Existem ativos sem cotação atual.")

        class_allocations = AllocationEngine.class_diagnosis(portfolio, policy)

        if not positions:
            return PortfolioDiagnosis(
                risk_level="Dados insuficientes",
                data_quality=PortfolioIntelligenceEngine._data_quality(
                    portfolio, policy
                ),
                warnings=warnings or ["Cadastre investimentos para liberar a análise."],
                weaknesses=warnings,
                class_allocations=class_allocations,
                unclassified_assets=unclassified,
                calculated_at=now,
            )

        largest_weight = max(
            (position.allocation or position.weight or Decimal("0"))
            for position in positions
        )
        concentration_score = max(Decimal("0"), Decimal("100") - largest_weight)
        diversification_score = min(
            Decimal("100"),
            Decimal(
                len(
                    {
                        item.asset_class
                        for item in class_allocations
                        if item.current_value and item.current_value > 0
                    }
                )
                * 20
            ),
        )
        data_quality_score = (
            Decimal("100")
            if not warnings and portfolio.market_data_status == "live"
            else (
                Decimal("60")
                if portfolio.market_data_status in {"live", "partial"}
                else Decimal("35")
            )
        )
        portfolio_score = (
            concentration_score + diversification_score + data_quality_score
        ) / Decimal("3")

        if largest_weight >= Decimal("50"):
            warnings.append("Há concentração relevante em uma única posição.")

        return PortfolioDiagnosis(
            portfolio_score=portfolio_score.quantize(Decimal("0.01")),
            risk_level=PortfolioIntelligenceEngine._risk_level(positions),
            diversification_score=diversification_score.quantize(Decimal("0.01")),
            concentration_score=concentration_score.quantize(Decimal("0.01")),
            liquidity_score=None,
            income_score=None,
            data_quality=PortfolioIntelligenceEngine._data_quality(portfolio, policy),
            warnings=warnings,
            strengths=["Carteira possui posições consolidadas."] if positions else [],
            weaknesses=warnings or ["Dados de renda e risco ainda incompletos."],
            class_allocations=class_allocations,
            unclassified_assets=unclassified,
            calculated_at=now,
        )

    @staticmethod
    def _risk_level(positions: list[PortfolioPosition]) -> str:
        if not positions:
            return "Dados insuficientes"
        largest_weight = max(
            (position.allocation or position.weight or Decimal("0"))
            for position in positions
        )
        if largest_weight >= Decimal("50"):
            return "Alto"
        if largest_weight >= Decimal("30"):
            return "Moderado"
        return "Baixo"

    @staticmethod
    def _data_quality(
        portfolio: PortfolioSummary,
        policy: PortfolioPolicyRead | None,
    ) -> str:
        issues = []
        if policy is None:
            issues.append("política ainda não configurada")
        if any(
            classify_position(position) == UNIDENTIFIED_CLASS
            for position in portfolio.positions
        ):
            issues.append("ativos sem classe")
        if portfolio.unpriced_symbols:
            issues.append("posições sem cotação")
        if any(position.average_price is None for position in portfolio.positions):
            issues.append("posições sem preço médio")
        if policy is not None:
            enabled_total = sum(
                (
                    allocation.target_percentage
                    for allocation in policy.allocations
                    if allocation.enabled
                ),
                Decimal("0"),
            )
            if enabled_total != Decimal("100"):
                issues.append("soma das metas inválida")

        if not portfolio.positions and policy is None:
            return "Sem dados suficientes"
        if issues:
            return "Pendente: " + ", ".join(issues)
        if portfolio.market_data_status == "live":
            return "Boa"
        if portfolio.market_data_status == "partial":
            return "Parcial"
        return "Limitada"


class RecommendationEngine:
    @staticmethod
    def recommend(
        portfolio: PortfolioSummary,
        policy: PortfolioPolicyRead | None,
        diagnosis: PortfolioDiagnosis,
        now: datetime,
    ) -> list[Recommendation]:
        recommendations = []
        if policy is None:
            return recommendations

        for item in diagnosis.class_allocations:
            if item.asset_class == UNIDENTIFIED_CLASS:
                action = "Revisar classificação"
            elif item.status == "Acima da estratégia":
                action = "Reduzir exposição"
            elif item.status == "Abaixo da estratégia":
                action = "Aumentar exposição"
            elif item.status == "Dentro da tolerância":
                action = "Dentro da estratégia"
            else:
                action = "Aguardar novo aporte"

            recommendations.append(
                Recommendation(
                    symbol=item.asset_class,
                    name=item.asset_class,
                    asset_class=item.asset_class,
                    recommendation=action,
                    valuation_status="Dados insuficientes",
                    confidence="Média" if policy is not None else "Baixa",
                    current_weight=item.current_percentage,
                    target_weight=item.target_percentage,
                    current_value=item.current_value,
                    positive_reasons=[
                        "Comparação feita contra a política de investimentos salva."
                    ],
                    risk_reasons=(
                        [f"Classe {item.status.lower()}."]
                        if item.status not in {"Dentro da tolerância", "Sem posição"}
                        else []
                    ),
                    missing_data=(
                        ["Classe do investimento"]
                        if item.asset_class == UNIDENTIFIED_CLASS
                        else []
                    ),
                    indicators=[
                        IndicatorStatus(
                            name="Política de investimentos",
                            status="disponível",
                            explanation="Meta configurada pelo usuário para esta classe.",
                        )
                    ],
                    generated_at=now,
                )
            )
        return recommendations


class AllocationEngine:
    @staticmethod
    def rebalance(
        portfolio: PortfolioSummary,
        policy: PortfolioPolicyRead | None,
    ) -> list[AllocationSuggestion]:
        if policy is None or not portfolio.positions:
            return []

        current = {
            item["asset_class"]: item
            for item in AllocationEngine.current_distribution(portfolio)
        }
        total_value = sum((item["value"] for item in current.values()), Decimal("0"))
        if total_value <= 0:
            return []

        suggestions = []
        enabled = [item for item in policy.allocations if item.enabled]
        missing_by_class = {}
        for allocation in enabled:
            current_value = current.get(allocation.asset_class, {}).get(
                "value", Decimal("0")
            )
            current_percentage = current.get(allocation.asset_class, {}).get(
                "percentage", Decimal("0")
            )
            target_value = (
                total_value * allocation.target_percentage / Decimal("100")
            ).quantize(Decimal("0.01"))
            difference_value = (target_value - current_value).quantize(Decimal("0.01"))
            missing_value = max(Decimal("0"), difference_value)
            excess_value = max(Decimal("0"), -difference_value)
            difference_percentage = (
                allocation.target_percentage - current_percentage
            ).quantize(Decimal("0.01"))
            status = AllocationEngine.status_for_difference(
                difference_percentage, policy.rebalance_tolerance
            )
            if missing_value > 0 and status == "Abaixo da estratégia":
                missing_by_class[allocation.asset_class] = missing_value

            suggestions.append(
                AllocationSuggestion(
                    asset_class=allocation.asset_class,
                    current_percentage=current_percentage,
                    target_percentage=allocation.target_percentage,
                    difference_percentage=difference_percentage,
                    current_value=current_value.quantize(Decimal("0.01")),
                    target_value=target_value,
                    suggested_contribution=Decimal("0"),
                    missing_value=missing_value,
                    excess_value=excess_value,
                    status=status,
                    explanation=AllocationEngine.explanation_for_status(status),
                )
            )

        next_contributions = AllocationEngine.next_contribution(
            policy.monthly_contribution,
            missing_by_class,
        )
        return [
            item.model_copy(
                update={
                    "suggested_contribution": next_contributions.get(
                        item.asset_class,
                        Decimal("0"),
                    )
                }
            )
            for item in suggestions
        ]

    @staticmethod
    def class_diagnosis(
        portfolio: PortfolioSummary,
        policy: PortfolioPolicyRead | None,
    ) -> list[ClassAllocationDiagnosis]:
        current = {
            item["asset_class"]: item
            for item in AllocationEngine.current_distribution(portfolio)
        }
        items = []
        if policy is None:
            for asset_class, current_item in current.items():
                items.append(
                    ClassAllocationDiagnosis(
                        asset_class=asset_class,
                        current_value=current_item["value"].quantize(Decimal("0.01")),
                        current_percentage=current_item["percentage"],
                        status="Estratégia não configurada",
                    )
                )
            return items

        for allocation in policy.allocations:
            if not allocation.enabled:
                continue
            current_item = current.get(allocation.asset_class)
            current_value = current_item["value"] if current_item else Decimal("0")
            current_percentage = (
                current_item["percentage"] if current_item else Decimal("0")
            )
            difference = (allocation.target_percentage - current_percentage).quantize(
                Decimal("0.01")
            )
            items.append(
                ClassAllocationDiagnosis(
                    asset_class=allocation.asset_class,
                    current_value=current_value.quantize(Decimal("0.01")),
                    current_percentage=current_percentage,
                    target_percentage=allocation.target_percentage,
                    minimum_percentage=allocation.minimum_percentage,
                    maximum_percentage=allocation.maximum_percentage,
                    difference_percentage=difference,
                    status=AllocationEngine.status_for_policy(
                        current_percentage,
                        allocation.minimum_percentage,
                        allocation.maximum_percentage,
                        difference,
                        policy.rebalance_tolerance,
                    ),
                )
            )

        for asset_class, current_item in current.items():
            if asset_class not in {item.asset_class for item in items}:
                items.append(
                    ClassAllocationDiagnosis(
                        asset_class=asset_class,
                        current_value=current_item["value"].quantize(Decimal("0.01")),
                        current_percentage=current_item["percentage"],
                        status=(
                            "Revisar classificação"
                            if asset_class == UNIDENTIFIED_CLASS
                            else "Classe sem meta"
                        ),
                    )
                )
        return items

    @staticmethod
    def current_distribution(portfolio: PortfolioSummary) -> list[dict]:
        totals = defaultdict(Decimal)
        for position in portfolio.positions:
            asset_class = classify_position(position)
            value = (
                position.market_value
                if position.market_value is not None
                else position.invested_amount
            )
            if value is None:
                continue
            totals[asset_class] += value
        total_value = sum(totals.values(), Decimal("0"))
        if total_value <= 0:
            return []
        return [
            {
                "asset_class": asset_class,
                "value": value,
                "percentage": (value / total_value * Decimal("100")).quantize(
                    Decimal("0.01")
                ),
            }
            for asset_class, value in sorted(totals.items())
        ]

    @staticmethod
    def next_contribution(
        available_amount: Decimal,
        missing_by_class: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        if available_amount <= 0 or not missing_by_class:
            return {}
        total_missing = sum(missing_by_class.values(), Decimal("0"))
        if total_missing <= 0:
            return {}
        remaining = available_amount.quantize(Decimal("0.01"))
        classes = list(missing_by_class)
        result = {}
        for index, asset_class in enumerate(classes):
            if index == len(classes) - 1:
                amount = remaining
            else:
                amount = (
                    available_amount * missing_by_class[asset_class] / total_missing
                ).quantize(Decimal("0.01"))
                remaining -= amount
            result[asset_class] = max(Decimal("0"), amount)
        return result

    @staticmethod
    def status_for_policy(
        current: Decimal,
        minimum: Decimal,
        maximum: Decimal,
        difference: Decimal,
        tolerance: Decimal,
    ) -> str:
        if current < minimum:
            return "Abaixo da estratégia"
        if current > maximum:
            return "Acima da estratégia"
        return AllocationEngine.status_for_difference(difference, tolerance)

    @staticmethod
    def status_for_difference(difference: Decimal, tolerance: Decimal) -> str:
        if abs(difference) <= tolerance:
            return "Dentro da tolerância"
        if difference > 0:
            return "Abaixo da estratégia"
        return "Acima da estratégia"

    @staticmethod
    def explanation_for_status(status: str) -> str:
        if status == "Abaixo da estratégia":
            return "Classe abaixo da política; priorize novos aportes."
        if status == "Acima da estratégia":
            return "Classe acima da política; evite novos aportes por enquanto."
        return "Classe dentro da tolerância definida."


class ValuationEngine:
    @staticmethod
    def status_for_position(position: PortfolioPosition) -> str:
        return "Dados insuficientes"


class OpportunityScanner:
    @staticmethod
    def scan(now: datetime) -> list[Opportunity]:
        return [
            Opportunity(
                asset_class=asset_class,
                classification="Dados insuficientes",
                indicators=[
                    IndicatorStatus(
                        name=indicator,
                        status="indisponível",
                        explanation="Indicador ainda não integrado a uma fonte confiável.",
                    )
                    for indicator in indicators[:3]
                ],
                highlight_reason="Não há dados suficientes para destacar oportunidades com segurança.",
                risks=["Aguarde integração de indicadores específicos da classe."],
                confidence="Baixa",
                updated_at=now,
            )
            for asset_class, indicators in INDICATORS_BY_CLASS.items()
        ]


class PortfolioBuilderEngine:
    @staticmethod
    def build(
        request: BuildPortfolioRequest,
        policy: PortfolioPolicyRead | None = None,
    ) -> BuildPortfolioResponse:
        now = datetime.now(timezone.utc)
        if policy is None:
            return BuildPortfolioResponse(
                class_allocations=[],
                selections=[],
                generated_at=now,
            )

        allocations = [
            BuildPortfolioClassAllocation(
                asset_class=allocation.asset_class,
                percentage=allocation.target_percentage,
                amount=(
                    request.available_amount
                    * allocation.target_percentage
                    / Decimal("100")
                ).quantize(Decimal("0.01")),
                explanation="Distribuição baseada na sua política de investimentos salva.",
            )
            for allocation in policy.allocations
            if allocation.enabled
        ]
        selections = [
            BuildPortfolioSelection(
                asset_class=allocation.asset_class,
                message="A seleção dos investimentos de cada classe será feita quando houver dados suficientes e critérios específicos integrados.",
                data_status="indisponível",
            )
            for allocation in policy.allocations
            if allocation.enabled
        ]
        return BuildPortfolioResponse(
            class_allocations=allocations,
            selections=selections,
            generated_at=now,
        )


def classify_position(position: PortfolioPosition) -> str:
    raw_type = (position.asset_type or "").strip().upper()
    if not raw_type:
        return UNIDENTIFIED_CLASS
    return ASSET_TYPE_TO_CLASS.get(raw_type, UNIDENTIFIED_CLASS)
