from __future__ import annotations

from typing import Any


ASSET_TYPE_LABELS = {
    "stock": "Ação",
    "fii": "Fundo Imobiliário",
    "real_estate_fund": "Fundo Imobiliário",
    "etf": "ETF",
    "bdr": "BDR",
    "unit": "Unit",
    "index": "Índice",
    "fund": "Fundo",
    "crypto": "Criptomoeda",
}

SUBTYPE_LABELS = {
    "common": "Ordinária",
    "ordinary": "Ordinária",
    "on": "Ordinária",
    "preferred": "Preferencial",
    "preferential": "Preferencial",
    "pn": "Preferencial",
    "unit": "Unit",
    "paper": "Papel",
    "brick": "Tijolo",
    "hybrid": "Híbrido",
}

BRAZILIAN_EXCHANGES = {"B3", "BVMF", "SAO"}


def normalize_asset_type(value: Any) -> str | None:
    normalized = _normalize_key(value)
    if not normalized:
        return None
    return ASSET_TYPE_LABELS.get(normalized, str(value).strip())


def normalize_asset_subtype(value: Any, asset_type: Any = None) -> str | None:
    normalized = _normalize_key(value)
    type_key = _normalize_key(asset_type)
    if not normalized or normalized == type_key:
        return None
    return SUBTYPE_LABELS.get(normalized, str(value).strip())


def normalize_country(value: Any, exchange: Any) -> str | None:
    if value:
        return str(value).strip()
    exchange_key = str(exchange or "").upper().strip()
    if exchange_key in BRAZILIAN_EXCHANGES:
        return "Brasil"
    return None


def nested_get(data: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current not in (None, ""):
            return current
    return None


def unwrap_brapi_item(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data")
    if isinstance(data, dict):
        merged = {**item, **data}
        merged.pop("data", None)
        return merged
    return item


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()
