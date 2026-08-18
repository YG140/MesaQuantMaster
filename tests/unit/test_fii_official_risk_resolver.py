from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
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
from app.services.indicator_resolver_service import (
    IndicatorResolverService,
    _fii_quarterly_valid_until,
)


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
    """CONTRATO DE ESCALA: o campo oficial Percentual_Vacancia (e a
    coluna agregada area_weighted_vacancy_rate, na mesma escala) é uma
    FRAÇÃO (0-1) -- 0,0512 = 5,12%. O indicador resolvido deve estar em
    PONTOS PERCENTUAIS (contrato interno de unit="percent", ver
    display_value): 5.12, nunca 0.0512."""
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
    assert item.value == Decimal("5.12")
    assert item.display_value == "5.12%"
    assert item.source == "CVM Dados Abertos (FII)"
    assert item.source_type == "official"
    assert item.provenance["cnpj_fundo_classe"] == cnpj
    db.close()


def test_physical_vacancy_collected_at_is_the_documents_own_collection_time():
    """BLOQUEADOR 4: collected_at do indicador deve vir do documento
    oficial (quando ele foi de fato coletado/sincronizado), nunca do
    horário desta análise -- são informações diferentes."""
    session_factory = _fresh_session_factory()
    cnpj = "44555666000124"
    document_collected_at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    analysis_collected_at = datetime(2026, 8, 18, 15, 30, tzinfo=timezone.utc)

    db = session_factory()
    repo = CvmFiiRepository(db)
    issuer = repo.upsert_issuer(cnpj, "FUNDO TESTE FII")
    db.commit()
    issuer_id = issuer.id
    repo.upsert_vacancy_document(
        issuer_id,
        reference_date=date(2026, 6, 30),
        version=1,
        property_count=5,
        area_weighted_vacancy_rate=Decimal("0.03"),
        aggregation_method="média ponderada pela área (teste)",
        source_resource="inf_trimestral_fii_imovel_2026.csv",
        collected_at=document_collected_at,
    )
    db.commit()
    db.close()

    resolver, _, db2 = _make_resolver(
        cnpj="44.555.666/0001-24", session_factory=session_factory
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=uuid4(),
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=analysis_collected_at,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.collected_at == document_collected_at
    assert item.collected_at != analysis_collected_at
    db2.close()


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


def _official_vacancy_status_at(cnpj_digits, cnpj_formatted, reference_date, collected_at):
    session_factory = _fresh_session_factory()
    _seed_fii_repository(
        session_factory,
        cnpj=cnpj_digits,
        reference_date=reference_date,
        vacancy_rate=Decimal("0.02"),
    )
    resolver, _, db = _make_resolver(cnpj=cnpj_formatted, session_factory=session_factory)
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=uuid4(),
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=collected_at,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    db.close()
    return item.status


# Prazo REGULATÓRIO CONFIRMADO (ver FII_QUARTERLY_FILING_DEADLINE_DAYS,
# Art. 36, II, Anexo Normativo III da Resolução CVM 175/2022): trimestralmente,
# até 45 dias após o encerramento do trimestre a que se referir. Valores de
# valid_until abaixo calculados diretamente por _fii_quarterly_valid_until
# (nunca transcritos manualmente), cobrindo os 4 fins de trimestre do ano.
@pytest.mark.parametrize(
    "reference_date,valid_until_boundary",
    [
        (date(2026, 3, 31), datetime(2026, 8, 14, tzinfo=timezone.utc)),
        (date(2026, 6, 30), datetime(2026, 11, 14, tzinfo=timezone.utc)),
        (date(2026, 9, 30), datetime(2027, 2, 14, tzinfo=timezone.utc)),
        (date(2026, 12, 31), datetime(2027, 5, 15, tzinfo=timezone.utc)),
    ],
)
def test_physical_vacancy_official_document_boundaries_per_quarter(
    reference_date, valid_until_boundary
):
    cnpj = f"{reference_date.month:02d}{reference_date.day:02d}0000000181"
    assert len(cnpj) == 14
    formatted = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

    # Imediatamente ANTES do vencimento -- ainda atual.
    before = _official_vacancy_status_at(
        cnpj, formatted, reference_date, valid_until_boundary - timedelta(seconds=1)
    )
    assert before == IndicatorStatus.AVAILABLE

    # NO instante exato do vencimento -- ainda atual (limite inclusivo:
    # _apply_fii_official_risk só recusa quando collected_at > valid_until).
    at_deadline = _official_vacancy_status_at(
        cnpj, formatted, reference_date, valid_until_boundary
    )
    assert at_deadline == IndicatorStatus.AVAILABLE

    # Imediatamente DEPOIS do vencimento -- já stale/não usado como atual.
    after = _official_vacancy_status_at(
        cnpj, formatted, reference_date, valid_until_boundary + timedelta(seconds=1)
    )
    assert after != IndicatorStatus.AVAILABLE


def test_fii_quarterly_valid_until_uses_the_real_calendar_quarter_end_not_add_months_clamping():
    """RESÍDUO B: 30/09 é fim de trimestre-calendário real; o PRÓXIMO
    trimestre termina genuinamente em 31/12 -- nunca 30/12, que seria o
    resultado de somar 3 meses ingenuamente e clampar o dia (viés de
    _add_months, usado pela lógica CVM corporativa e deliberadamente NÃO
    reaproveitado aqui). Expectativa conferida de forma independente
    (sem chamar a própria função para produzi-la): 31/12/2026 + 45 dias
    corridos -- dezembro contribui 0 dias restantes (a contagem começa
    em 01/01), janeiro contribui seus 31 dias completos (31/45), e os 14
    dias finais caem em fevereiro -- 14/02/2027."""
    result = _fii_quarterly_valid_until(date(2026, 9, 30))
    assert result == datetime(2027, 2, 14, tzinfo=timezone.utc)
    assert result != datetime(2027, 2, 13, tzinfo=timezone.utc)  # valor do bug antigo


def test_fii_quarterly_valid_until_returns_none_for_non_quarter_end_reference_date():
    """RESÍDUO B: uma reference_date que não é literalmente o último dia
    de um trimestre-calendário real (31/03, 30/06, 30/09, 31/12) nunca
    deve gerar uma janela trimestral fabricada -- o chamador deve cair
    para o fallback técnico conservador."""
    assert _fii_quarterly_valid_until(date(2026, 6, 15)) is None
    assert _fii_quarterly_valid_until(date(2026, 7, 1)) is None
    assert _fii_quarterly_valid_until(date(2026, 12, 30)) is None


def test_physical_vacancy_missing_reference_date_never_uses_collected_at_as_reference():
    """RESÍDUO A: quando o provedor não informa referenceDate, o
    indicador nunca finge que a competência econômica é o instante da
    coleta -- reference_date permanece None mesmo entre duas coletas em
    momentos diferentes, e a validade cai para o fallback técnico
    conservador genérico (collected_at + 30 dias), nunca uma janela
    trimestral fabricada."""
    properties_payload = {
        "fiis": [{"symbol": "TESTFII", "summary": {"vacancyRate": 0.02}}]
    }
    for collected_at in (
        datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 15, 18, 30, tzinfo=timezone.utc),
    ):
        resolver = IndicatorResolverService(
            market_service=FakeMarket(fii_payloads={"properties": properties_payload}),
            normalizer=IndicatorNormalizationService(),
        )
        resolved = resolver.resolve_asset(
            symbol="TESTFII",
            asset_class=InvestmentClass.FII,
            asset_id=None,
            user_id="user",
            baseline=[baseline_indicator("physical_vacancy")],
            collected_at=collected_at,
        )
        item = next(i for i in resolved if i.key == "physical_vacancy")
        assert item.status == IndicatorStatus.AVAILABLE
        assert item.value == Decimal("2")
        assert item.reference_date is None
        assert item.reference_date != collected_at
        assert item.valid_until == collected_at + timedelta(days=30)


def test_physical_vacancy_invalid_reference_date_never_grants_artificial_quarter_window():
    """RESÍDUO A: referenceDate presente mas ilegível (formato inválido)
    é tratado exatamente como ausente -- nunca vira collected_at, nunca
    concede uma janela trimestral."""
    properties_payload = {
        "fiis": [
            {
                "symbol": "TESTFII",
                "referenceDate": "not-a-date",
                "summary": {"vacancyRate": 0.02},
            }
        ]
    }
    resolver = IndicatorResolverService(
        market_service=FakeMarket(fii_payloads={"properties": properties_payload}),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.reference_date is None
    assert item.valid_until == NOW + timedelta(days=30)


def test_physical_vacancy_reference_date_not_a_real_quarter_end_never_grants_artificial_quarter_window():
    """RESÍDUO A + B: referenceDate presente e parseável, mas não é
    literalmente o fim de um trimestre-calendário real (15/06 é meio de
    trimestre) -- o valor real é preservado em reference_date (não é
    apagado), mas não gera uma janela trimestral fabricada; cai para o
    fallback técnico conservador."""
    properties_payload = {
        "fiis": [
            {
                "symbol": "TESTFII",
                "referenceDate": "2026-06-15",
                "summary": {"vacancyRate": 0.02},
            }
        ]
    }
    resolver = IndicatorResolverService(
        market_service=FakeMarket(fii_payloads={"properties": properties_payload}),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.reference_date == datetime(2026, 6, 15, tzinfo=timezone.utc)
    assert item.valid_until == NOW + timedelta(days=30)


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
    """CONTRATO DE ESCALA: _largest_issuer_share() calcula uma FRAÇÃO
    (700000/1000000 = 0.70); o indicador resolvido deve estar em PONTOS
    PERCENTUAIS -- 70.00, nunca 0.70 (0.70% seria uma ordem de grandeza
    errada)."""
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
    assert item.value == Decimal("70")
    assert item.display_value == "70.00%"
    assert item.source == "BRAPI"


def test_physical_vacancy_from_brapi_properties_dataset_is_in_percentage_points():
    """Mesmo contrato de escala, agora pela via BRAPI direta
    (fii/properties.summary.vacancyRate): fração 0.024133 -> 2.4133 pontos
    percentuais, nunca 0.024133%."""
    properties_payload = {
        "fiis": [
            {
                "symbol": "TESTFII",
                "referenceDate": "2026-06-30",
                "summary": {
                    "count": 37,
                    "vacancyRate": 0.024133196979528197,
                },
            }
        ]
    }
    resolver = IndicatorResolverService(
        market_service=FakeMarket(fii_payloads={"properties": properties_payload}),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.value == Decimal("0.024133196979528197") * Decimal("100")
    assert str(item.value).startswith("2.4133")
    assert item.source == "BRAPI"
    assert item.provenance["dataset"] == "fii/properties"


def test_physical_vacancy_provenance_points_to_the_dataset_that_actually_answered():
    """BLOQUEADOR 5: provenance.dataset deve ser o dataset REAL que o
    resolver efetivamente chamou e que respondeu com o campo -- nunca
    inferido pela forma do JSON. Aqui `properties` e `portfolio` têm
    estruturas parecidas (ambos têm summary com vacancyRate em algum
    nível) mas só um dos dois é o dataset verdadeiro em cada cenário.
    """
    # Cenário 1: só properties tem o campo -- provenance deve apontar
    # para fii/properties, mesmo que portfolio também tenha sido chamado
    # (sem o campo).
    resolver = IndicatorResolverService(
        market_service=FakeMarket(
            fii_payloads={
                "properties": {
                    "fiis": [
                        {
                            "symbol": "TESTFII",
                            "referenceDate": "2026-06-30",
                            "summary": {"vacancyRate": 0.03},
                        }
                    ]
                },
                "portfolio": {
                    "fiis": [
                        {"symbol": "TESTFII", "referenceDate": "2026-06-30", "summary": {}}
                    ]
                },
            }
        ),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.provenance["dataset"] == "fii/properties"

    # Cenário 2: properties não trouxe o campo (payload existe mas sem
    # vacancyRate), só portfolio tem -- provenance deve apontar para
    # fii/portfolio, o dataset que realmente respondeu.
    resolver2 = IndicatorResolverService(
        market_service=FakeMarket(
            fii_payloads={
                "properties": {
                    "fiis": [
                        {"symbol": "TESTFII", "referenceDate": "2026-06-30", "summary": {}}
                    ]
                },
                "portfolio": {
                    "fiis": [
                        {
                            "symbol": "TESTFII",
                            "referenceDate": "2026-06-30",
                            "summary": {"properties": {"vacancyRate": 0.04}},
                        }
                    ]
                },
            }
        ),
        normalizer=IndicatorNormalizationService(),
    )
    resolved2 = resolver2.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item2 = next(i for i in resolved2 if i.key == "physical_vacancy")
    assert item2.provenance["dataset"] == "fii/portfolio"


def test_physical_vacancy_valid_until_is_stable_across_different_collection_times():
    """BLOQUEADOR 3: o mesmo referenceDate econômico (2026-06-30),
    consultado em dois momentos de coleta diferentes, deve produzir o
    MESMO valid_until -- nunca duas janelas de validade diferentes só
    porque a consulta aconteceu em horários distintos."""
    properties_payload = {
        "fiis": [
            {
                "symbol": "TESTFII",
                "referenceDate": "2026-06-30",
                "summary": {"vacancyRate": 0.02},
            }
        ]
    }
    collected_at_1 = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    collected_at_2 = datetime(2026, 9, 15, 18, 30, tzinfo=timezone.utc)

    valid_untils = []
    for collected_at in (collected_at_1, collected_at_2):
        resolver = IndicatorResolverService(
            market_service=FakeMarket(fii_payloads={"properties": properties_payload}),
            normalizer=IndicatorNormalizationService(),
        )
        resolved = resolver.resolve_asset(
            symbol="TESTFII",
            asset_class=InvestmentClass.FII,
            asset_id=None,
            user_id="user",
            baseline=[baseline_indicator("physical_vacancy")],
            collected_at=collected_at,
        )
        item = next(i for i in resolved if i.key == "physical_vacancy")
        valid_untils.append(item.valid_until)

    assert valid_untils[0] == valid_untils[1]
    assert valid_untils[0] == datetime(2026, 11, 14, tzinfo=timezone.utc)


def test_physical_vacancy_from_brapi_portfolio_nested_summary_is_in_percentage_points():
    """Mesmo campo, mas vindo do dataset fii/portfolio (aninhado um nível
    a mais: summary.properties.vacancyRate) -- mesmo contrato de escala."""
    portfolio_payload = {
        "fiis": [
            {
                "symbol": "TESTFII",
                "referenceDate": "2026-06-30",
                "summary": {"properties": {"vacancyRate": 0.05}},
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
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.value == Decimal("5")
    assert item.display_value == "5.00%"


def test_physical_vacancy_zero_explicit_is_preserved_never_becomes_none():
    properties_payload = {
        "fiis": [
            {"symbol": "TESTFII", "referenceDate": "2026-06-30", "summary": {"vacancyRate": 0}}
        ]
    }
    resolver = IndicatorResolverService(
        market_service=FakeMarket(fii_payloads={"properties": properties_payload}),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.value == Decimal("0")
    assert item.display_value == "0.00%"


def test_physical_vacancy_missing_from_brapi_never_becomes_zero():
    properties_payload = {
        "fiis": [{"symbol": "TESTFII", "referenceDate": "2026-06-30", "summary": {"count": 2}}]
    }
    resolver = IndicatorResolverService(
        market_service=FakeMarket(fii_payloads={"properties": properties_payload}),
        normalizer=IndicatorNormalizationService(),
    )
    resolved = resolver.resolve_asset(
        symbol="TESTFII",
        asset_class=InvestmentClass.FII,
        asset_id=None,
        user_id="user",
        baseline=[baseline_indicator("physical_vacancy")],
        collected_at=NOW,
    )
    item = next(i for i in resolved if i.key == "physical_vacancy")
    assert item.status != IndicatorStatus.AVAILABLE
    assert item.value is None


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


# --- Caminho operacional: resolver nunca baixa o ZIP da CVM -----------------


def test_resolve_asset_never_touches_the_cvm_fii_download_provider():
    """BLOQUEADOR 3: o resolver só LÊ dados já sincronizados via
    CvmFiiRepository -- nunca instancia nem chama
    CvmFiiOpenDataProvider.download_year durante analyze/resolve. Isso é
    garantido estruturalmente (IndicatorResolverService nunca recebe uma
    referência ao provider), mas este teste prova isso em tempo de
    execução: qualquer tentativa de baixar o ZIP levantaria imediatamente.
    """
    from app.providers.cvm_fii_open_data_provider import CvmFiiOpenDataProvider

    original_download = CvmFiiOpenDataProvider.download_year

    def poison(self, year):
        raise AssertionError(
            "resolve_asset nunca deveria chamar CvmFiiOpenDataProvider.download_year"
        )

    CvmFiiOpenDataProvider.download_year = poison
    try:
        session_factory = _fresh_session_factory()
        cnpj = "55666777000105"
        _seed_fii_repository(
            session_factory,
            cnpj=cnpj,
            reference_date=date(2026, 6, 30),
            vacancy_rate=Decimal("0.02"),
        )
        resolver, _, db = _make_resolver(
            cnpj="55.666.777/0001-05", session_factory=session_factory
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
        assert item.status == IndicatorStatus.AVAILABLE
        db.close()
    finally:
        CvmFiiOpenDataProvider.download_year = original_download
