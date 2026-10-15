"""PTAX oficial do Banco Central, cotação de venda USD/BRL de fechamento.

Cotação diária de REFERÊNCIA, não taxa executável de corretora (spread,
IOF e tributos ausentes). Sem fechamento recente e origem verificável,
nenhuma taxa substituta é inventada.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field

from app.services.market_cache import TTLCache

PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
FX_CACHE_SECONDS = 3600
FX_MAX_AGE_DAYS = 6


class FxUnavailableError(RuntimeError):
    pass


class FxReference(BaseModel):
    pair: str = "USD/BRL"
    rate_brl_per_usd: Decimal = Field(gt=0)
    quoted_at: datetime
    source: str = "Banco Central do Brasil (PTAX venda, fechamento)"
    indicative_only: bool = True
    disclaimer: str = (
        "Taxa oficial de referência, não cotação de execução. "
        "Não inclui spread, IOF, taxas nem eventuais impostos."
    )


class BcbPtaxFxService:
    """Client injetável para testes; sempre consulta endpoint HTTPS fixo."""
    _cache: TTLCache[FxReference] = TTLCache()

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def latest_usd_brl(self, *, now: datetime | None = None) -> FxReference:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Horário de consulta deve conter fuso.")
        now = now.astimezone(timezone.utc)
        if self.client is None:
            cached = self._cache.get("USD/BRL")
            if cached is not None and _valid_age(cached.quoted_at, now):
                return cached
        asof = now.astimezone(SAO_PAULO).date()
        start = asof - timedelta(days=FX_MAX_AGE_DAYS)
        params = {
            "@moeda": "'USD'",
            "@dataInicial": f"'{start:%m-%d-%Y}'",
            "@dataFinalCotacao": f"'{asof:%m-%d-%Y}'",
            "$format": "json",
        }
        try:
            if self.client is not None:
                response = self.client.get(PTAX_URL, params=params, timeout=12)
            else:
                with httpx.Client(timeout=12, follow_redirects=False) as client:
                    response = client.get(PTAX_URL, params=params)
            if response.status_code != 200:
                raise FxUnavailableError("Banco Central não respondeu com cotação válida.")
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FxUnavailableError("Não foi possível obter cotação PTAX verificável.") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise FxUnavailableError("Formato de resposta da PTAX inválido.")

        candidates: list[FxReference] = []
        for item in payload["value"]:
            if not isinstance(item, dict) or str(item.get("tipoBoletim", "")).casefold() != "fechamento":
                continue
            try:
                quoted = _bcb_datetime(item.get("dataHoraCotacao"))
                rate = Decimal(str(item["cotacaoVenda"]))
                if not rate.is_finite() or not (Decimal("0") < rate < Decimal("1000")):
                    continue
                if not _valid_age(quoted, now):
                    continue
            except (InvalidOperation, ValueError, KeyError, TypeError):
                continue
            candidates.append(FxReference(rate_brl_per_usd=rate, quoted_at=quoted))
        if not candidates:
            raise FxUnavailableError("PTAX venda de fechamento recente indisponível.")
        latest = max(candidates, key=lambda item: item.quoted_at)
        if self.client is None:
            self._cache.set("USD/BRL", latest, FX_CACHE_SECONDS)
        return latest


def _bcb_datetime(raw) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("Data PTAX inválida")
    parsed = datetime.fromisoformat(raw.strip().replace(" ", "T"))
    # O BCB entrega horário de Brasília sem timezone neste recurso.
    # Ancorar ao fuso da instituição (não UTC do servidor).
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SAO_PAULO)
    return parsed.astimezone(timezone.utc)


def _valid_age(quoted_at: datetime, now: datetime) -> bool:
    if quoted_at.tzinfo is None:
        return False
    age = now - quoted_at.astimezone(timezone.utc)
    return timedelta(minutes=-10) <= age <= timedelta(days=FX_MAX_AGE_DAYS)
