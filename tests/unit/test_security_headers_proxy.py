"""HSTS must survive TLS termination without trusting client forwarding headers."""

import asyncio

import pytest

from app.middleware.security_headers import SecurityHeadersMiddleware


async def _response_headers(*, scheme: str, enabled: bool, forwarded_proto=None):
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    headers = []

    async def send(message):
        if message["type"] == "http.response.start":
            headers.extend(message["headers"])

    raw_headers = []
    if forwarded_proto is not None:
        raw_headers.append((b"x-forwarded-proto", forwarded_proto.encode()))
    scope = {"type": "http", "scheme": scheme, "headers": raw_headers}
    middleware = SecurityHeadersMiddleware(inner, hsts_enabled=enabled, hsts_max_age_seconds=31536000)
    await middleware(scope, lambda: None, send)
    return dict(headers)


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_hsts_when_enabled_even_behind_tls_terminating_proxy(scheme):
    headers = asyncio.run(_response_headers(scheme=scheme, enabled=True))
    assert headers[b"strict-transport-security"] == b"max-age=31536000"


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_hsts_disabled_in_local_configuration(scheme):
    headers = asyncio.run(_response_headers(scheme=scheme, enabled=False))
    assert b"strict-transport-security" not in headers


def test_spoofed_forwarded_proto_does_not_control_hsts():
    http_headers = asyncio.run(_response_headers(scheme="http", enabled=True, forwarded_proto="https"))
    https_headers = asyncio.run(_response_headers(scheme="https", enabled=True, forwarded_proto="http"))
    assert http_headers[b"strict-transport-security"] == https_headers[b"strict-transport-security"]
