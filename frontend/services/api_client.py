from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 10.0


@dataclass
class ApiError(Exception):
    message: str
    status_code: int | None = None
    details: Any | None = None

    def __str__(self) -> str:
        return self.message


class UnauthorizedError(ApiError):
    pass


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        token_getter: Callable[[], str | None] | None = None,
        on_unauthorized: Callable[[], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        load_dotenv()
        self.base_url = (
            base_url or os.getenv("API_BASE_URL") or DEFAULT_API_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self.token_getter = token_getter
        self.on_unauthorized = on_unauthorized
        self.transport = transport

    def auth_headers(self) -> dict[str, str]:
        token = self.token_getter() if self.token_getter is not None else None
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def get(self, path: str, *, auth: bool = True) -> Any:
        return self.request("GET", path, auth=auth)

    def post(
        self,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        return self.request("POST", path, json=json, data=data, auth=auth)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        headers = self.auth_headers() if auth else {}
        url = f"{self.base_url}{path}"

        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
                follow_redirects=True,
            ) as client:
                response = client.request(
                    method,
                    url,
                    json=json,
                    data=data,
                    headers=headers,
                )
        except httpx.ConnectError as exc:
            raise ApiError(
                "Nao foi possivel conectar a API. Verifique se o backend esta rodando."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ApiError("A API demorou demais para responder.") from exc

        if response.status_code == 401:
            if self.on_unauthorized is not None:
                self.on_unauthorized()
            raise UnauthorizedError(
                _extract_error_message(response),
                status_code=response.status_code,
                details=_extract_json(response),
            )

        if response.status_code >= 400:
            raise ApiError(
                _extract_error_message(response),
                status_code=response.status_code,
                details=_extract_json(response),
            )

        if response.status_code == 204 or not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise ApiError("A API retornou uma resposta invalida.") from exc


def _extract_json(response: httpx.Response) -> Any | None:
    try:
        return response.json()
    except ValueError:
        return None


def _extract_error_message(response: httpx.Response) -> str:
    payload = _extract_json(response)
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            return "; ".join(_format_validation_error(item) for item in detail)
        if detail is not None:
            return str(detail)

    fallback = {
        400: "Requisicao invalida.",
        404: "Registro nao encontrado.",
        409: "Conflito ao processar a requisicao.",
        422: "Dados invalidos.",
    }.get(response.status_code)
    return fallback or f"Erro da API ({response.status_code})."


def _format_validation_error(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    location = item.get("loc", [])
    field = ".".join(str(part) for part in location if part != "body")
    message = item.get("msg", "valor invalido")
    if not field:
        return str(message)
    return f"{field}: {message}"
