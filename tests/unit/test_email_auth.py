from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import decode_access_token, verify_password
from app.repositories.auth_token_repository import AuthTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthError, AuthService, VERIFY


class FakeEmailProvider:
    def __init__(self, fail: bool = False):
        self.messages: list[tuple[str, str, str]] = []
        self.fail = fail

    def send(self, recipient: str, subject: str, text: str) -> None:
        if self.fail:
            raise RuntimeError("smtp unavailable")
        self.messages.append((recipient, subject, text))

    def is_configured(self) -> bool:
        return True

    @property
    def token(self) -> str:
        return self.messages[-1][2].split("?token=", 1)[1].strip()


def service(db_session, provider=None):
    return AuthService(
        UserRepository(db_session),
        AuthTokenRepository(db_session),
        provider or FakeEmailProvider(),
    )


def test_register_stores_only_hash_and_requires_verification(db_session):
    email = FakeEmailProvider()
    auth = service(db_session, email)
    user = auth.register("Nova Pessoa", "NOVA@example.com", "senha-segura")
    stored = AuthTokenRepository(db_session).latest(user.id, VERIFY)
    assert user.is_email_verified is False
    assert stored is not None
    assert stored.token_hash != email.token
    with pytest.raises(AuthError) as error:
        auth.authenticate("nova@example.com", "senha-segura")
    assert error.value.code == "EMAIL_NOT_VERIFIED"


def test_verify_token_is_single_use_and_isolated(db_session):
    email = FakeEmailProvider()
    auth = service(db_session, email)
    first = auth.register("Primeira Pessoa", "first@example.com", "senha-segura")
    first_token = email.token
    second = auth.register("Segunda Pessoa", "second@example.com", "senha-segura")
    auth.verify_email(first_token)
    assert first.is_email_verified is True
    assert second.is_email_verified is False
    with pytest.raises(AuthError) as error:
        auth.verify_email(first_token)
    assert error.value.code == "TOKEN_USED"


def test_invalid_and_expired_tokens(db_session):
    auth = service(db_session)
    with pytest.raises(AuthError) as invalid:
        auth.verify_email("x" * 32)
    assert invalid.value.code == "TOKEN_INVALID"
    user = auth.register("Pessoa Teste", "expired@example.com", "senha-segura")
    token = AuthTokenRepository(db_session).latest(user.id, VERIFY)
    token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(AuthError) as expired:
        auth.verify_email(auth.email_provider.token)
    assert expired.value.code == "TOKEN_EXPIRED"


def test_cooldown_and_email_failure_do_not_corrupt_account(db_session):
    email = FakeEmailProvider()
    auth = service(db_session, email)
    user = auth.register("Pessoa Teste", "cooldown@example.com", "senha-segura")
    with pytest.raises(AuthError) as error:
        auth.resend_verification(user.email)
    assert error.value.code == "REQUEST_COOLDOWN"
    failed = service(db_session, FakeEmailProvider(fail=True))
    with pytest.raises(AuthError) as delivery:
        failed.register("Outra Pessoa", "smtp@example.com", "senha-segura")
    assert delivery.value.code == "EMAIL_DELIVERY_FAILED"
    assert UserRepository(db_session).get_by_email("smtp@example.com") is None


def test_password_reset_changes_password_and_revokes_old_jwt(db_session):
    email = FakeEmailProvider()
    auth = service(db_session, email)
    user = auth.register("Pessoa Teste", "reset@example.com", "senha-antiga")
    auth.verify_email(email.token)
    old_token = auth.authenticate(user.email, "senha-antiga")
    old_version = decode_access_token(old_token)["ver"]
    auth.forgot_password(user.email)
    reset_token = email.token
    auth.reset_password(reset_token, "senha-nova-segura")
    assert verify_password("senha-nova-segura", user.hashed_password)
    assert user.auth_version == old_version + 1
    with pytest.raises(AuthError) as used:
        auth.reset_password(reset_token, "outra-senha")
    assert used.value.code == "TOKEN_USED"


def test_forgot_password_api_is_generic(unauthenticated_client):
    existing = unauthenticated_client.post(
        "/auth/forgot-password", json={"email": "exists@example.com"}
    )
    missing = unauthenticated_client.post(
        "/auth/forgot-password", json={"email": "missing@example.com"}
    )
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json()


def test_register_refuses_unconfigured_email_without_creating_user(db_session):
    class UnconfiguredEmailProvider(FakeEmailProvider):
        def is_configured(self) -> bool:
            return False

    auth = service(db_session, UnconfiguredEmailProvider())
    with pytest.raises(AuthError) as error:
        auth.register("Pessoa Teste", "blocked@example.com", "senha-segura")
    assert error.value.code == "EMAIL_DELIVERY_UNAVAILABLE"
    assert UserRepository(db_session).get_by_email("blocked@example.com") is None
