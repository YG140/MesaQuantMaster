from __future__ import annotations

from typing import Any

from services.api_client import ApiClient


class BacktestingClient:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.api.post("/backtesting/run", json=payload)
