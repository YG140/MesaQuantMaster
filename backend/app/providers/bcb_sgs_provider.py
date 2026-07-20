from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.providers.exceptions import (
    MarketInvalidResponseError,
    MarketProviderUnavailableError,
)


class BcbSgsProvider:
    """Fallback oficial para séries públicas do Banco Central do Brasil."""

    provider_name = "Banco Central do Brasil - SGS"
    base_url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
    series = {
        "selic": {"code": 1178, "unit": "% a.a.", "frequency": "daily"},
        "cdi": {"code": 12, "unit": "% a.d.", "frequency": "daily"},
        "ipca": {"code": 433, "unit": "% a.m.", "frequency": "monthly"},
        "igpm": {"code": 189, "unit": "% a.m.", "frequency": "monthly"},
        "usd_brl": {"code": 1, "unit": "BRL/USD", "frequency": "daily"},
        "ibcbr": {"code": 24363, "unit": "index", "frequency": "monthly"},
    }

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 10):
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def get_series(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]:
        metadata = self.series.get(symbol)
        if metadata is None:
            raise ValueError("Série macroeconômica não configurada.")
        params = {"formato": "json"}
        if start_date:
            params["dataInicial"] = start_date
        if end_date:
            params["dataFinal"] = end_date
        try:
            response = self._client.get(
                f"{self.base_url}.{metadata['code']}/dados", params=params
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketProviderUnavailableError(
                "Banco Central temporariamente indisponível."
            ) from exc
        if not isinstance(rows, list):
            raise MarketInvalidResponseError("Resposta inválida do Banco Central.")
        values = []
        for row in rows:
            try:
                value = Decimal(str(row["valor"]).replace(",", "."))
            except (KeyError, InvalidOperation):
                continue
            values.append({"reference_date": row.get("data"), "value": value})
        return {
            "symbol": symbol,
            "series_code": metadata["code"],
            "unit": metadata["unit"],
            "frequency": metadata["frequency"],
            "source": self.provider_name,
            "values": values,
        }
