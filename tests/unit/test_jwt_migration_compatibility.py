"""Regression tests for JWT compatibility and strict algorithm validation.

JWT signatures remain compatible with the former python-jose HS256 format.
No database, account or password changes are required by this migration.
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _legacy_hs256(payload: dict, secret: str) -> str:
    """Reproduce the JWT wire format using Python's standard library."""
    header = {"alg": "HS256", "typ": "JWT"}
    parts = [
        _b64(json.dumps(header, separators=(",", ":")).encode()),
        _b64(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(parts).encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return ".".join(parts + [_b64(signature)])


def test_preexisting_hs256_token_remains_valid():
    assert settings.ALGORITHM == "HS256"
    payload = {
        "sub": "old-user",
        "email": "legacy@example.com",
        "ver": 3,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
    }
    token = _legacy_hs256(payload, settings.SECRET_KEY)
    assert decode_access_token(token) == payload


def test_new_token_contains_existing_account_claims():
    token = create_access_token({"sub": "existing-user", "email": "me@example.com", "ver": 4})
    claims = decode_access_token(token)
    assert claims["sub"] == "existing-user"
    assert claims["email"] == "me@example.com"
    assert claims["ver"] == 4
    assert claims["exp"] > int(datetime.now(timezone.utc).timestamp())


def test_modified_legacy_signature_is_rejected():
    payload = {
        "sub": "user",
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
    }
    original = _legacy_hs256(payload, settings.SECRET_KEY)
    part1, part2, _ = original.split(".")
    tampered = f"{part1}.{part2}.{_b64(bytes(32))}"
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_unsigned_or_expired_token_is_rejected():
    raw = _b64(b'{"alg":"none","typ":"JWT"}')
    body = _b64(b'{"sub":"user"}')
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(f"{raw}.{body}.")

    expired = _legacy_hs256(
        {"sub": "user", "exp": int((datetime.now(timezone.utc) - timedelta(seconds=5)).timestamp())},
        settings.SECRET_KEY,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired)
