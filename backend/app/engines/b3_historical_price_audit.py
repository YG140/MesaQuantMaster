"""Conferência offline de cotações históricas contra COTAHIST local da B3.

NUNCA faz download/crawling. Verifica layout, integridade do ZIP e
correspondência do preço NÃO AJUSTADO, deixando explícitas as limitações:
não verifica origem autenticada, data efetiva da publicação, dividendos,
desdobramentos, viés de sobrevivência, indicadores ou ganho de carteira.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from zipfile import ZipFile

from pydantic import BaseModel, Field

from app.engines.portfolio_walk_forward_engine import _validate_period
from app.providers.b3.cotahist import CotahistProvider
from app.providers.b3.models import B3_CASH_MARKET_TYPE
from app.schemas.portfolio_validation import WalkForwardRequest

B3_TZ = ZoneInfo("America/Sao_Paulo")
MEMBER_NAME = re.compile(r"^COTAHIST_(?:A(\d{4})|D(\d{2})(\d{2})(\d{4}))\.TXT$", re.I)
MAX_ARCHIVES = 24
MAX_COMPRESSED_BYTES = 105 * 1024 * 1024


class CotaHistArchiveEvidence(BaseModel):
    file_name: str
    sha256: str
    file_size_bytes: int
    historical_period: str
    records_matched: int


class B3QuoteEvidence(BaseModel):
    symbol: str
    decision_at: datetime
    trading_date: date
    close_price: Decimal
    isin: str | None
    archive_sha256: str
    currency: str
    quote_factor: int
    price_adjusted_for_events: bool = False


class B3PriceAuditReport(BaseModel):
    status: str = "source_price_checks_only"
    checked_quotes: int
    matched_quotes: int
    archives: list[CotaHistArchiveEvidence] = Field(default_factory=list)
    quotes: list[B3QuoteEvidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        "Arquivos locais com formato COTAHIST: SHA-256 comprova os bytes auditados, não a autenticidade de origem B3.",
        "Fechamentos NÃO AJUSTADOS por dividendos, bonificações, grupamentos ou desdobramentos.",
        "COTAÇÕES não demonstram quais indicadores financeiros ou versões de política estavam públicos na decisão.",
        "Fechamentos do MESMO DIA da decisão são rejeitados, pois a hora real de publicação do COTAHIST não foi auditada.",
        "Não calcula retorno total ou valida o desempenho das recomendações.",
        "Não substitui controle contra viés de sobrevivência e arquivos com data de publicação certificada.",
    ])


def _name_period(path: Path) -> tuple[str, date | None, int]:
    with ZipFile(path) as z:
        members = z.namelist()
        if len(members) != 1:
            raise ValueError("Arquivo COTAHIST deve conter exatamente um TXT.")
        match = MEMBER_NAME.fullmatch(members[0])
        if not match:
            raise ValueError("Nome interno do arquivo não corresponde ao padrão oficial COTAHIST_A/D.")
        if match.group(1):
            year = int(match.group(1))
            return f"ano {year}", None, year
        d, m, y = (int(match.group(i)) for i in (2, 3, 4))
        day = date(y, m, d)
        return f"pregão {day.isoformat()}", day, y


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


class B3HistoricalPriceAudit:
    """Compara todas as cotações dos snapshots ao COTAHIST inserido manualmente."""

    @classmethod
    def verify(
        cls,
        simulation: WalkForwardRequest,
        archives: list[Path],
        *,
        provider: CotahistProvider | None = None,
    ) -> B3PriceAuditReport:
        if not archives or len(archives) > MAX_ARCHIVES:
            raise ValueError(f"Informe de 1 a {MAX_ARCHIVES} arquivos COTAHIST locais.")
        for i, period in enumerate(simulation.periods):
            _validate_period(period, simulation.periods[i - 1] if i else None)

        claims: dict[tuple[str, date], list[tuple[datetime, Decimal]]] = {}
        for period in simulation.periods:
            for item in period.candidates:
                snap = item.snapshot
                if snap.market_updated_at is None or snap.current_price is None:
                    raise ValueError(f"{snap.symbol}: snapshot sem fechamento ou data.")
                if not snap.current_price.is_finite() or snap.current_price <= 0:
                    raise ValueError(f"{snap.symbol}: preço inválido.")
                trading_day = snap.market_updated_at.astimezone(B3_TZ).date()
                decision_day = period.decision_at.astimezone(B3_TZ).date()
                if trading_day >= decision_day:
                    raise ValueError(
                        f"{snap.symbol}: fechamento de {trading_day} não é comprovadamente "
                        "conhecido antes da decisão. Use pregão anterior."
                    )
                claims.setdefault((snap.symbol.upper(), trading_day), []).append(
                    (period.decision_at, snap.current_price)
                )

        if not claims:
            raise ValueError("Nenhuma cotação histórica para auditar.")
        feed = provider or CotahistProvider()
        found: dict[tuple[str, date], tuple] = {}
        manifests: list[CotaHistArchiveEvidence] = []
        seen_archives: set[str] = set()
        for archive in archives:
            archive = Path(archive)
            if not archive.is_file():
                raise ValueError(f"Arquivo COTAHIST não encontrado: {archive.name}")
            if archive.stat().st_size > MAX_COMPRESSED_BYTES:
                raise ValueError(f"Arquivo COTAHIST excede limite: {archive.name}")
            feed.validate_archive(archive, feed.annual_max_uncompressed_bytes)
            period_name, exact_day, year = _name_period(archive)
            digest = _sha256(archive)
            if digest in seen_archives:
                raise ValueError(f"Arquivo COTAHIST duplicado: {archive.name}")
            seen_archives.add(digest)
            matched = 0
            # Não encerrar iteração antecipadamente: trailer só é validado
            # depois da leitura COMPLETA do ZIP.
            for record in feed.iter_records(archive, feed.annual_max_uncompressed_bytes):
                if record.trading_date.year != year or (
                    exact_day is not None and record.trading_date != exact_day
                ):
                    raise ValueError(f"Data incompatível com o período do arquivo: {archive.name}")
                key = (record.trading_symbol.upper(), record.trading_date)
                if key not in claims:
                    continue
                if record.market_type != B3_CASH_MARKET_TYPE or record.codbdi != "02":
                    continue
                if record.quote_factor != 1:
                    raise ValueError(
                        f"{record.trading_symbol}: fator de cotação não unitário; "
                        "não comparar preços com unidades incompatíveis."
                    )
                if record.currency != "R$":
                    raise ValueError(f"{record.trading_symbol}: moeda não é BRL.")
                if record.close_price is None or not record.close_price.is_finite() or record.close_price <= 0:
                    raise ValueError(f"{record.trading_symbol}: fechamento oficial inválido.")
                if key in found:
                    raise ValueError(
                        f"Cotação duplicada nos arquivos informados: {key[0]}, {key[1]}."
                    )
                found[key] = (record, digest)
                matched += len(claims[key])
            manifests.append(CotaHistArchiveEvidence(
                file_name=archive.name,
                sha256=digest,
                file_size_bytes=archive.stat().st_size,
                historical_period=period_name,
                records_matched=matched,
            ))
        missing = sorted(set(claims) - set(found))
        if missing:
            preview = ", ".join(f"{symbol}/{day}" for symbol, day in missing[:5])
            raise ValueError(f"Cotações não encontradas nos arquivos COTAHIST: {preview}.")
        report_rows = []
        for (symbol, trading_day), observations in sorted(claims.items()):
            record, digest = found[(symbol, trading_day)]
            for decision_at, expected in observations:
                if record.close_price != expected:
                    raise ValueError(
                        f"{symbol}/{trading_day}: preço do snapshot {expected} difere "
                        f"do fechamento COTAHIST {record.close_price}."
                    )
                report_rows.append(B3QuoteEvidence(
                    symbol=symbol, decision_at=decision_at, trading_date=trading_day,
                    close_price=record.close_price, isin=record.isin,
                    archive_sha256=digest, currency=record.currency,
                    quote_factor=record.quote_factor,
                ))
        return B3PriceAuditReport(
            checked_quotes=sum(len(v) for v in claims.values()),
            matched_quotes=len(report_rows), archives=manifests, quotes=report_rows
        )
