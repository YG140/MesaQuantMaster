"""Regressões da montagem de reserva, com valores sintéticos."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.engines.emergency_reserve_engine import EmergencyReserveEngine
from app.schemas.emergency_reserve import EmergencyReservePlanRequest


def request(**changes):
    payload = {
        "essential_monthly_expenses": Decimal("3500"),
        "current_reserve": Decimal("4000"),
        "monthly_available": Decimal("1000"),
    }
    payload.update(changes)
    return EmergencyReservePlanRequest(**payload)


def test_basic_reserve_target_liquidity_split_and_time_without_returns():
    result = EmergencyReserveEngine.build(request(), policy_confirmed=True)
    assert result.basis == "confirmed_profile_policy"
    assert result.target_months == 6
    assert result.target_amount == Decimal("21000.00")
    assert result.shortfall == Decimal("17000.00")
    assert result.estimated_months_to_goal == 17
    assert result.suggested_next_reserve_contribution == Decimal("1000.00")
    assert result.remaining_next_contribution == Decimal("0.00")
    assert result.allocation_targets[0].target_amount == Decimal("3500.00")
    assert result.allocation_targets[1].target_amount == Decimal("17500.00")
    assert sum((x.target_amount for x in result.allocation_targets), Decimal("0")) == result.target_amount
    assert result.status == "planned"


def test_unstable_income_dependents_adjust_safety_and_instant_liquidity():
    result = EmergencyReserveEngine.build(
        request(), base_months=6, unstable_income=True, dependents=2,
        policy_confirmed=True,
    )
    assert result.target_months == 10
    assert result.target_amount == Decimal("35000.00")
    assert result.allocation_targets[0].target_amount == Decimal("7000.00")


def test_reserve_fully_funded_does_not_redirect_existing_money():
    result = EmergencyReserveEngine.build(
        request(current_reserve=Decimal("28000"), monthly_available=Decimal("3000")),
        policy_confirmed=True,
    )
    assert result.status == "complete"
    assert result.shortfall == Decimal("0.00")
    assert result.estimated_months_to_goal == 0
    assert result.progress_percentage == Decimal("100.00")
    assert result.suggested_next_reserve_contribution == Decimal("0.00")
    assert result.remaining_next_contribution == Decimal("3000.00")


def test_small_remaining_gap_leaves_surplus_without_autoinvestment():
    result = EmergencyReserveEngine.build(request(
        current_reserve=Decimal("20500"), monthly_available=Decimal("3000"),
    ))
    assert result.suggested_next_reserve_contribution == Decimal("500.00")
    assert result.remaining_next_contribution == Decimal("2500.00")
    assert result.shortfall == Decimal("500.00")
    assert result.estimated_months_to_goal == 1


def test_zero_monthly_amount_does_not_invent_deadline_or_fund_returns():
    result = EmergencyReserveEngine.build(request(monthly_available=Decimal("0")))
    assert result.status == "awaiting_contribution"
    assert result.estimated_months_to_goal is None
    assert result.suggested_next_reserve_contribution == Decimal("0")
    assert result.remaining_next_contribution == Decimal("0.00")


def test_debt_warns_without_auto_changing_user_position():
    result = EmergencyReserveEngine.build(
        request(), has_relevant_debt=True, policy_confirmed=True
    )
    assert result.has_relevant_debt is True
    assert any("dívida relevante" in warning for warning in result.warnings)
    assert result.suggested_next_reserve_contribution == Decimal("1000.00")


def test_no_profile_uses_identified_provisional_base():
    result = EmergencyReserveEngine.build(request())
    assert result.basis == "initial_reference"
    assert any("referência inicial" in warning for warning in result.warnings)


def test_months_are_bounded_even_with_unusually_long_policy():
    result = EmergencyReserveEngine.build(
        request(), base_months=30, unstable_income=True, dependents=10,
    )
    assert result.target_months == 18


@pytest.mark.parametrize("changes", [
    {"essential_monthly_expenses": "0"},
    {"essential_monthly_expenses": "-1"},
    {"current_reserve": "-3"},
    {"monthly_available": "-200"},
    {"monthly_available": "Infinity"},
    {"current_reserve": "NaN"},
])
def test_invalid_money_is_rejected_before_any_calculation(changes):
    with pytest.raises(ValidationError):
        request(**changes)
