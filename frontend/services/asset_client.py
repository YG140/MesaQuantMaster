from __future__ import annotations

from typing import Any

from services.api_client import ApiClient


class AssetClient:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def list_assets(self) -> list[dict[str, Any]]:
        return self.api.get("/assets")

    def create_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.api.post("/assets", json=payload)
