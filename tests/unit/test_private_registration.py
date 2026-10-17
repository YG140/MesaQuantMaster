"""Private deployments must reject public account creation."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api import auth
from app.schemas.user import UserCreate


def test_public_registration_disabled(monkeypatch):
    monkeypatch.setattr(auth.settings, "AUTH_PUBLIC_REGISTRATION_ENABLED", False)
    service = MagicMock()
    user = UserCreate(name="Private User", email="user@example.test", password="StrongPassword123!")
    with pytest.raises(HTTPException) as error:
        auth.register(user, service)
    assert error.value.status_code == 403
    service.register.assert_not_called()


def test_public_registration_enabled(monkeypatch):
    monkeypatch.setattr(auth.settings, "AUTH_PUBLIC_REGISTRATION_ENABLED", True)
    service = MagicMock()
    user = UserCreate(name="Local User", email="user@example.test", password="StrongPassword123!")
    auth.register(user, service)
    service.register.assert_called_once_with(user.name, user.email, user.password)
