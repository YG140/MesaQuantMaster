from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unicodedata import normalize

from app.engines.indicator_catalog import indicators_for_class
from app.schemas.market import QuoteResponse
from app.schemas.market_intelligence import (
    AnalysisImpact,
    ConfidenceLevel,
    IndicatorCatalogEntry,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
)


class IndicatorNormalizationService:
    PROVIDER_FIELD_ALIASES = {
        "price_earnings": ("priceEarnings", "trailingPE", "priceToEarnings"),
        "price_to_book": ("priceToBook", "priceToNav"),
        "ev_ebitda": ("enterpriseToEbitda", "evEbitda"),
        "ev_ebit": ("enterpriseToEbit", "evEbit"),
        "price_sales": ("priceToSales", "priceSales"),
        "peg": ("pegRatio", "peg"),
        "earnings_per_share": ("earningsPerShare", "trailingEps"),
        "book_value_per_share": ("bookValuePerShare", "navPerShare"),
        "dividend_yield": ("dividendYield", "dividendYield12m"),
        "beta": ("beta",),
        "week_52_low": ("fiftyTwoWeekLow", "52WeekLow"),
        "week_52_high": ("fiftyTwoWeekHigh", "52WeekHigh"),
        "revenue": ("totalRevenue", "revenue"),
        "gross_profit": ("grossProfit",),
        "ebitda": ("ebitda",),
        "ebit": ("ebit", "operatingIncome"),
        "net_income": ("netIncome",),
        "operating_cash_flow": (
            "operatingCashFlow",
            "totalCashFromOperatingActivities",
        ),
        "free_cash_flow": ("freeCashFlow",),
        "gross_margin": ("grossMargins", "grossMargin"),
        "ebitda_margin": ("ebitdaMargins", "ebitdaMargin"),
        "operating_margin": ("operatingMargins", "operatingMargin"),
        "net_margin": ("profitMargins", "netMargin"),
        "total_assets": ("totalAssets",),
        "total_liabilities": ("totalLiabilities", "totalLiab"),
        "equity": ("stockholdersEquity", "totalStockholderEquity", "equity"),
        "cash": ("cash", "cashAndCashEquivalents"),
        "gross_debt": ("totalDebt", "grossDebt"),
        "net_debt": ("netDebt",),
        "current_assets": ("totalCurrentAssets", "currentAssets"),
        "current_liabilities": ("totalCurrentLiabilities", "currentLiabilities"),
        "total_investors": ("totalInvestors",),
        "shares_outstanding": ("sharesOutstanding",),
        "monthly_return": ("monthlyReturn",),
        "segment": ("segmentType", "segmentoAtuacao"),
    }

    def normalize_quote(
        self,
        quote: QuoteResponse | None,
        *,
        requested_symbol: str,
        asset_type: str | None = None,
        collected_at: datetime | None = None,
    ) -> tuple[InvestmentClass, list[NormalizedIndicator]]:
        now = collected_at or datetime.now(timezone.utc)
        asset_class = classify_market_asset(
            asset_type or getattr(quote, "asset_type", None)
        )
        indicators = [
            self._indicator_from_quote(
                entry,
                quote=quote,
                requested_symbol=requested_symbol,
                collected_at=now,
            )
            for entry in indicators_for_class(asset_class)
        ]
        return asset_class, indicators

    def merge_provider_payloads(
        self,
        indicators: list[NormalizedIndicator],
        payloads: list[dict[str, Any]],
        *,
        collected_at: datetime,
    ) -> list[NormalizedIndicator]:
        flattened: dict[str, Any] = {}
        reference_date = None
        for payload in payloads:
            self._flatten(payload, flattened)
            reference_date = (
                reference_date
                or flattened.get("asOfDate")
                or flattened.get("updatedAt")
            )
        result = []
        for indicator in indicators:
            aliases = self.PROVIDER_FIELD_ALIASES.get(indicator.key, ())
            value = next(
                (
                    flattened.get(alias)
                    for alias in aliases
                    if flattened.get(alias) is not None
                ),
                None,
            )
            decimal = self._decimal(value)
            if decimal is None and not isinstance(value, str):
                result.append(indicator)
                continue
            result.append(
                indicator.model_copy(
                    update={
                        "value": decimal if decimal is not None else value,
                        "display_value": display_value(
                            decimal if decimal is not None else value,
                            indicator.unit,
                            None,
                        ),
                        "status": IndicatorStatus.AVAILABLE,
                        "source": "BRAPI",
                        "reference_date": parse_provider_datetime(reference_date),
                        "collected_at": collected_at,
                        "confidence": ConfidenceLevel.HIGH,
                        "period": "período informado pelo provedor",
                        "unavailable_reason": None,
                        "impact": AnalysisImpact.INFORMATIONAL,
                    }
                )
            )
        return result

    @classmethod
    def _flatten(cls, value: Any, target: dict[str, Any]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(item, (dict, list)) and item is not None:
                    target.setdefault(key, item)
                cls._flatten(item, target)
        elif isinstance(value, list):
            for item in value:
                cls._flatten(item, target)

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        try:
            return Decimal(str(value)) if value is not None and value != "" else None
        except Exception:
            return None

    def _indicator_from_quote(
        self,
        entry: IndicatorCatalogEntry,
        *,
        quote: QuoteResponse | None,
        requested_symbol: str,
        collected_at: datetime,
    ) -> NormalizedIndicator:
        source = (
            getattr(quote, "source", None)
            or getattr(quote, "provider", None)
            or "BRAPI"
        )
        reference_date = (
            getattr(quote, "market_time", None)
            or getattr(quote, "updated_at", None)
            or getattr(quote, "last_updated", None)
        )
        if quote is None:
            return unavailable_indicator(
                entry,
                source=source,
                collected_at=collected_at,
                reason=f"{requested_symbol} nao retornou cotacao no provedor atual.",
            )

        value = self._value_for_key(entry.key, quote)
        if value is None:
            return unavailable_indicator(
                entry,
                source=source,
                collected_at=collected_at,
                reference_date=reference_date,
                reason="O provedor atual nao entrega este indicador para o ativo.",
            )

        if isinstance(value, Decimal) and not self._is_plausible(entry, value):
            return NormalizedIndicator(
                key=entry.key,
                label=entry.label,
                description=entry.description,
                category=entry.category,
                layer=entry.layer,
                value=value,
                display_value=display_value(
                    value, entry.unit, getattr(quote, "currency", None)
                ),
                unit=entry.unit,
                status=IndicatorStatus.INVALID,
                source=source,
                reference_date=reference_date,
                collected_at=collected_at,
                confidence=ConfidenceLevel.LOW,
                period="ultima cotacao",
                unavailable_reason="Valor fora dos limites plausiveis do catalogo.",
                explanation=entry.description,
                impact=AnalysisImpact.BLOCKING,
            )

        return NormalizedIndicator(
            key=entry.key,
            label=entry.label,
            description=entry.description,
            category=entry.category,
            layer=entry.layer,
            value=value,
            display_value=display_value(
                value, entry.unit, getattr(quote, "currency", None)
            ),
            unit=entry.unit,
            status=IndicatorStatus.AVAILABLE,
            source=source,
            reference_date=reference_date,
            collected_at=collected_at,
            confidence=ConfidenceLevel.MEDIUM,
            period="ultima cotacao",
            explanation=entry.description,
            impact=AnalysisImpact.INFORMATIONAL,
        )

    @staticmethod
    def _value_for_key(key: str, quote: QuoteResponse) -> Decimal | str | None:
        if key in {"current_price", "price"}:
            return quote.current_price or quote.price
        if key in {"change_percent", "daily_change"}:
            return quote.change_percent
        if key == "volume":
            return Decimal(quote.volume) if quote.volume is not None else None
        if key == "liquidity":
            price = quote.current_price or quote.price
            if price is None or quote.volume is None:
                return None
            return (price * Decimal(quote.volume)).quantize(Decimal("0.01"))
        if key == "market_cap":
            return quote.market_cap
        if key == "previous_close":
            return quote.previous_close
        if key == "day_low":
            return quote.day_low or quote.low
        if key == "day_high":
            return quote.day_high or quote.high
        if key == "sector":
            return quote.sector
        if key == "subsector":
            return quote.subsector
        if key == "country":
            return quote.country
        if key == "currency":
            return quote.currency
        if key == "day_range":
            high = quote.day_high or quote.high
            low = quote.day_low or quote.low
            price = quote.current_price or quote.price or quote.previous_close
            if high is None or low is None or price is None or price <= 0:
                return None
            return ((high - low) / price * Decimal("100")).quantize(Decimal("0.01"))
        return None

    @staticmethod
    def _is_plausible(entry: IndicatorCatalogEntry, value: Decimal) -> bool:
        if entry.plausible_min is not None and value < entry.plausible_min:
            return False
        if entry.plausible_max is not None and value > entry.plausible_max:
            return False
        return True


def unavailable_indicator(
    entry: IndicatorCatalogEntry,
    *,
    source: str,
    collected_at: datetime,
    reason: str,
    reference_date: datetime | None = None,
) -> NormalizedIndicator:
    return NormalizedIndicator(
        key=entry.key,
        label=entry.label,
        description=entry.description,
        category=entry.category,
        layer=entry.layer,
        unit=entry.unit,
        status=IndicatorStatus.UNAVAILABLE,
        source=source,
        reference_date=reference_date,
        collected_at=collected_at,
        confidence=ConfidenceLevel.INSUFFICIENT,
        period=None,
        unavailable_reason=reason,
        explanation=entry.description,
        impact=AnalysisImpact.UNKNOWN,
    )


def classify_market_asset(value: Any) -> InvestmentClass:
    key = _ascii_key(value)
    if key in {"stock", "equity", "acao", "acoes"}:
        return InvestmentClass.STOCK
    if key in {"fii", "real estate fund", "real_estate_fund", "fundo imobiliario"}:
        return InvestmentClass.FII
    if key == "etf":
        return InvestmentClass.ETF
    if key in {"treasury", "tesouro direto", "tesouro_direto"}:
        return InvestmentClass.TREASURY
    if key == "cdb":
        return InvestmentClass.CDB
    if key == "lci":
        return InvestmentClass.LCI
    if key == "lca":
        return InvestmentClass.LCA
    if key in {"debenture", "debentures"}:
        return InvestmentClass.DEBENTURE
    if key in {"fund", "fundo", "fundos de investimento"}:
        return InvestmentClass.INVESTMENT_FUND
    if key == "bdr":
        return InvestmentClass.BDR
    if key in {"international", "ativo internacional", "ativos internacionais"}:
        return InvestmentClass.INTERNATIONAL
    if key in {"crypto", "cripto", "criptomoeda", "criptomoedas"}:
        return InvestmentClass.CRYPTO
    return InvestmentClass.UNKNOWN


def display_value(value: Decimal | str, unit: str, currency: str | None) -> str:
    if isinstance(value, str):
        return value
    if unit == "currency":
        return f"{currency or 'BRL'} {value.quantize(Decimal('0.01'))}"
    if unit == "percent":
        return f"{value.quantize(Decimal('0.01'))}%"
    if unit == "quantity":
        return str(value.quantize(Decimal("1")))
    return str(value)


def _ascii_key(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    return normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def parse_provider_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
