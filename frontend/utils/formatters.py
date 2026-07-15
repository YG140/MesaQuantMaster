from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def format_money(value: Any, currency: str = "R$") -> str:
    amount = to_decimal(value)
    if amount is None:
        return "-"
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency} {formatted}"


def format_percent(value: Any) -> str:
    amount = to_decimal(value)
    if amount is None:
        return "-"
    return f"{amount:.2f}%".replace(".", ",")


def format_decimal(value: Any) -> str:
    amount = to_decimal(value)
    if amount is None:
        return "-"
    return f"{amount.normalize():f}"
