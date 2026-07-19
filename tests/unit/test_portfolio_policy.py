from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.portfolio_policy import PortfolioPolicy, PortfolioPolicyAllocation
from app.models.user import User
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.schemas.intelligence import (
    PortfolioPolicyAllocationBase,
    PortfolioPolicyUpsert,
)


def policy_payload(
    *,
    target_a: Decimal = Decimal("60"),
    target_b: Decimal = Decimal("40"),
    minimum_a: Decimal = Decimal("50"),
    maximum_a: Decimal = Decimal("70"),
) -> PortfolioPolicyUpsert:
    return PortfolioPolicyUpsert(
        name="Minha estratégia",
        objective="crescimento patrimonial",
        risk_profile="moderado",
        investment_horizon="longo prazo",
        monthly_contribution=Decimal("900"),
        liquidity_need="média",
        income_need=False,
        emergency_reserve_months=6,
        maximum_weight_per_asset=Decimal("20"),
        maximum_weight_per_sector=Decimal("30"),
        maximum_weight_per_issuer=Decimal("30"),
        rebalance_tolerance=Decimal("5"),
        allocations=[
            PortfolioPolicyAllocationBase(
                asset_class="Ações",
                target_percentage=target_a,
                minimum_percentage=minimum_a,
                maximum_percentage=maximum_a,
                enabled=True,
            ),
            PortfolioPolicyAllocationBase(
                asset_class="Tesouro Direto",
                target_percentage=target_b,
                minimum_percentage=Decimal("30"),
                maximum_percentage=Decimal("50"),
                enabled=True,
            ),
        ],
    )


def test_policy_accepts_valid_total_100():
    payload = policy_payload()

    assert sum(
        item.target_percentage for item in payload.allocations if item.enabled
    ) == Decimal("100")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"target_a": Decimal("50"), "target_b": Decimal("40")}, "exatamente 100"),
        (
            {"target_a": Decimal("-1"), "target_b": Decimal("101")},
            "não podem ser negativos",
        ),
        ({"minimum_a": Decimal("80")}, "mínimo não pode ser maior"),
        ({"maximum_a": Decimal("55")}, "alvo não pode ser maior"),
    ],
)
def test_policy_rejects_invalid_percentages(kwargs, message):
    with pytest.raises(ValidationError) as exc:
        policy_payload(**kwargs)

    assert message in str(exc.value)


def test_policy_rejects_duplicate_asset_classes():
    with pytest.raises(ValidationError) as exc:
        PortfolioPolicyUpsert(
            name="Minha estratÃ©gia",
            objective="crescimento patrimonial",
            risk_profile="moderado",
            investment_horizon="longo prazo",
            monthly_contribution=Decimal("900"),
            liquidity_need="mÃ©dia",
            income_need=False,
            emergency_reserve_months=6,
            maximum_weight_per_asset=Decimal("20"),
            maximum_weight_per_sector=Decimal("30"),
            maximum_weight_per_issuer=Decimal("30"),
            rebalance_tolerance=Decimal("5"),
            allocations=[
                PortfolioPolicyAllocationBase(
                    asset_class="AÃ§Ãµes",
                    target_percentage=Decimal("100"),
                    minimum_percentage=Decimal("0"),
                    maximum_percentage=Decimal("100"),
                    enabled=True,
                ),
                PortfolioPolicyAllocationBase(
                    asset_class="AÃ§Ãµes",
                    target_percentage=Decimal("0"),
                    minimum_percentage=Decimal("0"),
                    maximum_percentage=Decimal("0"),
                    enabled=False,
                ),
            ],
        )

    assert "Classes duplicadas" in str(exc.value)


def test_policy_repository_isolates_users(db_session, active_user):
    other = User(
        name="Other User",
        email="other@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    repository = PortfolioPolicyRepository(db_session)
    policy = PortfolioPolicy(
        user_id=active_user.id,
        name="Minha estratégia",
        objective="crescimento patrimonial",
        risk_profile="moderado",
        investment_horizon="longo prazo",
        monthly_contribution=Decimal("900"),
        liquidity_need="média",
        income_need=False,
        emergency_reserve_months=6,
        maximum_weight_per_asset=Decimal("20"),
        maximum_weight_per_sector=Decimal("30"),
        maximum_weight_per_issuer=Decimal("30"),
        rebalance_tolerance=Decimal("5"),
    )
    saved = repository.save(policy)
    repository.replace_allocations(
        saved,
        [
            PortfolioPolicyAllocation(
                asset_class="Ações",
                target_percentage=Decimal("100"),
                minimum_percentage=Decimal("0"),
                maximum_percentage=Decimal("100"),
                enabled=True,
            )
        ],
    )

    assert repository.get_by_user(active_user.id) is not None
    assert repository.get_by_user(other.id) is None


def test_policy_repository_replaces_allocations_without_duplicates(
    db_session, active_user
):
    repository = PortfolioPolicyRepository(db_session)
    policy = PortfolioPolicy(
        user_id=active_user.id,
        name="Minha estratÃ©gia",
        objective="crescimento patrimonial",
        risk_profile="moderado",
        investment_horizon="longo prazo",
        monthly_contribution=Decimal("900"),
        liquidity_need="mÃ©dia",
        income_need=False,
        emergency_reserve_months=6,
        maximum_weight_per_asset=Decimal("20"),
        maximum_weight_per_sector=Decimal("30"),
        maximum_weight_per_issuer=Decimal("30"),
        rebalance_tolerance=Decimal("5"),
    )
    saved = repository.save(policy)

    repository.replace_allocations(
        saved,
        [
            PortfolioPolicyAllocation(
                asset_class="AÃ§Ãµes",
                target_percentage=Decimal("60"),
                minimum_percentage=Decimal("50"),
                maximum_percentage=Decimal("70"),
                enabled=True,
            ),
            PortfolioPolicyAllocation(
                asset_class="Tesouro Direto",
                target_percentage=Decimal("40"),
                minimum_percentage=Decimal("30"),
                maximum_percentage=Decimal("50"),
                enabled=True,
            ),
        ],
    )
    updated = repository.replace_allocations(
        saved,
        [
            PortfolioPolicyAllocation(
                asset_class="AÃ§Ãµes",
                target_percentage=Decimal("55"),
                minimum_percentage=Decimal("45"),
                maximum_percentage=Decimal("65"),
                enabled=True,
            ),
            PortfolioPolicyAllocation(
                asset_class="Caixa",
                target_percentage=Decimal("45"),
                minimum_percentage=Decimal("35"),
                maximum_percentage=Decimal("55"),
                enabled=True,
            ),
        ],
    )

    policy_count = db_session.scalar(
        select(func.count())
        .select_from(PortfolioPolicy)
        .where(PortfolioPolicy.user_id == active_user.id)
    )
    allocation_count = db_session.scalar(
        select(func.count())
        .select_from(PortfolioPolicyAllocation)
        .where(PortfolioPolicyAllocation.policy_id == saved.id)
    )

    assert policy_count == 1
    assert allocation_count == 2
    assert [item.asset_class for item in updated.allocations] == ["AÃ§Ãµes", "Caixa"]
