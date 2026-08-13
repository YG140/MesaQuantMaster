from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import settings
from app.providers.base_provider import BaseMarketProvider
from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketAuthenticationError,
    MarketInvalidResponseError,
    MarketPermissionError,
    MarketProviderError,
    MarketProviderUnavailableError,
    MarketRateLimitError,
)
from app.schemas.market import MarketAssetResponse, MarketProfileResponse, QuoteResponse
from app.services.market_normalizer import (
    nested_get,
    normalize_asset_subtype,
    normalize_asset_type,
    normalize_country,
    unwrap_brapi_item,
)


class BrapiProvider(BaseMarketProvider):
    """
    BRAPI provider backed by brapi.dev v2 endpoints.

    The API key is optional for local development, but no simulated market data is
    returned when it is absent or when the provider fails.
    """

    provider_name = "BRAPI"

    STOCK_DATASETS = {
        "statistics": "/api/v2/stocks/statistics",
        "financial_data": "/api/v2/stocks/financial-data",
        "balance_sheet": "/api/v2/stocks/balance-sheet",
        "income_statement": "/api/v2/stocks/income-statement",
        "cash_flow": "/api/v2/stocks/cash-flow",
        "value_added": "/api/v2/stocks/value-added",
        "dividends": "/api/v2/stocks/dividends",
        "historical": "/api/v2/stocks/historical",
    }
    FII_DATASETS = {
        "list": "/api/v2/fii/list",
        "indicators": "/api/v2/fii/indicators",
        "indicators_history": "/api/v2/fii/indicators/history",
        "historical": "/api/v2/fii/historical",
        "properties": "/api/v2/fii/properties",
        "portfolio": "/api/v2/fii/portfolio",
        "reports": "/api/v2/fii/reports",
        "dividends": "/api/v2/fii/dividends",
    }

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ):
        self.base_url = (base_url or settings.BRAPI_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.BRAPI_API_KEY
        self.timeout_seconds = timeout_seconds or settings.BRAPI_TIMEOUT_SECONDS
        self.limited_mode = not bool(self.api_key)
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    def search_assets(self, query: str, limit: int = 10) -> list[MarketAssetResponse]:
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return []

        payload = self._get_json(
            "/api/v2/tickers",
            params={"search": normalized_query, "limit": limit, "page": 1},
        )
        items = self._extract_items(payload)
        results = [self._asset_from_ticker(item) for item in items]
        return self._deduplicate_assets(results, normalized_query.upper())[:limit]

    def get_asset(self, ticker: str) -> MarketAssetResponse | None:
        symbol = self._normalize_symbol(ticker)
        try:
            quote = self.get_quote(symbol)
        except MarketAssetNotFoundError:
            return None

        profile: MarketProfileResponse | None = None
        try:
            profile = self.get_profile(symbol)
        except MarketAssetNotFoundError:
            profile = None
        ticker_metadata = self._find_exact_asset(symbol)

        return MarketAssetResponse(
            ticker=quote.ticker,
            symbol=quote.symbol or quote.ticker,
            name=quote.name
            or (profile.name if profile else None)
            or (ticker_metadata.name if ticker_metadata else None),
            long_name=quote.name
            or (profile.name if profile else None)
            or (ticker_metadata.long_name if ticker_metadata else None),
            asset_type=quote.asset_type
            or (ticker_metadata.asset_type if ticker_metadata else None),
            asset_subtype=quote.asset_subtype
            or (ticker_metadata.asset_subtype if ticker_metadata else None),
            sector=(
                (profile.sector if profile else None)
                or quote.sector
                or (ticker_metadata.sector if ticker_metadata else None)
            ),
            subsector=(
                (profile.industry if profile else None)
                or quote.subsector
                or (ticker_metadata.subsector if ticker_metadata else None)
            ),
            country=quote.country
            or (profile.country if profile else None)
            or (ticker_metadata.country if ticker_metadata else None),
            exchange=quote.exchange
            or (ticker_metadata.exchange if ticker_metadata else None),
            currency=quote.currency
            or (ticker_metadata.currency if ticker_metadata else None),
            logo_url=quote.logo_url
            or (profile.logo_url if profile else None)
            or (ticker_metadata.logo_url if ticker_metadata else None),
            current_price=quote.current_price,
            change_value=quote.change_value,
            change_percent=quote.change_percent,
            last_updated=quote.market_time,
            updated_at=quote.market_time,
            provider=self.provider_name,
            limited_mode=self.limited_mode,
        )

    def _find_exact_asset(self, symbol: str) -> MarketAssetResponse | None:
        try:
            assets = self.search_assets(symbol, limit=10)
        except MarketProviderError:
            return None
        return next((asset for asset in assets if asset.ticker == symbol), None)

    def get_quote(self, ticker: str) -> QuoteResponse:
        quotes = self.get_quotes([ticker])
        if not quotes:
            raise MarketAssetNotFoundError("Ativo nao encontrado.")
        return quotes[0]

    def get_quotes(self, tickers: list[str]) -> list[QuoteResponse]:
        symbols = self._normalize_symbols(tickers)
        if not symbols:
            return []

        payload = self._get_json(
            "/api/v2/stocks/quote",
            params={"symbols": ",".join(symbols)},
        )
        items = self._extract_items(payload)
        items = [unwrap_brapi_item(item) for item in items]
        if not items:
            raise MarketAssetNotFoundError("Ativo nao encontrado.")

        requested_by_symbol = {symbol: symbol for symbol in symbols}
        return [
            self._quote_from_item(
                item,
                requested_symbol=requested_by_symbol.get(
                    self._normalize_symbol(str(nested_get(item, "symbol") or "")),
                    symbols[0] if len(symbols) == 1 else None,
                ),
            )
            for item in items
        ]

    def get_profile(self, ticker: str) -> MarketProfileResponse:
        symbol = self._normalize_symbol(ticker)
        payload = self._get_json(
            "/api/v2/stocks/profile",
            params={"symbols": symbol},
        )
        items = self._extract_items(payload)
        if not items:
            raise MarketAssetNotFoundError("Ativo nao encontrado.")
        return self._profile_from_item(items[0], requested_symbol=symbol)

    def get_stock_dataset(
        self,
        dataset: str,
        symbols: list[str],
        **params: Any,
    ) -> dict[str, Any]:
        path = self.STOCK_DATASETS.get(dataset)
        if path is None:
            raise ValueError("Conjunto de dados de ações não suportado.")
        query = {"symbols": ",".join(self._normalize_symbols(symbols)), **params}
        return self._get_json(
            path,
            params={key: value for key, value in query.items() if value is not None},
        )

    def get_fii_dataset(
        self,
        dataset: str,
        symbols: list[str],
        **params: Any,
    ) -> dict[str, Any]:
        path = self.FII_DATASETS.get(dataset)
        if path is None:
            raise ValueError("Conjunto de dados de FIIs não suportado.")
        query = {"symbols": ",".join(self._normalize_symbols(symbols)), **params}
        return self._get_json(
            path,
            params={key: value for key, value in query.items() if value is not None},
        )

    def get_treasury(
        self, resource: str, symbols: list[str] | None = None, **params: Any
    ) -> dict[str, Any]:
        paths = {
            "list": "/api/v2/treasury/list",
            "indicators": "/api/v2/treasury/indicators",
            "history": "/api/v2/treasury/indicators/history",
        }
        if resource not in paths:
            raise ValueError("Recurso do Tesouro Direto não suportado.")
        query = dict(params)
        if symbols:
            query["symbols"] = ",".join(symbols)
        return self._get_json(paths[resource], params=query)

    def get_macro(self, symbols: list[str], **params: Any) -> dict[str, Any]:
        return self._get_json(
            "/api/v2/macro",
            params={"symbols": ",".join(symbols), **params},
        )

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self._client.get(path, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            raise MarketProviderUnavailableError(
                "Provider de mercado indisponivel."
            ) from exc

        self._raise_for_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketInvalidResponseError(
                "Resposta invalida do provider de mercado."
            ) from exc

        if not isinstance(payload, dict):
            raise MarketInvalidResponseError(
                "Resposta invalida do provider de mercado."
            )

        return payload

    def _raise_for_status(self, response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 400:
            return
        if status_code == 401:
            raise MarketAuthenticationError("Token BRAPI ausente ou invalido.")
        if status_code == 403:
            raise MarketPermissionError("Recurso BRAPI nao permitido pelo plano.")
        if status_code == 404:
            raise MarketAssetNotFoundError("Ativo nao encontrado.")
        if status_code == 429:
            raise MarketRateLimitError("Limite de consultas ao mercado atingido.")
        if status_code >= 500:
            raise MarketProviderUnavailableError("Provider de mercado indisponivel.")
        raise MarketInvalidResponseError("Resposta invalida do provider de mercado.")

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_items = (
            payload.get("results")
            or payload.get("stocks")
            or payload.get("tickers")
            or payload.get("data")
            or []
        )
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            raise MarketInvalidResponseError(
                "Resposta invalida do provider de mercado."
            )
        return [unwrap_brapi_item(item) for item in raw_items if isinstance(item, dict)]

    @classmethod
    def _normalize_symbols(cls, tickers: list[str]) -> list[str]:
        seen = set()
        symbols = []
        for ticker in tickers:
            symbol = cls._normalize_symbol(ticker)
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
        return symbols

    @staticmethod
    def _normalize_symbol(ticker: str) -> str:
        return ticker.upper().strip()

    @classmethod
    def _deduplicate_assets(
        cls,
        assets: list[MarketAssetResponse],
        exact_symbol: str,
    ) -> list[MarketAssetResponse]:
        unique = {}
        for asset in assets:
            unique.setdefault(asset.ticker, asset)
        return sorted(
            unique.values(),
            key=lambda asset: (
                asset.ticker != exact_symbol,
                not asset.ticker.startswith(exact_symbol),
                asset.ticker,
            ),
        )

    def _asset_from_ticker(self, item: dict[str, Any]) -> MarketAssetResponse:
        item = unwrap_brapi_item(item)
        symbol = self._normalize_symbol(
            str(nested_get(item, "symbol", "ticker", "stock") or "")
        )
        if not symbol:
            raise MarketInvalidResponseError("Ticker ausente na resposta da BRAPI.")

        updated_at = self._parse_datetime(
            item.get("updatedAt")
            or item.get("updated_at")
            or item.get("regularMarketTime")
            or item.get("marketTime")
        )

        exchange = nested_get(item, "exchange", "stockExchange")
        raw_type = nested_get(item, "type", "assetType")
        raw_subtype = nested_get(
            item,
            "subType",
            "subtype",
            "category",
            "class",
            "assetClass",
        )
        change_value = self._decimal(
            nested_get(item, "regularMarketChange", "change", "change_value")
        )

        return MarketAssetResponse(
            ticker=symbol,
            symbol=symbol,
            name=nested_get(item, "name", "shortName"),
            long_name=nested_get(item, "longName", "long_name"),
            asset_type=normalize_asset_type(raw_type),
            asset_subtype=normalize_asset_subtype(raw_subtype, raw_type),
            exchange=exchange,
            currency=nested_get(item, "currency"),
            sector=nested_get(item, "sector", "sectorName", "summaryProfile.sector"),
            subsector=nested_get(
                item,
                "subsector",
                "subSector",
                "industry",
                "industryName",
                "summaryProfile.industry",
            ),
            country=normalize_country(nested_get(item, "country"), exchange),
            logo_url=nested_get(item, "logo", "logoUrl", "logourl"),
            current_price=self._decimal(
                nested_get(item, "regularMarketPrice", "currentPrice", "close")
            ),
            change_value=change_value,
            change_percent=self._decimal(
                nested_get(
                    item,
                    "regularMarketChangePercent",
                    "changePercent",
                )
            ),
            last_updated=updated_at,
            updated_at=updated_at,
            provider=self.provider_name,
            limited_mode=self.limited_mode,
        )

    def _quote_from_item(
        self,
        item: dict[str, Any],
        requested_symbol: str | None,
    ) -> QuoteResponse:
        item = unwrap_brapi_item(item)
        symbol = self._normalize_symbol(
            str(nested_get(item, "symbol", "ticker", "stock") or "")
        )
        if not symbol:
            raise MarketInvalidResponseError("Ticker ausente na resposta da BRAPI.")

        current_price = self._decimal(
            nested_get(item, "regularMarketPrice", "currentPrice", "close", "price")
        )
        if current_price is None:
            raise MarketInvalidResponseError("Cotacao ausente na resposta da BRAPI.")

        market_time = self._parse_datetime(
            nested_get(
                item,
                "regularMarketTime",
                "marketTime",
                "updatedAt",
                "updated_at",
            )
        )
        previous_close = self._decimal(
            nested_get(
                item,
                "regularMarketPreviousClose",
                "previousClose",
                "previous_close",
            )
        )
        open_price = self._decimal(nested_get(item, "regularMarketOpen", "open"))
        day_high = self._decimal(nested_get(item, "regularMarketDayHigh", "dayHigh"))
        day_low = self._decimal(nested_get(item, "regularMarketDayLow", "dayLow"))
        raw_type = nested_get(item, "type", "assetType")
        raw_subtype = nested_get(
            item,
            "subType",
            "subtype",
            "category",
            "class",
            "assetClass",
        )
        exchange = nested_get(item, "exchange", "stockExchange")
        change_value = self._decimal(
            nested_get(item, "regularMarketChange", "change", "change_value")
        )

        return QuoteResponse(
            ticker=symbol,
            symbol=symbol,
            requested_symbol=requested_symbol or symbol,
            symbol_changed=bool(requested_symbol and requested_symbol != symbol),
            price=current_price,
            current_price=current_price,
            previous_close=previous_close,
            open=open_price,
            open_price=open_price,
            high=day_high,
            day_high=day_high,
            low=day_low,
            day_low=day_low,
            change=change_value,
            change_value=change_value,
            change_percent=self._decimal(
                nested_get(item, "regularMarketChangePercent", "changePercent")
            ),
            volume=self._int(nested_get(item, "regularMarketVolume", "volume")),
            market_cap=self._decimal(nested_get(item, "marketCap", "market_cap")),
            currency=(
                str(currency).upper()
                if (currency := nested_get(item, "currency")) is not None
                else None
            ),
            market_time=market_time,
            source=self.provider_name,
            name=nested_get(item, "shortName", "longName", "name"),
            asset_type=normalize_asset_type(raw_type),
            asset_subtype=normalize_asset_subtype(raw_subtype, raw_type),
            sector=nested_get(item, "sector", "sectorName", "summaryProfile.sector"),
            subsector=nested_get(
                item,
                "subsector",
                "subSector",
                "industry",
                "industryName",
                "summaryProfile.industry",
            ),
            country=normalize_country(nested_get(item, "country"), exchange),
            exchange=exchange,
            logo_url=nested_get(item, "logo", "logoUrl", "logourl"),
            last_updated=market_time,
            updated_at=market_time,
            provider=self.provider_name,
            limited_mode=self.limited_mode,
        )

    def _profile_from_item(
        self,
        item: dict[str, Any],
        requested_symbol: str,
    ) -> MarketProfileResponse:
        item = unwrap_brapi_item(item)
        symbol = self._normalize_symbol(
            str(nested_get(item, "symbol", "ticker") or requested_symbol)
        )
        return MarketProfileResponse(
            symbol=symbol,
            name=nested_get(item, "name", "longName", "shortName"),
            sector=nested_get(item, "sector", "sectorName", "summaryProfile.sector"),
            industry=nested_get(
                item,
                "subsector",
                "subSector",
                "industry",
                "industryName",
                "summaryProfile.industry",
            ),
            country=normalize_country(
                nested_get(item, "country"),
                nested_get(item, "exchange", "stockExchange"),
            ),
            website=nested_get(item, "website"),
            description=nested_get(
                item, "description", "summaryProfile.longBusinessSummary"
            ),
            cnpj=nested_get(item, "cnpj"),
            logo_url=nested_get(item, "logo", "logoUrl", "logourl"),
            provider=self.provider_name,
            limited_mode=self.limited_mode,
        )

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None or value == "":
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            timestamp = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized)
            except ValueError:
                return datetime.now(timezone.utc)
        return datetime.now(timezone.utc)
