"""Heurísticas explícitas para indicadores numéricos de AÇÕES.

Pontuação de atratividade de 0 a 100, distinta da cobertura de dados.
São referências iniciais, NÃO avaliações intrínsecas ou percentis setoriais.
Indicadores sem métrica comparável retornam None, nunca uma nota inventada.
Rácios de bancos, seguradoras e holdings precisam de modelos setoriais.
"""
from decimal import Decimal, InvalidOperation

from app.schemas.market_intelligence import IndicatorStatus


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("100"), value))


def _linear(value: Decimal, low: str, high: str, *, inverse: bool = False) -> Decimal:
    minimum, maximum = Decimal(low), Decimal(high)
    fraction = _clamp((value - minimum) / (maximum - minimum) * 100)
    return 100 - fraction if inverse else fraction


def score_stock_indicator(indicator) -> Decimal | None:
    """Return a real-value heuristic only when a recognized numeric ratio exists.

    Raw totals such as gross debt, balance-sheet size and share count are
    descriptive; rating them in isolation would reward company size, not
    investment quality. The same applies to raw traded share volume.
    """
    if indicator.status != IndicatorStatus.AVAILABLE or indicator.value is None:
        return None
    try:
        amount = Decimal(str(indicator.value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite():
        return None
    key = indicator.key

    if key == "roe":
        return _linear(amount, "-5", "25")
    if key == "roa":
        return _linear(amount, "-3", "15")
    if key == "roic":
        return _linear(amount, "-5", "25")
    if key == "price_earnings":
        # Negative P/E and very small P/E can be loss/distress, not a bargain.
        return _linear(amount, "5", "35", inverse=True) if amount >= 5 else None
    if key == "price_book":
        return _linear(amount, "0.5", "5", inverse=True) if amount >= Decimal("0.5") else None
    if key == "ev_ebitda":
        return _linear(amount, "4", "22", inverse=True) if amount >= 4 else None
    if key == "net_debt_equity":
        return _linear(amount, "0", "2.5", inverse=True)
    if key == "net_debt_ebitda":
        return _linear(amount, "0", "6", inverse=True)
    if key == "liabilities_assets":
        return _linear(amount, "20", "95", inverse=True)
    if key == "current_liquidity":
        return _linear(amount, "0.5", "2.5")
    if key in {"revenue_cagr_3y", "revenue_cagr_5y", "earnings_cagr_3y", "earnings_cagr_5y"}:
        return _linear(amount, "-10", "25")
    if key == "dividend_yield":
        # Yield excessively high is often unsustainable; never reward forever.
        if amount < 0:
            return None
        if amount <= 8:
            return _linear(amount, "0", "8")
        return _linear(amount, "8", "20", inverse=True)
    if key == "day_range":
        # One-day price range is weak evidence of long-horizon risk.
        return None
    if key == "liquidity" and indicator.unit == "currency":
        return _linear(amount, "0", "10000000")
    # Other raw quantities/text/rates cannot be scored without comparable
    # denominators, sector peer group and appropriate historical baselines.
    return None
