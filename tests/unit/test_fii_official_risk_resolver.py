from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.asset import Asset
from app.repositories.cvm_fii_repository import CvmFiiRepository
from app.schemas.market_intelligence import (
    ConfidenceLevel,
    IndicatorLayer,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
)
from app.services.indicator_normalization_service import IndicatorNormalizationService
from app.services.indicator_resolver_service import IndicatorResolverService


NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


def _fresh_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def baseline_indicator(key: str) -> NormalizedIndicator:
    return NormalizedIndicator(
        key=key,
        label=key,
        layer=IndicatorLayer.FUNDAMENTAL,
        value=None,
        unit="percent",
        status=IndicatorStatus.UNAVAILABLE,
        source="BRAPI",
        collected_at=NOW,
        confidence=ConfidenceLevel.INSUFFICIENT,
        unavailable_reason="Ausente.",
    )


class FakeMarket:
    def __init__(self, cnpj=None, fii_payloads=None):
        self.cnpj = cnpj
        self.fii_payloads = fii_payloads or {}

    def get_profile(self, symbol):
        return SimpleNamespace(cnpj=self.cnpj)

    def get_fii_dataset(self, dataset, symbols, **params):
        payload = self.fii_payloads.get(dataset)
        if isinstance(payload, Exception):
            raise payload
        return payload or {}

    def get_stock_dataset(self, dataset, symbols, **params):
        return {}


class NoProfileMarket:
    def get_profile(self, symbol):
        raise RuntimeError("sem perfil")

    def get_fii_dataset(self, dataset, symbols, **params):
        return {}


def _seed_fii_repository(session_factory, *, cnpj, reference_date, vacancy_rate):
    db = session_factory()
    repo = CvmFiiRepository(db)
    issuer = repo.upsert_issuer(cnpj, "FUNDO TESTE FII")
    db.commit()
    issuer_id = issuer.id
    repo.upsert_vacancy_document(
        issuer_id,
        reference_date=reference_date,
        version=1,
        property_count=10,
        area_weighted_vacancy_rate=vacancy_rate,
        aggregation_method="média ponderada pela área (teste)",
        source_resource="inf_trimestral_fii_imovel_2026.csv",
        collected_at=NOW,
    )
    db.commit()
    db.close()
    return issuer_id


def _make_resolver(*, cnpj=None, session_factory=None, fii_payloads=None):
    session_factory = session_factory or _fresh_session_factory()
    db = session_factory()
    cvm_fii_repository = CvmFiiRepository(db)
    resolver = IndicatorResolverService(
        market_service=FakeMarket(cnpj=cnpj, fii_payloads=fii_payloads),
        normalizer=IndicatorNormalizationService(),
        cvm_fii_repository=cvm_fii_repository,
        fii_link_session_factory=session_factory,
    )
    return resolver, session_factory, db


# --- Resolução via dado oficial CVM (auto-link + vacância) ------------------


def test_physical_vacancy_resolves_via_cvm_official_when_linked_by_exact_cnpj():
    session_factory = _fresh_session_factory()
    cnpj = "11222333000181"
    _seed_fii_repository(
        session_factory,
        cnpj=cnpj,
        reference_date=date(2026, 6, 30),
        vacancy_rate=Decimal("0.0512"),
    )
    resolver, _, db = _make_resolver(
        cnpj="11.222.333/0001-81", session_factory=session_factory
    )
    asset_id = uuid4()
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=asset_id,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.value == Decimal("0.0512")
    assert item.source == "CVM Dados Abertos (FII)"
    assert item.source_type == "official"
    assert item.provenance["cnpj_fundo_classe"] == cnpj
    db.close()


def test_physical_vacancy_never_overwrites_value_already_resolved_by_brapi():
    session_factory = _fresh_session_factory()
    cnpj = "22333444000162"
    _seed_fii_repository(
        session_factory,
        cnpj=cnpj,
        reference_date=date(2026, 6, 30),
        vacancy_rate=Decimal("0.9999"),
    )
    already_resolved = baseline_indicator("physical_vacancy").model_copy(
        update={
            "status": IndicatorStatus.AVAILABLE,
            "value": Decimal("0.03"),
            "source": "BRAPI",
        }
    )
    resolver, _, db = _make_resolver(
        cnpj="22.333.444/0001-62", session_factory=session_factory
    )
    asset_id = uuid4()
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=asset_id,
        user_id="user",
        baseline=[already_resolved],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.value == Decimal("0.03")
    assert item.source == "BRAPI"
    db.close()


def test_physical_vacancy_expired_official_document_is_never_used_as_current():
    session_factory = _fresh_session_factory()
    cnpj = "33444555000143"
    # Documento de mais de um ano atras -- ja passou de qualquer prazo
    # trimestral razoavel, nunca deve ser tratado como atual.
    _seed_fii_repository(
        session_factory,
        cnpj=cnpj,
        reference_date=date(2024, 3, 31),
        vacancy_rate=Decimal("0.05"),
    )
    resolver, _, db = _make_resolver(
        cnpj="33.444.555/0001-43", session_factory=session_factory
    )
    asset_id = uuid4()
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=asset_id,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status != IndicatorStatus.AVAILABLE
    db.close()


def test_fii_official_risk_gracefully_degrades_when_profile_lookup_fails():
    session_factory = _fresh_session_factory()
    db = session_factory()
    resolver = IndicatorResolverService(
        market_service=NoProfileMarket(),
        normalizer=IndicatorNormalizationService(),
        cvm_fii_repository=CvmFiiRepository(db),
        fii_link_session_factory=session_factory,
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=uuid4(),
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status != IndicatorStatus.AVAILABLE
    db.close()


def test_fii_auto_link_never_overwrites_link_to_a_different_fund():
    session_factory = _fresh_session_factory()
    db = session_factory()
    repo = CvmFiiRepository(db)
    asset = Asset(ticker="FIIX11", name="Fundo X", asset_type="FII", currency="BRL")
    db.add(asset)
    db.commit()
    issuer_a = repo.upsert_issuer("11222333000181", "FUNDO A")
    repo.upsert_issuer("22333444000162", "FUNDO B")
    db.commit()
    repo.ensure_asset_link(asset.id, issuer_a.id)
    db.commit()

    resolver = IndicatorResolverService(
        market_service=FakeMarket(cnpj="22.333.444/0001-62"),
        normalizer=IndicatorNormalizationService(),
        cvm_fii_repository=repo,
        fii_link_session_factory=session_factory,
    )
    linked = resolver._auto_link_fii_issuer(asset.id, "FIIX11")
    assert linked is None

    link = repo.find_link(asset.id)
    assert link.issuer_id == issuer_a.id
    db.close()


# --- debtor_concentration computado a partir de fii/portfolio ---------------


def test_debtor_concentration_computed_from_real_financial_assets_list():
    portfolio_payload = {
        "fiis": [
            {
                "symbol": "TESTFII",
                "referenceDate": "2026-06-30",
                "financialAssets": [
                    {"issuerCnpj": "AAA", "value": 300000},
                    {"issuerCnpj": "BBB", "value": 700000},
                ],
            }
        ]
    }
    resolver = IndicatorResolverService(
        market_service=FakeMarket(fii_payloads={"portfolio": portfolio_payload}),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("debtor_concentration")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "debtor_concentration")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.value == Decimal("700000") / Decimal("1000000")
    assert item.source == "BRAPI"


def test_debtor_concentration_never_fabricates_a_value_when_financial_assets_missing():
    resolver = IndicatorResolverService(
        market_service=FakeMarket(fii_payloads={"portfolio": {"fiis": [{"symbol": "TESTFII"}]}}),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("debtor_concentration")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "debtor_concentration")
    assert item.status != IndicatorStatus.AVAILABLE
    assert item.value is None
