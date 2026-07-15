from __future__ import annotations

from typing import Any
from urllib.parse import quote

from services.api_client import ApiClient


class MarketClient:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def search_assets(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        encoded_query = quote(query.strip())
        return self.api.get(f"/market/search?q={encoded_query}&limit={limit}")

    def get_asset(self, ticker: str) -> dict[str, Any]:
        return self.api.get(f"/market/assets/{quote(ticker.strip())}")

    def get_quote(self, ticker: str) -> dict[str, Any]:
        return self.api.get(f"/market/quote/{quote(ticker.strip())}")
