from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from app.repositories.asset_repository import AssetRepository
from app.repositories.market_sync_repository import MarketSyncRepository
from app.schemas.market import QuotesResponse
from app.schemas.market_sync import (
    MarketSyncReport,
    MarketSyncRequest,
    MarketSyncSnapshot,
)
from app.services.indicator_normalization_service import classify_market_asset


class QuoteBatchProvider(Protocol):
    def get_quotes(self, tickers: list[str]) -> QuotesResponse: ...


class MarketSyncService:
    # Cotacoes sao volateis: validade do snapshot e de 120 segundos apos a coleta.
    # Esse prazo e independente do TTL do cache em memoria do MarketService.
    CURRENT_PRICE_VALIDITY_SECONDS = 120

    def __init__(
        self,
        *,
        asset_repository: AssetRepository,
        sync_repository: MarketSyncRepository,
        provider: QuoteBatchProvider | None,
        now=lambda: datetime.now(timezone.utc),
    ):
        self.asset_repository = asset_repository
        self.sync_repository = sync_repository
        self.provider = provider
        self.now = now

    def run(
        self,
        request: MarketSyncRequest,
        *,
        apply: bool = False,
    ) -> MarketSyncReport:
        symbols = self._normalize_symbols(request.tickers)[: request.max_assets]
        warnings: list[str] = []
        if request.offline:
            return MarketSyncReport(
                dry_run=not apply,
                requested=len(symbols),
                processed=0,
                calls_used=0,
                snapshots_ready=0,
                snapshots_written=0,
                unavailable_symbols=symbols,
                warnings=["Modo offline: nenhuma chamada de provider foi realizada."],
            )
        if self.provider is None:
            raise ValueError("Provider de mercado não configurado.")
        if request.max_calls < 1:
            raise ValueError("Limite de chamadas insuficiente.")

        response = self.provider.get_quotes(symbols)
        collected_at = self.now()
        local_assets = {
            symbol: self.asset_repository.get_by_ticker(symbol) for symbol in symbols
        }
        snapshots: list[MarketSyncSnapshot] = []
        returned = set()
        for quote in response.quotes:
            symbol = (quote.requested_symbol or quote.ticker).upper().strip()
            returned.add(symbol)
            price = (
                quote.current_price if quote.current_price is not None else quote.price
            )
            if price is None:
                warnings.append(
                    f"{symbol}: cotação ausente; nenhum zero foi persistido."
                )
                continue
            value = Decimal(price)
            if value <= 0:
                warnings.append(f"{symbol}: cotação não positiva rejeitada.")
                continue
            asset = local_assets.get(symbol)
            if asset is None:
                warnings.append(f"{symbol}: ativo não cadastrado; ignorado.")
                continue
            asset_class = classify_market_asset(asset.asset_type)
            currency_code = self._normalize_currency_code(quote.currency)
            if quote.currency is None:
                warnings.append(
                    f"{symbol}: moeda ausente no provider; currency_code mantido ausente."
                )
            elif currency_code is None:
                warnings.append(
                    f"{symbol}: moeda invalida no provider; currency_code mantido ausente."
                )
            snapshots.append(
                MarketSyncSnapshot(
                    symbol=symbol,
                    asset_class=asset_class.value,
                    indicator_key="current_price",
                    value=value,
                    unit="currency",
                    currency_code=currency_code,
                    provider=quote.provider or response.provider,
                    source_type="provider",
                    reference_date=quote.market_time
                    or quote.updated_at
                    or collected_at,
                    collected_at=collected_at,
                    valid_until=collected_at
                    + timedelta(seconds=self.CURRENT_PRICE_VALIDITY_SECONDS),
                )
            )
        unavailable = sorted(
            set(symbols) - returned | set(response.unavailable_symbols)
        )
        written = self.sync_repository.upsert_batch(snapshots) if apply else 0
        return MarketSyncReport(
            dry_run=not apply,
            requested=len(symbols),
            processed=len(returned),
            calls_used=1,
            snapshots_ready=len(snapshots),
            snapshots_written=written,
            unavailable_symbols=unavailable,
            warnings=warnings,
            snapshots=snapshots,
        )

    @staticmethod
    def _normalize_symbols(tickers: list[str]) -> list[str]:
        return list(
            dict.fromkeys(item.upper().strip() for item in tickers if item.strip())
        )

    @staticmethod
    def _normalize_currency_code(currency: str | None) -> str | None:
        if currency is None:
            return None
        normalized = currency.upper().strip()
        return normalized if len(normalized) == 3 and normalized.isalpha() else None
