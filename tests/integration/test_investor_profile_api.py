from __future__ import annotations

from decimal import Decimal

from app.models.user import User


CORRECT_KNOWLEDGE_ANSWERS = {
    "volatilidade": "b",
    "diversificacao": "a",
    "risco_perda": "c",
    "renda_fixa_x_variavel": "a",
    "marcacao_a_mercado": "b",
}


def full_answers_payload(*, tolerance_choice="manteria", monthly_contribution="1000", restricted_classes=None):
    scenarios = {
        scenario: tolerance_choice
        for scenario in ("queda_20_curto_prazo", "queda_30_prolongada", "volatilidade_mensal")
    }
    return {
        "objectives": {"primary_objective": "crescimento_patrimonial", "secondary_objectives": []},
        "horizon": {"horizon": "5_a_10_anos"},
        "contribution": {"monthly_contribution": monthly_contribution, "contribution_stability": "fixo"},
        "financial_situation": {
            "emergency_reserve_months": 6,
            "has_relevant_debt": False,
            "dependents": 0,
        },
        "liquidity": {"liquidity_need": "moderada"},
        "income_need": {"income_need": "complemento"},
        "knowledge": {"answers": CORRECT_KNOWLEDGE_ANSWERS},
        "risk_tolerance": {"scenarios": scenarios},
        "restrictions": {"restricted_classes": restricted_classes or []},
    }


def second_user(db_session) -> User:
    user = User(
        name="Second User",
        email="second@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# --- status / novo usuário --------------------------------------------------


def test_new_user_needs_onboarding(client):
    response = client.get("/investor-profile/status")
    assert response.status_code == 200
    assert response.json()["status"] == "needs_onboarding"


def test_get_profile_creates_baseline_needs_onboarding_profile(client):
    response = client.get("/investor-profile")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_onboarding"
    assert body["dimensions"] is None


# --- salvar progresso --------------------------------------------------------


def test_save_partial_answers_moves_status_to_in_progress(client):
    response = client.put(
        "/investor-profile/answers",
        json={"objectives": {"primary_objective": "aposentadoria", "secondary_objectives": []}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["primary_objective"] == "aposentadoria"


def test_answers_persist_across_multiple_partial_saves(client):
    client.put(
        "/investor-profile/answers",
        json={"objectives": {"primary_objective": "renda_passiva", "secondary_objectives": []}},
    )
    client.put(
        "/investor-profile/answers",
        json={"horizon": {"horizon": "mais_10_anos"}},
    )
    response = client.get("/investor-profile")
    body = response.json()
    assert body["primary_objective"] == "renda_passiva"
    assert body["horizon"] == "mais_10_anos"


def test_save_answers_rejects_unexpected_fields(client):
    response = client.put(
        "/investor-profile/answers",
        json={"objectives": {"primary_objective": "aposentadoria"}, "user_id": "hacked-id"},
    )
    assert response.status_code == 422


def test_save_answers_rejects_invalid_enum_value(client):
    response = client.put(
        "/investor-profile/answers",
        json={"horizon": {"horizon": "para_sempre"}},
    )
    assert response.status_code == 422


# --- evaluate ----------------------------------------------------------------


def test_evaluate_fails_with_missing_sections(client):
    client.put("/investor-profile/answers", json={"objectives": {"primary_objective": "aposentadoria"}})
    response = client.post("/investor-profile/evaluate")
    assert response.status_code == 422
    assert "risk_tolerance" in response.text or "knowledge" in response.text


def test_evaluate_succeeds_after_all_sections_answered(client):
    client.put("/investor-profile/answers", json=full_answers_payload())
    response = client.post("/investor-profile/evaluate")
    assert response.status_code == 200
    body = response.json()
    assert body["dimensions"]["overall_classification"]
    assert len(body["explanations"]) >= 7
    total = sum(Decimal(item["target_percentage"]) for item in body["policy_preview"]["allocations"])
    assert total == Decimal("100.00")

    status_response = client.get("/investor-profile/status")
    assert status_response.json()["status"] == "pending_confirmation"


def test_evaluate_is_deterministic(client):
    client.put("/investor-profile/answers", json=full_answers_payload())
    first = client.post("/investor-profile/evaluate").json()
    second = client.post("/investor-profile/evaluate").json()
    assert first["dimensions"] == second["dimensions"]
    assert first["policy_preview"] == second["policy_preview"]


def test_evaluate_respects_restricted_classes(client):
    client.put(
        "/investor-profile/answers",
        json=full_answers_payload(restricted_classes=["Criptomoedas", "BDRs"]),
    )
    body = client.post("/investor-profile/evaluate").json()
    classes = {item["asset_class"] for item in body["policy_preview"]["allocations"]}
    assert classes.isdisjoint({"Criptomoedas", "BDRs"})


# --- confirm -------------------------------------------------------------


def test_confirm_without_evaluation_fails(client):
    response = client.post("/investor-profile/confirm")
    assert response.status_code == 400


def test_confirm_creates_portfolio_policy_and_marks_complete(client):
    client.put("/investor-profile/answers", json=full_answers_payload())
    client.post("/investor-profile/evaluate")

    response = client.post("/investor-profile/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert response.json()["confirmed_at"] is not None

    policy = client.get("/intelligence/policy")
    assert policy.status_code == 200
    assert policy.json() is not None
    assert policy.json()["name"] == "Política proposta pelo onboarding"
    total = sum(
        Decimal(item["target_percentage"])
        for item in policy.json()["allocations"]
        if item["enabled"]
    )
    assert total == Decimal("100.00")


def test_confirm_never_creates_a_second_policy(client, db_session):
    from app.models.portfolio_policy import PortfolioPolicy

    client.put("/investor-profile/answers", json=full_answers_payload())
    client.post("/investor-profile/evaluate")
    client.post("/investor-profile/confirm")

    client.post("/investor-profile/review")
    client.put("/investor-profile/answers", json=full_answers_payload(tolerance_choice="compraria_mais"))
    client.post("/investor-profile/evaluate")
    client.post("/investor-profile/confirm")

    db_session.expire_all()
    count = db_session.query(PortfolioPolicy).count()
    assert count == 1


def test_confirmed_policy_still_satisfies_existing_policy_validator(client):
    """Regressão: a política derivada precisa continuar válida perante as
    regras já existentes de PortfolioPolicyUpsert (soma==100, sem classes
    duplicadas, min<=target<=max)."""
    client.put("/investor-profile/answers", json=full_answers_payload())
    client.post("/investor-profile/evaluate")
    confirm_response = client.post("/investor-profile/confirm")
    assert confirm_response.status_code == 200

    policy = client.get("/intelligence/policy").json()
    classes = [item["asset_class"] for item in policy["allocations"]]
    assert len(classes) == len(set(classes))
    for item in policy["allocations"]:
        assert Decimal(item["minimum_percentage"]) <= Decimal(item["target_percentage"])
        assert Decimal(item["target_percentage"]) <= Decimal(item["maximum_percentage"])


# --- review --------------------------------------------------------------


def test_review_without_profile_fails(client):
    response = client.post("/investor-profile/review")
    assert response.status_code == 400


def test_review_reopens_profile_and_preserves_answers(client):
    client.put("/investor-profile/answers", json=full_answers_payload())
    client.post("/investor-profile/evaluate")
    client.post("/investor-profile/confirm")

    response = client.post("/investor-profile/review")
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    # respostas preservadas (pré-preenchidas para o wizard reabrir).
    assert response.json()["primary_objective"] == "crescimento_patrimonial"

    status_response = client.get("/investor-profile/status")
    assert status_response.json()["status"] == "in_progress"


# --- isolamento entre usuários -----------------------------------------------


def test_investor_profile_is_isolated_between_users(client, db_session):
    from app.api.deps import get_current_active_user
    from app.main import app

    client.put("/investor-profile/answers", json=full_answers_payload())
    client.post("/investor-profile/evaluate")
    client.post("/investor-profile/confirm")

    user_b = second_user(db_session)

    def override_user_b():
        return user_b

    app.dependency_overrides[get_current_active_user] = override_user_b
    try:
        status_b = client.get("/investor-profile/status")
        assert status_b.json()["status"] == "needs_onboarding"

        profile_b = client.get("/investor-profile")
        assert profile_b.json()["primary_objective"] is None
        assert profile_b.json()["dimensions"] is None

        confirm_b = client.post("/investor-profile/confirm")
        assert confirm_b.status_code == 400
    finally:
        from app.models.user import User as UserModel

        active_user = (
            db_session.query(UserModel).filter(UserModel.email == "test@example.com").first()
        )
        app.dependency_overrides[get_current_active_user] = lambda: active_user


def test_user_cannot_confirm_another_users_pending_evaluation(client, db_session):
    """Garante que confirm() de um usuário nunca opera sobre o
    InvestorProfile de outro, mesmo que ambos estejam pending_confirmation
    simultaneamente."""
    from app.api.deps import get_current_active_user
    from app.main import app
    from app.models.user import User as UserModel

    client.put("/investor-profile/answers", json=full_answers_payload(tolerance_choice="venderia_tudo"))
    client.post("/investor-profile/evaluate")

    user_b = second_user(db_session)

    def override_user_b():
        return user_b

    app.dependency_overrides[get_current_active_user] = override_user_b
    try:
        client.put("/investor-profile/answers", json=full_answers_payload(tolerance_choice="compraria_mais"))
        eval_b = client.post("/investor-profile/evaluate").json()
        confirm_b = client.post("/investor-profile/confirm")
        assert confirm_b.status_code == 200
        assert confirm_b.json()["dimensions"]["overall_classification"] == eval_b["dimensions"]["overall_classification"]
    finally:
        active_user = (
            db_session.query(UserModel).filter(UserModel.email == "test@example.com").first()
        )
        app.dependency_overrides[get_current_active_user] = lambda: active_user

    profile_a = client.get("/investor-profile").json()
    assert profile_a["status"] == "pending_confirmation"


# --- pré-preenchimento a partir de PortfolioPolicy legada --------------------


def test_existing_user_with_legacy_policy_gets_prefill_not_fabricated_scores(client):
    legacy_policy_payload = {
        "name": "Minha estratégia",
        "objective": "crescimento patrimonial",
        "risk_profile": "moderado",
        "investment_horizon": "longo prazo",
        "monthly_contribution": "800",
        "liquidity_need": "média",
        "income_need": False,
        "emergency_reserve_months": 5,
        "maximum_weight_per_asset": "20",
        "maximum_weight_per_sector": "30",
        "maximum_weight_per_issuer": "30",
        "rebalance_tolerance": "5",
        "allocations": [
            {
                "asset_class": "Ações",
                "target_percentage": "60",
                "minimum_percentage": "50",
                "maximum_percentage": "70",
                "enabled": True,
            },
            {
                "asset_class": "Tesouro Direto",
                "target_percentage": "40",
                "minimum_percentage": "30",
                "maximum_percentage": "50",
                "enabled": True,
            },
        ],
    }
    put_response = client.put("/intelligence/policy", json=legacy_policy_payload)
    assert put_response.status_code == 200

    profile = client.get("/investor-profile").json()
    assert profile["status"] == "needs_onboarding"
    # fatos estruturais comprovadamente equivalentes foram pré-preenchidos...
    assert profile["primary_objective"] == "crescimento_patrimonial"
    assert profile["horizon"] == "mais_10_anos"
    assert Decimal(profile["monthly_contribution"]) == Decimal("800")
    # ...mas nenhuma dimensão multidimensional foi fabricada a partir do
    # risk_profile textual antigo.
    assert profile["dimensions"] is None


# --- aporte mensal -----------------------------------------------------------


def test_monthly_contribution_zero_is_valid(client):
    client.put("/investor-profile/answers", json=full_answers_payload(monthly_contribution="0"))
    response = client.post("/investor-profile/evaluate")
    assert response.status_code == 200
    assert Decimal(response.json()["policy_preview"]["monthly_contribution"]) == Decimal("0")
