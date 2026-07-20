from __future__ import annotations

from app.core.config import settings
from app.providers.base_provider import BaseMarketProvider
from app.providers.exceptions import MarketAssetNotFoundError, MarketProviderError
from app.providers.provider_factory import ProviderFactory
from app.schemas.market import (
    MarketAssetResponse,
    MarketProfileResponse,
    QuoteResponse,
    QuotesResponse,
    ProviderCapabilitiesResponse,
)
from datetime import datetime, timezone
from app.providers.exceptions import MarketPermissionError, MarketAuthenticationError
from app.services.market_cache import TTLCache


class MarketService:
    """
    Orquestra dados de mercado via providers e cache temporario.
    """

    _search_cache: TTLCache[list[MarketAssetResponse]] = TTLCache()
    _quote_cache: TTLCache[QuoteResponse] = TTLCache()
    _profile_cache: TTLCache[MarketProfileResponse] = TTLCache()

    def __init__(self, provider: BaseMarketProvider | None = None):
        self.provider = provider or ProviderFactory.get_provider()

    def get_quote(self, ticker: str) -> QuoteResponse:
        quotes = self.get_quotes([ticker])
        if not quotes.quotes:
            raise MarketAssetNotFoundError("Ativo nao encontrado.")
        return quotes.quotes[0]

    def get_quotes(self, tickers: list[str]) -> QuotesResponse:
        symbols = self._normalize_symbols(tickers)
        if not symbols:
            return QuotesResponse(quotes=[], limited_mode=self._limited_mode())

        quotes: list[QuoteResponse] = []
        missing_symbols: list[str] = []
        cache_hit = True

        for symbol in symbols:
            cached = self._quote_cache.get(self._quote_key(symbol))
            if cached is None:
                cache_hit = False
                missing_symbols.append(symbol)
            else:
                quotes.append(cached.model_copy(update={"cache_hit": True}))

        if missing_symbols:
            try:
                fetched = self.provider.get_quotes(missing_symbols)
            except MarketProviderError as exc:
                if len(missing_symbols) <= 1:
                    raise
                fetched = self._fetch_individually_after_batch_error(
                    missing_symbols, exc
                )
            fetched = self._fetch_missing_individually(missing_symbols, fetched)
            for quote in fetched:
                quote = quote.model_copy(
                    update={
                        "limited_mode": self._limited_mode(),
                        "cache_hit": False,
                    }
                )
                self._quote_cache.set(
                    self._quote_key(quote.ticker),
                    quote,
                    settings.BRAPI_QUOTE_CACHE_SECONDS,
                )
                quotes.append(quote)

        quote_by_ticker = {quote.ticker: quote for quote in quotes}
        ordered_quotes = [
            quote_by_ticker[symbol] for symbol in symbols if symbol in quote_by_ticker
        ]
        unavailable = [symbol for symbol in symbols if symbol not in quote_by_ticker]

        return QuotesResponse(
            quotes=ordered_quotes,
            cache_hit=cache_hit,
            limited_mode=self._limited_mode(),
            unavailable_symbols=unavailable,
        )

    def _fetch_missing_individually(
        self, symbols: list[str], fetched: list[QuoteResponse]
    ) -> list[QuoteResponse]:
        fetched_by_symbol = {quote.ticker.upper(): quote for quote in fetched}
        missing = [symbol for symbol in symbols if symbol not in fetched_by_symbol]
        if len(symbols) <= 1 or not missing:
            return fetched

        completed = list(fetched)
        for symbol in missing:
            try:
                completed.extend(self.provider.get_quotes([symbol]))
            except MarketAssetNotFoundError:
                continue
        return completed

    def _fetch_individually_after_batch_error(
        self, symbols: list[str], batch_error: MarketProviderError
    ) -> list[QuoteResponse]:
        completed: list[QuoteResponse] = []
        provider_errors = 0
        for symbol in symbols:
            try:
                completed.extend(self.provider.get_quotes([symbol]))
            except MarketAssetNotFoundError:
                continue
            except MarketProviderError:
                provider_errors += 1
                continue
        if not completed and provider_errors == len(symbols):
            raise batch_error
        return completed

    def search_assets(self, query: str, limit: int = 10) -> list[MarketAssetResponse]:
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return []

        cache_key = f"search:{normalized_query.upper()}:{limit}"
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            return [item.model_copy(update={"cache_hit": True}) for item in cached]

        results = self.provider.search_assets(normalized_query, limit=limit)
        normalized = [
            item.model_copy(update={"limited_mode": self._limited_mode()})
            for item in self._deduplicate(results)
        ][:limit]
        self._search_cache.set(
            cache_key, normalized, settings.BRAPI_SEARCH_CACHE_SECONDS
        )
        return normalized

    def get_asset(self, ticker: str) -> MarketAssetResponse | None:
        symbol = self._normalize_symbol(ticker)
        if not symbol:
            return None

        quote = self.get_quote(symbol)
        profile = None
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
            last_updated=quote.last_updated or quote.market_time,
            updated_at=quote.updated_at or quote.market_time,
            provider=quote.provider or "BRAPI",
            cache_hit=quote.cache_hit,
            limited_mode=self._limited_mode(),
        )

    def _find_exact_asset(self, symbol: str) -> MarketAssetResponse | None:
        try:
            assets = self.search_assets(symbol, limit=10)
        except MarketProviderError:
            return None
        return next((asset for asset in assets if asset.ticker.upper() == symbol), None)

    def get_profile(self, ticker: str) -> MarketProfileResponse:
        symbol = self._normalize_symbol(ticker)
        cache_key = f"profile:{symbol}"
        cached = self._profile_cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(update={"cache_hit": True})

        profile = self.provider.get_profile(symbol).model_copy(
            update={"limited_mode": self._limited_mode()}
        )
        self._profile_cache.set(
            cache_key,
            profile,
            settings.BRAPI_PROFILE_CACHE_SECONDS,
        )
        return profile

    def provider_capabilities(self) -> ProviderCapabilitiesResponse:
        supported = [
            "quotes",
            "profiles",
            "statistics",
            "financials",
            "statements",
            "dividends",
            "historical",
            "fiis",
            "treasury",
            "macro",
        ]
        accessible: list[str] = []
        restricted: list[str] = []
        reachable: bool | None = None
        probes = {
            "quotes": lambda: self.provider.get_quotes(["PETR4"]),
            "statistics": lambda: self.provider.get_stock_dataset(
                "statistics", ["PETR4"], mode="current"
            ),
            "fiis": lambda: self.provider.get_fii_dataset("indicators", ["MXRF11"]),
            "treasury": lambda: self.provider.get_treasury(
                "indicators", ["tesouro-selic-01032031"]
            ),
            "macro": lambda: self.provider.get_macro(["selic"]),
        }
        for domain, probe in probes.items():
            try:
                probe()
                accessible.append(domain)
                reachable = True
            except (MarketPermissionError, MarketAuthenticationError):
                restricted.append(domain)
                reachable = True
            except Exception:
                if reachable is None:
                    reachable = False
        if "quotes" in accessible:
            accessible.append("profiles")
        if "statistics" in accessible:
            accessible.extend(["financials", "statements", "dividends", "historical"])
        return ProviderCapabilitiesResponse(
            provider=getattr(self.provider, "provider_name", "BRAPI"),
            configured=bool(getattr(self.provider, "api_key", None)),
            reachable=reachable,
            supported_domains=supported,
            accessible_domains=list(dict.fromkeys(accessible)),
            restricted_domains=list(dict.fromkeys(restricted)),
            last_checked_at=datetime.now(timezone.utc),
        )

    def get_stock_dataset(self, dataset: str, symbols: list[str], **params):
        return self.provider.get_stock_dataset(dataset, symbols, **params)

    def get_fii_dataset(self, dataset: str, symbols: list[str], **params):
        return self.provider.get_fii_dataset(dataset, symbols, **params)

    @classmethod
    def clear_caches(cls) -> None:
        cls._search_cache.clear()
        cls._quote_cache.clear()
        cls._profile_cache.clear()

    def _limited_mode(self) -> bool:
        return bool(getattr(self.provider, "limited_mode", False))

    @staticmethod
    def _normalize_symbol(ticker: str) -> str:
        return ticker.upper().strip()

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
    def _quote_key(symbol: str) -> str:
        return f"quote:{symbol}"

    @staticmethod
    def _deduplicate(
        assets: list[MarketAssetResponse],
    ) -> list[MarketAssetResponse]:
        unique = {}
        for asset in assets:
            unique.setdefault(asset.ticker.upper(), asset)
        return list(unique.values())
