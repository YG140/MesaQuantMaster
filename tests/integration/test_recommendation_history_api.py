"""Histórico de recomendações: isolamento, evidências e integridade.

Dados financeiros e usuários dos testes são sintéticos.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.api.deps import get_current_active_user
from app.main import app
from app.models.portfolio_recommendation_run import PortfolioRecommendationRun
from app.models.user import User
from app.repositories.portfolio_recommendation_history_repository import (
    PortfolioRecommendationHistoryRepository,
)
from app.engines.smart_portfolio_engine import SmartPortfolioEngine
from app.schemas.intelligence import (
    BuildPortfolioAsset,
    BuildPortfolioIndicator,
    BuildPortfolioRequest,
)

NOW = datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)


def request_payload(**changes):
    values = {
        "available_amount": "10000",
        "objective": "crescimento",
        "horizon": "longo prazo",
        "risk_profile": "moderado",
        "net_monthly_income": "987654.32",
        "high_cost_debt": "34567.89",
    }
    values.update(changes)
    return values


def test_every_explicit_portfolio_build_creates_a_private_immutable_decision(client, db_session, active_user):
    first = client.post("/intelligence/build-portfolio", json=request_payload())
    assert first.status_code == 200, first.text
    first_id = UUID(first.json()["history_id"])

    second = client.post("/intelligence/build-portfolio", json=request_payload())
    assert second.status_code == 200, second.text
    second_id = UUID(second.json()["history_id"])
    assert second_id != first_id

    listing = client.get("/intelligence/recommendation-history")
    assert listing.status_code == 200
    records = listing.json()
    assert {x["id"] for x in records} == {str(first_id), str(second_id)}
    assert all(x["content_sha256"] and len(x["content_sha256"]) == 64 for x in records)

    detail = client.get(f"/intelligence/recommendation-history/{first_id}")
    assert detail.status_code == 200, detail.text
    result = detail.json()
    assert result["integrity_verified"] is True
    assert result["record"]["validation_status"] == "recommendation_record_only"
    assert result["record"]["totals"]["unallocated"] == first.json()["unallocated_amount"]
    assert datetime.fromisoformat(result["record"]["generated_at"]) == datetime.fromisoformat(first.json()["generated_at"])
    assert result["record"]["status"] == first.json()["status"]
    assert result["record"]["assets"] == []
    assert result["record"]["schema_version"] == 1
    assert "987654.32" not in str(result)
    assert "34567.89" not in str(result)

    rows = db_session.query(PortfolioRecommendationRun).all()
    assert len(rows) == 2
    assert all(row.user_id == active_user.id for row in rows)


def test_other_user_cannot_list_or_read_another_users_portfolio_history(client, db_session, active_user):
    result = client.post("/intelligence/build-portfolio", json=request_payload())
    run_id = result.json()["history_id"]
    stranger = User(
        name="Outro investidor",
        email="stranger@example.com",
        hashed_password="synthetic",
        is_active=True,
    )
    db_session.add(stranger)
    db_session.commit()
    db_session.refresh(stranger)
    app.dependency_overrides[get_current_active_user] = lambda: stranger
    listing = client.get("/intelligence/recommendation-history")
    assert listing.status_code == 200
    assert listing.json() == []
    detail = client.get(f"/intelligence/recommendation-history/{run_id}")
    assert detail.status_code == 404


def test_tampered_saved_record_is_rejected(client, db_session):
    result = client.post("/intelligence/build-portfolio", json=request_payload())
    run_id = result.json()["history_id"]
    item = db_session.query(PortfolioRecommendationRun).filter_by(id=UUID(run_id)).one()
    item.record_json = item.record_json.replace('"status":"unavailable"', '"status":"alterado"')
    if '"status":"alterado"' not in item.record_json:
        item.record_json += " "
    db_session.commit()
    attempt = client.get(f"/intelligence/recommendation-history/{run_id}")
    assert attempt.status_code == 409


def test_decision_preserves_quote_observation_and_indicator_provenance(db_session, active_user):
    req = BuildPortfolioRequest(**request_payload())
    response = SmartPortfolioEngine.build(req, [])
    indicator = BuildPortfolioIndicator(
        key="roe",
        label="ROE",
        value=Decimal("17.5"),
        source="CVM DFP",
        source_type="official",
        reference_date=NOW,
        collected_at=NOW,
        valid_until=NOW,
        freshness_status="fresh",
    )
    chosen = BuildPortfolioAsset(
        symbol="EXEM3", name="Exemplo", asset_class="Ações",
        recommended_percentage=Decimal("20"),
        recommended_amount=Decimal("2000"),
        score=Decimal("85"),
        indicators_used=[indicator],
        confidence="high",
        quote_observed_at=NOW,
        reference_price=Decimal("25.75"),
        executable_quantity=Decimal("77"),
        executable_amount=Decimal("1982.75"),
    )
    response = response.model_copy(update={"assets": [chosen]})
    item = PortfolioRecommendationHistoryRepository(db_session).save(
        active_user.id, req, response
    )
    recovered = PortfolioRecommendationHistoryRepository.verify(item)
    recorded = recovered["assets"][0]
    assert recorded["quote_observed_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert recorded["indicators_used"][0]["source"] == "CVM DFP"
    assert recorded["indicators_used"][0]["collected_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert recorded["reference_price"] == "25.75"
    assert recorded["executable_quantity"] == "77"
    assert recovered["request"]["objective"] == "crescimento"
    assert "net_monthly_income" not in recovered["request"]
    assert "high_cost_debt" not in recovered["request"]


def test_pagination_is_bounded_and_invalid_uuid_or_private_id_is_not_exposed(client):
    assert client.get("/intelligence/recommendation-history?limit=101").status_code == 422
    assert client.get("/intelligence/recommendation-history?offset=-1").status_code == 422
    assert client.get("/intelligence/recommendation-history/invalid").status_code == 422
    assert client.get(f"/intelligence/recommendation-history/{uuid4()}").status_code == 404
