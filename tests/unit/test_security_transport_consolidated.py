"""Regression checks for SMTP transport and proxy HSTS."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from app.providers.email_provider import SMTPEmailProvider
from app.middleware.security_headers import SecurityHeadersMiddleware


def test_smtp_uses_verified_tls(monkeypatch):
    from app.providers import email_provider
    config = email_provider.settings
    for key, value in {"SMTP_HOST": "smtp.example.test", "SMTP_FROM_EMAIL": "from@example.test", "SMTP_USERNAME": "user", "SMTP_PASSWORD": "test", "SMTP_USE_TLS": True, "APP_ENV": "production"}.items():
        monkeypatch.setattr(config, key, value)
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch("app.providers.email_provider.smtplib.SMTP", return_value=smtp), patch("app.providers.email_provider.ssl.create_default_context") as context:
        SMTPEmailProvider().send("to@example.test", "subject", "body")
    smtp.starttls.assert_called_once_with(context=context.return_value)
    smtp.login.assert_called_once()


@pytest.mark.parametrize("env,username", [("production", ""), ("production", "user"), ("development", "user")])
def test_insecure_smtp_rejected_before_connect(monkeypatch, env, username):
    from app.providers import email_provider
    config = email_provider.settings
    for key, value in {"SMTP_HOST": "smtp.example.test", "SMTP_FROM_EMAIL": "from@example.test", "SMTP_USERNAME": username, "SMTP_USE_TLS": False, "APP_ENV": env}.items():
        monkeypatch.setattr(config, key, value)
    with patch("app.providers.email_provider.smtplib.SMTP") as smtp:
        with pytest.raises(RuntimeError, match="TLS"):
            SMTPEmailProvider().send("to@example.test", "subject", "body")
        smtp.assert_not_called()


def test_hsts_enabled_behind_tls_proxy():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
    async def check(scheme, enabled):
        messages = []
        async def send(message):
            messages.append(message)
        await SecurityHeadersMiddleware(app, hsts_enabled=enabled, hsts_max_age_seconds=31536000)({"type": "http", "scheme": scheme, "headers": [(b"x-forwarded-proto", b"https")]}, lambda: None, send)
        return dict(messages[0]["headers"])
    assert b"strict-transport-security" in asyncio.run(check("http", True))
    assert b"strict-transport-security" not in asyncio.run(check("http", False))
