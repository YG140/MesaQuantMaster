from datetime import datetime
from decimal import Decimal

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.main import app
from app.models.indicator_snapshot import IndicatorSnapshot
from app.models.manual_indicator import ManualIndicator
from app.models.user import User


def valid_payload(**updates):
    payload = {
        "indicator_key": "pe",
        "value": "8.75",
        "unit": "ratio",
        "reference_date": "2026-01-31",
        "source_description": "Fixture controlada",
        "notes": None,
    }
    payload.update(updates)
    return payload


def test_create_persists_once_and_returns_created_contract(
    client, db_session, asset_factory
):
    asset_factory(ticker="PETR4", asset_type="STOCK")
    snapshots_before = db_session.query(IndicatorSnapshot).count()

    response = client.post(
        "/intelligence/assets/PETR4/manual-indicators",
        json=valid_payload(),
    )

    assert response.status_code == 201, response.text
    assert response.json()["freshness_status"] == "current"
    assert response.json()["value"] == "8.75000000"
    assert response.json()["notes"] is None
    assert datetime.fromisoformat(response.json()["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(response.json()["updated_at"]).tzinfo is not None
    db_session.expire_all()
    assert db_session.query(ManualIndicator).count() == 1
    assert db_session.query(IndicatorSnapshot).count() == snapshots_before


def test_invalid_create_does_not_persist(client, db_session, asset_factory):
    asset_factory(ticker="PETR4", asset_type="STOCK")

    response = client.post(
        "/intelligence/assets/PETR4/manual-indicators",
        json=valid_payload(value="1000000000000001"),
    )

    assert response.status_code == 422
    assert db_session.query(ManualIndicator).count() == 0


def test_repeated_create_reports_duplicate_without_creating_another_row(
    client, db_session, asset_factory
):
    asset_factory(ticker="PETR4", asset_type="STOCK")

    first = client.post(
        "/intelligence/assets/PETR4/manual-indicators", json=valid_payload()
    )
    repeated = client.post(
        "/intelligence/assets/PETR4/manual-indicators", json=valid_payload()
    )

    assert first.status_code == 201
    assert repeated.status_code == 400
    assert db_session.query(ManualIndicator).count() == 1


def test_update_returns_current_status_and_preserves_decimal(
    client, db_session, asset_factory
):
    asset_factory(ticker="PETR4", asset_type="STOCK")
    created = client.post(
        "/intelligence/assets/PETR4/manual-indicators", json=valid_payload()
    )

    response = client.patch(
        f"/intelligence/assets/PETR4/manual-indicators/{created.json()['id']}",
        json={"value": "9.125", "notes": "Atualizado"},
    )

    assert response.status_code == 200, response.text
    assert Decimal(response.json()["value"]) == Decimal("9.125")
    assert response.json()["freshness_status"] == "current"
    db_session.expire_all()
    assert db_session.query(ManualIndicator).one().value == Decimal("9.125")


def test_invalid_update_does_not_leave_partial_change(
    client, db_session, asset_factory
):
    asset_factory(ticker="PETR4", asset_type="STOCK")
    created = client.post(
        "/intelligence/assets/PETR4/manual-indicators", json=valid_payload()
    )

    response = client.patch(
        f"/intelligence/assets/PETR4/manual-indicators/{created.json()['id']}",
        json={"value": "1000000000000001", "notes": "Nao deve persistir"},
    )

    assert response.status_code == 422
    db_session.expire_all()
    item = db_session.query(ManualIndicator).one()
    assert item.value == Decimal("8.75")
    assert item.notes is None


def test_list_returns_current_and_stale_status_for_every_item(client, asset_factory):
    asset_factory(ticker="PETR4", asset_type="STOCK")
    current = client.post(
        "/intelligence/assets/PETR4/manual-indicators", json=valid_payload()
    )
    stale = client.post(
        "/intelligence/assets/PETR4/manual-indicators",
        json=valid_payload(
            indicator_key="roe",
            value="12.5",
            unit="percent",
            reference_date="2024-01-01",
        ),
    )

    response = client.get("/intelligence/assets/PETR4/manual-indicators")

    assert current.status_code == 201
    assert stale.status_code == 201
    assert response.status_code == 200
    by_key = {item["indicator_key"]: item for item in response.json()}
    assert by_key["pe"]["freshness_status"] == "current"
    assert by_key["roe"]["freshness_status"] == "stale"
    assert all("freshness_status" in item for item in response.json())


def test_delete_still_removes_owned_indicator(client, db_session, asset_factory):
    asset_factory(ticker="PETR4", asset_type="STOCK")
    created = client.post(
        "/intelligence/assets/PETR4/manual-indicators", json=valid_payload()
    )

    response = client.delete(
        f"/intelligence/assets/PETR4/manual-indicators/{created.json()['id']}"
    )

    assert response.status_code == 204
    assert db_session.query(ManualIndicator).count() == 0


def test_user_cannot_list_update_or_delete_another_users_indicator(
    client, db_session, active_user, asset_factory
):
    asset = asset_factory(ticker="PETR4", asset_type="STOCK")
    other = User(
        name="Other User",
        email="other-manual@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()
    foreign = ManualIndicator(
        user_id=other.id,
        asset_id=asset.id,
        indicator_key="pe",
        value=Decimal("7.50"),
        unit="ratio",
        reference_date=datetime(2026, 1, 31).date(),
        source_type="manual",
        source_description="Outro usuario",
    )
    db_session.add(foreign)
    db_session.commit()

    listed = client.get("/intelligence/assets/PETR4/manual-indicators")
    updated = client.patch(
        f"/intelligence/assets/PETR4/manual-indicators/{foreign.id}",
        json={"value": "10"},
    )
    deleted = client.delete(
        f"/intelligence/assets/PETR4/manual-indicators/{foreign.id}"
    )

    assert listed.status_code == 200
    assert listed.json() == []
    assert updated.status_code == 404
    assert deleted.status_code == 404
    db_session.expire_all()
    assert db_session.query(ManualIndicator).filter_by(user_id=other.id).count() == 1
    assert active_user.id != other.id


def test_list_is_read_only_and_does_not_commit(
    client, db_session, active_user, asset_factory, monkeypatch
):
    asset_factory(ticker="PETR4", asset_type="STOCK")
    client.post("/intelligence/assets/PETR4/manual-indicators", json=valid_payload())
    commit_calls = 0

    def count_commit(*_args, **_kwargs):
        nonlocal commit_calls
        commit_calls += 1

    def override_get_db():
        yield db_session

    monkeypatch.setattr(db_session, "commit", count_commit)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: active_user
    try:
        response = client.get("/intelligence/assets/PETR4/manual-indicators")
    finally:
        app.dependency_overrides[get_db] = override_get_db

    assert response.status_code == 200
    assert commit_calls == 0
