"""Verificação oficial e independente de demonstrações: CVM (cache importado)
e SEC EDGAR (API aberta, opt-in User-Agent real).

Somente diagnóstico informativo. Nunca muda quotes, scores ou recomendações
de compra e NUNCA atribui confiança alta automaticamente.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.asset import Asset
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.repositories.cvm_fii_repository import CvmFiiRepository
from app.services.market_cache import TTLCache

SEC_ROOT = "https://data.sec.gov"
SEC_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}
US_EXCHANGES = {"NASDAQ", "NYSE", "NYSE AMERICAN"}
METRICS = {
    "assets": ("Assets",),
    "equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
    "net_income": ("NetIncomeLoss",),
}
METRIC_NAMES = frozenset(METRICS)
MAX_EDGAR_BYTES = 8 * 1024 * 1024
CACHE_TTL = 3600


class OfficialFact(BaseModel):
    metric: str
    value: Decimal
    unit: str
    period_end: date
    period_start: date | None = None
    filed_at: date | None = None
    document_type: str
    accession: str | None = None
    source: str
    source_url: str
    acquired_at: datetime
    detail: str | None = None


class OfficialVerification(BaseModel):
    symbol: str
    asset_class: str
    market: str
    status: Literal["verified_filing", "not_configured", "not_linked", "no_data", "identity_mismatch", "source_unavailable"]
    issuer_name: str | None = None
    issuer_id: str | None = None
    checked_at: datetime
    facts: list[OfficialFact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    interpretation: str = (
        "Confirma documento financeiro e identidade do emissor, não a "
        "cotação, o retorno futuro nem a qualidade de uma recomendação."
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(value) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None
    return out if out.is_finite() else None


def _sec_fact(payload: dict, metric: str, now: datetime, url: str) -> OfficialFact | None:
    facts = payload.get("facts", {}).get("us-gaap", {})
    if not isinstance(facts, dict):
        return None
    possibilities = []
    for tag in METRICS[metric]:
        concept = facts.get(tag)
        if not isinstance(concept, dict):
            continue
        usd = concept.get("units", {}).get("USD")
        if not isinstance(usd, list):
            continue
        for item in usd:
            if not isinstance(item, dict) or item.get("form") not in SEC_FORMS:
                continue
            value = _finite(item.get("val"))
            if value is None:
                continue
            try:
                ending = date.fromisoformat(item["end"])
                filed = date.fromisoformat(item["filed"])
                starting = date.fromisoformat(item["start"]) if item.get("start") else None
            except (KeyError, ValueError, TypeError):
                continue
            if ending > now.date() or filed > now.date() or filed < ending:
                continue
            if metric in {"assets", "equity"} and starting is not None:
                continue
            if metric in {"revenue", "net_income"}:
                if starting is None or (ending - starting).days not in range(65, 381):
                    continue
            accession = item.get("accn")
            if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                continue
            # Choose most recent reporting period, then latest known filing.
            # No mixing different revenue taxonomies within the same observation.
            possibilities.append((ending, filed, tag, value, starting, item["form"], accession))
    if not possibilities:
        return None
    ending, filed, tag, value, starting, form, accession = max(
        possibilities, key=lambda row: (row[0], row[1], row[2])
    )
    return OfficialFact(
        metric=metric, value=value, unit="USD", period_start=starting,
        period_end=ending, filed_at=filed, document_type=form,
        accession=accession, source="SEC EDGAR XBRL / us-gaap",
        source_url=url, acquired_at=now, detail=f"us-gaap:{tag}",
    )


class OfficialSourceVerificationService:
    """Readonly check on existing assets; identities are NEVER matched by name."""

    _cache: TTLCache[dict] = TTLCache()

    def __init__(self, cvm_repository: CvmFinancialRepository, *, fii_repository: CvmFiiRepository | None = None, client: httpx.Client | None = None,
                 user_agent: str | None = None):
        self.cvm_repository = cvm_repository
        self.fii_repository = fii_repository
        self.client = client
        self.user_agent = (user_agent if user_agent is not None else settings.SEC_USER_AGENT).strip()

    def _edgar_json(self, path: str) -> dict:
        cache_key = f"EDGAR:{path}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        if not self.user_agent or not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", self.user_agent):
            raise ValueError("SEC_USER_AGENT não configurado com contato real.")
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        url = f"{SEC_ROOT}{path}"
        try:
            if self.client is None:
                with httpx.Client(timeout=8, follow_redirects=False) as conn:
                    response = conn.get(url, headers=headers)
            else:
                response = self.client.get(url, headers=headers, timeout=8, follow_redirects=False)
            if response.status_code != 200:
                raise ValueError("SEC indisponível ou limitou a consulta.")
            if len(response.content) > MAX_EDGAR_BYTES:
                raise ValueError("Resposta SEC excede limite de dados.")
            obj = response.json()
            if not isinstance(obj, dict):
                raise ValueError("Resposta SEC em formato inesperado.")
        except (httpx.HTTPError, ValueError) as exc:
            raise ValueError("Consulta oficial SEC indisponível.") from exc
        self._cache.set(cache_key, obj, CACHE_TTL)
        return obj

    def verify_brazil(self, asset: Asset) -> OfficialVerification:
        now = _now()
        base = dict(symbol=asset.ticker, asset_class=asset.asset_type,
                    market="B3", checked_at=now)
        if not asset.is_active:
            return OfficialVerification(**base, status="no_data", warnings=["Ativo inativo no cadastro."])
        issuer = self.cvm_repository.linked_issuer(asset.id)
        if issuer is None:
            return OfficialVerification(**base, status="not_linked",
                warnings=["Ativo ainda não vinculado a emissor CVM por CNPJ oficial."])
        rows = self.cvm_repository.latest_normalized(asset.id)
        facts = []
        for account, document, linked in rows:
            metric = account.normalized_key
            if metric not in METRIC_NAMES or not account.is_fixed_account:
                continue
            if account.acquisition_method != "reported":
                continue
            # O campo moeda da CVM é textual (normalmente REAL). Não
            # carimbar valores USD ou moeda desconhecida como BRL.
            if str(document.currency).strip().upper() not in {"REAL", "REAIS", "BRL", "R$"}:
                continue
            value = _finite(account.normalized_value)
            if value is None:
                continue
            facts.append(OfficialFact(
                metric=metric, value=value, unit="BRL",
                period_start=document.period_start,
                period_end=document.period_end,
                # CVM reference_date is NOT the public filing date.
                filed_at=None, document_type=document.document_type,
                source="CVM Dados Abertos (arquivo importado)",
                source_url="https://dados.cvm.gov.br/dataset/cia_aberta-doc-" + document.document_type.lower(),
                acquired_at=now,
                detail=(f"cvm:{linked.cvm_code}; versão:{document.version}; "
                        f"conta:{account.account_code}; período:{document.period_kind}; "
                        f"data_referencia:{document.reference_date.isoformat()}; "
                        f"coletado_em:{document.collected_at.isoformat()}"),
            ))
        return OfficialVerification(**base, status="verified_filing" if facts else "no_data",
             issuer_name=issuer.official_name, issuer_id=f"CNPJ:{issuer.cnpj}",
             facts=sorted(facts, key=lambda x:x.metric),
             warnings=[
                 "Dados da CVM previamente importados no banco, sem atualização de rede nesta consulta.",
                 "Não há prova do horário de publicação original; data de competência não é data de publicação.",
                 "Métricas com períodos distintos não são diretamente comparáveis.",
             ])

    def verify_fii(self, asset: Asset) -> OfficialVerification:
        now = _now()
        base = dict(symbol=asset.ticker, asset_class=asset.asset_type,
                    market="B3", checked_at=now)
        if not asset.is_active:
            return OfficialVerification(**base, status="no_data",
                warnings=["FII inativo no cadastro."])
        if self.fii_repository is None:
            return OfficialVerification(**base, status="source_unavailable",
                warnings=["Repositório oficial de FIIs indisponível."])
        issuer = self.fii_repository.linked_issuer(asset.id)
        if issuer is None:
            return OfficialVerification(**base, status="not_linked",
                warnings=["FII ainda não vinculado à CVM por CNPJ."])
        doc = self.fii_repository.latest_vacancy_document(issuer.id)
        fact = None
        if doc is not None:
            vacancy = _finite(doc.area_weighted_vacancy_rate)
            if vacancy is not None and 0 <= vacancy <= 1 and doc.property_count > 0:
                fact = OfficialFact(
                    metric="vacancy_rate", value=vacancy, unit="ratio",
                    period_end=doc.reference_date, document_type="INF_TRIMESTRAL",
                    source="CVM FII Dados Abertos (arquivo importado)",
                    source_url="https://dados.cvm.gov.br/dataset/fii-doc-inf_trimestral",
                    acquired_at=now,
                    detail=(f"CNPJ:{issuer.cnpj}; imóveis:{doc.property_count}; "
                            f"versão:{doc.version}; método:{doc.aggregation_method}; "
                            f"coletado_em:{doc.collected_at.isoformat()}"),
                )
        return OfficialVerification(
            **base, status="verified_filing" if fact else "no_data",
            issuer_name=issuer.official_name, issuer_id=f"CNPJ:{issuer.cnpj}",
            facts=[fact] if fact else [],
            warnings=[
                "Consulta de vacância já importada da CVM, não de preço negociado na B3.",
                "Não representa receita, rendimento distribuído ou retorno total do FII.",
            ],
        )

    def verify_sec(self, asset: Asset, cik: str | None) -> OfficialVerification:
        now = _now()
        base = dict(symbol=asset.ticker, asset_class=asset.asset_type,
                    market="USA", checked_at=now)
        exchange = (asset.exchange or "").upper().strip()
        if not asset.is_active or exchange not in US_EXCHANGES or asset.asset_type.lower() not in {"international", "ativo internacional", "ativos internacionais"}:
            return OfficialVerification(**base, status="identity_mismatch",
                warnings=["Consulta SEC limitada a ações americanas cadastradas com bolsa NASDAQ/NYSE/NYSE AMERICAN."])
        if cik is None or not re.fullmatch(r"[0-9]{1,10}", cik) or int(cik) == 0:
            return OfficialVerification(**base, status="not_linked",
                warnings=["Informe o CIK oficial; não é permitido deduzi-lo pelo nome da empresa."])
        if not self.user_agent or not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", self.user_agent):
            return OfficialVerification(**base, status="not_configured",
                warnings=["SEC_USER_AGENT com nome e contato real precisa estar configurado no backend."])
        numeric_cik = int(cik)
        padded = f"{numeric_cik:010d}"
        try:
            submission = self._edgar_json(f"/submissions/CIK{padded}.json")
        except ValueError:
            return OfficialVerification(**base, status="source_unavailable",
                warnings=["Consulta ao cadastro oficial da SEC não respondeu."])
        if str(submission.get("cik")) != str(numeric_cik):
            return OfficialVerification(**base, status="identity_mismatch",
                warnings=["CIK devolvido não corresponde ao CIK solicitado."])
        tickers = submission.get("tickers", [])
        exchanges = submission.get("exchanges", [])
        if not isinstance(tickers, list) or not isinstance(exchanges, list) or len(tickers) != len(exchanges):
            return OfficialVerification(**base, status="identity_mismatch",
                warnings=["Cadastro SEC sem pares ticker/bolsa verificáveis."])
        if (asset.ticker.upper(), exchange) not in {
            (str(t).upper(), str(e).upper()) for t, e in zip(tickers, exchanges)
        }:
            return OfficialVerification(**base, status="identity_mismatch",
                warnings=["Ticker e bolsa cadastrados não correspondem ao registro SEC."])
        url = f"{SEC_ROOT}/api/xbrl/companyfacts/CIK{padded}.json"
        try:
            payload = self._edgar_json(f"/api/xbrl/companyfacts/CIK{padded}.json")
        except ValueError:
            return OfficialVerification(**base, status="source_unavailable",
                issuer_name=str(submission.get("name") or "")[:200],
                issuer_id=f"CIK:{padded}",
                warnings=["Identidade confirmada, porém demonstrações financeiras indisponíveis."])
        if str(payload.get("cik")) != str(numeric_cik):
            return OfficialVerification(**base, status="identity_mismatch",
                warnings=["CIK do XBRL difere do registro oficial da empresa."])
        facts = [
            f for key in METRICS if (f := _sec_fact(payload, key, now, url)) is not None
        ]
        return OfficialVerification(**base, status="verified_filing" if facts else "no_data",
            issuer_name=str(submission.get("name") or "")[:200],
            issuer_id=f"CIK:{padded}", facts=facts,
            warnings=[
                "SEC/EDGAR fornece demonstrações, não cotações da NYSE/Nasdaq.",
                "Períodos e conceitos contábeis distintos não são intercambiáveis.",
                "Conferência de demonstrações não comprova acerto de compra ou desempenho.",
            ])
