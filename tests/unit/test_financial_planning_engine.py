from decimal import Decimal

from app.engines.financial_planning_engine import (
    FinancialDiagnosisEngine,
    FinancialProfileContext,
    FinancialProjectionEngine,
)
from app.schemas.intelligence import BuildPortfolioRequest


def request(**updates):
    values = {
        "available_amount": Decimal("10000"),
        "objective": "crescimento",
        "horizon": "longo prazo",
        "risk_profile": "moderado",
        "monthly_contribution": Decimal("1000"),
        "net_monthly_income": Decimal("8000"),
        "essential_monthly_expenses": Decimal("3500"),
        "total_monthly_expenses": Decimal("5500"),
        "emergency_reserve": Decimal("5000"),
        "high_cost_debt": Decimal("0"),
        "current_financial_assets": Decimal("20000"),
        "desired_monthly_income": Decimal("5000"),
        "projection_years": 10,
        "inflation_rate": Decimal("4"),
    }
    values.update(updates)
    return BuildPortfolioRequest(**values)


def test_diagnosis_prioritizes_protection_when_reserve_is_short():
    diagnosis = FinancialDiagnosisEngine.diagnose(request())

    assert diagnosis.phase == "protection"
    assert diagnosis.estimated_monthly_capacity == Decimal("2500.00")
    assert diagnosis.reserve_target == Decimal("21000.00")
    assert diagnosis.priority_actions


def test_projection_has_four_ordered_scenarios_and_no_income_double_count():
    projections = FinancialProjectionEngine.project(request(reinvest_income=False))

    assert [item.name for item in projections] == [
        "stress",
        "conservative",
        "central",
        "optimistic",
    ]
    assert projections[0].projected_wealth < projections[-1].projected_wealth
    assert all(
        item.projected_wealth == item.projected_without_reinvestment
        for item in projections
    )


def test_financial_freedom_target_applies_withdrawal_rate_and_safety_margin():
    data = request(withdrawal_rate=Decimal("4"), safety_margin=Decimal("20"))
    goal = FinancialProjectionEngine.freedom_goal(
        data, FinancialProjectionEngine.project(data)
    )

    assert goal.required_wealth == Decimal("1800000.00")
    assert goal.gap == Decimal("1780000.00")


def test_profile_protects_when_debt_or_reserve_inadequate_without_inventing_amounts():
    context = FinancialProfileContext(emergency_reserve_months=2, has_relevant_debt=True)
    data = request(
        net_monthly_income=None,
        essential_monthly_expenses=None,
        total_monthly_expenses=None,
        emergency_reserve=None,
        high_cost_debt=None,
    )
    diagnosis = FinancialDiagnosisEngine.diagnose(data, context)
    assert diagnosis.phase == "protection"
    assert diagnosis.reserve_months_covered == Decimal("2")
    assert diagnosis.reserve_target is None  # sem despesas exatas, não inventar R$
    assert diagnosis.estimated_monthly_capacity is None
    assert diagnosis.debt_alerts
    assert any("Completar a reserva" in action for action in diagnosis.priority_actions)


def test_profile_with_sufficient_reserve_and_no_debt_permits_accumulation():
    context = FinancialProfileContext(emergency_reserve_months=8, has_relevant_debt=False)
    data = request(
        essential_monthly_expenses=None,
        total_monthly_expenses=None,
        emergency_reserve=None,
        high_cost_debt=None,
    )
    diagnosis = FinancialDiagnosisEngine.diagnose(data, context)
    assert diagnosis.phase == "accumulation"
    assert diagnosis.reserve_months_covered == Decimal("8")
    assert not diagnosis.debt_alerts
