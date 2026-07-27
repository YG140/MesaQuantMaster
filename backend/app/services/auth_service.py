import hmac
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_one_time_token,
    hash_one_time_token,
    hash_password,
    verify_password,
)
from app.models.auth_token import AuthToken
from app.models.user import User
from app.providers.email_provider import EmailProvider
from app.repositories.auth_token_repository import AuthTokenRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
VERIFY = "email_verification"
RESET = "password_reset"


class AuthError(ValueError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        tokens: AuthTokenRepository | None = None,
        email_provider: EmailProvider | None = None,
    ):
        self.repository = repository
        self.tokens = tokens
        self.email_provider = email_provider

    def register(self, name: str, email: str, password: str) -> User:
        email = email.strip().lower()
        if not self.email_provider or not self.email_provider.is_configured():
            raise AuthError(
                "Cadastro temporariamente indisponível: envio de e-mail não configurado.",
                "EMAIL_DELIVERY_UNAVAILABLE",
            )
        if self.repository.get_by_email(email):
            raise AuthError("E-mail já cadastrado.", "EMAIL_ALREADY_EXISTS")
        user = self.repository.create(
            User(
                name=name,
                email=email,
                hashed_password=hash_password(password),
                is_email_verified=False,
            )
        )
        if not self._issue_and_send(user, VERIFY, enforce_cooldown=False):
            self.tokens.delete_for_user(user.id)
            self.repository.delete(user)
            raise AuthError(
                "Não foi possível enviar a verificação. Tente novamente mais tarde.",
                "EMAIL_DELIVERY_FAILED",
            )
        return user

    def authenticate(self, email: str, password: str) -> str:
        user = self.repository.get_by_email(email.strip().lower())
        if not user or not verify_password(password, user.hashed_password):
            raise AuthError("Usuário ou senha inválidos.", "INVALID_CREDENTIALS")
        if not user.is_email_verified:
            raise AuthError(
                "Confirme seu e-mail antes de entrar.", "EMAIL_NOT_VERIFIED"
            )
        return create_access_token(
            {"sub": str(user.id), "email": user.email, "ver": user.auth_version}
        )

    def resend_verification(self, email: str) -> None:
        user = self.repository.get_by_email(email.strip().lower())
        if user and not user.is_email_verified:
            self._issue_and_send(user, VERIFY, enforce_cooldown=True)

    def forgot_password(self, email: str) -> None:
        user = self.repository.get_by_email(email.strip().lower())
        if user:
            self._issue_and_send(user, RESET, enforce_cooldown=True)

    def verify_email(self, raw_token: str) -> None:
        token, user = self._consume(raw_token, VERIFY)
        user.is_email_verified = True
        token.used_at = datetime.now(timezone.utc)
        self.tokens.commit()

    def reset_password(self, raw_token: str, new_password: str) -> None:
        token, user = self._consume(raw_token, RESET)
        user.hashed_password = hash_password(new_password)
        user.auth_version += 1
        token.used_at = datetime.now(timezone.utc)
        self.tokens.invalidate(user.id, RESET)
        self.tokens.commit()

    def _consume(self, raw_token: str, token_type: str) -> tuple[AuthToken, User]:
        if not self.tokens:
            raise RuntimeError("Repositório de tokens não configurado.")
        digest = hash_one_time_token(raw_token)
        token = self.tokens.get_by_hash(digest, token_type)
        if not token or not hmac.compare_digest(token.token_hash, digest):
            raise AuthError("Token inválido.", "TOKEN_INVALID")
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if token.used_at is not None:
            raise AuthError("Token já utilizado.", "TOKEN_USED")
        if expires_at <= datetime.now(timezone.utc):
            raise AuthError("Token expirado.", "TOKEN_EXPIRED")
        user = self.repository.get_by_id(token.user_id)
        if not user:
            raise AuthError("Token inválido.", "TOKEN_INVALID")
        return token, user

    def _issue_and_send(
        self, user: User, token_type: str, *, enforce_cooldown: bool
    ) -> bool:
        if not self.tokens or not self.email_provider:
            return False
        latest = self.tokens.latest(user.id, token_type)
        now = datetime.now(timezone.utc)
        if latest and enforce_cooldown:
            created_at = latest.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (
                created_at
                + timedelta(seconds=settings.AUTH_EMAIL_REQUEST_COOLDOWN_SECONDS)
                > now
            ):
                raise AuthError(
                    "Aguarde antes de solicitar outro e-mail.", "REQUEST_COOLDOWN"
                )
        raw, digest = create_one_time_token()
        self.tokens.invalidate(user.id, token_type)
        lifetime = (
            timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
            if token_type == VERIFY
            else timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
        )
        self.tokens.create(
            AuthToken(
                user_id=user.id,
                token_type=token_type,
                token_hash=digest,
                expires_at=now + lifetime,
            )
        )
        path = "/verificar-email" if token_type == VERIFY else "/redefinir-senha"
        url = f"{settings.FRONTEND_PUBLIC_URL.rstrip('/')}{path}?token={quote(raw)}"
        subject = (
            "Confirme seu e-mail - Mesa Quant Master"
            if token_type == VERIFY
            else "Redefina sua senha - Mesa Quant Master"
        )
        text = (
            f"Olá, {user.name}.\n\nUse o link abaixo para "
            f"{'confirmar seu e-mail' if token_type == VERIFY else 'definir uma nova senha'}."
            f"\nO link é temporário e pode ser usado uma única vez.\n\n{url}\n"
        )
        try:
            self.email_provider.send(user.email, subject, text)
        except Exception:
            logger.warning("Falha ao enviar evento de autenticação por e-mail.")
            return False
        return True
