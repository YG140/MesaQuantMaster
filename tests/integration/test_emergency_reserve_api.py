"""O plano da reserva é privado, só preview, sem gravar operações."""
from decimal import Decimal

from app.models.investor_profile import InvestorProfile
from app.models.portfolio_policy import PortfolioPolicy
from app.models.operation import Operation
from app.models.user import User
from app.api.deps import get_current_active_user
from app.main import app


def payload(**updates):
    values = {
        "essential_monthly_expenses": "3500",
        "current_reserve": "4000",
        "monthly_available": "1000",
        "income_unstable": False,
    }
    values.update(updates)
    return values


def test_reserve_preview_without_profile_is_provisional_and_read_only(client, db_session):
    before_ops = db_session.query(Operation).count()
    before_profiles = db_session.query(InvestorProfile).count()
    result = client.post("/intelligence/emergency-reserve/plan", json=payload())
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["basis"] == "initial_reference"
    assert data["target_amount"] == "21000.00"
    assert data["shortfall"] == "17000.00"
    assert data["estimated_months_to_goal"] == 17
    assert [asset["asset_type"] for asset in data["asset_allocations"]] == [
        "renda_fixa_bancaria", "titulo_publico_pos_fixado",
    ]
    assert sum(
        (Decimal(asset["next_contribution_amount"]) for asset in data["asset_allocations"]),
        Decimal("0"),
    ) == Decimal("1000.00")
    assert all(
        asset["selection_status"] == "categoria_sem_produto_validado"
        for asset in data["asset_allocations"]
    )
    assert db_session.query(Operation).count() == before_ops
    assert db_session.query(InvestorProfile).count() == before_profiles


def test_complete_profile_changes_months_without_asking_for_advanced_limits(
    client, db_session, active_user
):
    profile = InvestorProfile(
        user_id=active_user.id, status="complete", dependents=2,
        has_relevant_debt=True,
    )
    policy = PortfolioPolicy(
        user_id=active_user.id, name="Plano", objective="crescimento",
        risk_profile="moderado", investment_horizon="longo prazo",
        monthly_contribution=Decimal("3000"), liquidity_need="alta",
        income_need=False, emergency_reserve_months=8,
        maximum_weight_per_asset=Decimal("20"),
        maximum_weight_per_sector=Decimal("30"),
        maximum_weight_per_issuer=Decimal("30"),
        rebalance_tolerance=Decimal("5"),
    )
    db_session.add_all([profile, policy])
    db_session.commit()
    result = client.post(
        "/intelligence/emergency-reserve/plan",
        json=payload(income_unstable=True),
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["basis"] == "confirmed_profile_policy"
    assert body["target_months"] == 12  # 8 policy + 3 unstable income + 1 dependents
    assert body["target_amount"] == "42000.00"
    assert body["has_relevant_debt"] is True
    assert body["allocation_targets"][0]["suggested_months"] == 2
    assert db_session.query(Operation).count() == 0


def test_reserve_inputs_are_validated_and_do_not_accept_mass_assignment(client):
    for change in [
        {"essential_monthly_expenses": "0"},
        {"current_reserve": "-5"},
        {"monthly_available": "not-a-number"},
        {"user_id": "not-allowed"},
    ]:
        response = client.post(
            "/intelligence/emergency-reserve/plan",
            json=payload(**change),
        )
        assert response.status_code == 422


def test_reserve_uses_authenticated_user_not_any_other_profile(
    client, db_session, active_user
):
    other = User(
        name="Segunda pessoa", email="other-reserve@example.com",
        hashed_password="test", is_active=True,
    )
    db_session.add(other)
    db_session.commit()
    db_session.add(InvestorProfile(
        user_id=other.id, status="complete", dependents=4,
        has_relevant_debt=True,
    ))
    db_session.commit()
    result = client.post("/intelligence/emergency-reserve/plan", json=payload())
    assert result.status_code == 200
    assert result.json()["target_months"] == 6
    assert result.json()["has_relevant_debt"] is False
