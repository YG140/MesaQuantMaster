from app.core.config import settings
from app.models.asset import Asset


def test_oversized_json_rejected_before_endpoint(client, db_session):
    payload = (
        b"{" + b'"padding":"' + b"x" * (settings.MAX_REQUEST_BODY_BYTES + 1) + b'"}'
    )
    response = client.post(
        "/assets", content=payload, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert db_session.query(Asset).count() == 0


def test_get_remains_normal(client):
    assert client.get("/assets").status_code == 200


def test_login_form_remains_normal(unauthenticated_client):
    assert (
        unauthenticated_client.post(
            "/auth/login", data={"username": "missing@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
