from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.providers.email_provider import SMTPEmailProvider
from app.repositories.auth_token_repository import AuthTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    EmailRequest,
    MessageResponse,
    OneTimeTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthError, AuthService
from app.services.login_rate_limiter import LoginRateLimiter

router = APIRouter(prefix="/auth", tags=["Autenticação"])
GENERIC_EMAIL_MESSAGE = (
    "Se o e-mail estiver cadastrado, você receberá as instruções em instantes."
)
login_rate_limiter = LoginRateLimiter(
    attempts=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    max_entries=settings.LOGIN_RATE_LIMIT_MAX_ENTRIES,
)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db), AuthTokenRepository(db), SMTPEmailProvider())


def raise_auth_error(error: AuthError, default_status: int = 400) -> None:
    http_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if error.code in {"EMAIL_DELIVERY_UNAVAILABLE", "EMAIL_DELIVERY_FAILED"}
        else 429 if error.code == "REQUEST_COOLDOWN" else default_status
    )
    raise HTTPException(
        status_code=http_status, detail={"message": str(error), "code": error.code}
    )


@router.post("/register", response_model=UserResponse, status_code=201)
def register(user: UserCreate, service: AuthService = Depends(get_auth_service)):
    try:
        return service.register(user.name, user.email, user.password)
    except AuthError as error:
        raise_auth_error(error)


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    key = login_rate_limiter.key(
        request.client.host if request.client else None,
        form_data.username,
    )
    decision = login_rate_limiter.check(key)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(decision.retry_after)},
        )
    try:
        response = TokenResponse(
            access_token=service.authenticate(form_data.username, form_data.password)
        )
        login_rate_limiter.clear_key(key)
        return response
    except AuthError as error:
        if error.code == "INVALID_CREDENTIALS":
            login_rate_limiter.record_failure(key)
        raise_auth_error(error, status.HTTP_401_UNAUTHORIZED)


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    request: OneTimeTokenRequest, service: AuthService = Depends(get_auth_service)
):
    try:
        service.verify_email(request.token)
        return MessageResponse(message="E-mail confirmado com sucesso.")
    except AuthError as error:
        raise_auth_error(error)


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    request: EmailRequest, service: AuthService = Depends(get_auth_service)
):
    try:
        service.resend_verification(request.email)
    except AuthError:
        pass
    return MessageResponse(message=GENERIC_EMAIL_MESSAGE)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    request: EmailRequest, service: AuthService = Depends(get_auth_service)
):
    try:
        service.forgot_password(request.email)
    except AuthError:
        pass
    return MessageResponse(message=GENERIC_EMAIL_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    request: ResetPasswordRequest, service: AuthService = Depends(get_auth_service)
):
    try:
        service.reset_password(request.token, request.password)
        return MessageResponse(message="Senha redefinida com sucesso.")
    except AuthError as error:
        raise_auth_error(error)
