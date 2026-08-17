from decimal import Decimal

import pytest

from app.engines.investor_profile_engine import (
    BASE_ALLOCATION_BY_CLASSIFICATION,
    InvestorProfileEngine,
    InvestorProfileEvaluation,
)
from app.schemas.investor_profile import (
    ContributionAnswer,
    FinancialSituationAnswer,
    HorizonAnswer,
    IncomeNeedAnswer,
    InvestorProfileAnswers,
    KnowledgeAnswer,
    LiquidityAnswer,
    ObjectivesAnswer,
    RestrictionsAnswer,
    RiskToleranceAnswer,
)


CORRECT_KNOWLEDGE_ANSWERS = {
    "volatilidade": "b",
    "diversificacao": "a",
    "risco_perda": "c",
    "renda_fixa_x_variavel": "a",
    "marcacao_a_mercado": "b",
}


def build_answers(
    *,
    tolerance_choice="manteria",
    horizon="3_a_5_anos",
    reserve_months=6,
    debt=False,
    dependents=0,
    liquidity="moderada",
    income_need="complemento",
    knowledge_answers=None,
    restrictions=None,
    monthly_contribution=Decimal("1000"),
):
    scenarios = {
        s: tolerance_choice
        for s in ("queda_20_curto_prazo", "queda_30_prolongada", "volatilidade_mensal")
    }
    return InvestorProfileAnswers(
        objectives=ObjectivesAnswer(primary_objective="crescimento_patrimonial"),
        horizon=HorizonAnswer(horizon=horizon),
        contribution=ContributionAnswer(
            monthly_contribution=monthly_contribution, contribution_stability="fixo"
        ),
        financial_situation=FinancialSituationAnswer(
            emergency_reserve_months=reserve_months,
            has_relevant_debt=debt,
            dependents=dependents,
        ),
        liquidity=LiquidityAnswer(liquidity_need=liquidity),
        income_need=IncomeNeedAnswer(income_need=income_need),
        knowledge=KnowledgeAnswer(answers=knowledge_answers or CORRECT_KNOWLEDGE_ANSWERS),
        risk_tolerance=RiskToleranceAnswer(scenarios=scenarios),
        restrictions=RestrictionsAnswer(**(restrictions or {})),
    )


# --- estrutura do envelope base -------------------------------------------


@pytest.mark.parametrize("classification", list(BASE_ALLOCATION_BY_CLASSIFICATION))
def test_base_allocation_rows_sum_to_exactly_100(classification):
    row = BASE_ALLOCATION_BY_CLASSIFICATION[classification]
    assert sum(row.values(), Decimal("0")) == Decimal("100")


# --- seções obrigatórias ----------------------------------------------------


def test_missing_required_sections_lists_every_gap():
    answers = InvestorProfileAnswers()
    missing = InvestorProfileEngine.missing_required_sections(answers)
    assert "objectives" in missing
    assert "risk_tolerance" in missing
    assert "knowledge" in missing


def test_evaluate_raises_when_required_sections_missing():
    answers = InvestorProfileAnswers(objectives=ObjectivesAnswer(primary_objective="preservacao"))
    with pytest.raises(ValueError):
        InvestorProfileEngine.evaluate(answers)


def test_missing_required_sections_empty_when_fully_answered():
    answers = build_answers()
    assert InvestorProfileEngine.missing_required_sections(answers) == []


# --- classificação: capacidade sempre restringe tolerância ------------------


def test_extreme_conservative_case_classifies_as_conservador():
    answers = build_answers(
        tolerance_choice="venderia_tudo",
        horizon="menos_1_ano",
        reserve_months=0,
        debt=True,
        dependents=4,
        liquidity="alta",
        income_need="dependencia",
    )
    evaluation = InvestorProfileEngine.evaluate(answers)
    assert evaluation.overall_classification == "Conservador"
    assert evaluation.risk_tolerance_score == 0
    assert evaluation.risk_capacity_score == 0


def test_extreme_aggressive_case_classifies_as_arrojado():
    answers = build_answers(
        tolerance_choice="compraria_mais",
        horizon="mais_10_anos",
        reserve_months=12,
        debt=False,
        dependents=0,
        liquidity="baixa",
        income_need="nenhuma",
    )
    evaluation = InvestorProfileEngine.evaluate(answers)
    assert evaluation.overall_classification == "Arrojado"


def test_intermediate_case_classifies_as_moderado():
    answers = build_answers(
        tolerance_choice="manteria",
        horizon="5_a_10_anos",
        reserve_months=6,
        debt=False,
        dependents=1,
        liquidity="moderada",
        income_need="complemento",
    )
    evaluation = InvestorProfileEngine.evaluate(answers)
    assert evaluation.overall_classification in {"Moderado", "Moderado-conservador", "Moderado-arrojado"}


def test_high_tolerance_low_capacity_is_gated_by_capacity():
    """tolerância psicológica alta + capacidade financeira baixa é um estado
    válido — a classificação nunca pode ser mais arrojada do que a
    capacidade permite (seção 12 do prompt: dimensões independentes)."""
    answers = build_answers(
        tolerance_choice="compraria_mais",
        horizon="menos_1_ano",
        reserve_months=0,
        debt=True,
        dependents=4,
        liquidity="alta",
        income_need="dependencia",
    )
    evaluation = InvestorProfileEngine.evaluate(answers)
    assert evaluation.risk_tolerance_score == 100
    assert evaluation.risk_capacity_score < evaluation.risk_tolerance_score
    assert evaluation.overall_classification in {"Conservador", "Moderado-conservador"}


def test_low_tolerance_high_capacity_is_gated_by_tolerance():
    answers = build_answers(
        tolerance_choice="venderia_tudo",
        horizon="mais_10_anos",
        reserve_months=12,
        debt=False,
        dependents=0,
        liquidity="baixa",
        income_need="nenhuma",
    )
    evaluation = InvestorProfileEngine.evaluate(answers)
    assert evaluation.risk_capacity_score == 100
    assert evaluation.risk_tolerance_score < evaluation.risk_capacity_score
    assert evaluation.overall_classification == "Conservador"


# --- conhecimento -----------------------------------------------------------


def test_knowledge_score_is_percentage_of_correct_answers():
    wrong_answers = {key: "d" for key in CORRECT_KNOWLEDGE_ANSWERS}
    answers = build_answers(knowledge_answers=wrong_answers)
    evaluation = InvestorProfileEngine.evaluate(answers)
    assert evaluation.knowledge_score == 0

    answers_correct = build_answers(knowledge_answers=CORRECT_KNOWLEDGE_ANSWERS)
    evaluation_correct = InvestorProfileEngine.evaluate(answers_correct)
    assert evaluation_correct.knowledge_score == 100


# --- explicações --------------------------------------------------------


def test_evaluation_produces_explanation_for_every_dimension():
    answers = build_answers()
    evaluation = InvestorProfileEngine.evaluate(answers)
    dimensions_explained = {item.dimension for item in evaluation.explanations}
    assert dimensions_explained == {
        "horizon",
        "liquidity_need",
        "income_need",
        "knowledge",
        "emergency_reserve_adequacy",
        "risk_tolerance",
        "risk_capacity",
        "overall_classification",
    }


def test_classification_explanation_cites_the_gating_rule():
    answers = build_answers(tolerance_choice="compraria_mais", reserve_months=0, debt=True, dependents=4, liquidity="alta")
    evaluation = InvestorProfileEngine.evaluate(answers)
    classification_explanation = next(
        item for item in evaluation.explanations if item.dimension == "overall_classification"
    )
    assert "min(" in classification_explanation.rule


# --- derivação de política -------------------------------------------------


def test_derived_policy_allocations_always_sum_to_100():
    for tolerance in ("venderia_tudo", "manteria", "compraria_mais"):
        answers = build_answers(tolerance_choice=tolerance)
        evaluation = InvestorProfileEngine.evaluate(answers)
        policy, _explanations = InvestorProfileEngine.derive_policy(evaluation, answers)
        total = sum((item["target_percentage"] for item in policy["allocations"]), Decimal("0"))
        assert total == Decimal("100")


def test_derived_policy_never_includes_restricted_classes():
    answers = build_answers(restrictions={"restricted_classes": ["Criptomoedas", "BDRs", "ETFs"]})
    evaluation = InvestorProfileEngine.evaluate(answers)
    policy, _explanations = InvestorProfileEngine.derive_policy(evaluation, answers)
    classes = {item["asset_class"] for item in policy["allocations"]}
    assert classes.isdisjoint({"Criptomoedas", "BDRs", "ETFs"})
    total = sum((item["target_percentage"] for item in policy["allocations"]), Decimal("0"))
    assert total == Decimal("100")


def test_derived_policy_allowed_classes_always_keeps_emergency_reserve():
    answers = build_answers(restrictions={"allowed_classes": ["Ações"]})
    evaluation = InvestorProfileEngine.evaluate(answers)
    policy, _explanations = InvestorProfileEngine.derive_policy(evaluation, answers)
    classes = {item["asset_class"] for item in policy["allocations"]}
    assert "Reserva de emergência" in classes


def test_derived_policy_never_produces_negative_or_invalid_bounds():
    for classification_case in ("venderia_tudo", "manteria", "compraria_mais"):
        answers = build_answers(tolerance_choice=classification_case)
        evaluation = InvestorProfileEngine.evaluate(answers)
        policy, _explanations = InvestorProfileEngine.derive_policy(evaluation, answers)
        for item in policy["allocations"]:
            assert item["target_percentage"] >= 0
            assert item["minimum_percentage"] >= 0
            assert item["minimum_percentage"] <= item["target_percentage"]
            assert item["target_percentage"] <= item["maximum_percentage"]


def test_derived_policy_reduces_growth_weight_when_reserve_is_inadequate():
    poor_reserve_answers = build_answers(reserve_months=0)
    healthy_reserve_answers = build_answers(reserve_months=12)

    poor_eval = InvestorProfileEngine.evaluate(poor_reserve_answers)
    healthy_eval = InvestorProfileEngine.evaluate(healthy_reserve_answers)

    poor_policy, poor_explanations = InvestorProfileEngine.derive_policy(poor_eval, poor_reserve_answers)
    healthy_policy, _healthy_explanations = InvestorProfileEngine.derive_policy(
        healthy_eval, healthy_reserve_answers
    )

    poor_reserve_weight = next(
        item["target_percentage"]
        for item in poor_policy["allocations"]
        if item["asset_class"] == "Reserva de emergência"
    )
    healthy_reserve_weight = next(
        (
            item["target_percentage"]
            for item in healthy_policy["allocations"]
            if item["asset_class"] == "Reserva de emergência"
        ),
        Decimal("0"),
    )
    assert poor_reserve_weight > healthy_reserve_weight
    assert any(item.dimension == "reserve_allocation" for item in poor_explanations)


def test_derived_policy_income_need_maps_to_legacy_boolean():
    answers_none = build_answers(income_need="nenhuma")
    evaluation_none = InvestorProfileEngine.evaluate(answers_none)
    policy_none, _explanations_none = InvestorProfileEngine.derive_policy(evaluation_none, answers_none)
    assert policy_none["income_need"] is False

    answers_dependent = build_answers(income_need="dependencia")
    evaluation_dependent = InvestorProfileEngine.evaluate(answers_dependent)
    policy_dependent, _explanations_dependent = InvestorProfileEngine.derive_policy(
        evaluation_dependent, answers_dependent
    )
    assert policy_dependent["income_need"] is True


# --- multidimensionalidade real da política (não apenas classificação) -----
#
# As dimensões horizon / liquidity_need / income_need são fixadas via uma
# InvestorProfileEvaluation construída manualmente (mesmos scores e mesma
# classificação geral em ambos os lados de cada comparação), isolando
# exatamente a variável sob teste. Isso testa o comportamento financeiro
# público de derive_policy(evaluation, answers) — não um detalhe frágil de
# implementação — provando que a política não é apenas
# `classificação -> alocação fixa`.


def _fixed_evaluation(classification="Moderado") -> InvestorProfileEvaluation:
    return InvestorProfileEvaluation(
        risk_tolerance_score=66,
        risk_capacity_score=66,
        horizon_score=45,
        liquidity_need_score=55,
        income_need_score=40,
        knowledge_score=100,
        emergency_reserve_adequacy_score=100,
        overall_classification=classification,
    )


def _target_percentages(policy: dict) -> dict[str, Decimal]:
    return {item["asset_class"]: item["target_percentage"] for item in policy["allocations"]}


def test_a_same_tolerance_and_capacity_short_vs_long_horizon_yield_different_policy():
    evaluation = _fixed_evaluation()
    short_answers = build_answers(horizon="menos_1_ano")
    long_answers = build_answers(horizon="mais_10_anos")

    short_policy, short_explanations = InvestorProfileEngine.derive_policy(evaluation, short_answers)
    long_policy, long_explanations = InvestorProfileEngine.derive_policy(evaluation, long_answers)

    short_weights = _target_percentages(short_policy)
    long_weights = _target_percentages(long_policy)
    assert short_weights != long_weights
    # horizonte curto prioriza Tesouro Direto; horizonte longo prioriza Ações.
    assert short_weights["Tesouro Direto"] > long_weights["Tesouro Direto"]
    assert short_weights["Ações"] < long_weights["Ações"]
    assert any(item.dimension == "horizon_allocation" for item in short_explanations)
    assert any(item.dimension == "horizon_allocation" for item in long_explanations)
    assert sum(short_weights.values(), Decimal("0")) == Decimal("100")
    assert sum(long_weights.values(), Decimal("0")) == Decimal("100")


def test_b_same_tolerance_horizon_high_vs_low_liquidity_need_yield_different_policy():
    evaluation = _fixed_evaluation()
    high_liquidity_answers = build_answers(liquidity="alta")
    low_liquidity_answers = build_answers(liquidity="baixa")

    high_policy, high_explanations = InvestorProfileEngine.derive_policy(evaluation, high_liquidity_answers)
    low_policy, low_explanations = InvestorProfileEngine.derive_policy(evaluation, low_liquidity_answers)

    high_weights = _target_percentages(high_policy)
    low_weights = _target_percentages(low_policy)
    assert high_weights != low_weights
    assert high_weights["Tesouro Direto"] > low_weights["Tesouro Direto"]
    assert any(item.dimension == "liquidity_allocation" for item in high_explanations)
    assert not any(item.dimension == "liquidity_allocation" for item in low_explanations)
    assert sum(high_weights.values(), Decimal("0")) == Decimal("100")
    assert sum(low_weights.values(), Decimal("0")) == Decimal("100")


def test_c_same_tolerance_horizon_liquidity_income_need_yields_different_policy():
    evaluation = _fixed_evaluation()
    strong_income_answers = build_answers(income_need="dependencia")
    no_income_answers = build_answers(income_need="nenhuma")

    strong_policy, strong_explanations = InvestorProfileEngine.derive_policy(
        evaluation, strong_income_answers
    )
    none_policy, none_explanations = InvestorProfileEngine.derive_policy(evaluation, no_income_answers)

    strong_weights = _target_percentages(strong_policy)
    none_weights = _target_percentages(none_policy)
    assert strong_weights != none_weights
    assert strong_weights["FIIs"] > none_weights["FIIs"]
    assert any(item.dimension == "income_need_allocation" for item in strong_explanations)
    assert not any(item.dimension == "income_need_allocation" for item in none_explanations)
    assert sum(strong_weights.values(), Decimal("0")) == Decimal("100")
    assert sum(none_weights.values(), Decimal("0")) == Decimal("100")


def test_e_high_tolerance_low_capacity_policy_still_reflects_conservative_gate():
    """Mesmo com tolerância psicológica máxima, a política derivada deve
    refletir o envelope conservador determinado pela capacidade (gate), não
    o envelope arrojado que a tolerância isolada sugeriria."""
    answers = build_answers(
        tolerance_choice="compraria_mais",
        horizon="menos_1_ano",
        reserve_months=0,
        debt=True,
        dependents=4,
        liquidity="alta",
        income_need="dependencia",
    )
    evaluation = InvestorProfileEngine.evaluate(answers)
    assert evaluation.overall_classification in {"Conservador", "Moderado-conservador"}

    policy, _explanations = InvestorProfileEngine.derive_policy(evaluation, answers)
    weights = _target_percentages(policy)
    arrojado_stocks_weight = BASE_ALLOCATION_BY_CLASSIFICATION["Arrojado"]["Ações"]
    assert weights.get("Ações", Decimal("0")) < arrojado_stocks_weight


def test_f_prohibited_classes_remain_excluded_across_all_dimension_adjustments():
    answers = build_answers(
        horizon="mais_10_anos",
        liquidity="alta",
        income_need="dependencia",
        reserve_months=0,
        restrictions={"restricted_classes": ["Ações", "FIIs", "Criptomoedas", "ETFs", "BDRs"]},
    )
    evaluation = InvestorProfileEngine.evaluate(answers)
    policy, _explanations = InvestorProfileEngine.derive_policy(evaluation, answers)
    classes = {item["asset_class"] for item in policy["allocations"]}
    assert classes.isdisjoint({"Ações", "FIIs", "Criptomoedas", "ETFs", "BDRs"})
    total = sum((item["target_percentage"] for item in policy["allocations"]), Decimal("0"))
    assert total == Decimal("100")


@pytest.mark.parametrize("horizon", ["menos_1_ano", "1_a_3_anos", "3_a_5_anos", "5_a_10_anos", "mais_10_anos"])
@pytest.mark.parametrize("liquidity", ["baixa", "moderada", "alta"])
@pytest.mark.parametrize("income_need", ["nenhuma", "complemento", "renda_passiva", "dependencia"])
def test_g_every_combination_of_dimensions_sums_to_exactly_100(horizon, liquidity, income_need):
    answers = build_answers(horizon=horizon, liquidity=liquidity, income_need=income_need)
    evaluation = InvestorProfileEngine.evaluate(answers)
    policy, _explanations = InvestorProfileEngine.derive_policy(evaluation, answers)
    total = sum((item["target_percentage"] for item in policy["allocations"]), Decimal("0"))
    assert total == Decimal("100")
    for item in policy["allocations"]:
        assert item["minimum_percentage"] <= item["target_percentage"] <= item["maximum_percentage"]
    classes = [item["asset_class"] for item in policy["allocations"]]
    assert len(classes) == len(set(classes))


# --- determinismo ------------------------------------------------------------


def test_h_same_answers_always_produce_the_same_evaluation_and_policy():
    answers = build_answers(tolerance_choice="manteria", restrictions={"restricted_classes": ["Criptomoedas"]})
    eval_a = InvestorProfileEngine.evaluate(answers)
    eval_b = InvestorProfileEngine.evaluate(answers)
    assert eval_a.overall_classification == eval_b.overall_classification
    assert eval_a.risk_tolerance_score == eval_b.risk_tolerance_score
    assert eval_a.risk_capacity_score == eval_b.risk_capacity_score

    policy_a, explanations_a = InvestorProfileEngine.derive_policy(eval_a, answers)
    policy_b, explanations_b = InvestorProfileEngine.derive_policy(eval_b, answers)
    assert policy_a == policy_b
    assert explanations_a == explanations_b


# --- rejeição de mass assignment (extra="forbid") ---------------------------


def test_answers_reject_unknown_top_level_field():
    with pytest.raises(Exception):
        InvestorProfileAnswers.model_validate({"unexpected_field": "value"})


def test_objectives_answer_rejects_unknown_field():
    with pytest.raises(Exception):
        ObjectivesAnswer.model_validate({"primary_objective": "aposentadoria", "user_id": "hack"})
