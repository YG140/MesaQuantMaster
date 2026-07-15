from __future__ import annotations

from typing import Any

from services.api_client import ApiClient


class BrokerageClient:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def list_brokerages(self) -> list[dict[str, Any]]:
        return self.api.get("/brokerages")

    def create_brokerage(self, name: str) -> dict[str, Any]:
        return self.api.post("/brokerages", json={"name": name})
