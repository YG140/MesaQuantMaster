from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any

from jose import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Gera um hash seguro da senha utilizando Argon2.
    """
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifica se a senha informada corresponde ao hash armazenado.
    """
    return password_hash.verify(password, hashed_password)


def create_access_token(data: dict[str, Any]) -> str:
    """
    Cria um JWT com tempo de expiração configurado.
    """
    payload = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload["exp"] = expire

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodifica e valida um JWT.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )


def create_one_time_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_one_time_token(token)


def hash_one_time_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
