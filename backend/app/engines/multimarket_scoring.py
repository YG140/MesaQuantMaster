"""Pontuação prudente para ETF, BDR, ações no exterior e criptoativos.

Um indicador disponível NÃO vira automaticamente uma nota. Apenas proporções
com unidade, data, origem e direção conhecidas são pontuáveis. Volume absoluto,
capitalização, preço, dominância e retornos passados isolados não implicam
qualidade. Estas heurísticas não são preços justos ou promessas de retorno.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from app.engines.equity_indicator_scoring import score_stock_indicator
from app.schemas.market_intelligence import ConfidenceLevel, IndicatorStatus, InvestmentClass

HUNDRED = Decimal("100")
# Requer data observada e evita pontuar "atual" algo sem validade identificável.
MAX_AGE_DAYS = {
    "bid_ask_spread": 7,
    "turnover_ratio_24h": 2,
    "premium_discount": 7,
    "liquidity": 7,
    "bdr_liquidity": 7,
    "management_fee": 395,
    "tracking_difference": 395,
    "tracking_error": 395,
    "volatility": 395,
    "maximum_drawdown": 395,
    "concentration": 395,
    "top_holdings_concentration": 395,
    "holder_concentration": 395,
}
GLOBAL_EQUITY_KEYS = {
    "roe", "roa", "roic", "price_earnings", "price_book", "ev_ebitda",
    "net_debt_equity", "net_debt_ebitda", "liabilities_assets",
    "current_liquidity", "revenue_cagr_3y", "revenue_cagr_5y",
    "earnings_cagr_3y", "earnings_cagr_5y", "dividend_yield",
}


def specialized_categories(asset_class: InvestmentClass) -> dict[str, list[str]]:
    if asset_class == InvestmentClass.CRYPTO:
        return {
            "quality": [],
            "valuation": [],
            "debt": [],
            "income": [],
            "growth": [],
            "risk": ["volatility", "maximum_drawdown", "holder_concentration"],
            "liquidity": ["bid_ask_spread", "turnover_ratio_24h"],
        }
    if asset_class == InvestmentClass.ETF:
        return {
            "quality": ["management_fee", "tracking_difference"],
            "valuation": ["premium_discount"],
            "debt": [],
            "income": [],
            "growth": [],
            "risk": [
                "tracking_error", "volatility", "maximum_drawdown",
                "concentration", "top_holdings_concentration",
            ],
            "liquidity": ["bid_ask_spread"],
        }
    if asset_class in {InvestmentClass.BDR, InvestmentClass.INTERNATIONAL}:
        return {
            "quality": ["roe", "roa", "roic"],
            "valuation": ["price_earnings", "price_book", "ev_ebitda"],
            "debt": ["net_debt_equity", "net_debt_ebitda", "liabilities_assets"],
            "income": ["dividend_yield"],
            "growth": [
                "revenue_cagr_3y", "revenue_cagr_5y",
                "earnings_cagr_3y", "earnings_cagr_5y",
            ],
            "risk": ["volatility", "maximum_drawdown"],
            "liquidity": ["bid_ask_spread"],
        }
    return {}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _observed_number(indicator, now: datetime) -> Decimal | None:
    if indicator.status != IndicatorStatus.AVAILABLE or indicator.value is None:
        return None
    if indicator.source_type in {"manual", "user"}:
        return None
    if indicator.confidence in {ConfidenceLevel.LOW, ConfidenceLevel.INSUFFICIENT}:
        return None
    if indicator.reference_date is None:
        return None
    dated = _aware(indicator.reference_date)
    max_age_days = MAX_AGE_DAYS.get(indicator.key, 395)
    age = now - dated
    if age < -timedelta(days=1) or age > timedelta(days=max_age_days):
        return None
    if indicator.valid_until is not None and _aware(indicator.valid_until) < now:
        return None
    try:
        value = Decimal(str(indicator.value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return value if value.is_finite() else None


def _inverse(amount: Decimal, good: str, bad: str) -> Decimal | None:
    low, high = Decimal(good), Decimal(bad)
    if amount < 0 or high <= low:
        return None
    fraction = (amount - low) / (high - low)
    return max(Decimal("0"), min(HUNDRED, (Decimal("1") - fraction) * HUNDRED))


def _percent(indicator, value: Decimal) -> Decimal | None:
    return value if indicator.unit in {"percent", "percentage"} else None


def score_specialized_indicator(
    asset_class: InvestmentClass, indicator, *, now: datetime | None = None
) -> Decimal | None:
    """Score entre 0 e 100, ou None quando não existe interpretação segura."""
    if asset_class not in {
        InvestmentClass.CRYPTO, InvestmentClass.ETF,
        InvestmentClass.BDR, InvestmentClass.INTERNATIONAL
    }:
        return None
    now = now or datetime.now(timezone.utc)
    value = _observed_number(indicator, now)
    if value is None:
        return None
    key = indicator.key
    if asset_class in {InvestmentClass.BDR, InvestmentClass.INTERNATIONAL} and key in GLOBAL_EQUITY_KEYS:
        return score_stock_indicator(indicator)
    if key == "turnover_ratio_24h" and asset_class == InvestmentClass.CRYPTO:
        amount = _percent(indicator, value)
        if amount is None or amount <= 0 or amount > 50:
            return None  # Giro excessivo pode ser manipulação.
        return max(Decimal("0"), min(Decimal("100"), (
            (amount - Decimal("0.1")) / Decimal("2") * Decimal("100")
        )))
    if key == "bid_ask_spread":
        amount = _percent(indicator, value)
        return _inverse(amount, "0.05", "3") if amount is not None else None
    if key == "management_fee" and asset_class == InvestmentClass.ETF:
        amount = _percent(indicator, value)
        return _inverse(amount, "0.10", "2") if amount is not None else None
    if key in {"tracking_error", "tracking_difference"} and asset_class == InvestmentClass.ETF:
        amount = _percent(indicator, value)
        return _inverse(abs(amount), "0", "8") if amount is not None else None
    if key == "premium_discount" and asset_class == InvestmentClass.ETF:
        amount = _percent(indicator, value)
        return _inverse(abs(amount), "0", "8") if amount is not None else None
    if key == "volatility":
        amount = _percent(indicator, value)
        return _inverse(amount, "8", "110") if amount is not None else None
    if key == "maximum_drawdown":
        amount = _percent(indicator, value)
        return _inverse(abs(amount), "5", "90") if amount is not None else None
    if key in {"holder_concentration", "top_holdings_concentration", "concentration"}:
        amount = _percent(indicator, value)
        if amount is None or amount > 100:
            return None
        return _inverse(amount, "10", "90")
    # Nunca dar score só porque há cotação, volume ou alta recente.
    return None
