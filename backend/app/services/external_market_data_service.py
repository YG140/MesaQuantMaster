"""Fontes de cotações e séries históricas externas, com identidade explícita.

CoinGecko Demo (cripto) e Twelve Data (ações/ETFs listados no exterior).
Sem chave válida, erro, símbolo conflitante ou histórico suficiente: não
fabricar cotações nem indicadores. Nenhum segredo entra no frontend.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from math import sqrt
from statistics import stdev
from re import fullmatch

import httpx

from app.core.config import settings
from app.schemas.market import QuoteResponse
from app.schemas.market_intelligence import (
    ConfidenceLevel, IndicatorStatus, InvestmentClass, NormalizedIndicator,
)
from app.services.market_cache import TTLCache

# Evita colisões de tickers de tokens: somente IDs conhecidos ou identidade
# CoinGecko declarada no cadastro. Para outros tokens, atribua
# asset.exchange = "COINGECKO:<id-do-ativo>"; jamais adivinhe pelo ticker.
KNOWN_COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "ADA": "cardano", "XRP": "ripple",
}
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
TWELVEDATA_BASE = "https://api.twelvedata.com"


@dataclass(frozen=True)
class ExternalMarketResult:
    quote: QuoteResponse
    indicators: tuple[NormalizedIndicator, ...]


class ExternalMarketDataService:
    """Consulta somente ativos cadastrados e com tipo explícito.

    Sem fallback por igualdade de ticker da B3: 'ADA' não prova que é ADA
    cripto, e o campo exchange/símbolo estrangeiro deve bater com o retorno.
    """
    _cache: TTLCache[ExternalMarketResult] = TTLCache()

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    @staticmethod
    def eligible(asset) -> bool:
        return getattr(asset, "asset_type", "").strip().lower() in {
            "crypto", "cripto", "criptomoeda", "criptomoedas",
            "international", "ativo internacional", "ativos internacionais",
            "etf internacional", "global_etf",
        }

    @staticmethod
    def _class(asset) -> InvestmentClass:
        kind = asset.asset_type.strip().lower()
        if kind in {"crypto", "cripto", "criptomoeda", "criptomoedas"}:
            return InvestmentClass.CRYPTO
        if kind in {"etf internacional", "global_etf"}:
            return InvestmentClass.ETF
        return InvestmentClass.INTERNATIONAL

    @staticmethod
    def _crypto_id(asset) -> str:
        exchange = (getattr(asset, "exchange", None) or "").strip()
        symbol = asset.ticker.strip().upper()
        if exchange:
            if not exchange.upper().startswith("COINGECKO:"):
                raise ValueError("Identidade cripto exige exchange COINGECKO:<coin-id>.")
            coin_id = exchange.split(":", 1)[1].strip().lower()
            if not fullmatch(r"[a-z0-9][a-z0-9-]{1,80}", coin_id):
                raise ValueError("Identificador CoinGecko inválido.")
            return coin_id
        if symbol not in KNOWN_COINGECKO_IDS:
            raise ValueError("Token sem CoinGecko ID verificado; informe COINGECKO:<id> no cadastro.")
        return KNOWN_COINGECKO_IDS[symbol]

    @staticmethod
    def _equity_identity(asset) -> tuple[str, str]:
        symbol = asset.ticker.strip().upper()
        exchange = (getattr(asset, "exchange", None) or "").strip().upper()
        if not fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,18}", symbol):
            raise ValueError("Ticker internacional inválido.")
        if exchange and not fullmatch(r"[A-Z0-9][A-Z0-9 _-]{0,35}", exchange):
            raise ValueError("Exchange internacional inválida.")
        if exchange in {"B3", "BOVESPA", "SAO PAULO"}:
            raise ValueError("Ações e ETFs da B3 não são cotação internacional Twelve Data.")
        return symbol, exchange

    def _json(self, url: str, *, params: dict, headers: dict) -> object:
        try:
            if self.client is not None:
                response = self.client.get(url, params=params, headers=headers, timeout=10)
            else:
                with httpx.Client(follow_redirects=False, timeout=10) as client:
                    response = client.get(url, params=params, headers=headers)
            if response.status_code != 200:
                raise ValueError(f"Provedor retornou HTTP {response.status_code}; cotação indisponível.")
            data = response.json()
            if isinstance(data, dict) and data.get("status") == "error":
                raise ValueError("Provedor não retornou dados válidos para o plano ou ativo.")
            if isinstance(data, dict) and data.get("code") is not None and data.get("message"):
                raise ValueError("Provedor recusou a consulta (plano, símbolo ou limite).")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError("Provedor externo não respondeu; não foi possível validar a cotação.") from exc

    def load(self, asset) -> ExternalMarketResult:
        asset_class = self._class(asset)
        symbol = asset.ticker.upper().strip()
        if asset_class == InvestmentClass.CRYPTO:
            key = settings.COINGECKO_DEMO_API_KEY
            if not key:
                raise ValueError("Configure COINGECKO_DEMO_API_KEY no backend.")
            identity = self._crypto_id(asset)
        else:
            key = settings.TWELVEDATA_API_KEY
            if not key:
                raise ValueError("Configure TWELVEDATA_API_KEY no backend.")
            identity = "|".join(self._equity_identity(asset))
        cache_key = f"{asset_class.value}:{symbol}:{identity}"
        previous = self._cache.get(cache_key)
        if previous is not None:
            return previous
        if asset_class == InvestmentClass.CRYPTO:
            response = self._crypto(asset, identity, key)
        else:
            response = self._international(asset, asset_class, key)
        self._cache.set(cache_key, response, 300)
        return response

    def _crypto(self, asset, identity: str, key: str) -> ExternalMarketResult:
        headers = {"x-cg-demo-api-key": key, "accept": "application/json"}
        data = self._json(
            f"{COINGECKO_BASE}/coins/markets",
            params={"vs_currency": "usd", "ids": identity}, headers=headers
        )
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError("CoinGecko não encontrou uma identidade única.")
        coin = data[0]
        if not isinstance(coin, dict) or coin.get("id") != identity:
            raise ValueError("CoinGecko retornou identidade diferente da solicitada.")
        if str(coin.get("symbol", "")).upper() != asset.ticker.upper():
            raise ValueError("CoinGecko ID e ticker cadastrado são incompatíveis.")
        price = _positive(coin.get("current_price"))
        observed = _timestamp(coin.get("last_updated"))
        _fresh(observed, timedelta(days=2))
        market_cap = _optional_positive(coin.get("market_cap"))
        volume_usd = _optional_positive(coin.get("total_volume"))
        # CoinGecko informa volume financeiro USD/24h, não quantidade.
        # Esta é uma aproximação de unidades usando preço pontual de USD.
        volume_units = int((volume_usd / price).to_integral_value(rounding=ROUND_DOWN)) if volume_usd else None
        quote = QuoteResponse(
            ticker=asset.ticker.upper(), requested_symbol=asset.ticker.upper(),
            name=str(coin.get("name") or asset.name), asset_type="crypto",
            currency="USD", current_price=price, price=price, volume=volume_units,
            market_cap=market_cap, market_time=observed, source="CoinGecko",
            provider="CoinGecko",
        )
        indicators_list = []
        if volume_usd and market_cap and market_cap > 0:
            turnover = volume_usd / market_cap * Decimal("100")
            if turnover.is_finite() and Decimal("0") < turnover <= Decimal("50"):
                indicators_list.append(NormalizedIndicator(
                    key="turnover_ratio_24h", label="Giro financeiro 24h",
                    value=turnover.quantize(Decimal("0.01")),
                    display_value=f"{turnover.quantize(Decimal('0.01'))}%",
                    unit="percent", status=IndicatorStatus.AVAILABLE,
                    source="CoinGecko", source_type="provider",
                    reference_date=observed, collected_at=datetime.now(timezone.utc),
                    valid_until=observed + timedelta(days=2),
                    confidence=ConfidenceLevel.MEDIUM,
                    period="últimas 24 horas",
                    explanation="Volume 24h USD dividido pela capitalização USD; não é liquidez garantida.",
                ))
        indicators = tuple(indicators_list)
        try:
            historical = self._json(
                f"{COINGECKO_BASE}/coins/{identity}/market_chart",
                params={"vs_currency": "usd", "days": "90"}, headers=headers
            )
            if isinstance(historical, dict):
                prices = _coingecko_daily(historical.get("prices"))
                indicators += _historical_indicators(
                    prices, source="CoinGecko", asset_class=InvestmentClass.CRYPTO
                )
        except ValueError:
            pass  # Price can be valid while risk history is missing.
        return ExternalMarketResult(quote=quote, indicators=indicators)

    def _international(self, asset, asset_class: InvestmentClass, key: str) -> ExternalMarketResult:
        symbol, expected_exchange = self._equity_identity(asset)
        params = {"symbol": symbol, "apikey": key}
        data = self._json(f"{TWELVEDATA_BASE}/quote", params=params, headers={})
        if not isinstance(data, dict) or str(data.get("symbol", "")).upper() != symbol:
            raise ValueError("Twelve Data retornou símbolo diferente do cadastrado.")
        observed = _timestamp(data.get("timestamp"))
        _fresh(observed, timedelta(days=7))
        # Twelve Data /quote não documenta o campo "type". A classe
        # precisa ser confirmada pelo meta de /time_series, nunca inferida.
        exchange = str(data.get("exchange", "")).upper()
        if expected_exchange and expected_exchange != exchange:
            raise ValueError("Bolsa de negociação diferente do cadastro; identidade rejeitada.")
        currency = str(data.get("currency", "")).upper()
        if len(currency) != 3 or not currency.isalpha() or currency == "BRL":
            raise ValueError("Moeda da cotação internacional ausente ou incoerente.")
        configured_currency = (getattr(asset, "currency", None) or "").strip().upper()
        if configured_currency and configured_currency != currency:
            raise ValueError("Moeda do provedor difere do cadastro; identidade rejeitada.")
        price = _positive(data.get("close"))
        quote = QuoteResponse(
            ticker=symbol, requested_symbol=symbol, name=str(data.get("name") or asset.name),
            asset_type="etf" if asset_class == InvestmentClass.ETF else "international",
            exchange=exchange or None, currency=currency,
            current_price=price, price=price, market_time=observed,
            source="Twelve Data", provider="Twelve Data",
            volume=_optional_int(data.get("volume")),
            previous_close=_optional_positive(data.get("previous_close")),
        )
        # Metadados de time_series validam a identidade e o tipo.
        # Sem esse endpoint não usamos a cotação para ações/ETFs:
        # símbolos homônimos podem apontar para classes diferentes.
        historical = self._json(
            f"{TWELVEDATA_BASE}/time_series",
            params={"symbol": symbol, "interval": "1day", "outputsize": "120", "apikey": key},
            headers={},
        )
        if not isinstance(historical, dict):
            raise ValueError("Resposta histórica inválida para o ativo.")
        meta = historical.get("meta")
        if not isinstance(meta, dict) or str(meta.get("symbol", "")).upper() != symbol:
            raise ValueError("Histórico Twelve Data pertence a outro símbolo.")
        if str(meta.get("currency", "")).upper() != currency:
            raise ValueError("Moeda do histórico incompatível com a cotação.")
        if expected_exchange and str(meta.get("exchange", "")).upper() != expected_exchange:
            raise ValueError("Bolsa do histórico incompatível com o cadastro.")
        kind = str(meta.get("type", "")).lower()
        if asset_class == InvestmentClass.ETF:
            if kind != "etf":
                raise ValueError("O provedor não confirmou que este símbolo é ETF.")
        elif kind not in {"common stock", "preferred stock", "american depositary receipt"}:
            raise ValueError("O provedor não confirmou que este símbolo é ação internacional.")
        indicators = _historical_indicators(
            _twelvedata_daily(historical.get("values")),
            source="Twelve Data", asset_class=asset_class
        )
        return ExternalMarketResult(quote=quote, indicators=indicators)


def _positive(value) -> Decimal:
    try:
        val = Decimal(str(value))
        if val.is_finite() and val > 0:
            return val
    except (InvalidOperation, TypeError, ValueError):
        pass
    raise ValueError("Preço do provedor ausente ou inválido.")


def _optional_positive(value) -> Decimal | None:
    try:
        return _positive(value)
    except ValueError:
        return None


def _optional_int(value) -> int | None:
    try:
        result = int(value)
        return result if 0 <= result < 10**16 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _timestamp(value) -> datetime:
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            when = datetime.fromtimestamp(int(value), tz=timezone.utc)
        else:
            when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise ValueError("Timestamp sem fuso horário.")
        return when.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError) as exc:
        raise ValueError("Horário da cotação ausente ou inválido.") from exc


def _fresh(observed: datetime, tolerance: timedelta) -> None:
    age = datetime.now(timezone.utc) - observed
    if age < -timedelta(minutes=10) or age > tolerance:
        raise ValueError("Cotação do provedor desatualizada ou no futuro.")


def _coingecko_daily(raw) -> list[tuple[datetime, Decimal]]:
    if not isinstance(raw, list):
        return []
    daily: dict[date, tuple[datetime, Decimal]] = {}
    for entry in raw:
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        try:
            instant = datetime.fromtimestamp(int(entry[0]) / 1000, tz=timezone.utc)
            price = _positive(entry[1])
        except (ValueError, OSError, OverflowError):
            continue
        day = instant.date()
        if day not in daily or instant > daily[day][0]:
            daily[day] = (instant, price)
    return [daily[day] for day in sorted(daily)]


def _twelvedata_daily(raw) -> list[tuple[datetime, Decimal]]:
    if not isinstance(raw, list):
        return []
    observations = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            day = date.fromisoformat(str(item["datetime"])[:10])
            instant = datetime.combine(day, time(hour=0), tzinfo=timezone.utc)
            observations.append((instant, _positive(item.get("close"))))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted({x[0]: x for x in observations}.values())


def _historical_indicators(
    prices: list[tuple[datetime, Decimal]], *, source: str, asset_class: InvestmentClass
) -> tuple[NormalizedIndicator, ...]:
    now = datetime.now(timezone.utc)
    if len(prices) < 61:
        return ()
    observations = sorted(prices)
    if len({t.date() for t, _ in observations}) < 61:
        return ()
    last = observations[-1][0]
    max_age = timedelta(days=3 if asset_class == InvestmentClass.CRYPTO else 8)
    if now - last > max_age or last > now + timedelta(days=1):
        return ()
    closes = [float(x) for _, x in observations]
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    if any(not (-1 < r < 10) for r in returns):
        return ()
    volatility = Decimal(str(stdev(returns) * sqrt(
        365 if asset_class == InvestmentClass.CRYPTO else 252
    ) * 100))
    highest = closes[0]
    worst = 0.0
    for close in closes:
        highest = max(highest, close)
        worst = min(worst, close / highest - 1)
    drawdown = Decimal(str(worst * 100))
    if not volatility.is_finite() or volatility > 500:
        return ()
    return tuple(NormalizedIndicator(
        key=key, label=label, value=value.quantize(Decimal("0.01")),
        display_value=f"{value.quantize(Decimal('0.01'))}%",
        unit="percent", status=IndicatorStatus.AVAILABLE,
        source=source, source_type="provider",
        reference_date=last, collected_at=now,
        valid_until=last + max_age,
        freshness_status="current", confidence=ConfidenceLevel.MEDIUM,
        period=f"{len(closes)} datas de fechamento observadas",
        explanation="Estimativa histórica, não previsão de rentabilidade.",
    ) for key, label, value in [
        ("volatility", "Volatilidade anualizada estimada", volatility),
        ("maximum_drawdown", "Queda máxima na janela", drawdown),
    ])
