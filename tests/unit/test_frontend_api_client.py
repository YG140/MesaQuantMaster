import httpx
import pytest

from services.api_client import ApiClient, ApiError, UnauthorizedError


def make_client(
    handler,
    token: str | None = None,
    on_unauthorized=None,
) -> ApiClient:
    return ApiClient(
        base_url="http://testserver",
        token_getter=lambda: token,
        on_unauthorized=on_unauthorized,
        transport=httpx.MockTransport(handler),
    )


def test_auth_headers_with_token() -> None:
    client = make_client(lambda request: httpx.Response(200), token="secret")

    assert client.auth_headers() == {"Authorization": "Bearer secret"}


def test_auth_headers_without_token() -> None:
    client = make_client(lambda request: httpx.Response(200), token=None)

    assert client.auth_headers() == {}


def test_get_sends_bearer_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, token="secret")

    assert client.get("/status") == {"ok": True}


def test_error_keeps_backend_detail_message() -> None:
    client = make_client(
        lambda request: httpx.Response(400, json={"detail": "Ativo nao encontrado."})
    )

    with pytest.raises(ApiError) as exc:
        client.get("/assets/missing")

    assert exc.value.status_code == 400
    assert exc.value.message == "Ativo nao encontrado."


def test_validation_error_is_readable() -> None:
    client = make_client(
        lambda request: httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "loc": ["body", "quantity"],
                        "msg": "Input should be greater than 0",
                    }
                ]
            },
        )
    )

    with pytest.raises(ApiError) as exc:
        client.post("/operations", json={"quantity": 0})

    assert exc.value.message == "quantity: Input should be greater than 0"


def test_unauthorized_clears_session_callback() -> None:
    cleared = False

    def clear() -> None:
        nonlocal cleared
        cleared = True

    client = make_client(
        lambda request: httpx.Response(401, json={"detail": "Not authenticated"}),
        on_unauthorized=clear,
    )

    with pytest.raises(UnauthorizedError):
        client.get("/users/me")

    assert cleared is True
