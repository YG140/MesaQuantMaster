from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import decode_access_token, verify_password
from app.repositories.auth_token_repository import AuthTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthError, AuthService, RESET, VERIFY
from app.providers.email_provider import SMTPEmailProvider


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


def test_forgot_password_api_is_generic(
    unauthenticated_client, active_user, monkeypatch
):
    monkeypatch.setattr(SMTPEmailProvider, "is_configured", lambda self: True)
    monkeypatch.setattr(SMTPEmailProvider, "send", lambda *args: None)
    existing = unauthenticated_client.post(
        "/auth/forgot-password", json={"email": active_user.email}
    )
    missing = unauthenticated_client.post(
        "/auth/forgot-password", json={"email": "missing@example.com"}
    )
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json()
    assert "não confirma cadastro nem entrega" in existing.json()["message"]


def test_recovery_unconfigured_is_global_and_does_not_issue_tokens(
    unauthenticated_client, active_user, db_session, monkeypatch
):
    monkeypatch.setattr(SMTPEmailProvider, "is_configured", lambda self: False)
    responses = [
        unauthenticated_client.post("/auth/forgot-password", json={"email": email})
        for email in [active_user.email, "missing@example.com"]
    ]
    assert responses[0].status_code == responses[1].status_code == 503
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()["detail"]["code"] == "EMAIL_DELIVERY_UNAVAILABLE"
    assert AuthTokenRepository(db_session).latest(active_user.id, RESET) is None
    assert active_user.hashed_password == "hashed"


def test_recovery_send_failure_never_promises_delivery_or_exposes_account(
    unauthenticated_client, active_user, monkeypatch, caplog
):
    monkeypatch.setattr(SMTPEmailProvider, "is_configured", lambda self: True)

    def fail(*args):
        raise RuntimeError("private-provider-diagnostic")

    monkeypatch.setattr(SMTPEmailProvider, "send", fail)
    responses = [
        unauthenticated_client.post("/auth/forgot-password", json={"email": email})
        for email in [active_user.email, "missing@example.com"]
    ]
    assert responses[0].json() == responses[1].json()
    assert "não confirma cadastro nem entrega" in responses[0].json()["message"]
    assert "private-provider-diagnostic" not in caplog.text
    assert active_user.email not in caplog.text


def test_reset_api_rejects_invalid_expired_and_consumed_links(
    unauthenticated_client, db_session
):
    email = FakeEmailProvider()
    auth = service(db_session, email)
    user = auth.register("Recovery test", "recovery@example.com", "old-test-password")
    auth.verify_email(email.token)
    old_hash = user.hashed_password
    auth.forgot_password(user.email)
    token = email.token
    stored = AuthTokenRepository(db_session).latest(user.id, RESET)
    for raw, expected in [
        ("invalid-test-token-123456789", "TOKEN_INVALID"),
        (token, "TOKEN_EXPIRED"),
    ]:
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.commit()
        response = unauthenticated_client.post(
            "/auth/reset-password", json={"token": raw, "password": "new-test-password"}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == expected
        db_session.refresh(user)
        assert user.hashed_password == old_hash
    stored.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    db_session.commit()
    payload = {"token": token, "password": "new-test-password"}
    assert (
        unauthenticated_client.post("/auth/reset-password", json=payload).status_code
        == 200
    )
    reused = unauthenticated_client.post("/auth/reset-password", json=payload)
    assert reused.status_code == 400
    assert reused.json()["detail"]["code"] == "TOKEN_USED"
    db_session.refresh(user)
    assert verify_password("new-test-password", user.hashed_password)


def test_register_refuses_unconfigured_email_without_creating_user(db_session):
    class UnconfiguredEmailProvider(FakeEmailProvider):
        def is_configured(self) -> bool:
            return False

    auth = service(db_session, UnconfiguredEmailProvider())
    with pytest.raises(AuthError) as error:
        auth.register("Pessoa Teste", "blocked@example.com", "senha-segura")
    assert error.value.code == "EMAIL_DELIVERY_UNAVAILABLE"
    assert UserRepository(db_session).get_by_email("blocked@example.com") is None
