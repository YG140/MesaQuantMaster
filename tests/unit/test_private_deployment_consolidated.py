"""Regression checks for private registration and production guard."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from app.api import auth
from app.core.production_guard import assert_production_ready
from app.schemas.user import UserCreate


def test_private_registration_rejected(monkeypatch):
    monkeypatch.setattr(auth.settings, "AUTH_PUBLIC_REGISTRATION_ENABLED", False)
    service = MagicMock()
    user = UserCreate(name="Private User", email="user@example.test", password="StrongPassword123!")
    with pytest.raises(HTTPException) as exc:
        auth.register(user, service)
    assert exc.value.status_code == 403
    service.register.assert_not_called()


def test_private_production_guard():
    config = SimpleNamespace(APP_ENV="production", DATABASE_URL="postgresql://user:pass@localhost/test", SECRET_KEY="x" * 40, DEBUG=False, API_DOCS_ENABLED=False, SECURITY_HSTS_ENABLED=True, FRONTEND_ORIGINS=["https://example.test"], SMTP_HOST="smtp.example.test", SMTP_USE_TLS=True, AUTH_PUBLIC_REGISTRATION_ENABLED=False)
    assert_production_ready(config)
    config.SMTP_USE_TLS = False
    with pytest.raises(RuntimeError, match="SMTP_USE_TLS"):
        assert_production_ready(config)
    config.SMTP_USE_TLS = True
    config.AUTH_PUBLIC_REGISTRATION_ENABLED = True
    with pytest.raises(RuntimeError, match="Cadastro público"):
        assert_production_ready(config)
