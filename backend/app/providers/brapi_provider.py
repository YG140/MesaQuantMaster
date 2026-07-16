from datetime import datetime, timezone
from decimal import Decimal

from app.providers.base_provider import BaseMarketProvider
from app.schemas.market import MarketAssetResponse, QuoteResponse


_ASSET_CATALOG = [
    {
        "ticker": "PETR4",
        "name": "Petrobras PN",
        "asset_type": "Acao",
        "sector": "Energia",
        "country": "Brasil",
        "exchange": "B3",
        "currency": "BRL",
        "current_price": Decimal("38.42"),
    },
    {
        "ticker": "PETR3",
        "name": "Petrobras ON",
        "asset_type": "Acao",
        "sector": "Energia",
        "country": "Brasil",
        "exchange": "B3",
        "currency": "BRL",
        "current_price": Decimal("41.10"),
    },
    {
        "ticker": "B3SA3",
        "name": "B3",
        "asset_type": "Acao",
        "sector": "Financeiro",
        "country": "Brasil",
        "exchange": "B3",
        "currency": "BRL",
        "current_price": Decimal("12.50"),
    },
    {
        "ticker": "ITUB4",
        "name": "Itau Unibanco PN",
        "asset_type": "Acao",
        "sector": "Financeiro",
        "country": "Brasil",
        "exchange": "B3",
        "currency": "BRL",
        "current_price": Decimal("30.00"),
    },
]


class BrapiProvider(BaseMarketProvider):
    """
    Implementacao inicial da BRAPI.

    Nesta sprint utilizamos dados simulados para manter os testes sem internet.
    """

    def get_quote(self, ticker: str) -> QuoteResponse:
        asset = self.get_asset(ticker)
        if asset is None:
            return QuoteResponse(
                ticker=ticker.upper(),
                price=Decimal("0"),
                current_price=None,
                currency="BRL",
                source="BRAPI",
                provider="BRAPI",
            )

        return QuoteResponse(
            ticker=asset.ticker,
            price=asset.current_price or Decimal("0"),
            currency=asset.currency or "BRL",
            market_time=asset.last_updated,
            source=asset.provider,
            name=asset.name,
            asset_type=asset.asset_type,
            sector=asset.sector,
            country=asset.country,
            exchange=asset.exchange,
            current_price=asset.current_price,
            last_updated=asset.last_updated,
            provider=asset.provider,
        )

    def search_assets(self, query: str, limit: int = 10) -> list[MarketAssetResponse]:
        normalized_query = query.upper().strip()
        if not normalized_query:
            return []

        matches = []
        seen = set()
        for item in _ASSET_CATALOG:
            ticker = item["ticker"]
            name = item["name"]
            if normalized_query in ticker or normalized_query in name.upper():
                if ticker in seen:
                    continue
                seen.add(ticker)
                matches.append(self._to_response(item))

        matches.sort(
            key=lambda asset: (
                asset.ticker != normalized_query,
                not asset.ticker.startswith(normalized_query),
                asset.ticker,
            )
        )
        return matches[:limit]

    def get_asset(self, ticker: str) -> MarketAssetResponse | None:
        normalized_ticker = ticker.upper().strip()
        for item in _ASSET_CATALOG:
            if item["ticker"] == normalized_ticker:
                return self._to_response(item)
        return None

    def _to_response(self, item: dict) -> MarketAssetResponse:
        return MarketAssetResponse(
            ticker=item["ticker"],
            name=item.get("name"),
            asset_type=item.get("asset_type"),
            sector=item.get("sector"),
            country=item.get("country"),
            exchange=item.get("exchange"),
            currency=item.get("currency"),
            current_price=item.get("current_price"),
            last_updated=datetime.now(timezone.utc),
            provider="BRAPI",
        )
