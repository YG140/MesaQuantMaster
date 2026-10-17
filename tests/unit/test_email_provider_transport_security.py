"""Regression checks for SMTP transport security."""

from unittest.mock import MagicMock, patch

import pytest

from app.providers.email_provider import SMTPEmailProvider


@pytest.fixture
def smtp_config(monkeypatch):
    from app.providers import email_provider

    monkeypatch.setattr(email_provider.settings, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(email_provider.settings, "SMTP_FROM_EMAIL", "sender@example.test")
    monkeypatch.setattr(email_provider.settings, "SMTP_FROM_NAME", "Mesa Quant")
    monkeypatch.setattr(email_provider.settings, "SMTP_USERNAME", "account")
    monkeypatch.setattr(email_provider.settings, "SMTP_PASSWORD", "test-password")
    monkeypatch.setattr(email_provider.settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_provider.settings, "APP_ENV", "production")
    return email_provider.settings


def test_smtp_starttls_uses_validating_context(smtp_config):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    with patch("app.providers.email_provider.smtplib.SMTP", return_value=smtp), patch(
        "app.providers.email_provider.ssl.create_default_context"
    ) as context_factory:
        SMTPEmailProvider().send("recipient@example.test", "Subject", "Text")
    smtp.starttls.assert_called_once_with(context=context_factory.return_value)
    smtp.login.assert_called_once_with("account", "test-password")
    smtp.send_message.assert_called_once()


@pytest.mark.parametrize("environment,username", [("production", ""), ("production", "account"), ("development", "account")])
def test_plaintext_smtp_is_rejected_before_network(smtp_config, monkeypatch, environment, username):
    monkeypatch.setattr(smtp_config, "APP_ENV", environment)
    monkeypatch.setattr(smtp_config, "SMTP_USERNAME", username)
    monkeypatch.setattr(smtp_config, "SMTP_USE_TLS", False)
    with patch("app.providers.email_provider.smtplib.SMTP") as smtp:
        with pytest.raises(RuntimeError, match="TLS"):
            SMTPEmailProvider().send("recipient@example.test", "Subject", "Text")
        smtp.assert_not_called()


def test_smtp_without_starttls_fails_closed(smtp_config):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.starttls.side_effect = RuntimeError("STARTTLS unavailable")
    with patch("app.providers.email_provider.smtplib.SMTP", return_value=smtp):
        with pytest.raises(RuntimeError, match="STARTTLS unavailable"):
            SMTPEmailProvider().send("recipient@example.test", "Subject", "Text")
    smtp.login.assert_not_called()
    smtp.send_message.assert_not_called()
