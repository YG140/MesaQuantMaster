from __future__ import annotations

from typing import Any

from services.api_client import ApiClient


class PortfolioClient:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def get_portfolio(self) -> dict[str, Any]:
        return self.api.get("/portfolio")

    def get_dashboard(self) -> dict[str, Any]:
        return self.api.get("/dashboard")

    def add_investment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.api.post("/portfolio/investments", json=payload)

    def import_initial_portfolio(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.api.post("/portfolio/import-initial", json=payload)
