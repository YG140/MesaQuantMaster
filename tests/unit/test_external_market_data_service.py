"""Contrato dos provedores reais: identidade, moeda, cotação e histórico."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import settings
from app.engines.multimarket_scoring import score_specialized_indicator
from app.schemas.market_intelligence import InvestmentClass
from app.services.external_market_data_service import ExternalMarketDataService


def asset(ticker, kind, exchange=None):
    return SimpleNamespace(ticker=ticker, asset_type=kind, exchange=exchange, name=ticker)


def crypto_payload(symbol="btc", identity="bitcoin", *, days=91, stale=False):
    now = datetime.now(timezone.utc)
    when = now - timedelta(days=5) if stale else now - timedelta(minutes=15)
    chart = [
        [
            int((now - timedelta(days=i)).timestamp() * 1000),
            100.0 + (days - i) * 0.5 + (i % 6) * 0.12,
        ]
        for i in range(days - 1, -1, -1)
    ]
    return [
        {
            "id": identity, "symbol": symbol, "name": "Bitcoin",
            "current_price": 110, "market_cap": 200000000,
            "total_volume": 6000000, "last_updated": when.isoformat(),
        },
    ], {"prices": chart}


def twelve_payload(*, kind="Common Stock", currency="USD", exchange="NASDAQ", symbol="MSFT"):
    now = datetime.now(timezone.utc)
    quote = {
        "symbol": symbol, "name": "Microsoft",
        "currency": currency, "exchange": exchange,
        "timestamp": int((now - timedelta(hours=2)).timestamp()),
        "close": "414.50", "volume": "1234567",
    }
    series = {
        "meta": {
            "symbol": symbol, "currency": currency, "exchange": exchange,
            "type": kind,
        },
        "values": [
            {
                "datetime": (now - timedelta(days=n * 7 / 5)).date().isoformat(),
                "close": str(300 + n * 0.4 + (n % 5) * 0.04),
            }
            for n in range(119, -1, -1)
        ],
    }
    return quote, series


def make_client(responses):
    def handle(request):
        for path, payload in responses.items():
            if request.url.path.endswith(path):
                return httpx.Response(200, json=payload)
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handle))


@pytest.fixture(autouse=True)
def clear_cache():
    ExternalMarketDataService._cache.clear()
    yield
    ExternalMarketDataService._cache.clear()


def test_coingecko_verified_bitcoin_and_historical_risk(monkeypatch):
    monkeypatch.setattr(settings, "COINGECKO_DEMO_API_KEY", "test-key")
    market, chart = crypto_payload()
    with make_client({"/coins/markets": market, "/coins/bitcoin/market_chart": chart}) as client:
        fetched = ExternalMarketDataService(client).load(asset("BTC", "crypto"))
    assert fetched.quote.currency == "USD"
    assert fetched.quote.source == "CoinGecko"
    assert fetched.quote.market_time is not None
    assert fetched.quote.volume and fetched.quote.volume > 0
    values = {item.key: item for item in fetched.indicators}
    assert {"turnover_ratio_24h", "volatility", "maximum_drawdown"} <= set(values)
    assert values["turnover_ratio_24h"].value == Decimal("3.00")
    assert score_specialized_indicator(InvestmentClass.CRYPTO, values["volatility"]) is not None


def test_ticker_and_coin_id_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "COINGECKO_DEMO_API_KEY", "test-key")
    market, chart = crypto_payload(symbol="fake")
    with make_client({"/coins/markets": market, "/coins/bitcoin/market_chart": chart}) as client:
        with pytest.raises(ValueError, match="incompatíveis"):
            ExternalMarketDataService(client).load(asset("BTC", "crypto"))


def test_crypto_without_id_for_ambiguous_altcoin_abstains(monkeypatch):
    monkeypatch.setattr(settings, "COINGECKO_DEMO_API_KEY", "test-key")
    with pytest.raises(ValueError, match="CoinGecko ID"):
        ExternalMarketDataService().load(asset("FAKEX", "crypto"))


def test_stale_crypto_quote_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "COINGECKO_DEMO_API_KEY", "test-key")
    market, chart = crypto_payload(stale=True)
    with make_client({"/coins/markets": market, "/coins/bitcoin/market_chart": chart}) as client:
        with pytest.raises(ValueError, match="desatualizada"):
            ExternalMarketDataService(client).load(asset("BTC", "crypto"))


def test_crypto_history_missing_keeps_quote_without_inventing_risk(monkeypatch):
    monkeypatch.setattr(settings, "COINGECKO_DEMO_API_KEY", "test-key")
    market, chart = crypto_payload(days=10)
    with make_client({"/coins/markets": market, "/coins/bitcoin/market_chart": chart}) as client:
        fetched = ExternalMarketDataService(client).load(asset("BTC", "crypto"))
    assert fetched.quote.current_price == Decimal("110")
    assert all(item.key not in {"volatility", "maximum_drawdown"} for item in fetched.indicators)


def test_no_credentials_means_no_network_attempt(monkeypatch):
    monkeypatch.setattr(settings, "COINGECKO_DEMO_API_KEY", "")
    with pytest.raises(ValueError, match="COINGECKO_DEMO_API_KEY"):
        ExternalMarketDataService().load(asset("BTC", "crypto"))


def test_twelvedata_global_quote_and_risk(monkeypatch):
    monkeypatch.setattr(settings, "TWELVEDATA_API_KEY", "test-key")
    quote, series = twelve_payload()
    with make_client({"/quote": quote, "/time_series": series}) as client:
        fetched = ExternalMarketDataService(client).load(
            asset("MSFT", "international", "NASDAQ")
        )
    assert fetched.quote.currency == "USD"
    assert fetched.quote.source == "Twelve Data"
    assert fetched.quote.current_price == Decimal("414.50")
    assert {"volatility", "maximum_drawdown"} <= {i.key for i in fetched.indicators}


def test_twelvedata_meta_proves_etf_type(monkeypatch):
    monkeypatch.setattr(settings, "TWELVEDATA_API_KEY", "test-key")
    quote, series = twelve_payload(kind="ETF", symbol="QQQ", exchange="NASDAQ")
    with make_client({"/quote": quote, "/time_series": series}) as client:
        fetched = ExternalMarketDataService(client).load(
            asset("QQQ", "global_etf", "NASDAQ")
        )
    assert fetched.quote.asset_type == "etf"
    assert fetched.quote.currency == "USD"


@pytest.mark.parametrize("kind,fx,exchange", [
    ("ETF", "USD", "NASDAQ"),
    ("Common Stock", "BRL", "NASDAQ"),
    ("Common Stock", "USD", "NYSE"),
])
def test_twelvedata_wrong_instrument_or_currency_is_rejected(monkeypatch, kind, fx, exchange):
    monkeypatch.setattr(settings, "TWELVEDATA_API_KEY", "test-key")
    quote, series = twelve_payload(kind=kind, currency=fx, exchange=exchange)
    with make_client({"/quote": quote, "/time_series": series}) as client:
        with pytest.raises(ValueError):
            ExternalMarketDataService(client).load(
                asset("MSFT", "international", "NASDAQ")
            )


def test_twelvedata_price_without_verified_history_metadata_is_not_trusted(monkeypatch):
    monkeypatch.setattr(settings, "TWELVEDATA_API_KEY", "test-key")
    quote, series = twelve_payload()
    series["meta"]["symbol"] = "META"
    with make_client({"/quote": quote, "/time_series": series}) as client:
        with pytest.raises(ValueError, match="outro símbolo"):
            ExternalMarketDataService(client).load(asset("MSFT", "international"))


def test_unregistered_crypto_or_missing_key_is_not_automatically_probed():
    service = ExternalMarketDataService()
    assert not service.eligible(asset("PETR4", "stock"))
    assert service.eligible(asset("BTC", "crypto"))
    assert not service.eligible(asset("AAPL34", "bdr"))
