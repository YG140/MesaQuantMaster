from datetime import date
from decimal import Decimal

from app.models.operation import Operation
from app.models.portfolio_action_audit import PortfolioActionAudit
from app.models.user import User


def test_patch_operation_recalculates_from_decimal_and_audits(
    client, db_session, asset_factory, operation_factory
):
    asset = asset_factory()
    operation = operation_factory(
        asset, "BUY", date(2026, 7, 1), Decimal("10.12500000"), Decimal("37.12345678")
    )

    response = client.patch(
        f"/operations/{operation.id}",
        json={
            "quantity": "11.12500000",
            "unit_price": "38.12345678",
            "fees": "1.23",
            "taxes": "0.45",
        },
    )

    assert response.status_code == 200
    assert Decimal(response.json()["quantity"]) == Decimal("11.12500000")
    assert Decimal(response.json()["unit_price"]) == Decimal("38.12345678")
    db_session.expire_all()
    saved = db_session.get(Operation, operation.id)
    assert saved.quantity == Decimal("11.12500000")
    audit = db_session.query(PortfolioActionAudit).one()
    assert audit.action == "UPDATE_OPERATION"
    assert '"quantity": "10.12500000"' in audit.before_json
    assert '"quantity": "11.12500000"' in audit.after_json


def test_patch_rejects_invalid_financial_values(
    client, asset_factory, operation_factory
):
    operation = operation_factory(
        asset_factory(), "BUY", date(2026, 7, 1), "10", "37"
    )

    response = client.patch(
        f"/operations/{operation.id}", json={"unit_price": "0"}
    )

    assert response.status_code == 422


def test_operations_of_another_user_are_hidden(
    client, db_session, asset_factory
):
    other = User(
        name="Other",
        email="other@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    asset = asset_factory()
    db_session.add(other)
    db_session.flush()
    operation = Operation(
        user_id=other.id,
        asset_id=asset.id,
        operation_type="BUY",
        operation_date=date(2026, 7, 1),
        quantity=Decimal("2"),
        unit_price=Decimal("20"),
        fees=Decimal("0"),
        taxes=Decimal("0"),
    )
    db_session.add(operation)
    db_session.commit()

    assert client.get(f"/operations/{operation.id}").status_code == 404
    assert client.patch(
        f"/operations/{operation.id}", json={"quantity": "3"}
    ).status_code == 404
    assert client.delete(f"/operations/{operation.id}").status_code == 404


def test_delete_position_is_atomic_and_preserves_global_and_other_user_data(
    client, db_session, active_user, asset_factory, operation_factory
):
    asset = asset_factory()
    first = operation_factory(asset, "BUY", date(2026, 7, 1), "10", "30")
    second = operation_factory(asset, "BUY", date(2026, 7, 2), "5", "31")
    other = User(
        name="Other",
        email="other-delete@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(other)
    db_session.flush()
    other_operation = Operation(
        user_id=other.id,
        asset_id=asset.id,
        operation_type="BUY",
        operation_date=date(2026, 7, 3),
        quantity=Decimal("4"),
        unit_price=Decimal("32"),
        fees=Decimal("0"),
        taxes=Decimal("0"),
    )
    db_session.add(other_operation)
    db_session.commit()
    first_id, second_id, other_operation_id = first.id, second.id, other_operation.id

    response = client.request(
        "DELETE",
        f"/portfolio/positions/{asset.id}",
        json={"ticker": asset.ticker, "expected_operations": 2},
    )

    assert response.status_code == 200
    assert response.json()["operations_deleted"] == 2
    db_session.expire_all()
    assert db_session.get(type(asset), asset.id) is not None
    assert db_session.get(Operation, first_id) is None
    assert db_session.get(Operation, second_id) is None
    assert db_session.get(Operation, other_operation_id) is not None
    audit = db_session.query(PortfolioActionAudit).filter_by(
        user_id=active_user.id, asset_id=asset.id, action="DELETE_POSITION"
    ).one()
    assert audit.operation_count == 2


def test_delete_position_detects_stale_confirmation_and_rolls_back(
    client, db_session, asset_factory, operation_factory
):
    asset = asset_factory()
    operation = operation_factory(asset, "BUY", date(2026, 7, 1), "10", "30")

    response = client.request(
        "DELETE",
        f"/portfolio/positions/{asset.id}",
        json={"ticker": asset.ticker, "expected_operations": 2},
    )

    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(Operation, operation.id) is not None
    assert db_session.query(PortfolioActionAudit).count() == 0


def test_delete_position_twice_returns_not_found(
    client, asset_factory, operation_factory
):
    asset = asset_factory()
    operation_factory(asset, "BUY", date(2026, 7, 1), "10", "30")
    payload = {"ticker": asset.ticker, "expected_operations": 1}

    assert client.request(
        "DELETE", f"/portfolio/positions/{asset.id}", json=payload
    ).status_code == 200
    assert client.request(
        "DELETE", f"/portfolio/positions/{asset.id}", json=payload
    ).status_code == 404


def test_position_mutations_require_authentication(unauthenticated_client):
    response = unauthenticated_client.request(
        "DELETE",
        "/portfolio/positions/11111111-1111-1111-1111-111111111111",
        json={"ticker": "PETR4", "expected_operations": 1},
    )
    assert response.status_code == 401
