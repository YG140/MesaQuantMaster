"""Motor determinístico do Perfil do Investidor.

Responsável por normalizar respostas do questionário, calcular dimensões
independentes (0..100), determinar a classificação geral e derivar o
envelope estratégico de uma PortfolioPolicy — tudo de forma explicável e
testável, sem score mágico e sem regra central do tipo "moderado = 50/50".

Este engine NUNCA seleciona ativos. Ele produz apenas: dimensões,
classificação e uma política operacional (envelope por classe), que
continua sendo o único insumo do SmartPortfolio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.schemas.intelligence import INVESTMENT_CLASSES
from app.schemas.investor_profile import InvestorProfileAnswers

# ---------------------------------------------------------------------------
# Constantes canônicas — nenhum número mágico espalhado pelo código.
# ---------------------------------------------------------------------------

HORIZON_BUCKETS = (
    "menos_1_ano",
    "1_a_3_anos",
    "3_a_5_anos",
    "5_a_10_anos",
    "mais_10_anos",
)
HORIZON_POINTS = {
    "menos_1_ano": 0,
    "1_a_3_anos": 20,
    "3_a_5_anos": 45,
    "5_a_10_anos": 70,
    "mais_10_anos": 90,
}

LIQUIDITY_NEED_POINTS = {"baixa": 20, "moderada": 55, "alta": 90}
INCOME_NEED_POINTS = {
    "nenhuma": 10,
    "complemento": 40,
    "renda_passiva": 70,
    "dependencia": 95,
}
# income_need textual -> booleano legado consumido por PortfolioPolicyUpsert.
INCOME_NEED_TO_LEGACY_BOOLEAN = {
    "nenhuma": False,
    "complemento": True,
    "renda_passiva": True,
    "dependencia": True,
}

# Cenários de tolerância psicológica: cada opção mapeia para um score 0..100.
RISK_SCENARIO_CHOICE_SCORES = {
    "venderia_tudo": 0,
    "venderia_parte": 33,
    "manteria": 66,
    "compraria_mais": 100,
}
REQUIRED_RISK_SCENARIOS = ("queda_20_curto_prazo", "queda_30_prolongada", "volatilidade_mensal")

# Quiz de conhecimento: 5 perguntas objetivas, resposta correta fixa no backend.
# Nunca exposto como "gabarito" ao cliente — apenas o resultado (score) volta.
KNOWLEDGE_QUESTIONS = {
    "volatilidade": "b",
    "diversificacao": "a",
    "risco_perda": "c",
    "renda_fixa_x_variavel": "a",
    "marcacao_a_mercado": "b",
}

# Pesos/penalidades da capacidade financeira de risco (independente da
# tolerância psicológica — um investidor pode ter tolerância alta e
# capacidade baixa, ou o inverso).
RESERVE_ADEQUACY_BONUS = 10
RESERVE_INADEQUACY_PENALTY = 20
RESERVE_ADEQUATE_MONTHS = 6
RESERVE_MINIMAL_MONTHS = 3
DEBT_PENALTY = 20
DEPENDENTS_PENALTY_PER = 5
DEPENDENTS_PENALTY_CAP = 20
LIQUIDITY_HIGH_CAPACITY_PENALTY = 15
STABLE_CONTRIBUTION_BONUS = 10

# Classificação geral: min(tolerância, capacidade) — o mais restritivo
# domina, princípio padrão de suitability (capacidade nunca é ultrapassada
# pela tolerância psicológica sozinha).
CLASSIFICATION_THRESHOLDS = (
    (20, "Conservador"),
    (40, "Moderado-conservador"),
    (60, "Moderado"),
    (80, "Moderado-arrojado"),
    (101, "Arrojado"),
)

MINIMUM_SCORING_DIMENSIONS = (
    "risk_tolerance",
    "risk_capacity",
    "liquidity_need",
    "income_need",
    "knowledge",
)

# Envelope base por classificação (soma sempre exatamente 100). Índice pelas
# 13 classes canônicas de app.schemas.intelligence.INVESTMENT_CLASSES;
# classes omitidas do dicionário recebem peso 0.
BASE_ALLOCATION_BY_CLASSIFICATION: dict[str, dict[str, Decimal]] = {
    "Conservador": {
        "Reserva de emergência": Decimal("10"),
        "Tesouro Direto": Decimal("45"),
        "Renda fixa bancária": Decimal("35"),
        "Crédito privado": Decimal("5"),
        "Ações": Decimal("3"),
        "FIIs": Decimal("2"),
    },
    "Moderado-conservador": {
        "Reserva de emergência": Decimal("8"),
        "Tesouro Direto": Decimal("32"),
        "Renda fixa bancária": Decimal("25"),
        "Crédito privado": Decimal("10"),
        "Ações": Decimal("12"),
        "FIIs": Decimal("10"),
        "ETFs": Decimal("3"),
    },
    "Moderado": {
        "Reserva de emergência": Decimal("5"),
        "Tesouro Direto": Decimal("20"),
        "Renda fixa bancária": Decimal("15"),
        "Crédito privado": Decimal("10"),
        "Ações": Decimal("25"),
        "FIIs": Decimal("15"),
        "ETFs": Decimal("7"),
        "BDRs": Decimal("3"),
    },
    "Moderado-arrojado": {
        "Reserva de emergência": Decimal("5"),
        "Tesouro Direto": Decimal("10"),
        "Renda fixa bancária": Decimal("10"),
        "Crédito privado": Decimal("10"),
        "Ações": Decimal("35"),
        "FIIs": Decimal("15"),
        "ETFs": Decimal("10"),
        "BDRs": Decimal("3"),
        "Criptomoedas": Decimal("2"),
    },
    "Arrojado": {
        "Reserva de emergência": Decimal("3"),
        "Tesouro Direto": Decimal("5"),
        "Renda fixa bancária": Decimal("5"),
        "Crédito privado": Decimal("7"),
        "Ações": Decimal("45"),
        "FIIs": Decimal("15"),
        "ETFs": Decimal("13"),
        "BDRs": Decimal("4"),
        "Criptomoedas": Decimal("3"),
    },
}

# Classes de renda variável elegíveis a ceder peso para a reserva quando a
# adequação da reserva de emergência está baixa.
GROWTH_CLASSES = ("Ações", "FIIs", "ETFs", "BDRs", "Criptomoedas")
RESERVE_SHORTFALL_ADEQUACY_THRESHOLD = 60
RESERVE_SHORTFALL_MAX_SHIFT = Decimal("15")

# Agrupamentos usados pelos ajustes explicáveis de horizon/liquidity_need/
# income_need em derive_policy(): cada ajuste desloca peso de forma limitada
# e determinística entre classes, mesmo dentro da MESMA classificação geral
# (que sozinha nunca é suficiente — ver auditoria de multidimensionalidade).
DEFENSIVE_CLASSES = ("Tesouro Direto", "Renda fixa bancária")
HIGH_LIQUIDITY_CLASSES = ("Tesouro Direto",)
LOWER_LIQUIDITY_CLASSES = ("Renda fixa bancária", "Crédito privado", "FIIs")
INCOME_FOCUSED_CLASSES = ("FIIs",)
GROWTH_WITHOUT_INCOME_CLASSES = ("Ações", "ETFs", "BDRs", "Criptomoedas")

# Horizonte: quanto mais curto, maior o deslocamento de classes voláteis
# para o ativo com liquidez diária garantida (Tesouro Direto); quanto mais
# longo, maior o deslocamento de classes defensivas para classes de
# crescimento — mesmo sem mudar a classificação geral de risco.
HORIZON_ALLOCATION_SHIFT = {
    "menos_1_ano": Decimal("-15"),
    "1_a_3_anos": Decimal("-8"),
    "3_a_5_anos": Decimal("0"),
    "5_a_10_anos": Decimal("5"),
    "mais_10_anos": Decimal("10"),
}

# Necessidade de liquidez: quanto mais alta, maior o deslocamento de classes
# com liquidez restrita (renda fixa bancária, crédito privado, FIIs) para o
# Tesouro Direto (resgate diário garantido pelo Tesouro Nacional).
LIQUIDITY_ALLOCATION_SHIFT = {"baixa": Decimal("0"), "moderada": Decimal("3"), "alta": Decimal("10")}

# Necessidade de renda: quanto mais forte, maior o deslocamento de classes
# de crescimento sem distribuição periódica para FIIs, a classe do envelope
# com foco em geração de renda recorrente.
INCOME_NEED_ALLOCATION_SHIFT = {
    "nenhuma": Decimal("0"),
    "complemento": Decimal("3"),
    "renda_passiva": Decimal("8"),
    "dependencia": Decimal("12"),
}

# Limites de concentração e tolerância de rebalanceamento por classificação —
# perfis mais conservadores recebem limites de concentração mais apertados.
POLICY_LIMITS_BY_CLASSIFICATION: dict[str, dict[str, Decimal]] = {
    "Conservador": {
        "maximum_weight_per_asset": Decimal("10"),
        "maximum_weight_per_sector": Decimal("20"),
        "maximum_weight_per_issuer": Decimal("20"),
        "rebalance_tolerance": Decimal("3"),
    },
    "Moderado-conservador": {
        "maximum_weight_per_asset": Decimal("15"),
        "maximum_weight_per_sector": Decimal("25"),
        "maximum_weight_per_issuer": Decimal("25"),
        "rebalance_tolerance": Decimal("4"),
    },
    "Moderado": {
        "maximum_weight_per_asset": Decimal("20"),
        "maximum_weight_per_sector": Decimal("30"),
        "maximum_weight_per_issuer": Decimal("30"),
        "rebalance_tolerance": Decimal("5"),
    },
    "Moderado-arrojado": {
        "maximum_weight_per_asset": Decimal("25"),
        "maximum_weight_per_sector": Decimal("35"),
        "maximum_weight_per_issuer": Decimal("35"),
        "rebalance_tolerance": Decimal("6"),
    },
    "Arrojado": {
        "maximum_weight_per_asset": Decimal("30"),
        "maximum_weight_per_sector": Decimal("40"),
        "maximum_weight_per_issuer": Decimal("40"),
        "rebalance_tolerance": Decimal("8"),
    },
}

ALWAYS_ELIGIBLE_CLASSES = {"Reserva de emergência"}


@dataclass
class DimensionExplanation:
    dimension: str
    rule: str
    result: int | str
    message: str


@dataclass
class InvestorProfileEvaluation:
    risk_tolerance_score: int
    risk_capacity_score: int
    horizon_score: int
    liquidity_need_score: int
    income_need_score: int
    knowledge_score: int
    emergency_reserve_adequacy_score: int
    overall_classification: str
    explanations: list[DimensionExplanation] = field(default_factory=list)


class InvestorProfileEngine:
    """Normaliza respostas, calcula dimensões e classifica — determinístico."""

    @classmethod
    def missing_required_sections(cls, answers: InvestorProfileAnswers) -> list[str]:
        """Seções indispensáveis para evaluate(). Nunca infere o que falta."""
        missing = []
        if answers.objectives is None or not answers.objectives.primary_objective:
            missing.append("objectives")
        if answers.horizon is None or not answers.horizon.horizon:
            missing.append("horizon")
        if answers.contribution is None or answers.contribution.monthly_contribution is None:
            missing.append("contribution")
        if answers.financial_situation is None:
            missing.append("financial_situation")
        if answers.liquidity is None or not answers.liquidity.liquidity_need:
            missing.append("liquidity")
        if answers.income_need is None or not answers.income_need.income_need:
            missing.append("income_need")
        if answers.knowledge is None or len(answers.knowledge.answers) < len(KNOWLEDGE_QUESTIONS):
            missing.append("knowledge")
        if answers.risk_tolerance is None or any(
            scenario not in answers.risk_tolerance.scenarios for scenario in REQUIRED_RISK_SCENARIOS
        ):
            missing.append("risk_tolerance")
        return missing

    @classmethod
    def evaluate(cls, answers: InvestorProfileAnswers) -> InvestorProfileEvaluation:
        missing = cls.missing_required_sections(answers)
        if missing:
            raise ValueError(f"Seções obrigatórias ausentes: {', '.join(missing)}")

        explanations: list[DimensionExplanation] = []

        horizon_key = answers.horizon.horizon
        horizon_score = HORIZON_POINTS[horizon_key]
        explanations.append(
            DimensionExplanation(
                "horizon",
                f"horizon={horizon_key}",
                horizon_score,
                f"Horizonte declarado '{horizon_key}' equivale a {horizon_score}/100.",
            )
        )

        liquidity_key = answers.liquidity.liquidity_need
        liquidity_score = LIQUIDITY_NEED_POINTS[liquidity_key]
        explanations.append(
            DimensionExplanation(
                "liquidity_need",
                f"liquidity_need={liquidity_key}",
                liquidity_score,
                f"Necessidade de liquidez '{liquidity_key}' equivale a {liquidity_score}/100.",
            )
        )

        income_key = answers.income_need.income_need
        income_score = INCOME_NEED_POINTS[income_key]
        explanations.append(
            DimensionExplanation(
                "income_need",
                f"income_need={income_key}",
                income_score,
                f"Necessidade de renda '{income_key}' equivale a {income_score}/100.",
            )
        )

        knowledge_score = cls._score_knowledge(answers.knowledge.answers)
        explanations.append(
            DimensionExplanation(
                "knowledge",
                "acertos_no_quiz / total_perguntas * 100",
                knowledge_score,
                f"Acertou o equivalente a {knowledge_score}/100 no quiz de conhecimento.",
            )
        )

        reserve_score, reserve_detail = cls._score_reserve_adequacy(
            answers.financial_situation.emergency_reserve_months
        )
        explanations.append(
            DimensionExplanation(
                "emergency_reserve_adequacy", reserve_detail, reserve_score,
                f"Adequação da reserva de emergência: {reserve_score}/100.",
            )
        )

        tolerance_score = cls._score_risk_tolerance(answers.risk_tolerance.scenarios)
        explanations.append(
            DimensionExplanation(
                "risk_tolerance",
                "média dos cenários de queda de carteira",
                tolerance_score,
                f"Tolerância psicológica ao risco: {tolerance_score}/100.",
            )
        )

        capacity_score, capacity_terms = cls._score_risk_capacity(
            horizon_key=horizon_key,
            emergency_reserve_months=answers.financial_situation.emergency_reserve_months,
            has_relevant_debt=answers.financial_situation.has_relevant_debt,
            dependents=answers.financial_situation.dependents,
            liquidity_need=liquidity_key,
            contribution_stability=(
                answers.contribution.contribution_stability if answers.contribution else None
            ),
        )
        explanations.append(
            DimensionExplanation(
                "risk_capacity", "; ".join(capacity_terms), capacity_score,
                f"Capacidade financeira de assumir risco: {capacity_score}/100.",
            )
        )

        classification = cls._classify(tolerance_score, capacity_score)
        explanations.append(
            DimensionExplanation(
                "overall_classification",
                f"min(tolerância={tolerance_score}, capacidade={capacity_score})",
                classification,
                (
                    f"Classificação geral '{classification}': o menor entre tolerância "
                    f"psicológica ({tolerance_score}) e capacidade financeira "
                    f"({capacity_score}) determina o envelope de risco, nunca o maior."
                ),
            )
        )

        return InvestorProfileEvaluation(
            risk_tolerance_score=tolerance_score,
            risk_capacity_score=capacity_score,
            horizon_score=horizon_score,
            liquidity_need_score=liquidity_score,
            income_need_score=income_score,
            knowledge_score=knowledge_score,
            emergency_reserve_adequacy_score=reserve_score,
            overall_classification=classification,
            explanations=explanations,
        )

    @staticmethod
    def _score_knowledge(quiz_answers: dict[str, str]) -> int:
        correct = sum(
            1
            for question, expected in KNOWLEDGE_QUESTIONS.items()
            if quiz_answers.get(question) == expected
        )
        return round(correct / len(KNOWLEDGE_QUESTIONS) * 100)

    @staticmethod
    def _score_risk_tolerance(scenarios: dict[str, str]) -> int:
        values = [
            RISK_SCENARIO_CHOICE_SCORES[scenarios[scenario]]
            for scenario in REQUIRED_RISK_SCENARIOS
        ]
        return round(sum(values) / len(values))

    @staticmethod
    def _score_reserve_adequacy(months: int | None) -> tuple[int, str]:
        if months is None or months <= 0:
            return 0, "emergency_reserve_months ausente ou zero"
        if months < RESERVE_MINIMAL_MONTHS:
            return 20, f"emergency_reserve_months={months} < {RESERVE_MINIMAL_MONTHS}"
        if months < RESERVE_ADEQUATE_MONTHS:
            return 60, f"{RESERVE_MINIMAL_MONTHS} <= emergency_reserve_months={months} < {RESERVE_ADEQUATE_MONTHS}"
        return 100, f"emergency_reserve_months={months} >= {RESERVE_ADEQUATE_MONTHS}"

    @staticmethod
    def _score_risk_capacity(
        *,
        horizon_key: str,
        emergency_reserve_months: int | None,
        has_relevant_debt: bool | None,
        dependents: int | None,
        liquidity_need: str,
        contribution_stability: str | None,
    ) -> tuple[int, list[str]]:
        terms = []
        score = HORIZON_POINTS[horizon_key]
        terms.append(f"base(horizonte)={score}")

        if emergency_reserve_months is not None and emergency_reserve_months >= RESERVE_ADEQUATE_MONTHS:
            score += RESERVE_ADEQUACY_BONUS
            terms.append(f"+{RESERVE_ADEQUACY_BONUS}(reserva adequada)")
        elif not emergency_reserve_months or emergency_reserve_months < RESERVE_MINIMAL_MONTHS:
            score -= RESERVE_INADEQUACY_PENALTY
            terms.append(f"-{RESERVE_INADEQUACY_PENALTY}(reserva inadequada)")

        if has_relevant_debt:
            score -= DEBT_PENALTY
            terms.append(f"-{DEBT_PENALTY}(dívida relevante)")

        if dependents:
            penalty = min(dependents * DEPENDENTS_PENALTY_PER, DEPENDENTS_PENALTY_CAP)
            score -= penalty
            terms.append(f"-{penalty}({dependents} dependente(s))")

        if liquidity_need == "alta":
            score -= LIQUIDITY_HIGH_CAPACITY_PENALTY
            terms.append(f"-{LIQUIDITY_HIGH_CAPACITY_PENALTY}(liquidez alta necessária)")

        if contribution_stability == "fixo":
            score += STABLE_CONTRIBUTION_BONUS
            terms.append(f"+{STABLE_CONTRIBUTION_BONUS}(aporte estável)")

        return max(0, min(100, score)), terms

    @staticmethod
    def _classify(tolerance_score: int, capacity_score: int) -> str:
        gate = min(tolerance_score, capacity_score)
        for threshold, label in CLASSIFICATION_THRESHOLDS:
            if gate < threshold:
                return label
        return CLASSIFICATION_THRESHOLDS[-1][1]

    # -----------------------------------------------------------------
    # Derivação da política (envelope estratégico) — nunca escolhe ativos.
    # -----------------------------------------------------------------

    @classmethod
    def derive_policy(
        cls,
        evaluation: InvestorProfileEvaluation,
        answers: InvestorProfileAnswers,
    ) -> tuple[dict, list[DimensionExplanation]]:
        """Deriva um payload equivalente a PortfolioPolicyUpsert (dict) e a
        lista de explicações dos ajustes efetivamente aplicados.

        Determinístico e explicável: parte do envelope base da classificação
        (tolerância x capacidade) e então aplica, em sequência, ajustes
        limitados e rastreáveis por horizonte, necessidade de liquidez,
        necessidade de renda e adequação da reserva de emergência — cada um
        pode deslocar peso entre classes mesmo dentro da MESMA classificação
        geral, para que a política nunca dependa apenas do rótulo de risco.
        Por fim filtra por classes restritas/permitidas e renormaliza para
        somar exatamente 100.
        """
        classification = evaluation.overall_classification
        weights = dict(BASE_ALLOCATION_BY_CLASSIFICATION[classification])
        policy_explanations: list[DimensionExplanation] = []

        horizon_key = answers.horizon.horizon
        horizon_shift = HORIZON_ALLOCATION_SHIFT[horizon_key]
        if horizon_shift < 0:
            weights, applied = cls._shift_weight(
                weights,
                amount=-horizon_shift,
                from_classes=GROWTH_CLASSES,
                to_classes=HIGH_LIQUIDITY_CLASSES,
            )
            if applied > 0:
                policy_explanations.append(
                    DimensionExplanation(
                        "horizon_allocation",
                        f"horizon={horizon_key} desloca até {-horizon_shift}pp de classes voláteis "
                        "para Tesouro Direto",
                        str(applied),
                        f"Horizonte curto ('{horizon_key}') reduziu em {applied} pontos percentuais a "
                        "exposição a classes mais voláteis, priorizando Tesouro Direto.",
                    )
                )
        elif horizon_shift > 0:
            weights, applied = cls._shift_weight(
                weights,
                amount=horizon_shift,
                from_classes=DEFENSIVE_CLASSES,
                to_classes=GROWTH_CLASSES,
            )
            if applied > 0:
                policy_explanations.append(
                    DimensionExplanation(
                        "horizon_allocation",
                        f"horizon={horizon_key} desloca até {horizon_shift}pp de classes defensivas "
                        "para classes de crescimento",
                        str(applied),
                        f"Horizonte longo ('{horizon_key}') permitiu deslocar {applied} pontos "
                        "percentuais de classes defensivas para classes com maior potencial de "
                        "crescimento.",
                    )
                )

        liquidity_key = answers.liquidity.liquidity_need
        liquidity_shift = LIQUIDITY_ALLOCATION_SHIFT[liquidity_key]
        if liquidity_shift > 0:
            weights, applied = cls._shift_weight(
                weights,
                amount=liquidity_shift,
                from_classes=LOWER_LIQUIDITY_CLASSES,
                to_classes=HIGH_LIQUIDITY_CLASSES,
            )
            if applied > 0:
                policy_explanations.append(
                    DimensionExplanation(
                        "liquidity_allocation",
                        f"liquidity_need={liquidity_key} desloca até {liquidity_shift}pp de classes "
                        "menos líquidas para Tesouro Direto",
                        str(applied),
                        f"Necessidade de liquidez '{liquidity_key}' elevou em {applied} pontos "
                        "percentuais os componentes com liquidez diária garantida (Tesouro Direto), "
                        "reduzindo classes com liquidez mais restrita (renda fixa bancária, crédito "
                        "privado, FIIs).",
                    )
                )

        income_key = answers.income_need.income_need
        income_shift = INCOME_NEED_ALLOCATION_SHIFT[income_key]
        if income_shift > 0:
            weights, applied = cls._shift_weight(
                weights,
                amount=income_shift,
                from_classes=GROWTH_WITHOUT_INCOME_CLASSES,
                to_classes=INCOME_FOCUSED_CLASSES,
            )
            if applied > 0:
                policy_explanations.append(
                    DimensionExplanation(
                        "income_need_allocation",
                        f"income_need={income_key} desloca até {income_shift}pp de classes de "
                        "crescimento puro para FIIs",
                        str(applied),
                        f"Necessidade de renda '{income_key}' aumentou em {applied} pontos "
                        "percentuais a preferência estratégica por FIIs, a classe do envelope com "
                        "foco em distribuição de renda recorrente.",
                    )
                )

        weights, reserve_applied = cls._apply_reserve_shortfall_adjustment(
            weights, evaluation.emergency_reserve_adequacy_score
        )
        if reserve_applied > 0:
            policy_explanations.append(
                DimensionExplanation(
                    "reserve_allocation",
                    f"emergency_reserve_adequacy={evaluation.emergency_reserve_adequacy_score} < "
                    f"{RESERVE_SHORTFALL_ADEQUACY_THRESHOLD} desloca até {RESERVE_SHORTFALL_MAX_SHIFT}pp "
                    "para a reserva de emergência",
                    str(reserve_applied),
                    "Baixa capacidade financeira restringiu risco mesmo com tolerância psicológica "
                    f"mais alta: a adequação da reserva de emergência "
                    f"({evaluation.emergency_reserve_adequacy_score}/100) elevou em {reserve_applied} "
                    "pontos percentuais a alocação em Reserva de emergência, reduzindo classes de "
                    "crescimento.",
                )
            )

        allowed_classes = answers.restrictions.allowed_classes if answers.restrictions else []
        restricted_classes = answers.restrictions.restricted_classes if answers.restrictions else []
        weights = cls._apply_class_restrictions(
            weights, allowed_classes=allowed_classes, restricted_classes=restricted_classes
        )
        if allowed_classes or restricted_classes:
            policy_explanations.append(
                DimensionExplanation(
                    "class_restrictions",
                    f"restricted_classes={list(restricted_classes)}; allowed_classes={list(allowed_classes)}",
                    ", ".join(sorted(weights.keys())),
                    "Restrições declaradas pelo investidor excluíram classes vedadas e/ou limitaram o "
                    "envelope às classes explicitamente permitidas.",
                )
            )

        weights = cls._normalize_to_100(weights)

        limits = POLICY_LIMITS_BY_CLASSIFICATION[classification]
        allocations = [
            {
                "asset_class": asset_class,
                "target_percentage": weight,
                "minimum_percentage": (weight * Decimal("0.7")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                "maximum_percentage": min(
                    Decimal("100"),
                    (weight * Decimal("1.3") + Decimal("5")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                ),
                "enabled": True,
            }
            for asset_class, weight in sorted(weights.items())
            if weight > 0
        ]

        income_need_key = answers.income_need.income_need
        policy = {
            "name": "Política proposta pelo onboarding",
            "objective": answers.objectives.primary_objective,
            "risk_profile": classification,
            "investment_horizon": answers.horizon.horizon,
            "monthly_contribution": answers.contribution.monthly_contribution or Decimal("0"),
            "liquidity_need": answers.liquidity.liquidity_need,
            "income_need": INCOME_NEED_TO_LEGACY_BOOLEAN[income_need_key],
            "emergency_reserve_months": answers.financial_situation.emergency_reserve_months or 0,
            "maximum_weight_per_asset": limits["maximum_weight_per_asset"],
            "maximum_weight_per_sector": limits["maximum_weight_per_sector"],
            "maximum_weight_per_issuer": limits["maximum_weight_per_issuer"],
            "rebalance_tolerance": limits["rebalance_tolerance"],
            "allocations": allocations,
        }
        return policy, policy_explanations

    @staticmethod
    def _shift_weight(
        weights: dict[str, Decimal],
        *,
        amount: Decimal,
        from_classes: tuple[str, ...],
        to_classes: tuple[str, ...],
    ) -> tuple[dict[str, Decimal], Decimal]:
        """Desloca até `amount` pontos percentuais de from_classes para
        to_classes, proporcionalmente ao peso atual de cada lado (ou
        dividido igualmente entre to_classes se nenhuma delas tiver peso
        ainda). Nunca deixa uma classe negativa. Retorna o deslocamento
        efetivamente aplicado — pode ser menor que `amount` se from_classes
        não tiver peso suficiente disponível no envelope atual; qualquer
        pequeno resíduo de arredondamento é absorvido depois por
        _normalize_to_100."""
        if amount <= 0:
            return weights, Decimal("0")
        source_total = sum((weights.get(name, Decimal("0")) for name in from_classes), Decimal("0"))
        if source_total <= 0:
            return weights, Decimal("0")
        applied = min(amount, source_total)
        adjusted = dict(weights)
        for name in from_classes:
            current = adjusted.get(name, Decimal("0"))
            if current <= 0:
                continue
            reduction = (applied * current / source_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            adjusted[name] = max(Decimal("0"), current - reduction)
        destination_total = sum((adjusted.get(name, Decimal("0")) for name in to_classes), Decimal("0"))
        if destination_total > 0:
            for name in to_classes:
                current = adjusted.get(name, Decimal("0"))
                share = (applied * current / destination_total).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                adjusted[name] = current + share
        else:
            share = (applied / len(to_classes)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for name in to_classes:
                adjusted[name] = adjusted.get(name, Decimal("0")) + share
        return adjusted, applied

    @classmethod
    def _apply_reserve_shortfall_adjustment(
        cls, weights: dict[str, Decimal], reserve_adequacy_score: int
    ) -> tuple[dict[str, Decimal], Decimal]:
        if reserve_adequacy_score >= RESERVE_SHORTFALL_ADEQUACY_THRESHOLD:
            return weights, Decimal("0")
        shortfall_ratio = Decimal(RESERVE_SHORTFALL_ADEQUACY_THRESHOLD - reserve_adequacy_score) / Decimal(
            RESERVE_SHORTFALL_ADEQUACY_THRESHOLD
        )
        amount = (shortfall_ratio * RESERVE_SHORTFALL_MAX_SHIFT).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return cls._shift_weight(
            weights, amount=amount, from_classes=GROWTH_CLASSES, to_classes=("Reserva de emergência",)
        )

    @staticmethod
    def _apply_class_restrictions(
        weights: dict[str, Decimal],
        *,
        allowed_classes: list[str],
        restricted_classes: list[str],
    ) -> dict[str, Decimal]:
        adjusted = dict(weights)
        for asset_class in restricted_classes:
            if asset_class in ALWAYS_ELIGIBLE_CLASSES:
                continue
            adjusted.pop(asset_class, None)
        if allowed_classes:
            allowed_set = set(allowed_classes) | ALWAYS_ELIGIBLE_CLASSES
            adjusted = {
                asset_class: weight
                for asset_class, weight in adjusted.items()
                if asset_class in allowed_set
            }
        return adjusted

    @staticmethod
    def _normalize_to_100(weights: dict[str, Decimal]) -> dict[str, Decimal]:
        positive = {k: v for k, v in weights.items() if v > 0}
        total = sum(positive.values(), Decimal("0"))
        if total <= 0:
            # Nunca deveria ocorrer (Reserva de emergência é sempre elegível
            # e sempre presente no envelope base) — rede de segurança
            # determinística sem fabricar alocação: devolve reserva a 100%.
            return {"Reserva de emergência": Decimal("100")}
        scaled = {
            k: (v / total * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for k, v in positive.items()
        }
        residual = Decimal("100") - sum(scaled.values(), Decimal("0"))
        if residual != 0:
            largest_key = max(scaled, key=lambda k: (scaled[k], k))
            scaled[largest_key] = scaled[largest_key] + residual
        return scaled


assert set(cls_name for row in BASE_ALLOCATION_BY_CLASSIFICATION.values() for cls_name in row).issubset(
    set(INVESTMENT_CLASSES)
), "BASE_ALLOCATION_BY_CLASSIFICATION referencia uma classe fora de INVESTMENT_CLASSES"
