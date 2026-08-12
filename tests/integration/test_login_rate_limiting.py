import pytest

from app.api.auth import login_rate_limiter
from app.core.security import hash_password
from app.models.user import User


@pytest.fixture(autouse=True)
def clear_limiter():
    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


def login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_five_failures_then_429(unauthenticated_client):
    statuses = [
        login(unauthenticated_client, "missing@example.com", "wrong").status_code
        for _ in range(6)
    ]
    assert statuses == [401, 401, 401, 401, 401, 429]


def test_valid_login_and_public_equivalence(unauthenticated_client, db_session):
    user = User(
        name="Valid",
        email="valid@example.com",
        hashed_password=hash_password("correct-password"),
        is_active=True,
        is_email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    missing = login(unauthenticated_client, "missing@example.com", "wrong")
    wrong = login(unauthenticated_client, "valid@example.com", "wrong")
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()
    assert (
        login(
            unauthenticated_client, "valid@example.com", "correct-password"
        ).status_code
        == 200
    )
