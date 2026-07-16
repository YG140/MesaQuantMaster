import pytest

from utils import session


@pytest.fixture
def fake_state(monkeypatch):
    state = {}
    monkeypatch.setattr(session.st, "session_state", state)
    return state


def test_initialize_session_without_token_keeps_user_unauthenticated(
    fake_state,
) -> None:
    session.initialize_session()

    assert session.is_authenticated() is False
    assert fake_state[session.TOKEN_KEY] is None
    assert fake_state[session.USER_KEY] is None


def test_valid_login_saves_session_without_password(fake_state) -> None:
    session.set_authenticated_session(
        "jwt-token",
        {
            "id": "1",
            "email": "user@example.com",
            "name": "User",
            "password": "secret",
            "hashed_password": "hash",
        },
    )

    assert session.is_authenticated() is True
    assert session.get_access_token() == "jwt-token"
    assert fake_state[session.USER_KEY]["email"] == "user@example.com"
    assert "password" not in fake_state
    assert "password" not in fake_state[session.USER_KEY]
    assert "hashed_password" not in fake_state[session.USER_KEY]


def test_invalid_login_does_not_create_session(fake_state) -> None:
    session.clear_session()

    assert session.is_authenticated() is False
    assert fake_state[session.TOKEN_KEY] is None
    assert fake_state[session.USER_KEY] is None


def test_validate_session_requires_users_me(fake_state) -> None:
    fake_state[session.TOKEN_KEY] = "jwt-token"
    fake_state[session.USER_KEY] = None
    fake_state[session.SESSION_VALIDATED_KEY] = False

    valid = session.validate_session(
        lambda token: {"id": "1", "email": f"{token}@example.com"}
    )

    assert valid is True
    assert session.is_authenticated() is True
    assert fake_state[session.USER_KEY]["email"] == "jwt-token@example.com"


def test_401_like_validation_error_clears_session(fake_state) -> None:
    fake_state[session.TOKEN_KEY] = "expired"
    fake_state[session.USER_KEY] = {"email": "user@example.com"}
    fake_state[session.SESSION_VALIDATED_KEY] = True

    def reject(_token: str) -> dict:
        raise RuntimeError("401")

    assert session.validate_session(reject) is False
    assert session.is_authenticated() is False
    assert fake_state[session.TOKEN_KEY] is None
    assert fake_state[session.USER_KEY] is None


def test_empty_users_me_response_clears_session(fake_state) -> None:
    fake_state[session.TOKEN_KEY] = "jwt-token"
    fake_state[session.USER_KEY] = {"email": "user@example.com"}
    fake_state[session.SESSION_VALIDATED_KEY] = True

    assert session.validate_session(lambda _token: {}) is False
    assert session.is_authenticated() is False
    assert fake_state[session.TOKEN_KEY] is None
    assert fake_state[session.USER_KEY] is None


def test_logout_clears_token_and_user(fake_state, monkeypatch) -> None:
    rerun_called = False
    session.set_authenticated_session("jwt-token", {"email": "user@example.com"})

    def rerun() -> None:
        nonlocal rerun_called
        rerun_called = True

    monkeypatch.setattr(session.st, "rerun", rerun)

    session.logout()

    assert rerun_called is True
    assert fake_state[session.TOKEN_KEY] is None
    assert fake_state[session.USER_KEY] is None
