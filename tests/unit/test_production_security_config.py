"""Production deployment rejects insecure SMTP and public registration."""

from types import SimpleNamespace

import pytest

from app.core.production_guard import assert_production_ready


def production_settings(**overrides):
    defaults = dict(
        APP_ENV="production",
        DATABASE_URL="postgresql://example:example@localhost:5432/example",
        SECRET_KEY="a" * 48,
        DEBUG=False,
        API_DOCS_ENABLED=False,
        SECURITY_HSTS_ENABLED=True,
        FRONTEND_ORIGINS=["https://example.test"],
        SMTP_HOST="smtp.example.test",
        SMTP_USE_TLS=True,
        AUTH_PUBLIC_REGISTRATION_ENABLED=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_private_production_settings_are_accepted():
    assert_production_ready(production_settings())


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"SMTP_USE_TLS": False}, "SMTP_USE_TLS"),
        ({"AUTH_PUBLIC_REGISTRATION_ENABLED": True}, "AUTH_PUBLIC_REGISTRATION_ENABLED"),
    ],
)
def test_insecure_production_settings_are_rejected(overrides, expected):
    with pytest.raises(RuntimeError, match=expected):
        assert_production_ready(production_settings(**overrides))


def test_development_keeps_existing_defaults():
    assert_production_ready(production_settings(APP_ENV="development", SMTP_USE_TLS=False, AUTH_PUBLIC_REGISTRATION_ENABLED=True))
