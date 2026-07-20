from __future__ import annotations

from typing import Any

import httpx

from app.providers.exceptions import (
    MarketInvalidResponseError,
    MarketProviderUnavailableError,
)


class TesouroTransparenteProvider:
    """Cliente do conjunto oficial diário de preços e taxas do Tesouro Direto."""

    provider_name = "Tesouro Transparente"

    def __init__(
        self,
        dataset_url: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20,
    ):
        self.dataset_url = dataset_url
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_daily_dataset(self) -> list[dict[str, Any]]:
        try:
            response = self._client.get(self.dataset_url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketProviderUnavailableError(
                "Tesouro Transparente temporariamente indisponível."
            ) from exc
        rows = payload.get("value", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise MarketInvalidResponseError(
                "Resposta inválida do Tesouro Transparente."
            )
        return [row for row in rows if isinstance(row, dict)]
