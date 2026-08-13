from decimal import Decimal

from app.models.indicator_snapshot import IndicatorSnapshot


def policy_payload(target_a="60", target_b="40"):
    return {
        "name": "Minha estratégia",
        "objective": "crescimento patrimonial",
        "risk_profile": "moderado",
        "investment_horizon": "longo prazo",
        "monthly_contribution": "900",
        "liquidity_need": "média",
        "income_need": False,
        "emergency_reserve_months": 6,
        "maximum_weight_per_asset": "20",
        "maximum_weight_per_sector": "30",
        "maximum_weight_per_issuer": "30",
        "rebalance_tolerance": "5",
        "allocations": [
            {
                "asset_class": "Ações",
                "target_percentage": target_a,
                "minimum_percentage": "50",
                "maximum_percentage": "70",
                "enabled": True,
            },
            {
                "asset_class": "Tesouro Direto",
                "target_percentage": target_b,
                "minimum_percentage": "30",
                "maximum_percentage": "50",
                "enabled": True,
            },
        ],
    }


def test_get_policy_returns_null_without_saved_policy(client):
    response = client.get("/intelligence/policy")

    assert response.status_code == 200
    assert response.json() is None


def test_put_policy_persists_and_intelligence_uses_it(client):
    saved = client.put("/intelligence/policy", json=policy_payload())

    assert saved.status_code == 200
    assert saved.json()["allocations"][0]["target_percentage"] == "60.00"

    loaded = client.get("/intelligence/policy")
    assert loaded.status_code == 200
    assert loaded.json()["name"] == "Minha estratégia"

    intelligence = client.get("/intelligence/portfolio")
    assert intelligence.status_code == 200
    assert intelligence.json()["policy"]["name"] == "Minha estratégia"


def test_policy_rejects_invalid_total(client):
    response = client.put("/intelligence/policy", json=policy_payload("50", "40"))

    assert response.status_code == 422
    assert "100" in response.text


def test_build_portfolio_uses_policy_percentages(client, db_session):
    snapshots_before = db_session.query(IndicatorSnapshot).count()
    client.put("/intelligence/policy", json=policy_payload())

    response = client.post(
        "/intelligence/build-portfolio",
        json={
            "available_amount": "10000",
            "objective": "crescimento patrimonial",
            "horizon": "longo prazo",
            "risk_profile": "moderado",
            "allowed_classes": ["Ações", "Tesouro Direto"],
        },
    )

    assert response.status_code == 200
    by_class = {
        item["asset_class"]: Decimal(item["amount"])
        for item in response.json()["class_allocations"]
    }
    assert by_class == {
        "Ações": Decimal("6000.00"),
        "Tesouro Direto": Decimal("4000.00"),
    }
    db_session.expire_all()
    assert db_session.query(IndicatorSnapshot).count() == snapshots_before
