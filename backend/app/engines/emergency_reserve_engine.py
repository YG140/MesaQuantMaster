"""Plano de reserva de emergência: cálculo puro, sem compras ou mutações.

Depende de despesa essencial REAL informada pelo usuário, não de faixas de
renda, tamanho da carteira nem expectativa de rentabilidade.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from app.schemas.emergency_reserve import (
    EmergencyReservePlanRequest, EmergencyReservePlanResponse, ReserveBucket,
)

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def suggested_reserve_months(*, base_months: int, unstable_income: bool, dependents: int) -> int:
    """Mesma lógica de proteção do FinancialDiagnosisEngine, sem inventar saldo."""
    return min(18, max(1, base_months) + (3 if unstable_income else 0) + (1 if dependents else 0))


class EmergencyReserveEngine:
    @staticmethod
    def build(
        data: EmergencyReservePlanRequest,
        *,
        base_months: int = 6,
        unstable_income: bool = False,
        dependents: int = 0,
        has_relevant_debt: bool = False,
        policy_confirmed: bool = False,
    ) -> EmergencyReservePlanResponse:
        months = suggested_reserve_months(
            base_months=base_months,
            unstable_income=unstable_income,
            dependents=dependents,
        )
        expenses = data.essential_monthly_expenses
        saved = data.current_reserve
        available = data.monthly_available
        target = (expenses * months).quantize(CENT, rounding=ROUND_HALF_UP)
        gap = max(Decimal("0"), target - saved).quantize(CENT)
        covered = (saved / expenses).quantize(CENT)
        progress = min(HUNDRED, saved / target * HUNDRED).quantize(CENT)
        # Simulação de direcionamento do próximo aporte, sem transferências.
        reserve_from_next_month = min(available, gap).quantize(CENT)
        remaining_for_other_goals = (available - reserve_from_next_month).quantize(CENT)
        time_needed = (
            int((gap / available).to_integral_value(rounding=ROUND_CEILING))
            if gap > 0 and available > 0
            else (0 if gap == 0 else None)
        )
        # Objetivos de alocação, NÃO comprovante de que o valor já guardado
        # se encontra nos instrumentos sugeridos. Prioriza 1-2 meses
        # realmente disponíveis em caso de imprevisto.
        immediate_months = min(months, 2 if (unstable_income or dependents > 0) else 1)
        immediate_target = (expenses * immediate_months).quantize(CENT)
        liquid_target = (target - immediate_target).quantize(CENT)
        notes = [
            "Plano hipotético, sem movimentação de dinheiro ou alteração da carteira.",
            "Valor guardado informado manualmente: não é saldo bancário comprovado ou sincronizado.",
            "O orçamento do próximo mês é uma sugestão, não uma ordem automática.",
            "Priorizar segurança, baixo risco e acesso ao dinheiro; não usar ações, FIIs ou cripto como reserva.",
            "Verificar prazos reais de resgate, garantias, tributação e condições de cada instituição.",
        ]
        if has_relevant_debt:
            notes.append(
                "Perfil sinaliza dívida relevante: rever o custo efetivo da dívida e a prioridade dos aportes "
                "antes de direcionar eventual sobra a investimentos de risco."
            )
        if not policy_confirmed:
            notes.append(
                "Meta baseada em referência inicial de 6 meses; confirme o Perfil do Investidor para personalizar."
            )
        return EmergencyReservePlanResponse(
            status="complete" if gap == 0 else ("planned" if available > 0 else "awaiting_contribution"),
            basis="confirmed_profile_policy" if policy_confirmed else "initial_reference",
            essential_monthly_expenses=expenses,
            target_months=months,
            target_amount=target,
            current_reserve=saved,
            months_covered=covered,
            progress_percentage=progress,
            shortfall=gap,
            monthly_available=available,
            suggested_next_reserve_contribution=reserve_from_next_month,
            remaining_next_contribution=remaining_for_other_goals,
            estimated_months_to_goal=time_needed,
            allocation_targets=[
                ReserveBucket(
                    label="Acesso imediato",
                    target_amount=immediate_target,
                    suggested_months=immediate_months,
                    description=(
                        "Conta remunerada ou aplicação de risco baixo com resgate efetivamente imediato "
                        "e sem carência; conferir regras e proteção aplicável."
                    ),
                ),
                ReserveBucket(
                    label="Reserva complementar",
                    target_amount=liquid_target,
                    suggested_months=months - immediate_months,
                    description=(
                        "Liquidez diária em instituição confiável ou Tesouro Selic; "
                        "o Tesouro não garante disponibilidade instantânea ou preço fixo antes do vencimento."
                    ),
                ),
            ],
            has_relevant_debt=has_relevant_debt,
            warnings=notes,
        )
