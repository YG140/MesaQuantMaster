from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.schemas.intelligence import (
    BuildPortfolioRequest,
    PortfolioPolicyRead,
    FinancialDiagnosis,
    FinancialFreedomGoal,
    ProjectionScenario,
)

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
TWELVE = Decimal("12")


@dataclass(frozen=True)
class FinancialProfileContext:
    """Fatos declarados e confirmados no perfil, sem criar valores monetários."""
    emergency_reserve_months: int | None = None
    has_relevant_debt: bool | None = None


def apply_policy_to_planning_request(
    data: BuildPortfolioRequest,
    policy: PortfolioPolicyRead | None,
) -> BuildPortfolioRequest:
    """Política confirmada governa diagnóstico e projeção, inclusive sem ativos."""
    if policy is None:
        return data
    years = {
        "menos_1_ano": 1, "1_a_3_anos": 3, "3_a_5_anos": 5,
        "5_a_10_anos": 10, "mais_10_anos": 20,
        "curto prazo": 2, "médio prazo": 5, "longo prazo": 20,
    }
    return data.model_copy(update={
        "objective": policy.objective,
        "horizon": policy.investment_horizon,
        "risk_profile": policy.risk_profile,
        "monthly_contribution": policy.monthly_contribution,
        "needs_income": policy.income_need,
        "needs_liquidity": policy.liquidity_need in {"moderada", "média", "alta"},
        "max_percentage_per_asset": min(
            data.max_percentage_per_asset, policy.maximum_weight_per_asset
        ),
        "max_percentage_per_sector": min(
            data.max_percentage_per_sector, policy.maximum_weight_per_sector
        ),
        "emergency_months": policy.emergency_reserve_months,
        "projection_years": years.get(policy.investment_horizon, data.projection_years),
    })


class FinancialDiagnosisEngine:
    @staticmethod
    def diagnose(
        data: BuildPortfolioRequest,
        financial_profile: FinancialProfileContext | None = None,
    ) -> FinancialDiagnosis:
        missing = [
            label
            for value, label in (
                (data.net_monthly_income, "renda mensal líquida"),
                (data.essential_monthly_expenses, "despesas essenciais"),
                (data.total_monthly_expenses, "despesas totais"),
                (data.emergency_reserve, "reserva de emergência"),
                (data.high_cost_debt, "dívidas de custo elevado"),
            )
            if value is None
        ]
        capacity = None
        if (
            data.net_monthly_income is not None
            and data.total_monthly_expenses is not None
        ):
            capacity = max(
                Decimal("0"), data.net_monthly_income - data.total_monthly_expenses
            ).quantize(CENT)
        reserve_target = reserve_months = None
        if data.essential_monthly_expenses is not None:
            months = Decimal(str(max(1, data.emergency_months)))
            if data.income_type in {"variável", "sazonal"}:
                months += Decimal("3")
            if data.dependents:
                months += Decimal("1")
            reserve_target = (data.essential_monthly_expenses * months).quantize(CENT)
            if (
                data.emergency_reserve is not None
                and data.essential_monthly_expenses > 0
            ):
                reserve_months = (
                    data.emergency_reserve / data.essential_monthly_expenses
                ).quantize(CENT)
        # O questionário guarda meses cobertos e presença de dívida, não
        # reais exatos. Usar os fatos conhecidos sem inventar montantes.
        if reserve_months is None and financial_profile is not None:
            if financial_profile.emergency_reserve_months is not None:
                reserve_months = Decimal(financial_profile.emergency_reserve_months)
        debts = []
        has_debt = bool(data.high_cost_debt is not None and data.high_cost_debt > 0)
        if financial_profile is not None and financial_profile.has_relevant_debt:
            has_debt = True
        if has_debt:
            debts.append(
                "Existe dívida de custo elevado; priorize sua redução antes de ampliar risco."
            )
        reserve_short = (
            (reserve_target is not None
             and data.emergency_reserve is not None
             and data.emergency_reserve < reserve_target)
            or (reserve_months is not None
                and reserve_months < Decimal(data.emergency_months))
        )
        required = FinancialProjectionEngine.required_wealth(data)
        if debts or reserve_short:
            phase = "protection"
        elif (
            required
            and data.current_financial_assets is not None
            and data.current_financial_assets >= required
        ):
            phase = "independence"
        else:
            phase = "accumulation"
        actions = []
        if debts:
            actions.append("Amortizar primeiro as dívidas com maior custo efetivo.")
        if reserve_short:
            actions.append(
                "Completar a reserva em instrumentos líquidos e de baixo risco."
            )
        if not actions:
            actions.append(
                "Manter aportes, reinvestimento e rebalanceamento periódico."
            )
        return FinancialDiagnosis(
            phase=phase,
            estimated_monthly_capacity=capacity,
            reserve_months_covered=reserve_months,
            reserve_target=reserve_target,
            debt_alerts=debts,
            liquidity_assessment="alta" if data.needs_liquidity else "baixa",
            missing_data=missing,
            priority_actions=actions,
            confidence=(
                "high" if not missing else "medium" if len(missing) <= 2 else "low"
            ),
        )


class FinancialProjectionEngine:
    SCENARIOS = {
        "stress": (Decimal("-8"), Decimal("1")),
        "conservative": (Decimal("2"), Decimal("2")),
        "central": (Decimal("5"), Decimal("3")),
        "optimistic": (Decimal("8"), Decimal("4")),
    }

    @classmethod
    def project(cls, data: BuildPortfolioRequest) -> list[ProjectionScenario]:
        initial = (
            data.current_financial_assets
            if data.current_financial_assets is not None
            else data.available_amount
        )
        inflation = (
            data.inflation_rate / HUNDRED if data.inflation_rate is not None else None
        )
        contribution_growth = (
            data.annual_contribution_growth or Decimal("0")
        ) / HUNDRED
        results = []
        for name, (appreciation, income_rate) in cls.SCENARIOS.items():
            wealth = without = contributed = initial
            income_total = Decimal("0")
            monthly = data.monthly_contribution
            appreciation_monthly = (
                (appreciation - data.annual_cost_rate) / HUNDRED / TWELVE
            )
            income_monthly = (
                income_rate
                / HUNDRED
                * (Decimal("1") - data.tax_rate / HUNDRED)
                / TWELVE
            )
            for _ in range(data.projection_years):
                for _ in range(12):
                    wealth += monthly
                    without += monthly
                    contributed += monthly
                    income = wealth * income_monthly
                    income_total += income
                    wealth += wealth * appreciation_monthly
                    if data.reinvest_income:
                        wealth += income
                    without += without * appreciation_monthly
                monthly *= Decimal("1") + contribution_growth
            real = (
                wealth / ((Decimal("1") + inflation) ** data.projection_years)
                if inflation is not None
                else None
            )
            results.append(
                ProjectionScenario(
                    name=name,
                    annual_appreciation_rate=appreciation,
                    annual_income_rate=income_rate,
                    total_contributed=contributed.quantize(CENT),
                    projected_wealth=wealth.quantize(CENT),
                    estimated_appreciation=(
                        wealth
                        - contributed
                        - (income_total if data.reinvest_income else Decimal("0"))
                    ).quantize(CENT),
                    estimated_income=income_total.quantize(CENT),
                    estimated_periodic_income=(wealth * income_monthly).quantize(CENT),
                    real_projected_wealth=(
                        real.quantize(CENT) if real is not None else None
                    ),
                    projected_without_reinvestment=without.quantize(CENT),
                )
            )
        return results

    @staticmethod
    def required_wealth(data: BuildPortfolioRequest) -> Decimal | None:
        # Meta patrimonial informada prevalece sobre a meta derivada de renda.
        if data.wealth_goal_amount is not None:
            return data.wealth_goal_amount.quantize(CENT)
        if data.desired_monthly_income is None:
            return None
        base = data.desired_monthly_income * TWELVE / (data.withdrawal_rate / HUNDRED)
        return (base * (Decimal("1") + data.safety_margin / HUNDRED)).quantize(CENT)

    @classmethod
    def freedom_goal(
        cls, data: BuildPortfolioRequest, projections: list[ProjectionScenario]
    ) -> FinancialFreedomGoal:
        required = cls.required_wealth(data)
        current = data.current_financial_assets
        gap = (
            max(Decimal("0"), required - current).quantize(CENT)
            if required is not None and current is not None
            else None
        )
        achieved = (
            min(HUNDRED, current / required * HUNDRED).quantize(CENT)
            if required and current is not None
            else None
        )
        central = next((item for item in projections if item.name == "central"), None)
        # Detecta o primeiro mês da meta usando as MESMAS regras do cenário
        # central em project(), sem confundir prazo do gráfico com prazo da meta.
        months = None
        if required is not None and central is not None:
            wealth = (
                data.current_financial_assets
                if data.current_financial_assets is not None
                else data.available_amount
            )
            monthly = data.monthly_contribution
            contribution_growth = (data.annual_contribution_growth or Decimal("0")) / HUNDRED
            appreciation = (cls.SCENARIOS["central"][0] - data.annual_cost_rate) / HUNDRED / TWELVE
            income_rate = (
                cls.SCENARIOS["central"][1] / HUNDRED
                * (Decimal("1") - data.tax_rate / HUNDRED) / TWELVE
            )
            if wealth >= required:
                months = 0
            else:
                for year in range(data.projection_years):
                    for month in range(12):
                        wealth += monthly
                        income = wealth * income_rate
                        wealth += wealth * appreciation
                        if data.reinvest_income:
                            wealth += income
                        if wealth >= required:
                            months = year * 12 + month + 1
                            break
                    if months is not None:
                        break
                    monthly *= Decimal("1") + contribution_growth
        years = (months + 11) // 12 if months is not None else None
        return FinancialFreedomGoal(
            desired_monthly_income=data.desired_monthly_income,
            required_wealth=required,
            current_wealth=current,
            gap=gap,
            achieved_percentage=achieved,
            estimated_years=years,
            estimated_months=months,
            withdrawal_rate=data.withdrawal_rate,
            safety_margin=data.safety_margin,
            risks=[
                "Taxa de retirada, inflação e retornos são hipóteses e podem mudar."
            ],
            improvement_actions=[
                "Elevar aportes sustentavelmente, reinvestir proventos e revisar premissas anualmente."
            ],
            confidence="low" if required is None or current is None else "medium",
        )
