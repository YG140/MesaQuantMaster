"""Verificação oficial CVM/SEC — testes determinísticos, rede 100% simulada."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from app.models.cvm_financial import (
    CvmIssuer, AssetCvmIssuer, CvmFinancialDocument, CvmFinancialAccount
)
from app.models.cvm_fii import FiiIssuer, AssetFiiIssuer, FiiPropertyVacancyDocument
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.repositories.cvm_fii_repository import CvmFiiRepository
from app.services.official_source_verification_service import (
    OfficialSourceVerificationService
)

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
CIK = "0000320193"
SUBMISSIONS = {
    "cik": 320193, "name": "Synthetic Issuer",
    "tickers": ["EXM", "OTHER"], "exchanges": ["NASDAQ", "NYSE"]
}
FACTS = {
    "cik": 320193,
    "facts": {
        "us-gaap": {
            "Assets": {"units": {"USD": [
                {"val": 1000000, "end": "2025-12-31", "filed": "2026-02-20",
                 "form": "10-K", "accn": "0000320193-26-000001"},
            ]}},
            "Revenues": {"units": {"USD": [
                {"val": 230000, "start": "2025-01-01", "end": "2025-12-31",
                 "filed": "2026-02-20", "form": "10-K",
                 "accn": "0000320193-26-000001"},
            ]}},
        },
    },
}


def sec_client(*, submission=SUBMISSIONS, facts=FACTS, status=200):
    seen = []
    def handler(req):
        seen.append(req)
        if status != 200:
            return httpx.Response(status)
        if "/submissions/" in str(req.url):
            return httpx.Response(200, json=submission)
        return httpx.Response(200, json=facts)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return client, seen


def verified_service(db_session, client=None, agent="Mesa Quant User tests@example.org"):
    return OfficialSourceVerificationService(
        CvmFinancialRepository(db_session),
        fii_repository=CvmFiiRepository(db_session),
        client=client, user_agent=agent,
    )


def test_sec_validates_identity_and_returns_revenue_assets_with_filing_provenance(asset_factory, db_session):
    asset = asset_factory(ticker="EXM", name="Exemplo", asset_type="international")
    asset.currency = "USD"
    asset.exchange = "NASDAQ"
    db_session.commit()
    client, seen = sec_client()
    service = verified_service(db_session, client)
    service._cache.clear()
    response = service.verify_sec(asset, CIK)
    assert response.status == "verified_filing"
    assert response.issuer_id == f"CIK:{CIK}"
    assert {f.metric: f.value for f in response.facts} == {
        "assets": Decimal("1000000"), "revenue": Decimal("230000"),
    }
    assert all(f.unit == "USD" for f in response.facts)
    assert all(f.source.startswith("SEC EDGAR") for f in response.facts)
    assert len(seen) == 2
    assert all(r.headers["User-Agent"] == "Mesa Quant User tests@example.org" for r in seen)
    assert all(r.url.host == "data.sec.gov" for r in seen)
    # Requests still verified, but served from a cache bounded to an hour.
    assert service.verify_sec(asset, CIK).status == "verified_filing"
    assert len(seen) == 2


def test_sec_never_guesses_ticker_from_name_or_accepts_wrong_listing(asset_factory, db_session):
    asset = asset_factory(ticker="EXM", asset_type="international")
    asset.currency = "USD"
    asset.exchange = "NYSE"
    db_session.commit()
    client, seen = sec_client()
    service = verified_service(db_session, client)
    service._cache.clear()
    assert service.verify_sec(asset, CIK).status == "identity_mismatch"
    assert len(seen) == 1
    assert service.verify_sec(asset, None).status == "not_linked"


def test_sec_refuses_wrong_cik_companyfacts_or_missing_config(asset_factory, db_session):
    asset = asset_factory(ticker="EXM", asset_type="international")
    asset.currency = "USD"
    asset.exchange = "NASDAQ"
    db_session.commit()
    client, seen = sec_client(facts={**FACTS, "cik": 999})
    service = verified_service(db_session, client)
    service._cache.clear()
    assert service.verify_sec(asset, CIK).status == "identity_mismatch"
    assert verified_service(db_session, agent="").verify_sec(asset, CIK).status == "not_configured"
    assert service.verify_sec(asset, "0000000000").status == "not_linked"


def test_sec_mismatched_ticker_never_loads_companyfacts(asset_factory, db_session):
    asset = asset_factory(ticker="NOTEXM", asset_type="international")
    asset.currency = "USD"
    asset.exchange = "NASDAQ"
    db_session.commit()
    client, seen = sec_client()
    service = verified_service(db_session, client)
    service._cache.clear()
    assert service.verify_sec(asset, CIK).status == "identity_mismatch"
    assert len(seen) == 1


def test_sec_rejects_future_filing_unrelated_units_or_unverified_fields(asset_factory, db_session):
    asset = asset_factory(ticker="EXM", asset_type="international")
    asset.currency = "USD"
    asset.exchange = "NASDAQ"
    db_session.commit()
    bad = {"cik":320193, "facts":{"us-gaap":{"Assets":{"units":{"EUR":[
        {"val": 9000, "end":"2024-12-31","filed":"2025-03-20","form":"10-K",
         "accn":"0000320193-25-000001"}
    ], "USD":[
        {"val": 2000, "end":"2029-12-31","filed":"2029-03-20","form":"10-K",
         "accn":"0000320193-29-000001"}
    ]}}}}}
    client, _ = sec_client(facts=bad)
    service = verified_service(db_session, client)
    service._cache.clear()
    assert service.verify_sec(asset, CIK).status == "no_data"


def test_sec_offline_or_rate_limited_is_unavailable_not_fake_verified(asset_factory, db_session):
    asset = asset_factory(ticker="EXM", asset_type="international")
    asset.currency = "USD"
    asset.exchange = "NASDAQ"
    db_session.commit()
    client, _ = sec_client(status=429)
    service = verified_service(db_session, client)
    service._cache.clear()
    assert service.verify_sec(asset, CIK).status == "source_unavailable"


def test_cvm_stock_checks_link_and_reported_fixed_accounts_only(asset_factory, db_session):
    asset = asset_factory(ticker="EXEM3")
    service = verified_service(db_session)
    assert service.verify_brazil(asset).status == "not_linked"
    issuer = CvmIssuer(cnpj="12345678000199",cvm_code="12345",official_name="Companhia Exemplo")
    db_session.add(issuer)
    db_session.flush()
    db_session.add(AssetCvmIssuer(asset_id=asset.id, issuer_id=issuer.id))
    doc = CvmFinancialDocument(
        issuer_id=issuer.id, document_type="DFP", reference_date=date(2025,12,31),
        version=1, statement_type="BPA", scope="consolidated",
        period_start=None, period_end=date(2025,12,31),
        period_kind="point_in_time",currency="REAL",scale="UNIDADE",collected_at=NOW,
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(CvmFinancialAccount(
        document_id=doc.id,account_code="1",account_description="Ativo total",
        original_value=Decimal("50000"),normalized_value=Decimal("50000"),
        normalized_key="assets",is_fixed_account=True,acquisition_method="reported"
    ))
    db_session.commit()
    result = service.verify_brazil(asset)
    assert result.status == "verified_filing"
    assert result.issuer_id == "CNPJ:12345678000199"
    assert len(result.facts) == 1 and result.facts[0].value == Decimal("50000")
    assert result.facts[0].filed_at is None
    assert result.facts[0].unit == "BRL"


def test_cvm_fii_returns_only_documented_vacancy_ratio(asset_factory, db_session):
    asset = asset_factory(ticker="EXEM11", asset_type="FII")
    service = verified_service(db_session)
    assert service.verify_fii(asset).status == "not_linked"
    issuer = FiiIssuer(cnpj="11223344000188", official_name="Fundo Exemplo")
    db_session.add(issuer)
    db_session.flush()
    db_session.add(AssetFiiIssuer(asset_id=asset.id,issuer_id=issuer.id))
    db_session.add(FiiPropertyVacancyDocument(
        issuer_id=issuer.id, reference_date=date(2026,6,30), version=1,
        property_count=4, area_weighted_vacancy_rate=Decimal("0.125"),
        aggregation_method="area_weighted", source_resource="cvm-exemplo",
        collected_at=NOW
    ))
    db_session.commit()
    result = service.verify_fii(asset)
    assert result.status == "verified_filing"
    assert result.facts[0].unit == "ratio"
    assert result.facts[0].value == Decimal("0.125")
    assert "cotação" in " ".join(result.warnings).lower() or "preço" in " ".join(result.warnings).lower()


def test_official_endpoint_requires_login_and_refuses_unknown_assets(unauthenticated_client):
    assert unauthenticated_client.get("/intelligence/official-verification/EXM").status_code == 401


def test_official_endpoint_returns_cvm_missing_link_and_rejects_bad_type(client, asset_factory):
    asset_factory(ticker="EXEM3")
    assert client.get("/intelligence/official-verification/EXEM3").json()["status"] == "not_linked"
    assert client.get("/intelligence/official-verification/NOPE3").status_code == 404
    assert client.get("/intelligence/official-verification/EXEM3?cik=abcdef").status_code == 422
    asset_factory(ticker="CRPT",asset_type="crypto")
    assert client.get("/intelligence/official-verification/CRPT").status_code == 422
