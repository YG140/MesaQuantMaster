import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import settings


class EmailProvider(Protocol):
    def is_configured(self) -> bool: ...

    def send(self, recipient: str, subject: str, text: str) -> None: ...


class SMTPEmailProvider:
    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)

    def send(self, recipient: str, subject: str, text: str) -> None:
        if not self.is_configured():
            raise RuntimeError("Serviço de e-mail não configurado.")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        message["To"] = recipient
        message.set_content(text)
        with smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        ) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
