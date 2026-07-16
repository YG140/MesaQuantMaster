from __future__ import annotations

from typing import Any

from services.api_client import ApiClient


class OperationClient:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def list_operations(self) -> list[dict[str, Any]]:
        return self.api.get("/operations")

    def create_operation(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.api.post("/operations", json=payload)
