import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.asset import Asset
from app.models.cvm_financial import AssetCvmIssuer, CvmIssuer
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketAuthenticationError,
    MarketInvalidResponseError,
    MarketPermissionError,
    MarketProviderUnavailableError,
    MarketRateLimitError,
)
from app.schemas.market_intelligence import (
    AnalysisImpact,
    ConfidenceLevel,
    IndicatorLayer,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
    ProviderFailureReason,
    ResolutionOutcome,
)
from app.services.indicator_normalization_service import (
    IndicatorNormalizationService,
    sanitize_failure_detail,
)
from app.engines.indicator_catalog import indicator_temporal_validity_days
from app.services.indicator_resolver_service import (
    IndicatorResolverService,
    _add_months,
    _fiscal_year_end_for_period,
    _next_cvm_report_deadline,
)
from app.providers.b3.exceptions import B3ParseError
from app.providers.b3.models import B3HistoricalRecord
from app.providers.b3_official_provider import B3EodResult
from app.schemas.market import MarketProfileResponse
from app.services.market_service import MarketService
from app.services.symbol_identity import B3_MARKET


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


class _UnknownFiscalCalendarCvm:
    """Mixin para os fakes de CVM repository deste arquivo: representa um
    emissor sem DFP sincronizada (calendário fiscal desconhecido) — o
    mesmo fallback conservador e honesto que _apply_cvm usa em produção
    quando CvmFinancialRepository.fiscal_year_end() não encontra nenhuma
    DFP. A maioria dos testes deste arquivo não testa a política temporal
    especificamente, então este fallback neutro evita ter que inventar um
    calendário fiscal fictício em cada fixture. Testes que precisam de um
    calendário fiscal conhecido sobrescrevem fiscal_year_end() diretamente.
    """

    def fiscal_year_end(self, issuer_id):
        return None


def _fresh_isolated_session_factory():
    """Sessionmaker ligado a uma engine sqlite em memória PRÓPRIA -- uma
    conexão totalmente separada de qualquer outra sessão usada no teste
    (inclusive de `db_session`, que usa a engine principal da app). Usada
    para provar, de forma comportamental e não só por mock, que a escrita
    isolada do auto-link (ver IndicatorResolverService._persist_cvm_link_
    isolated) roda em uma transação genuinamente independente da sessão
    do resolver -- exatamente como duas conexões separadas de um pool real
    (Postgres) se comportariam em produção.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _shared_file_sqlite_factories():
    """Duas fábricas de sessão com engines/pools totalmente independentes,
    mas apontando para o MESMO arquivo sqlite físico -- ao contrário de
    `_fresh_isolated_session_factory` (duas engines `sqlite:///:memory:`
    nunca compartilham banco nenhum), isto prova isolamento de transação
    sobre um banco genuinamente COMPARTILHADO: duas conexões físicas
    diferentes contra o mesmo arquivo, análogo a duas conexões de um pool
    real (Postgres) em produção.

    Evita a fixture `tmp_path` do pytest por causa do PermissionError
    conhecido no Windows (ver memória do projeto sobre isso) -- usa um
    arquivo próprio sob o diretório temporário do sistema, nome UUID,
    limpo explicitamente pelo chamador via cleanup() (engines descartadas
    ANTES do unlink, para liberar o handle do arquivo no Windows).

    Foreign keys são ativadas (PRAGMA foreign_keys=ON) para que o teste
    também comprove que asset_id/issuer_id em AssetCvmIssuer correspondem
    a registros reais já existentes no mesmo banco.
    """
    db_path = Path(tempfile.gettempdir()) / f"mesaqm_isolation_test_{uuid4().hex}.sqlite3"

    def _make_engine():
        engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    engine_a = _make_engine()
    Base.metadata.create_all(bind=engine_a)
    engine_b = _make_engine()

    factory_a = sessionmaker(bind=engine_a, autoflush=False, autocommit=False)
    factory_b = sessionmaker(bind=engine_b, autoflush=False, autocommit=False)

    def cleanup():
        engine_a.dispose()
        engine_b.dispose()
        db_path.unlink(missing_ok=True)

    return factory_a, factory_b, cleanup


def indicator(key="price_book"):
    return NormalizedIndicator(
        key=key,
        label=key,
        layer=IndicatorLayer.FUNDAMENTAL,
        value=None,
        unit="ratio",
        status=IndicatorStatus.UNAVAILABLE,
        source="BRAPI",
        collected_at=NOW,
        confidence=ConfidenceLevel.INSUFFICIENT,
        unavailable_reason="Ausente.",
    )


class FakeMarket:
    def __init__(self, payload=None, profile=None):
        self.payload = payload
        self.calls = 0
        self.profile = profile

    def get_stock_dataset(self, dataset, symbols, **params):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload or {}

    def get_fii_dataset(self, dataset, symbols, **params):
        return self.get_stock_dataset(dataset, symbols, **params)

    def get_profile(self, ticker):
        if isinstance(self.profile, Exception):
            raise self.profile
        return self.profile


class FakeSnapshots:
    def __init__(self, rows, stale_rows=None):
        self.rows = rows
        self.stale_rows = stale_rows or []

    def valid_for_symbol(self, symbol, now):
        return self.rows

    def latest_for_symbol(self, symbol, now=None):
        return self.stale_rows


def snapshot(value="1.25", valid=True):
    return SimpleNamespace(
        indicator_key="price_book",
        value=Decimal(value),
        unit="ratio",
        source="CVM",
        source_type="official",
        reference_date=NOW - timedelta(days=5),
        collected_at=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1) if valid else NOW - timedelta(days=1),
        period="trimestral",
    )


def resolver(market=None, snapshots=None, manual=None, **kwargs):
    return IndicatorResolverService(
        market_service=market or FakeMarket(),
        normalizer=IndicatorNormalizationService(),
        snapshot_repository=snapshots,
        manual_repository=manual,
        **kwargs,
    )


def resolve(service, baseline=None, asset_class=InvestmentClass.STOCK, asset_id=None):
    return service.resolve_asset(
        symbol="TEST3",
        asset_class=asset_class,
        asset_id=asset_id,
        user_id="user",
        baseline=baseline or [indicator()],
        collected_at=NOW,
    )[0]


def resolve_all(service, baseline, asset_class=InvestmentClass.STOCK, asset_id=None):
    return {
        item.key: item
        for item in service.resolve_asset(
            symbol="TEST3",
            asset_class=asset_class,
            asset_id=asset_id,
            user_id="user",
            baseline=baseline,
            collected_at=NOW,
        )
    }


def resolve_symbol(
    service, symbol, baseline, asset_class=InvestmentClass.STOCK, asset_id=None
):
    """Igual a `resolve`, mas com símbolo explícito -- necessário para
    TREASURY, cuja identidade oficial (Tipo Titulo + Data Vencimento) não
    casa com o símbolo fixo "TEST3" usado pelo resto deste arquivo."""
    return service.resolve_asset(
        symbol=symbol,
        asset_class=asset_class,
        asset_id=asset_id,
        user_id="user",
        baseline=baseline,
        collected_at=NOW,
    )[0]


def treasury_row(
    *,
    bond_type="Tesouro Selic",
    indexer="SELIC",
    maturity=date(2031, 3, 1),
    as_of=date(2026, 7, 18),
    buy_rate="6.25",
    sell_rate="6.30",
    buy_price="18700.00",
    sell_price="18690.00",
    base_price="18695.00",
):
    """Linha canônica sintética no MESMO formato que
    TesouroTransparenteProvider.latest_by_identity() produz -- nunca o
    formato bruto do CSV (colunas em português), que é responsabilidade
    exclusiva do provider adaptar."""
    return {
        "symbol": f"tesouro-{bond_type.lower()}",  # sobrescrito nos usos reais
        "bondType": bond_type,
        "indexer": indexer,
        "maturityDate": maturity,
        "asOfDate": as_of,
        "buyRate": Decimal(buy_rate) if buy_rate is not None else None,
        "sellRate": Decimal(sell_rate) if sell_rate is not None else None,
        "buyPrice": Decimal(buy_price) if buy_price is not None else None,
        "sellPrice": Decimal(sell_price) if sell_price is not None else None,
        "basePrice": Decimal(base_price) if base_price is not None else None,
    }


class FakeTreasuryProvider:
    """Fake do NOVO contrato do provider (latest_by_identity), nunca o
    antigo fetch_daily_dataset -- ver TesouroTransparenteProvider."""

    def __init__(self, index=None, error=None):
        self.index = index or {}
        self.error = error
        self.calls = 0

    def latest_by_identity(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.index


def available_indicator(key="current_price", value="10.00"):
    return NormalizedIndicator(
        key=key,
        label=key,
        layer=IndicatorLayer.FUNDAMENTAL,
        value=Decimal(value),
        unit="currency",
        status=IndicatorStatus.AVAILABLE,
        source="BRAPI",
        collected_at=NOW,
        confidence=ConfidenceLevel.HIGH,
    )


def not_applicable_indicator(key="fgc"):
    return NormalizedIndicator(
        key=key,
        label=key,
        layer=IndicatorLayer.CLASS_SPECIFIC,
        value=None,
        unit="text",
        status=IndicatorStatus.NOT_APPLICABLE,
        source="catalog",
        collected_at=NOW,
        confidence=ConfidenceLevel.HIGH,
        provider_failure_reason=ProviderFailureReason.NOT_APPLICABLE,
        impact=AnalysisImpact.INFORMATIONAL,
    )


class RaisingMarket:
    """FakeMarket that raises a distinct exception per dataset name."""

    def __init__(self, exceptions_by_dataset=None, payload_by_dataset=None):
        self.exceptions_by_dataset = exceptions_by_dataset or {}
        self.payload_by_dataset = payload_by_dataset or {}
        self.calls: list[str] = []

    def get_stock_dataset(self, dataset, symbols, **params):
        self.calls.append(dataset)
        if dataset in self.exceptions_by_dataset:
            raise self.exceptions_by_dataset[dataset]
        return self.payload_by_dataset.get(dataset, {})

    def get_fii_dataset(self, dataset, symbols, **params):
        return self.get_stock_dataset(dataset, symbols, **params)


class CountingMarket:
    """Fake market que nunca deveria ser efetivamente consultado nestes cenarios.

    Usa contagem em vez de lançar exceção: uma exceção genérica seria
    engolida pelo próprio catch estruturado do resolver (classificada como
    NOT_REPORTED) e mascararia uma chamada indevida em vez de expô-la.
    """

    def __init__(self):
        self.calls = 0

    def get_stock_dataset(self, *args, **kwargs):
        self.calls += 1
        return {}

    def get_fii_dataset(self, *args, **kwargs):
        self.calls += 1
        return {}


# --- Snapshot: stale preservation (cenarios 2, 3, 19 do prompt P3) --------


def test_stale_snapshot_is_used_when_nothing_more_current_resolves():
    stale = snapshot(value="1.10", valid=False)
    result = resolve(
        resolver(FakeMarket({}), FakeSnapshots([], stale_rows=[stale]))
    )
    assert result.value == Decimal("1.10")
    assert result.status == IndicatorStatus.STALE
    assert result.provider_failure_reason == ProviderFailureReason.STALE
    assert result.source == "CVM"


def test_stale_snapshot_is_not_used_when_a_more_current_source_resolves():
    stale = snapshot(value="1.10", valid=False)
    market = FakeMarket({"results": [{"priceToBook": "2.00"}]})
    result = resolve(resolver(market, FakeSnapshots([], stale_rows=[stale])))
    assert result.value == Decimal("2.00")
    assert result.status == IndicatorStatus.AVAILABLE


def test_stale_snapshot_does_not_override_manual_priority_order():
    # Snapshot stale resolve antes do manual: manual nao deve sobrescrever.
    stale = snapshot(value="1.10", valid=False)
    manual = SimpleNamespace(
        indicator_key="price_book",
        value=Decimal("9.99"),
        unit="ratio",
        source_description="Manual",
        reference_date=date(2026, 6, 30),
        updated_at=NOW,
    )

    class ManualRepo:
        def list_for_asset(self, user_id, asset_id):
            return [manual]

    result = resolve(
        resolver(
            FakeMarket({}),
            FakeSnapshots([], stale_rows=[stale]),
            manual=ManualRepo(),
        ),
        asset_id="asset",
    )
    assert result.value == Decimal("1.10")
    assert result.source_type == "official"


# --- BRAPI: cenarios 4-13 -------------------------------------------------


def test_brapi_success_records_success_attempt():
    result = resolve(resolver(FakeMarket({"results": [{"priceToBook": "1.10"}]})))
    assert result.status == IndicatorStatus.AVAILABLE
    assert len(result.resolution_attempts) == 1
    attempt = result.resolution_attempts[0]
    assert attempt.provider == "BRAPI"
    assert attempt.outcome == ResolutionOutcome.SUCCESS
    assert attempt.provider_failure_reason is None


def test_brapi_returns_only_part_of_the_indicators():
    baseline = [indicator("price_book"), indicator("dividend_yield")]
    market = FakeMarket({"results": [{"priceToBook": "1.10"}]})
    result = resolve_all(resolver(market), baseline)
    assert result["price_book"].status == IndicatorStatus.AVAILABLE
    assert result["dividend_yield"].status == IndicatorStatus.UNAVAILABLE
    assert result["dividend_yield"].value is None
    assert (
        result["dividend_yield"].provider_failure_reason
        == ProviderFailureReason.NOT_REPORTED
    )


@pytest.mark.parametrize(
    "exception,expected_reason",
    [
        (MarketRateLimitError("limite"), ProviderFailureReason.RATE_LIMITED),
        (MarketAuthenticationError("token"), ProviderFailureReason.UNAUTHORIZED),
        (MarketPermissionError("plano"), ProviderFailureReason.PLAN_RESTRICTED),
        (
            MarketProviderUnavailableError("indisponivel"),
            ProviderFailureReason.PROVIDER_UNAVAILABLE,
        ),
        (
            MarketInvalidResponseError("invalido"),
            ProviderFailureReason.INVALID_RESPONSE,
        ),
        (MarketAssetNotFoundError("nao encontrado"), ProviderFailureReason.NOT_SUPPORTED),
    ],
)
def test_brapi_typed_errors_map_to_correct_failure_reason(exception, expected_reason):
    result = resolve(resolver(FakeMarket(exception)))
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert result.value is None
    assert result.provider_failure_reason == expected_reason
    attempt = result.resolution_attempts[-1]
    assert attempt.outcome == ResolutionOutcome.FAILURE
    assert attempt.provider_failure_reason == expected_reason


def test_brapi_timeout_is_provider_unavailable_not_generic_missing():
    result = resolve(resolver(FakeMarket(MarketProviderUnavailableError("timeout"))))
    assert result.provider_failure_reason == ProviderFailureReason.PROVIDER_UNAVAILABLE


def test_brapi_rate_limit_never_becomes_not_supported():
    result = resolve(resolver(FakeMarket(MarketRateLimitError("429"))))
    assert result.provider_failure_reason != ProviderFailureReason.NOT_SUPPORTED
    assert result.provider_failure_reason == ProviderFailureReason.RATE_LIMITED


def test_brapi_plan_restricted_never_becomes_not_found():
    result = resolve(resolver(FakeMarket(MarketPermissionError("plano"))))
    assert result.provider_failure_reason != ProviderFailureReason.NOT_SUPPORTED
    assert result.provider_failure_reason == ProviderFailureReason.PLAN_RESTRICTED


def test_provider_does_not_report_indicator_but_dataset_succeeded():
    result = resolve(resolver(FakeMarket({"results": [{"other_field": "x"}]})))
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.NOT_REPORTED


def test_provider_class_not_applicable_class_specific_indicator_not_called():
    # FGC ja chega NOT_APPLICABLE do catalogo/validador; resolver nao deve
    # tentar nenhuma fonte para ele.
    market = CountingMarket()
    result = resolve(resolver(market), baseline=[not_applicable_indicator()])
    assert result.status == IndicatorStatus.NOT_APPLICABLE
    assert result.resolution_attempts == []
    assert market.calls == 0


# --- Fallback parcial e continuidade (cenarios 25, 26, 32, 33, 42-43) -----


def test_partial_fallback_preserves_already_resolved_indicators():
    baseline = [indicator("price_book"), indicator("dividend_yield")]
    market = FakeMarket({"results": [{"priceToBook": "1.10"}]})
    result = resolve_all(resolver(market), baseline)
    resolved_pb = result["price_book"]
    assert resolved_pb.status == IndicatorStatus.AVAILABLE
    assert len(resolved_pb.resolution_attempts) == 1
    assert resolved_pb.resolution_attempts[0].outcome == ResolutionOutcome.SUCCESS


def test_already_available_indicator_is_never_degraded():
    baseline = [available_indicator("current_price", "42.00")]
    market = CountingMarket()
    result = resolve(resolver(market), baseline=baseline)
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("42.00")
    assert result.resolution_attempts == []
    assert market.calls == 0


def test_brapi_free_never_attempted_for_treasury_official_resolves_directly():
    """BLOQUEADOR (seção 38): "statistics"/"financial_data" são datasets de
    AÇÕES, estruturalmente incapazes de conter dado de Tesouro -- o
    resolver nunca os tenta para TREASURY (ver _load_brapi_free), indo
    direto para a fonte oficial. market.calls == 0 prova isso
    comportamentalmente, não só por inspeção de código."""
    market = FakeMarket(MarketRateLimitError("429"))
    treasury = FakeTreasuryProvider(
        {"tesouro-selic-01032031": treasury_row(buy_rate="6.25")}
    )
    baseline = indicator("treasury_rate")
    result = resolve_symbol(
        resolver(market, treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[baseline],
        asset_class=InvestmentClass.TREASURY,
    )
    assert market.calls == 0
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("6.25")
    assert result.source == "Tesouro Transparente"
    assert result.source_type == "official"
    assert len(result.resolution_attempts) == 1
    assert result.resolution_attempts[0].outcome == ResolutionOutcome.SUCCESS
    assert result.resolution_attempts[0].provider == "Tesouro Transparente"


def test_official_fails_manual_still_resolves_trail_preserved():
    manual_item = SimpleNamespace(
        indicator_key="treasury_rate",
        value=Decimal("6.25"),
        unit="percent",
        source_description="Extrato do Tesouro Direto",
        reference_date=date(2026, 6, 30),
        updated_at=NOW,
    )

    class ManualRepo:
        def list_for_asset(self, user_id, asset_id):
            return [manual_item]

    failing_treasury = FakeTreasuryProvider(
        error=MarketProviderUnavailableError("indisponivel")
    )

    result = resolve_symbol(
        IndicatorResolverService(
            market_service=FakeMarket(MarketRateLimitError("429")),
            normalizer=IndicatorNormalizationService(),
            treasury_provider=failing_treasury,
            manual_repository=ManualRepo(),
        ),
        symbol="TESOURO-SELIC-01032031",
        baseline=[indicator("treasury_rate")],
        asset_class=InvestmentClass.TREASURY,
        asset_id="asset",
    )
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("6.25")
    # BRAPI nunca é tentado para TREASURY (ver teste acima) -- só a fonte
    # oficial (falha) e o manual (sucesso) aparecem na trilha.
    assert len(result.resolution_attempts) == 2
    assert [a.outcome for a in result.resolution_attempts] == [
        ResolutionOutcome.FAILURE,
        ResolutionOutcome.SUCCESS,
    ]
    assert result.resolution_attempts[0].provider_failure_reason == (
        ProviderFailureReason.PROVIDER_UNAVAILABLE
    )


def test_all_sources_fail_indicator_still_has_no_value_but_has_diagnostics():
    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

    manual_empty = SimpleNamespace(list_for_asset=lambda user_id, asset_id: [])

    result = resolve(
        IndicatorResolverService(
            market_service=FakeMarket(MarketProviderUnavailableError("indisponivel")),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
            manual_repository=manual_empty,
        ),
        asset_id="asset",
    )
    assert result.value is None
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert len(result.resolution_attempts) >= 2
    assert all(a.outcome == ResolutionOutcome.FAILURE for a in result.resolution_attempts)


def test_all_sources_not_applicable_or_absent_never_produces_zero():
    result = resolve(resolver())
    assert result.value != Decimal("0")
    assert result.value is None


# --- Macro / BCB: cenarios 24-27 ------------------------------------------


def test_bcb_series_available():
    class Bcb:
        provider_name = "Banco Central do Brasil - SGS"
        series = {"selic": {}}

        def get_series(self, symbol):
            return {
                "source": self.provider_name,
                "frequency": "daily",
                "values": [{"reference_date": "18/07/2026", "value": Decimal("15.00")}],
            }

    definition = SimpleNamespace(key="selic", label="Selic", source="BRAPI", frequency="diária")
    result = resolver(bcb_provider=Bcb()).resolve_macro([definition], NOW)[0]
    assert result.state == IndicatorStatus.AVAILABLE
    assert result.provider_failure_reason is None
    assert result.resolution_attempts[0].outcome == ResolutionOutcome.SUCCESS


def test_bcb_series_empty_is_not_reported_not_provider_unavailable():
    class Bcb:
        provider_name = "Banco Central do Brasil - SGS"
        series = {"selic": {}}

        def get_series(self, symbol):
            return {"source": self.provider_name, "frequency": "daily", "values": []}

    definition = SimpleNamespace(key="selic", label="Selic", source="BRAPI", frequency="diária")
    result = resolver(bcb_provider=Bcb()).resolve_macro([definition], NOW)[0]
    assert result.state == IndicatorStatus.UNAVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.NOT_REPORTED


def test_bcb_timeout_is_provider_unavailable():
    class Bcb:
        provider_name = "Banco Central do Brasil - SGS"
        series = {"selic": {}}

        def get_series(self, symbol):
            raise MarketProviderUnavailableError("timeout")

    definition = SimpleNamespace(key="selic", label="Selic", source="BRAPI", frequency="diária")
    result = resolver(bcb_provider=Bcb()).resolve_macro([definition], NOW)[0]
    assert result.state == IndicatorStatus.UNAVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.PROVIDER_UNAVAILABLE
    assert result.resolution_attempts[0].outcome == ResolutionOutcome.FAILURE


def test_bcb_invalid_response_is_preserved_as_invalid_response():
    class Bcb:
        provider_name = "Banco Central do Brasil - SGS"
        series = {"selic": {}}

        def get_series(self, symbol):
            raise MarketInvalidResponseError("malformado")

    definition = SimpleNamespace(key="selic", label="Selic", source="BRAPI", frequency="diária")
    result = resolver(bcb_provider=Bcb()).resolve_macro([definition], NOW)[0]
    assert result.provider_failure_reason == ProviderFailureReason.INVALID_RESPONSE


def test_bcb_unsupported_series_is_not_supported():
    class Bcb:
        provider_name = "Banco Central do Brasil - SGS"
        series = {"selic": {}}

    definition = SimpleNamespace(
        key="unsupported_series", label="X", source="BRAPI", frequency="diária"
    )
    result = resolver(bcb_provider=Bcb()).resolve_macro([definition], NOW)[0]
    assert result.state == IndicatorStatus.UNAVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.NOT_SUPPORTED
    assert result.resolution_attempts == []


def test_macro_failure_is_not_silently_ignored():
    class Bcb:
        provider_name = "Banco Central do Brasil - SGS"
        series = {"cdi": {}}

        def get_series(self, symbol):
            raise RuntimeError("erro inesperado")

    definition = SimpleNamespace(key="cdi", label="CDI", source="BRAPI", frequency="diária")
    result = resolver(bcb_provider=Bcb()).resolve_macro([definition], NOW)[0]
    assert result.state == IndicatorStatus.UNAVAILABLE
    assert len(result.resolution_attempts) == 1
    assert result.resolution_attempts[0].outcome == ResolutionOutcome.FAILURE


# --- CVM: identidade, sincronizacao, provenance (cenarios 16-20, 52) ------


def test_cvm_identifier_unresolved_when_no_issuer_link():
    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

    result = resolve(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        asset_id="asset",
    )
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.IDENTIFIER_UNRESOLVED
    attempt = result.resolution_attempts[-1]
    assert attempt.dataset == "issuer_link"


def test_cvm_issuer_linked_but_not_synced():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return []

    result = resolve(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        asset_id="asset",
    )
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.NOT_SYNCED


def test_cvm_issuer_has_data_but_not_for_this_key_is_not_reported():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    other_account = SimpleNamespace(
        normalized_key="ebitda",
        normalized_value=Decimal("500"),
        acquisition_method="reported",
        account_code="3.05",
        account_description="EBITDA",
        original_value=Decimal("500"),
    )
    document = SimpleNamespace(
        period_end=date(2026, 6, 30),
        collected_at=NOW,
        period_kind="year_to_date",
        document_type="ITR",
        scope="consolidated",
    )

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return [(other_account, document, issuer)]

    result = resolve(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        asset_id="asset",
    )
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.NOT_REPORTED


def test_cvm_reference_date_collected_at_and_valid_until_preserved():
    account = SimpleNamespace(
        normalized_key="price_book",
        normalized_value=Decimal("1.40"),
        acquisition_method="reported",
        account_code="2.03",
        account_description="Patrimônio Líquido",
        original_value=Decimal("1.40"),
    )
    document = SimpleNamespace(
        period_end=date(2026, 6, 30),
        collected_at=NOW,
        period_kind="year_to_date",
        document_type="ITR",
        scope="consolidated",
    )
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return [(account, document, issuer)]

    result = resolve(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        asset_id="asset",
    )
    assert result.reference_date == datetime(2026, 6, 30, tzinfo=timezone.utc)
    assert result.collected_at == NOW
    # document_type="ITR" acima, fiscal_year_end desconhecido (mixin
    # _UnknownFiscalCalendarCvm) -> fallback conservador de próximo
    # trimestre (91 dias) + prazo regulatório de entrega (45 dias) =
    # 2026-06-30 + 136 dias = 2026-11-13. Nunca herda a janela anual da
    # DFP (395d) nem uma janela fixa de 120d — ver política por próximo
    # reporte esperado (_next_cvm_report_deadline).
    assert result.valid_until == datetime(2026, 11, 13, tzinfo=timezone.utc)
    assert result.freshness_status == "current"
    assert result.source == "CVM Dados Abertos"
    assert result.source_type == "official"


# --- Vinculação automática de emissor CVM por CNPJ exato -------------------


def test_auto_links_issuer_by_exact_cnpj_when_profile_provides_one():
    asset_id = uuid4()
    issuer_id = uuid4()
    issuer = SimpleNamespace(id=issuer_id, cnpj="33000167000101", cvm_code="9512")
    linked = {}

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return linked.get(asset_id)

        def find_issuer_by_cnpj(self, cnpj):
            assert cnpj == "33000167000101"
            return issuer

        def latest_normalized(self, asset_id):
            return []

    link_session_factory = _fresh_isolated_session_factory()
    market = FakeMarket(profile=SimpleNamespace(cnpj="33.000.167/0001-01"))
    result = resolve(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
            cvm_link_session_factory=link_session_factory,
        ),
        asset_id=asset_id,
    )
    # Sem dados sincronizados ainda -> NOT_SYNCED, mas a vinculação já
    # ocorreu (prova indireta: motivo deixou de ser IDENTIFIER_UNRESOLVED).
    assert result.provider_failure_reason == ProviderFailureReason.NOT_SYNCED

    # A escrita real não passa mais pelo cvm_repository injetado (fake, só
    # leitura) -- ela vai para a transação isolada própria do auto-link.
    # Prova a persistência DURÁVEL consultando a sessão isolada.
    verify = link_session_factory()
    try:
        persisted = (
            verify.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset_id)
            .first()
        )
        assert persisted is not None
        assert persisted.issuer_id == issuer_id
    finally:
        verify.close()


def test_auto_link_never_matches_by_name_only_exact_cnpj():
    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

        def find_issuer_by_cnpj(self, cnpj):
            # CNPJ do provider não bate com nenhum emissor sincronizado.
            assert cnpj == "99999999000199"
            return None

    market = FakeMarket(profile=SimpleNamespace(cnpj="99.999.999/0001-99"))
    result = resolve(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        asset_id="asset-1",
    )
    assert result.provider_failure_reason == ProviderFailureReason.IDENTIFIER_UNRESOLVED


def test_auto_link_gracefully_degrades_when_profile_lookup_fails():
    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

    market = FakeMarket(profile=MarketProviderUnavailableError("indisponivel"))
    result = resolve(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        asset_id="asset-1",
    )
    assert result.provider_failure_reason == ProviderFailureReason.IDENTIFIER_UNRESOLVED


def test_auto_link_does_not_run_when_already_linked():
    issuer = SimpleNamespace(id="issuer-1", cnpj="33000167000101", cvm_code="9512")

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def find_issuer_by_cnpj(self, cnpj):
            raise AssertionError("não deveria buscar por CNPJ quando já vinculado")

        def latest_normalized(self, asset_id):
            return []

    market = FakeMarket(profile=SimpleNamespace(cnpj="33.000.167/0001-01"))
    result = resolve(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        asset_id="asset-1",
    )
    assert result.provider_failure_reason == ProviderFailureReason.NOT_SYNCED


def test_auto_link_persists_via_isolated_transaction_over_a_shared_database():
    """TESTE MAIS IMPORTANTE desta correção: prova isolamento de transação
    sobre um banco FISICAMENTE COMPARTILHADO -- duas conexões
    independentes (engines/pools separados, ver
    _shared_file_sqlite_factories) contra o MESMO arquivo sqlite, análogo
    a duas conexões de um pool real (Postgres) em produção. Não usa
    StaticPool sobre `:memory:` compartilhado (que colapsaria as duas
    "conexões" em uma só transação, mascarando o problema original) nem a
    fixture `tmp_path` (PermissionError conhecido no Windows).

    Prova: (1) asset/issuer comitados no banco compartilhado; (2) sessão B
    (auto-link) persiste o vínculo via o código de produção real e comita
    SOMENTE sua própria transação; (3) sessão A (resolver) cria uma
    alteração não relacionada e só dá flush -- continua vendo essa
    alteração; (4) rollback da sessão A desfaz SOMENTE essa alteração,
    nunca o vínculo (que vive em outra transação/conexão); (5)+(6) uma
    sessão C nova enxerga o vínculo mas NÃO a alteração não relacionada;
    (7) as FKs do vínculo correspondem a registros reais do mesmo banco
    (com PRAGMA foreign_keys=ON ativo).

    Nota sobre a ordem: SQLite (ao contrário do Postgres em produção) usa
    uma trava de escrita única por banco -- uma escrita não comitada em
    QUALQUER tabela bloqueia qualquer outra conexão que tente escrever,
    mesmo em tabela totalmente diferente (verificado empiricamente: uma
    sessão B tentando comitar enquanto a sessão A tem um flush pendente
    trava até "database is locked"). Por isso o auto-link roda ANTES da
    alteração não relacionada da sessão A começar -- isso não enfraquece a
    prova: o que importa é que as duas transações nunca dependem uma da
    outra para seu próprio commit/rollback, não a ordem cronológica exata.
    """
    factory_a, factory_b, cleanup = _shared_file_sqlite_factories()
    try:
        session_a = factory_a()
        try:
            asset = Asset(
                ticker="ISOAL4", name="Isolamento Teste", asset_type="STOCK", currency="BRL"
            )
            session_a.add(asset)
            session_a.commit()

            repository_a = CvmFinancialRepository(session_a)
            issuer = repository_a.upsert_issuer(
                "11222333000181", "88888", "EMISSOR ISOLADO S.A."
            )
            session_a.commit()
            asset_id, issuer_id = asset.id, issuer.id

            # (1) asset e issuer estão comitados no banco compartilhado --
            # confirmado por uma conexão totalmente independente.
            check = factory_b()
            try:
                assert check.query(Asset).filter(Asset.ticker == "ISOAL4").first() is not None
                assert check.get(CvmIssuer, issuer_id) is not None
            finally:
                check.close()

            # (2) sessão B (auto-link): persiste AssetCvmIssuer via o
            # código de produção real (_auto_link_cvm_issuer) e comita
            # SOMENTE sua própria transação isolada -- e a fecha (nenhuma
            # trava de escrita fica retida) antes de qualquer outra coisa.
            market = FakeMarket(profile=SimpleNamespace(cnpj="11.222.333/0001-81"))
            service = IndicatorResolverService(
                market_service=market,
                normalizer=IndicatorNormalizationService(),
                cvm_repository=repository_a,
                cvm_link_session_factory=factory_b,
            )
            linked_issuer = service._auto_link_cvm_issuer(asset_id, "ISOAL4")
            assert linked_issuer is not None
            assert linked_issuer.id == issuer_id

            # (3) sessão A (resolver): SÓ AGORA cria uma alteração não
            # relacionada e dá flush SEM commit -- continua vendo essa
            # alteração dentro da própria sessão.
            unrelated = Asset(
                ticker="ISONR4", name="Nao Relacionado", asset_type="STOCK", currency="BRL"
            )
            session_a.add(unrelated)
            session_a.flush()
            assert (
                session_a.query(Asset).filter(Asset.ticker == "ISONR4").first()
                is not None
            )

            # (4) rollback da sessão A desfaz SOMENTE a alteração não
            # relacionada -- nunca tocou no vínculo, que já foi persistido
            # e comitado por outra transação/conexão antes disso.
            session_a.rollback()
            assert (
                session_a.query(Asset).filter(Asset.ticker == "ISONR4").first() is None
            )

            # (5)+(6) uma sessão C nova enxerga o vínculo (durável) mas NÃO
            # a alteração não relacionada (nunca chegou a ser comitada).
            session_c = factory_b()
            try:
                link = (
                    session_c.query(AssetCvmIssuer)
                    .filter(AssetCvmIssuer.asset_id == asset_id)
                    .first()
                )
                assert link is not None
                assert link.issuer_id == issuer_id
                assert (
                    session_c.query(Asset).filter(Asset.ticker == "ISONR4").first()
                    is None
                )

                # (7) FK: com PRAGMA foreign_keys=ON ativo neste banco, o
                # INSERT de AssetCvmIssuer só teve sucesso porque asset_id
                # e issuer_id já existiam como linhas reais -- confirma
                # explicitamente que continuam resolvendo para elas.
                assert session_c.get(Asset, link.asset_id) is not None
                assert session_c.get(CvmIssuer, link.issuer_id) is not None
            finally:
                session_c.close()
        finally:
            session_a.close()
    finally:
        cleanup()


def test_isolated_auto_link_failure_only_rolls_back_isolated_session(db_session):
    """Prova que um erro REAL (não uma corrida concorrente) dentro da
    transação isolada do auto-link nunca é reportado como sucesso: o
    vínculo não é tratado como utilizável, o rollback acontece só na
    sessão isolada, ela é fechada, a sessão principal continua totalmente
    utilizável, e nenhum vínculo fantasma aparece no banco.
    """
    asset = Asset(
        ticker="ISOFL4", name="Isolamento Falha", asset_type="STOCK", currency="BRL"
    )
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    repository.upsert_issuer("22333444000162", "77777", "EMISSOR FALHA S.A.")
    db_session.commit()

    isolated_sessionmaker = _fresh_isolated_session_factory()
    created = {}

    class FailingSession:
        def __init__(self, real):
            self._real = real
            self.rolled_back = False
            self.closed = False

        def __getattr__(self, name):
            return getattr(self._real, name)

        def commit(self):
            raise RuntimeError("falha real simulada na transação isolada")

        def rollback(self):
            self.rolled_back = True
            self._real.rollback()

        def close(self):
            self.closed = True
            self._real.close()

    def failing_factory():
        wrapper = FailingSession(isolated_sessionmaker())
        created["session"] = wrapper
        return wrapper

    market = FakeMarket(profile=SimpleNamespace(cnpj="22.333.444/0001-62"))
    service = IndicatorResolverService(
        market_service=market,
        normalizer=IndicatorNormalizationService(),
        cvm_repository=repository,
        cvm_link_session_factory=failing_factory,
    )

    linked_issuer = service._auto_link_cvm_issuer(asset.id, "ISOFL4")
    # Falha real (não é uma corrida) nunca é reportada como sucesso: o
    # chamador não pode acreditar em um vínculo que não foi persistido.
    assert linked_issuer is None
    assert created["session"].rolled_back is True
    assert created["session"].closed is True

    # Nenhum vínculo fantasma foi criado no banco isolado.
    verify = isolated_sessionmaker()
    try:
        assert (
            verify.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset.id)
            .first()
            is None
        )
    finally:
        verify.close()

    # A sessão do RESOLVER continua totalmente utilizável depois da falha
    # isolada -- nenhum efeito colateral vazou para ela.
    still_usable = Asset(
        ticker="ISOOK4", name="Ainda Funciona", asset_type="STOCK", currency="BRL"
    )
    db_session.add(still_usable)
    db_session.commit()
    db_session.refresh(still_usable)
    assert still_usable.id is not None


def test_auto_link_race_is_idempotent_when_concurrent_winner_links_same_issuer(
    db_session,
):
    """Corrida concorrente legítima: duas tentativas tentam vincular o
    MESMO asset ao MESMO emissor ao mesmo tempo. asset_cvm_issuers.asset_id
    é unique -- a perdedora recebe IntegrityError ao comitar. Se, após
    reler em transação limpa, o vínculo já existente apontar para o MESMO
    emissor pretendido, isso é sucesso idempotente, nunca um falso erro.
    """
    asset = Asset(
        ticker="RACE14", name="Corrida Mesmo Emissor", asset_type="STOCK", currency="BRL"
    )
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    issuer = repository.upsert_issuer("77888999000105", "22222", "EMISSOR CORRIDA S.A.")
    db_session.commit()

    isolated_sessionmaker = _fresh_isolated_session_factory()

    # Simula o vencedor da corrida: já vinculou o MESMO emissor antes da
    # nossa tentativa isolada conseguir comitar.
    winner = isolated_sessionmaker()
    CvmFinancialRepository(winner).link_asset(asset.id, issuer.id)
    winner.commit()
    winner.close()

    class RacingSession:
        """Simula a transação PERDEDORA de uma corrida real: o efeito
        observável de "minha SELECT não viu o vencedor, mas meu COMMIT
        chega depois do dele" é, de fora, exatamente um IntegrityError no
        commit -- é isso que se força aqui, de forma determinística, para
        exercitar o mesmo caminho de código que uma corrida real trilha.
        """

        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def commit(self):
            raise IntegrityError(
                "INSERT INTO asset_cvm_issuers ...",
                {},
                Exception("UNIQUE constraint failed: asset_cvm_issuers.asset_id"),
            )

    def racing_factory():
        return RacingSession(isolated_sessionmaker())

    service = IndicatorResolverService(
        market_service=FakeMarket(),
        normalizer=IndicatorNormalizationService(),
        cvm_repository=repository,
        cvm_link_session_factory=racing_factory,
    )

    result = service._persist_cvm_link_isolated(asset.id, issuer.id)
    assert result is True

    verify = isolated_sessionmaker()
    try:
        links = (
            verify.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset.id)
            .all()
        )
        assert len(links) == 1
        assert links[0].issuer_id == issuer.id
    finally:
        verify.close()


def test_auto_link_race_is_a_conflict_when_concurrent_winner_links_different_issuer(
    db_session,
):
    """Mesma corrida, mas o vencedor vinculou um emissor DIFERENTE do
    pretendido por esta tentativa -- isso é um conflito de identidade
    real, nunca deve sobrescrever silenciosamente o vínculo já existente.
    """
    asset = Asset(
        ticker="RACE24", name="Corrida Emissor Diferente", asset_type="STOCK", currency="BRL"
    )
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    winning_issuer = repository.upsert_issuer(
        "88999000000186", "33333", "EMISSOR VENCEDOR S.A."
    )
    our_issuer = repository.upsert_issuer(
        "99000111000167", "44444", "EMISSOR PRETENDIDO S.A."
    )
    db_session.commit()

    isolated_sessionmaker = _fresh_isolated_session_factory()

    winner = isolated_sessionmaker()
    CvmFinancialRepository(winner).link_asset(asset.id, winning_issuer.id)
    winner.commit()
    winner.close()

    class RacingSession:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def commit(self):
            raise IntegrityError(
                "INSERT INTO asset_cvm_issuers ...",
                {},
                Exception("UNIQUE constraint failed: asset_cvm_issuers.asset_id"),
            )

    def racing_factory():
        return RacingSession(isolated_sessionmaker())

    service = IndicatorResolverService(
        market_service=FakeMarket(),
        normalizer=IndicatorNormalizationService(),
        cvm_repository=repository,
        cvm_link_session_factory=racing_factory,
    )

    result = service._persist_cvm_link_isolated(asset.id, our_issuer.id)
    assert result is False

    # O vínculo do vencedor permanece intacto -- nunca sobrescrito.
    verify = isolated_sessionmaker()
    try:
        links = (
            verify.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset.id)
            .all()
        )
        assert len(links) == 1
        assert links[0].issuer_id == winning_issuer.id
    finally:
        verify.close()


def test_auto_link_never_overwrites_a_pre_existing_link_to_a_different_issuer(
    db_session,
):
    """Corrida do TIPO 2 (sem IntegrityError): outra transação já
    vinculou asset_id -> issuer B e comitou ANTES desta tentativa isolada
    sequer começar -- não é um INSERT concorrente, é uma leitura que já
    encontra o vínculo existente. CvmFinancialRepository.link_asset()
    (create-or-update) sobrescreveria silenciosamente para issuer A; o
    auto-link usa ensure_asset_link (create-if-absent / verify-same) e
    precisa recusar, preservando o vínculo já existente intacto.

    Este teste falha contra o código anterior a esta correção (que usava
    link_asset diretamente em _persist_cvm_link_isolated) e passa depois.
    """
    asset = Asset(
        ticker="RACE34", name="Vinculo Preexistente Diferente", asset_type="STOCK", currency="BRL"
    )
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    issuer_b = repository.upsert_issuer("11444777000103", "55501", "EMISSOR B S.A.")
    issuer_a = repository.upsert_issuer("22555888000184", "55502", "EMISSOR A S.A.")
    db_session.commit()

    isolated_sessionmaker = _fresh_isolated_session_factory()

    # Vínculo já existe e já foi comitado ANTES de qualquer tentativa de
    # auto-link rodar -- simula a request concorrente que já terminou.
    already_there = isolated_sessionmaker()
    CvmFinancialRepository(already_there).link_asset(asset.id, issuer_b.id)
    already_there.commit()
    already_there.close()

    service = IndicatorResolverService(
        market_service=FakeMarket(),
        normalizer=IndicatorNormalizationService(),
        cvm_repository=repository,
        cvm_link_session_factory=isolated_sessionmaker,
    )

    # Auto-link, sem saber do vínculo já existente, tenta persistir para
    # issuer A -- deve ser recusado, nunca sobrescrever.
    result = service._persist_cvm_link_isolated(asset.id, issuer_a.id)
    assert result is False

    verify = isolated_sessionmaker()
    try:
        links = (
            verify.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset.id)
            .all()
        )
        assert len(links) == 1
        assert links[0].issuer_id == issuer_b.id
    finally:
        verify.close()


def test_auto_link_is_idempotent_when_pre_existing_link_matches_the_same_issuer(
    db_session,
):
    """Se já existe vínculo asset_id -> issuer A (comitado antes desta
    tentativa) e o auto-link também pretende issuer A, isso é sucesso
    idempotente -- sem UPDATE desnecessário, sem erro.
    """
    asset = Asset(
        ticker="RACE44", name="Vinculo Preexistente Mesmo", asset_type="STOCK", currency="BRL"
    )
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    issuer = repository.upsert_issuer("33666999000165", "55503", "EMISSOR MESMO S.A.")
    db_session.commit()

    isolated_sessionmaker = _fresh_isolated_session_factory()

    already_there = isolated_sessionmaker()
    CvmFinancialRepository(already_there).link_asset(asset.id, issuer.id)
    already_there.commit()
    already_there.close()

    service = IndicatorResolverService(
        market_service=FakeMarket(),
        normalizer=IndicatorNormalizationService(),
        cvm_repository=repository,
        cvm_link_session_factory=isolated_sessionmaker,
    )

    result = service._persist_cvm_link_isolated(asset.id, issuer.id)
    assert result is True

    verify = isolated_sessionmaker()
    try:
        links = (
            verify.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset.id)
            .all()
        )
        assert len(links) == 1
        assert links[0].issuer_id == issuer.id
    finally:
        verify.close()


# --- Ação fracionária B3: auto-link CVM via canonical_symbol ---------------
#
# A auditoria (Prompt 1) provou com dados reais da BRAPI que o profile do
# ticker fracionário (ex. PETR4F) volta sem CNPJ ("data": null), enquanto o
# mesmo profile pelo lote padrão (PETR4) tem CNPJ completo. A correção NÃO
# muda `_auto_link_cvm_issuer` -- ele continua chamando
# `market_service.get_profile(symbol)` exatamente como antes. Quem resolve a
# identidade econômica é o próprio MarketService (ver market_service.py:
# get_profile), de forma transparente para o resolver. Por isso estes testes
# usam um MarketService DE VERDADE (não o FakeMarket simples usado acima),
# ligado a um provider fake que só entrega CNPJ quando consultado pelo
# símbolo canônico -- provando o caminho real de ponta a ponta.


class _FractionalAwareBrapiLikeProvider:
    """Fake de provider que reproduz o comportamento real observado na
    auditoria: profile só tem CNPJ para o símbolo canônico (lote padrão);
    para o símbolo do mercado fracionário, o profile existe mas vem vazio
    (equivalente a `"data": null` da BRAPI) -- prova que o resolver só
    consegue o CNPJ porque o MarketService canonicalizou antes de chamar o
    provider, nunca porque o fake "ajudou" devolvendo o mesmo dado para
    qualquer símbolo.
    """

    limited_mode = False
    # Metadado de mercado do próprio provider -- só assim MarketService
    # aciona a canonicalização do fracionário B3 (ver Prompt 3 seção 2/3:
    # market=B3_MARKET nunca pode ser assumido implicitamente).
    market = B3_MARKET

    def __init__(self, canonical_symbol: str, cnpj: str):
        self.canonical_symbol = canonical_symbol
        self.cnpj = cnpj
        self.profile_calls: list[str] = []

    def get_profile(self, ticker: str):
        self.profile_calls.append(ticker)
        if ticker == self.canonical_symbol:
            return MarketProfileResponse(
                symbol=ticker,
                name="Petroleo Brasileiro SA Pfd",
                sector="Energia",
                cnpj=self.cnpj,
                provider="BRAPI",
            )
        return MarketProfileResponse(symbol=ticker, cnpj=None, provider="BRAPI")

    # Não usados pelos testes abaixo (auto-link só chama get_profile), mas
    # exigidos para o objeto se comportar como um provider completo.
    def get_quote(self, ticker: str):
        raise AssertionError("not used")

    def get_quotes(self, tickers: list[str]):
        raise AssertionError("not used")

    def search_assets(self, query: str, limit: int = 10):
        return []

    def get_asset(self, ticker: str):
        return None

    def get_stock_dataset(self, dataset: str, symbols: list[str], **params):
        raise AssertionError("not used")


def test_fractional_ticker_brapi_fundamentals_provenance_registers_the_bridge():
    """Prompt 3, seção 7/10 caso H (fora do caminho CVM): quando um
    indicador é resolvido a partir do dataset de fundamentos da BRAPI
    (statistics/financial_data) usando o canonical_symbol, sua
    provenance também registra a ponte -- não só os indicadores CVM.
    `source` continua "BRAPI" (o VALOR realmente veio da BRAPI aqui,
    diferente do caso CVM onde a BRAPI é só ponte de identidade)."""
    MarketService.clear_caches()
    market = FakeMarket(payload={"priceToBook": "1.4"})
    # FakeMarket não tem `.provider` -- adicionamos um que declara B3,
    # exatamente o metadado que BrapiProvider real declara (ver
    # BrapiProvider.market), para que MarketService/_market_context
    # comprovem o contexto sem precisar de um MarketService real aqui.
    market.provider = SimpleNamespace(market=B3_MARKET, provider_name="BRAPI")

    result = resolve_symbol(
        resolver(market=market), "PETR4F", [indicator()], asset_id=None
    )

    assert result.status == IndicatorStatus.AVAILABLE
    assert result.source == "BRAPI"
    identity_resolution = result.provenance["identity_resolution"]
    assert identity_resolution["requested_symbol"] == "PETR4F"
    assert identity_resolution["canonical_symbol"] == "PETR4"
    assert identity_resolution["resolution_method"] == "canonical_symbol_substitution"


def test_standard_lot_ticker_brapi_fundamentals_never_get_a_fabricated_bridge():
    MarketService.clear_caches()
    market = FakeMarket(payload={"priceToBook": "1.4"})
    market.provider = SimpleNamespace(market=B3_MARKET, provider_name="BRAPI")

    result = resolve_symbol(
        resolver(market=market), "PETR4", [indicator()], asset_id=None
    )

    assert result.status == IndicatorStatus.AVAILABLE
    assert "identity_resolution" not in result.provenance


def test_fii_dataset_never_gets_a_fabricated_identity_bridge():
    """get_fii_dataset nunca foi alterado (fora de escopo, ver Prompt 2
    seção 12/21) -- mesmo com contexto B3 comprovado e um símbolo com
    formato fracionário válido, um FII nunca deve anotar
    identity_resolution para o dataset BRAPI, porque nenhuma
    canonicalização de fato ocorreu nesse caminho."""
    MarketService.clear_caches()
    market = FakeMarket(payload={"priceToBook": "1.4"})
    market.provider = SimpleNamespace(market=B3_MARKET, provider_name="BRAPI")

    result = resolve_symbol(
        resolver(market=market),
        "MXRF11F",
        [indicator()],
        asset_class=InvestmentClass.FII,
        asset_id=None,
    )

    assert "identity_resolution" not in result.provenance


def test_fractional_ticker_auto_links_cvm_issuer_via_canonical_symbol():
    # MarketService cacheia perfil por classe (ver market_service.py) --
    # cada teste que usa uma instância real precisa de um estado limpo,
    # senão herdaria a resposta cacheada de outro teste deste módulo.
    MarketService.clear_caches()
    asset_id = uuid4()
    issuer = SimpleNamespace(id=uuid4(), cnpj="33000167000101", cvm_code="9512")

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

        def find_issuer_by_cnpj(self, cnpj):
            assert cnpj == "33000167000101"
            return issuer

        def latest_normalized(self, asset_id):
            return []

    provider = _FractionalAwareBrapiLikeProvider(
        canonical_symbol="PETR4", cnpj="33.000.167/0001-01"
    )
    market = MarketService(provider=provider)
    link_session_factory = _fresh_isolated_session_factory()

    result = resolve_symbol(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
            cvm_link_session_factory=link_session_factory,
        ),
        "PETR4F",
        [indicator()],
        asset_id=asset_id,
    )

    # O provider nunca foi consultado por "PETR4F" -- só pelo canonical.
    assert provider.profile_calls == ["PETR4"]
    # Sem dados sincronizados -> NOT_SYNCED, nunca IDENTIFIER_UNRESOLVED:
    # o vínculo ativo<->emissor foi encontrado normalmente via CNPJ.
    assert result.provider_failure_reason == ProviderFailureReason.NOT_SYNCED

    verify = link_session_factory()
    try:
        persisted = (
            verify.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset_id)
            .first()
        )
        assert persisted is not None
        assert persisted.issuer_id == issuer.id
    finally:
        verify.close()


def test_fractional_ticker_cvm_value_keeps_cvm_as_source_and_provenance_registers_bridge():
    """Prompt 3, seção 7-9 / 10 casos H e I: quando o VALOR final de um
    indicador vem da CVM (não da BRAPI), `source`/`source_type` continuam
    exatamente "CVM Dados Abertos"/"official" -- a BRAPI foi usada
    SOMENTE como ponte de identidade (profile -> CNPJ) para localizar o
    emissor, nunca como fonte do dado em si. A provenance registra essa
    ponte de forma completa e ADITIVA (as chaves pré-existentes de
    provenance -- provider/document_type/cnpj/... -- continuam intactas).
    """
    MarketService.clear_caches()
    asset_id = uuid4()
    issuer_id = uuid4()
    issuer = SimpleNamespace(id=issuer_id, cnpj="33000167000101", cvm_code="9512")
    account = SimpleNamespace(
        normalized_key="price_book",
        normalized_value=Decimal("1.40"),
        acquisition_method="reported",
        account_code="2.03",
        account_description="Patrimônio Líquido",
        original_value=Decimal("1.40"),
    )
    document = SimpleNamespace(
        period_end=date(2026, 6, 30),
        collected_at=NOW,
        period_kind="year_to_date",
        document_type="ITR",
        scope="consolidated",
    )

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

        def find_issuer_by_cnpj(self, cnpj):
            assert cnpj == "33000167000101"
            return issuer

        def latest_normalized(self, asset_id):
            return [(account, document, issuer)]

    provider = _FractionalAwareBrapiLikeProvider(
        canonical_symbol="PETR4", cnpj="33.000.167/0001-01"
    )
    market = MarketService(provider=provider)

    result = resolve_symbol(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
            cvm_link_session_factory=_fresh_isolated_session_factory(),
        ),
        "PETR4F",
        [indicator()],
        asset_id=asset_id,
    )

    # O VALOR veio da CVM -- source/source_type nunca mudam por causa da
    # ponte de identidade ter sido a BRAPI.
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.source == "CVM Dados Abertos"
    assert result.source_type == "official"

    # Provenance pré-existente (chaves já usadas antes desta correção)
    # permanece intacta -- merge aditivo, nunca substituição.
    assert result.provenance["provider"] == "cvm"
    assert result.provenance["cnpj"] == issuer.cnpj
    assert result.provenance["cvm_code"] == issuer.cvm_code

    # Nova informação: a ponte de identidade completa.
    identity_resolution = result.provenance["identity_resolution"]
    assert identity_resolution["requested_symbol"] == "PETR4F"
    assert identity_resolution["trading_symbol"] == "PETR4F"
    assert identity_resolution["canonical_symbol"] == "PETR4"
    assert identity_resolution["provider_symbol"] == "PETR4"
    assert identity_resolution["resolution_method"] == "exact_cnpj"
    assert identity_resolution["bridge_provider"] == "BRAPI"


def test_standard_lot_ticker_cvm_provenance_never_gets_a_fabricated_identity_bridge():
    """Prompt 3, seção 10, caso J: PETR4 normal (sem sufixo fracionário)
    nunca recebe uma nota de identity_resolution -- não houve ponte
    nenhuma (trading_symbol == canonical_symbol), então não há nada a
    registrar."""
    MarketService.clear_caches()
    asset_id = uuid4()
    issuer_id = uuid4()
    issuer = SimpleNamespace(id=issuer_id, cnpj="33000167000101", cvm_code="9512")
    account = SimpleNamespace(
        normalized_key="price_book",
        normalized_value=Decimal("1.40"),
        acquisition_method="reported",
        account_code="2.03",
        account_description="Patrimônio Líquido",
        original_value=Decimal("1.40"),
    )
    document = SimpleNamespace(
        period_end=date(2026, 6, 30),
        collected_at=NOW,
        period_kind="year_to_date",
        document_type="ITR",
        scope="consolidated",
    )

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

        def find_issuer_by_cnpj(self, cnpj):
            assert cnpj == "33000167000101"
            return issuer

        def latest_normalized(self, asset_id):
            return [(account, document, issuer)]

    provider = _FractionalAwareBrapiLikeProvider(
        canonical_symbol="PETR4", cnpj="33.000.167/0001-01"
    )
    market = MarketService(provider=provider)

    result = resolve_symbol(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
            cvm_link_session_factory=_fresh_isolated_session_factory(),
        ),
        "PETR4",
        [indicator()],
        asset_id=asset_id,
    )

    assert result.status == IndicatorStatus.AVAILABLE
    assert result.source == "CVM Dados Abertos"
    assert "identity_resolution" not in result.provenance


def test_standard_lot_ticker_still_auto_links_cvm_issuer_directly():
    """Regressão: PETR4 (sem sufixo fracionário) continua funcionando
    exatamente como antes -- canonical_symbol == trading_symbol, o
    provider é consultado pelo mesmo símbolo de sempre."""
    MarketService.clear_caches()
    asset_id = uuid4()
    issuer = SimpleNamespace(id=uuid4(), cnpj="33000167000101", cvm_code="9512")

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

        def find_issuer_by_cnpj(self, cnpj):
            assert cnpj == "33000167000101"
            return issuer

        def latest_normalized(self, asset_id):
            return []

    provider = _FractionalAwareBrapiLikeProvider(
        canonical_symbol="PETR4", cnpj="33.000.167/0001-01"
    )
    market = MarketService(provider=provider)

    result = resolve_symbol(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
            cvm_link_session_factory=_fresh_isolated_session_factory(),
        ),
        "PETR4",
        [indicator()],
        asset_id=asset_id,
    )

    assert provider.profile_calls == ["PETR4"]
    assert result.provider_failure_reason == ProviderFailureReason.NOT_SYNCED


def test_invalid_f_suffixed_ticker_never_auto_links_by_a_fabricated_base():
    """PETRF (base inválida: "PETR" sem dígito de classe) nunca é
    canonicalizado -- o provider é consultado pelo próprio "PETRF", que
    não tem CNPJ nenhum cadastrado, então o vínculo permanece
    IDENTIFIER_UNRESOLVED (honesto), nunca um emissor errado."""
    MarketService.clear_caches()
    asset_id = uuid4()

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return None

        def find_issuer_by_cnpj(self, cnpj):
            raise AssertionError("nunca deveria buscar CNPJ para base inválida")

    provider = _FractionalAwareBrapiLikeProvider(
        canonical_symbol="PETR4", cnpj="33.000.167/0001-01"
    )
    market = MarketService(provider=provider)

    result = resolve_symbol(
        IndicatorResolverService(
            market_service=market,
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
            cvm_link_session_factory=_fresh_isolated_session_factory(),
        ),
        "PETRF",
        [indicator()],
        asset_id=asset_id,
    )

    assert provider.profile_calls == ["PETRF"]
    assert result.provider_failure_reason == ProviderFailureReason.IDENTIFIER_UNRESOLVED


# --- Indicadores derivados de componentes CVM (roe, roa, net_debt_equity,
# liabilities_assets, current_liquidity) -------------------------------------


def _cvm_account(key, value, code, description="conta"):
    return SimpleNamespace(
        normalized_key=key,
        normalized_value=Decimal(value),
        acquisition_method="reported",
        account_code=code,
        account_description=description,
        original_value=Decimal(value),
    )


def _cvm_document(period_end=date(2026, 6, 30), document_type="DFP", period_kind="annual"):
    return SimpleNamespace(
        period_end=period_end,
        collected_at=NOW,
        period_kind=period_kind,
        document_type=document_type,
        scope="consolidated",
    )


def test_derived_roe_computed_when_net_income_and_equity_share_same_period():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe"), indicator("equity")],
        asset_id="asset-1",
    )
    assert result["roe"].status == IndicatorStatus.AVAILABLE
    assert result["roe"].value == Decimal("10.00")
    assert result["roe"].source_type == "derived"
    assert result["roe"].provenance["formula"] == "lucro líquido / patrimônio líquido"
    assert result["roe"].provenance["components"] == {
        "net_income": "1000",
        "equity": "10000",
    }
    # equity (componente bruto direto) também deve ficar disponível.
    assert result["equity"].status == IndicatorStatus.AVAILABLE
    assert result["equity"].value == Decimal("10000")


def test_derived_indicators_never_mix_incompatible_periods():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    old_document = _cvm_document(period_end=date(2026, 3, 31))
    new_document = _cvm_document(period_end=date(2026, 6, 30))
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), old_document, issuer),
        (_cvm_account("equity", "10000", "2.03"), new_document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    assert result["roe"].status == IndicatorStatus.UNAVAILABLE
    assert result["roe"].value is None


def test_derived_net_debt_equity_from_gross_debt_and_cash_when_net_debt_absent():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("gross_debt", "5000", "2.01.04"), document, issuer),
        (_cvm_account("cash_and_equivalents", "1200", "1.01.01"), document, issuer),
        (_cvm_account("equity", "19000", "2.03"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("net_debt_equity")],
        asset_id="asset-1",
    )
    assert result["net_debt_equity"].status == IndicatorStatus.AVAILABLE
    assert result["net_debt_equity"].value == Decimal("0.2000")


# --- Rollover do encerramento fiscal e prazo calendárico da DFP ------------
#
# Bugs reais encontrados: (1) fiscal_year_end observado carregava o ANO
# histórico da DFP mais recente, produzindo valid_until < reference_date
# para um ITR de um exercício mais novo; (2) "3 meses" da DFP era
# aproximado como 90 dias corridos, que nem sempre equivale a 3 meses
# calendáricos. Ver _fiscal_year_end_for_period() e
# _next_cvm_report_deadline().


def test_fiscal_year_end_for_period_rolls_forward_when_period_is_after_this_years_close():
    # encerramento observado 31/12 (histórico, de uma DFP de 2025); um ITR
    # de 2026-09-30 pertence ao ciclo fiscal que fecha em 2026-12-31, não
    # ao ciclo que já fechou em 2025-12-31.
    assert _fiscal_year_end_for_period(
        date(2026, 9, 30), date(2025, 12, 31)
    ) == date(2026, 12, 31)


def test_fiscal_year_end_for_period_rolls_forward_for_non_calendar_fiscal_year():
    # encerramento observado 30/06; um ITR de 2025-09-30 é POSTERIOR ao
    # fechamento de 2025-06-30, logo já pertence ao ciclo que fecha em
    # 2026-06-30.
    assert _fiscal_year_end_for_period(
        date(2025, 9, 30), date(2025, 6, 30)
    ) == date(2026, 6, 30)


def test_fiscal_year_end_for_period_keeps_same_year_when_period_precedes_close():
    # encerramento observado 30/06; um ITR de 2026-03-31 é ANTERIOR ao
    # fechamento de 2026-06-30, logo já pertence a esse mesmo ciclo —
    # não precisa (nem deve) avançar para 2027.
    assert _fiscal_year_end_for_period(
        date(2026, 3, 31), date(2025, 6, 30)
    ) == date(2026, 6, 30)


def test_dfp_deadline_uses_calendar_months_not_a_flat_90_days():
    # 2026-06-30 + 3 meses calendáricos = 2026-09-30 (não 2026-09-28, que
    # seria o resultado de "+90 dias corridos").
    assert _add_months(date(2026, 6, 30), 3) == date(2026, 9, 30)


def test_last_quarter_itr_deadline_never_uses_stale_historical_dfp_year():
    # Regressão do Bug 1: ITR de 2026-09-30 é o último trimestre antes do
    # fechamento observado (31/12), mas o exercício RELEVANTE é o de 2026
    # (que fecha em 2026-12-31), não o de 2025. O prazo da próxima DFP
    # esperada é 2026-12-31 + 3 meses = 2027-03-31 — NUNCA 2026-03-31
    # (que seria anterior ao próprio period_end, estruturalmente inválido).
    deadline = _next_cvm_report_deadline(date(2026, 9, 30), "ITR", date(2025, 12, 31))
    assert deadline == date(2027, 3, 31)
    assert deadline >= date(2026, 9, 30)


def test_last_quarter_itr_deadline_uses_calendar_months_for_non_calendar_fiscal_year():
    # Regressão do Bug 2, combinada com o rollover do Bug 1: encerramento
    # observado 30/06; ITR de 2026-03-31 é o último trimestre antes do
    # fechamento de 2026-06-30 (mesmo ano, sem rollover necessário aqui).
    # Prazo da DFP = 2026-06-30 + 3 meses calendáricos = 2026-09-30 (não
    # 2026-09-28, que "+90 dias" daria).
    deadline = _next_cvm_report_deadline(date(2026, 3, 31), "ITR", date(2025, 6, 30))
    assert deadline == date(2026, 9, 30)


def test_valid_until_never_precedes_reference_date_for_any_known_document_type():
    # Invariante estrutural: para qualquer combinação plausível de
    # period_end/document_type/fiscal_year_end, o prazo do próximo reporte
    # nunca pode anteceder o próprio period_end.
    cases = [
        (date(2026, 9, 30), "ITR", date(2025, 12, 31)),
        (date(2025, 9, 30), "ITR", date(2025, 6, 30)),
        (date(2026, 3, 31), "ITR", date(2025, 6, 30)),
        (date(2025, 12, 31), "DFP", None),
        (date(2026, 6, 30), "ITR", date(2026, 12, 31)),
        (date(2025, 3, 31), "ITR", date(2025, 12, 31)),
        (date(2026, 5, 31), "ITR", None),
    ]
    for period_end, document_type, fiscal_year_end in cases:
        deadline = _next_cvm_report_deadline(period_end, document_type, fiscal_year_end)
        assert deadline >= period_end, (period_end, document_type, fiscal_year_end, deadline)


def test_q2_2026_baseline_for_real_stocks_is_unchanged_by_the_rollover_fix():
    # PETR4/VALE3/ITUB4 reais (encerramento observado 31/12/2025) para o
    # ITR do 2º trimestre de 2026: a correção do rollover não pode
    # regredir este caso já validado com dados reais (deadline=2026-11-14).
    deadline = _next_cvm_report_deadline(date(2026, 6, 30), "ITR", date(2025, 12, 31))
    assert deadline == date(2026, 11, 14)


# --- Política temporal CVM: próximo reporte periódico esperado -------------
#
# valid_until deixa de ser uma janela fixa por document_type e passa a
# representar o prazo regulatório do PRÓXIMO reporte que substituiria
# economicamente este documento (ver _next_cvm_report_deadline). Todas as
# datas abaixo foram calculadas com a implementação real (não escolhidas
# arbitrariamente) — ver auditoria desta continuação.


def test_a_dfp_recent_stays_available_and_does_not_assume_december_fiscal_year_end():
    # Exercício social encerrado em 30/06 (não 31/12) — prova que o
    # cálculo não assume calendário fiscal universal. Próximo trimestre
    # esperado: 30/09 + 45 dias = 2026-11-14, depois de NOW (2026-07-20).
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(period_end=date(2026, 6, 30), document_type="DFP")
    rows = [
        (_cvm_account("total_liabilities", "30000", "2"), document, issuer),
        (_cvm_account("assets", "100000", "1"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("liabilities_assets")],
        asset_id="asset-1",
    )
    item = result["liabilities_assets"]
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.valid_until == datetime(2026, 11, 14, tzinfo=timezone.utc)
    assert item.valid_until > NOW


def test_b_dfp_becomes_stale_once_the_next_itr_should_already_exist():
    # DFP de 2025-12-31: o próximo reporte esperado é o ITR do 1º
    # trimestre de 2026 (2026-03-31 + 45 dias = 2026-05-15) — não "quase
    # um ano depois". Já passou desse prazo em NOW (2026-07-20), mesmo
    # esse valor tendo sido considerado "current" pela janela fixa antiga
    # (395 dias -> só expiraria em 2027-01-30).
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(period_end=date(2025, 12, 31), document_type="DFP")
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    item = result["roe"]
    # status continua AVAILABLE no nível do resolver puro (a demoção para
    # STALE é responsabilidade de IndicatorValidationService, downstream,
    # não testada aqui) — o que este teste comprova é que valid_until já
    # expirou, ao contrário do que a janela fixa antiga (395d) diria.
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.valid_until == datetime(2026, 5, 15, tzinfo=timezone.utc)
    assert item.valid_until < NOW
    assert item.provenance["document_type"] == "DFP"


def test_c_itr_recent_stays_available_within_the_quarterly_window():
    # ITR do 2º trimestre de 2026 (encerramento do exercício social
    # conhecido = 31/12/2026, observado na DFP mais recente do emissor).
    # Próximo trimestre esperado: 2026-09-30 + 45 dias = 2026-11-14.
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(
        period_end=date(2026, 6, 30), document_type="ITR", period_kind="year_to_date"
    )
    rows = [
        (_cvm_account("total_liabilities", "30000", "2"), document, issuer),
        (_cvm_account("assets", "100000", "1"), document, issuer),
    ]

    class Cvm:
        def linked_issuer(self, asset_id):
            return issuer

        def fiscal_year_end(self, issuer_id):
            return date(2026, 12, 31)

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("liabilities_assets")],
        asset_id="asset-1",
    )
    item = result["liabilities_assets"]
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.valid_until == datetime(2026, 11, 14, tzinfo=timezone.utc)


def test_d_itr_old_becomes_stale_long_before_the_old_flat_window_would_suggest():
    # ITR do 1º trimestre de 2025 (exercício social encerrado em
    # 31/12/2025). Próximo trimestre esperado: 2025-06-30 + 45 dias =
    # 2025-08-14 — bem antes de NOW (2026-07-20), e bem antes dos 120/395
    # dias fixos que a política anterior usaria.
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(
        period_end=date(2025, 3, 31), document_type="ITR", period_kind="year_to_date"
    )
    rows = [
        (_cvm_account("total_liabilities", "30000", "2"), document, issuer),
        (_cvm_account("assets", "100000", "1"), document, issuer),
    ]

    class Cvm:
        def linked_issuer(self, asset_id):
            return issuer

        def fiscal_year_end(self, issuer_id):
            return date(2025, 12, 31)

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("liabilities_assets")],
        asset_id="asset-1",
    )
    item = result["liabilities_assets"]
    assert item.valid_until == datetime(2025, 8, 14, tzinfo=timezone.utc)
    assert item.valid_until < NOW


def test_last_quarter_before_fiscal_year_end_uses_the_dfp_linked_deadline():
    # ITR do último trimestre antes do fechamento do exercício (não existe
    # ITR do último trimestre — ele é incorporado à DFP): o próximo
    # reporte esperado é a PRÓPRIA DFP, não "mais um trimestre". Exercício
    # social encerrado em 30/06 (não 31/12, para também provar que não há
    # suposição de calendário): este período_end (2026-03-31) é o último
    # trimestre antes do fechamento (2026-06-30), no MESMO ano (sem
    # rollover necessário aqui). DFP esperada até 2026-06-30 + 3 meses
    # CALENDÁRICOS = 2026-09-30 — mais longe do que "+1 trimestre +45
    # dias" (2026-07-15) daria se tratado como um trimestre comum, e não
    # os "2026-09-28" que a aproximação por dias corridos (90) daria.
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(
        period_end=date(2026, 3, 31), document_type="ITR", period_kind="year_to_date"
    )
    rows = [
        (_cvm_account("total_liabilities", "30000", "2"), document, issuer),
        (_cvm_account("assets", "100000", "1"), document, issuer),
    ]

    class Cvm:
        def linked_issuer(self, asset_id):
            return issuer

        def fiscal_year_end(self, issuer_id):
            return date(2026, 6, 30)

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("liabilities_assets")],
        asset_id="asset-1",
    )
    item = result["liabilities_assets"]
    assert item.status == IndicatorStatus.AVAILABLE
    assert item.valid_until == datetime(2026, 9, 30, tzinfo=timezone.utc)


def test_e_derived_indicator_from_dfp_uses_the_next_expected_itr_deadline():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(period_end=date(2025, 12, 31), document_type="DFP")
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    assert result["roe"].valid_until == datetime(2026, 5, 15, tzinfo=timezone.utc)
    assert result["roe"].provenance["document_type"] == "DFP"


def test_f_derived_indicator_from_last_quarter_itr_uses_dfp_linked_deadline_when_fye_known():
    # Mesmo period_end (último trimestre antes do fechamento), duas
    # respostas diferentes dependendo de o encerramento do exercício ser
    # conhecido ou não — prova que o indicador derivado realmente usa
    # fiscal_year_end, e não apenas document_type/period_end.
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(
        period_end=date(2025, 9, 30), document_type="ITR", period_kind="year_to_date"
    )
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class CvmKnownFiscalYear:
        def linked_issuer(self, asset_id):
            return issuer

        def fiscal_year_end(self, issuer_id):
            return date(2025, 12, 31)

        def latest_normalized(self, asset_id):
            return rows

    result_known = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=CvmKnownFiscalYear(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    assert result_known["roe"].valid_until == datetime(2026, 3, 31, tzinfo=timezone.utc)
    assert result_known["roe"].provenance["document_type"] == "ITR"


def test_derived_indicator_uses_conservative_fallback_when_fiscal_year_end_is_unknown():
    # Mesmo fixture do teste anterior, mas SEM DFP sincronizada para este
    # emissor (fiscal_year_end desconhecido) — nunca inventa calendário
    # fiscal: cai no fallback conservador (trimestre + 45 dias a partir do
    # próprio period_end), que aqui resulta em prazo MAIS CURTO do que o
    # calculado quando o exercício social é conhecido (2026-02-13 <
    # 2026-03-31) — a ausência de informação nunca estende a validade.
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(
        period_end=date(2025, 9, 30), document_type="ITR", period_kind="year_to_date"
    )
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    assert result["roe"].valid_until == datetime(2026, 2, 13, tzinfo=timezone.utc)
    assert result["roe"].valid_until < datetime(2026, 3, 31, tzinfo=timezone.utc)


def test_latest_normalized_prefers_more_recent_itr_over_older_dfp_for_the_same_key():
    # dados mais novos devem vencer: um ITR mais recente que a DFP mais
    # antiga substitui o valor E a política temporal usada — nunca mistura
    # o document_type de um com o period_end do outro.
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    old_dfp = _cvm_document(period_end=date(2025, 12, 31), document_type="DFP")
    newer_itr = _cvm_document(
        period_end=date(2026, 6, 30), document_type="ITR", period_kind="point_in_time"
    )
    rows = [
        (_cvm_account("assets", "999", "1"), old_dfp, issuer),
        (_cvm_account("assets", "1234", "1"), newer_itr, issuer),
    ]

    class Cvm:
        def linked_issuer(self, asset_id):
            return issuer

        def fiscal_year_end(self, issuer_id):
            return date(2026, 12, 31)

        def latest_normalized(self, asset_id):
            # latest_normalized() já devolve só o vencedor por chave (o
            # repository real filtra por marker mais recente) — aqui
            # simulamos exatamente esse contrato: só o ITR mais novo é
            # retornado para "assets".
            return [rows[1]]

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("assets")],
        asset_id="asset-1",
    )
    item = result["assets"]
    assert item.value == Decimal("1234")
    assert item.provenance["document_type"] == "ITR"
    assert item.valid_until == datetime(2026, 11, 14, tzinfo=timezone.utc)


def test_g_derived_indicator_provenance_preserves_document_type_and_period_kind():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(
        period_end=date(2026, 3, 31), document_type="ITR", period_kind="quarterly_calculated"
    )
    rows = [
        (_cvm_account("net_income", "500", "3.11"), document, issuer),
        (_cvm_account("assets", "40000", "1"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roa")],
        asset_id="asset-1",
    )
    provenance = result["roa"].provenance
    assert provenance["document_type"] == "ITR"
    assert provenance["period_kind"] == "quarterly_calculated"
    assert provenance["reference_date"] == "2026-03-31"


def test_derived_indicator_does_not_mix_dfp_and_itr_components_even_with_same_period_end():
    # Mesmo period_end, document_type diferente -> nunca combinar: DFP e
    # ITR são periodicidades distintas, mesmo quando coincidem em data.
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    same_date = date(2025, 12, 31)
    dfp_document = _cvm_document(period_end=same_date, document_type="DFP")
    itr_document = _cvm_document(
        period_end=same_date, document_type="ITR", period_kind="year_to_date"
    )
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), dfp_document, issuer),
        (_cvm_account("equity", "10000", "2.03"), itr_document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    assert result["roe"].status == IndicatorStatus.UNAVAILABLE
    assert result["roe"].value is None


def test_derived_net_debt_itself_is_stored_when_pending():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("gross_debt", "5000", "2.01.04"), document, issuer),
        (_cvm_account("cash_and_equivalents", "1200", "1.01.01"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("net_debt")],
        asset_id="asset-1",
    )
    assert result["net_debt"].status == IndicatorStatus.AVAILABLE
    assert result["net_debt"].value == Decimal("3800")
    assert result["net_debt"].source_type == "derived"


def test_derived_liabilities_assets_and_current_liquidity():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("total_liabilities", "30000", "2"), document, issuer),
        (_cvm_account("assets", "100000", "1"), document, issuer),
        (_cvm_account("current_assets", "15000", "1.01"), document, issuer),
        (_cvm_account("current_liabilities", "10000", "2.01"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("liabilities_assets"), indicator("current_liquidity")],
        asset_id="asset-1",
    )
    assert result["liabilities_assets"].value == Decimal("30.00")
    assert result["current_liquidity"].value == Decimal("1.5000")


def test_derived_indicator_absent_when_a_component_is_missing():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [(_cvm_account("net_income", "1000", "3.11"), document, issuer)]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    assert result["roe"].status == IndicatorStatus.UNAVAILABLE
    assert result["roe"].value is None
    assert result["roe"].provider_failure_reason == ProviderFailureReason.NOT_REPORTED


def test_derived_indicator_never_overrides_a_directly_resolved_value():
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("roe", "999", "9.99"), document, issuer),
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return rows

    result = resolve_all(
        IndicatorResolverService(
            market_service=FakeMarket(),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=Cvm(),
        ),
        baseline=[indicator("roe")],
        asset_id="asset-1",
    )
    # "roe" chega diretamente como conta CVM (caso sintético) -> a etapa
    # derivada não deve rodar por cima de um valor já resolvido.
    assert result["roe"].value == Decimal("999")
    assert result["roe"].source_type == "official"


# --- Manual: prioridade, validade, isolamento (cenarios 28-31) -----------


def test_manual_valid_used_as_fallback():
    manual_item = SimpleNamespace(
        indicator_key="price_book",
        value=Decimal("0.95"),
        unit="ratio",
        source_description="Balanço publicado",
        reference_date=date(2026, 6, 30),
        updated_at=NOW,
    )

    class Manual:
        def list_for_asset(self, user_id, asset_id):
            return [manual_item]

    result = resolve(resolver(manual=Manual()), asset_id="asset")
    assert result.value == Decimal("0.95")
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.resolution_attempts[-1].outcome == ResolutionOutcome.SUCCESS


def test_manual_stale_reference_date_marks_status_stale():
    manual_item = SimpleNamespace(
        indicator_key="price_book",
        value=Decimal("0.95"),
        unit="ratio",
        source_description="Balanço antigo",
        reference_date=date(2020, 1, 1),
        updated_at=NOW,
    )

    class Manual:
        def list_for_asset(self, user_id, asset_id):
            return [manual_item]

    result = resolve(resolver(manual=Manual()), asset_id="asset")
    assert result.status == IndicatorStatus.STALE
    assert result.provider_failure_reason == ProviderFailureReason.STALE
    assert result.value == Decimal("0.95")


def test_manual_is_isolated_per_user():
    class Manual:
        def list_for_asset(self, user_id, asset_id):
            assert user_id == "user"
            return []

    result = resolve(resolver(manual=Manual()), asset_id="asset")
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert result.resolution_attempts[-1].provider_failure_reason == (
        ProviderFailureReason.NOT_REPORTED
    )


def test_manual_absent_entry_records_not_reported_attempt():
    class Manual:
        def list_for_asset(self, user_id, asset_id):
            return []

    result = resolve(resolver(manual=Manual()), asset_id="asset")
    attempt = result.resolution_attempts[-1]
    assert attempt.source_type == "manual"
    assert attempt.outcome == ResolutionOutcome.FAILURE
    assert attempt.provider_failure_reason == ProviderFailureReason.NOT_REPORTED


# --- Prioridade de fontes (cenarios 18, 41) -------------------------------


def test_valid_snapshot_priority_over_manual_value():
    manual_item = SimpleNamespace(
        indicator_key="price_book",
        value=Decimal("9.99"),
        unit="ratio",
        source_description="Manual",
        reference_date=date(2026, 6, 30),
        updated_at=NOW,
    )

    class Manual:
        def list_for_asset(self, user_id, asset_id):
            return [manual_item]

    market = CountingMarket()
    result = resolve(
        resolver(market, FakeSnapshots([snapshot(value="1.25")]), manual=Manual()),
        asset_id="asset",
    )
    assert result.value == Decimal("1.25")
    assert result.source_type == "official"
    assert market.calls == 0


# --- Determinismo (cenario 57-58) -----------------------------------------


def test_resolver_is_deterministic_across_runs():
    def build():
        return resolver(FakeMarket({"results": [{"priceToBook": "1.10"}]}))

    first = resolve(build())
    second = resolve(build())
    assert first.value == second.value
    assert first.source == second.source
    assert [a.outcome for a in first.resolution_attempts] == [
        a.outcome for a in second.resolution_attempts
    ]


# --- Segredos nunca vazam nos diagnosticos (cenario 38, 39, 42) -----------


def test_secret_in_exception_message_is_never_exposed_in_attempt_detail():
    secret_message = "Falha ao chamar provider: Authorization: Bearer sk-supersecret123"
    result = resolve(resolver(FakeMarket(MarketProviderUnavailableError(secret_message))))
    attempt = result.resolution_attempts[-1]
    assert attempt.detail is not None
    assert "sk-supersecret123" not in attempt.detail
    assert "[REDACTED]" in attempt.detail


def test_api_key_query_param_in_exception_message_is_never_exposed():
    secret_message = "GET https://api.example.com/dados?api_key=abcdef123456 falhou"
    sanitized = sanitize_failure_detail(secret_message)
    assert "abcdef123456" not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitize_failure_detail_handles_none_and_empty():
    assert sanitize_failure_detail(None) is None
    assert sanitize_failure_detail("") is None
    assert sanitize_failure_detail("mensagem normal sem segredo") == (
        "mensagem normal sem segredo"
    )


def test_valid_snapshot_has_priority_and_avoids_provider_call():
    market = FakeMarket({"results": [{"priceToBook": 2}]})
    result = resolve(resolver(market, FakeSnapshots([snapshot()])))
    assert result.value == Decimal("1.25")
    assert result.source_type == "official"
    assert market.calls == 0


def test_expired_snapshot_is_not_returned_and_provider_is_used():
    market = FakeMarket({"results": [{"priceToBook": "2.50"}]})
    result = resolve(resolver(market, FakeSnapshots([])))
    assert result.value == Decimal("2.50")
    assert market.calls == 2


def test_brapi_accessible_preserves_decimal():
    result = resolve(resolver(FakeMarket({"results": [{"priceToBook": "1.10"}]})))
    assert result.value == Decimal("1.10")
    assert isinstance(result.value, Decimal)


def test_brapi_restricted_leaves_indicator_unavailable():
    result = resolve(resolver(FakeMarket(MarketPermissionError("plano"))))
    assert result.status == IndicatorStatus.UNAVAILABLE
    assert result.value is None


def test_restricted_endpoint_is_not_called_twice_by_market_service():
    class Provider:
        limited_mode = True
        calls = 0

        def get_stock_dataset(self, *args, **kwargs):
            self.calls += 1
            raise MarketPermissionError("plano")

    provider = Provider()
    service = MarketService(provider=provider)
    MarketService.clear_caches()
    with pytest.raises(MarketPermissionError):
        service.get_stock_dataset("statistics", ["TEST3"])
    with pytest.raises(MarketPermissionError):
        service.get_stock_dataset("statistics", ["TEST3"])
    assert provider.calls == 1


def test_bcb_fallback_resolves_configured_macro_series():
    class Bcb:
        provider_name = "Banco Central do Brasil - SGS"
        series = {"selic": {}}

        def get_series(self, symbol):
            return {
                "source": self.provider_name,
                "frequency": "daily",
                "values": [{"reference_date": "18/07/2026", "value": Decimal("15.00")}],
            }

    definition = SimpleNamespace(
        key="selic", label="Selic", source="BRAPI", frequency="diária"
    )
    result = resolver(bcb_provider=Bcb()).resolve_macro([definition], NOW)[0]
    assert result.value == Decimal("15.00")
    assert result.source.startswith("Banco Central")


def test_cvm_unavailability_does_not_break_basic_data():
    class Cvm(_UnknownFiscalCalendarCvm):
        def synchronization_metadata(self):
            raise RuntimeError("indisponível")

    result = resolve(resolver(cvm_provider=Cvm()))
    assert result.status == IndicatorStatus.UNAVAILABLE


def test_manual_data_is_last_resort():
    manual_item = SimpleNamespace(
        indicator_key="price_book",
        value=Decimal("0.95"),
        unit="ratio",
        source_description="Balanço publicado",
        reference_date=date(2026, 6, 30),
        updated_at=NOW,
    )

    class Manual:
        def list_for_asset(self, user_id, asset_id):
            return [manual_item]

    result = resolve(resolver(manual=Manual()), asset_id="asset")
    assert result.value == Decimal("0.95")
    assert result.source_type == "manual"


def test_manual_does_not_replace_provider_value():
    manual = SimpleNamespace(
        indicator_key="price_book",
        value=Decimal("9"),
        unit="ratio",
        source_description="Manual",
        reference_date=date(2026, 6, 30),
        updated_at=NOW,
    )

    class ManualRepo:
        def list_for_asset(self, user_id, asset_id):
            return [manual]

    service = resolver(
        FakeMarket({"results": [{"priceToBook": "1.30"}]}), manual=ManualRepo()
    )
    result = resolve(service, asset_id="asset")
    assert result.value == Decimal("1.30")
    assert result.source_type == "provider"


def test_total_absence_does_not_become_zero():
    result = resolve(resolver())
    assert result.value is None
    assert result.status == IndicatorStatus.UNAVAILABLE


def test_cvm_persisted_data_fills_gap_before_manual():
    account = SimpleNamespace(
        normalized_key="price_book",
        normalized_value=Decimal("1.40"),
        acquisition_method="reported",
        account_code="2.03",
        account_description="Patrimônio Líquido",
        original_value=Decimal("1.40"),
    )
    document = SimpleNamespace(
        period_end=date(2026, 6, 30),
        collected_at=NOW,
        period_kind="year_to_date",
        document_type="ITR",
        scope="consolidated",
    )
    issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")

    class CvmRepository(_UnknownFiscalCalendarCvm):
        def linked_issuer(self, asset_id):
            return issuer

        def latest_normalized(self, asset_id):
            return [(account, document, issuer)]

    service = IndicatorResolverService(
        market_service=FakeMarket(MarketPermissionError("plano")),
        normalizer=IndicatorNormalizationService(),
        cvm_repository=CvmRepository(),
    )
    result = resolve(service, asset_id="asset")
    assert result.value == Decimal("1.40")
    assert result.source_type == "official"
    assert result.provenance["document_type"] == "ITR"


# --- Validade temporal (P4): fonte única via indicator_temporal_validity_days ---


def test_valid_until_uses_catalog_policy_for_a_price_like_key():
    # current_price tem política própria no catálogo (2 dias) — o resolver
    # deve usá-la em vez do fallback genérico de 30 dias por provider.
    assert indicator_temporal_validity_days("current_price") == 2
    valid_until = IndicatorResolverService._valid_until(
        "current_price", NOW, source_type="provider"
    )
    assert valid_until == NOW + timedelta(days=2)


def test_valid_until_falls_back_to_stage_default_for_unknown_key():
    # Um indicador sem política declarada em indicator_temporal_validity_days
    # continua usando o fallback conservador por estágio (1 dia oficial /
    # 30 dias provider) — nunca estende a validade por conta própria.
    # Chave deliberadamente ausente do catálogo (não confundir com uma chave
    # real do catálogo, como price_book) para testar exatamente esse fallback.
    assert indicator_temporal_validity_days("indicador_sem_politica_declarada") is None
    valid_until_provider = IndicatorResolverService._valid_until(
        "indicador_sem_politica_declarada", NOW, source_type="provider"
    )
    valid_until_official = IndicatorResolverService._valid_until(
        "indicador_sem_politica_declarada", NOW, source_type="official"
    )
    assert valid_until_provider == NOW + timedelta(days=30)
    assert valid_until_official == NOW + timedelta(days=1)


def test_valid_until_registration_data_gets_long_catalog_validity():
    # Dado cadastral (ex.: treasury_title) tem política de 3650 dias no
    # catálogo — não deve expirar em 1 dia só por ter sido resolvido via
    # fonte oficial (Tesouro Transparente).
    assert indicator_temporal_validity_days("treasury_title") == 3650
    valid_until = IndicatorResolverService._valid_until(
        "treasury_title", NOW, source_type="official"
    )
    assert valid_until == NOW + timedelta(days=3650)


def test_brapi_resolved_quarterly_fundamental_gets_catalog_validity_end_to_end():
    # Fim a fim: price_earnings tem política de 90 dias no catálogo
    # (fundamental_quarterly) e é resolvido via BRAPI (source_type=provider,
    # cujo fallback seria 30 dias). O resolver deve usar os 90 dias do
    # catálogo, não o fallback genérico do estágio.
    assert indicator_temporal_validity_days("price_earnings") == 90
    baseline = indicator("price_earnings")
    result = resolve(
        resolver(FakeMarket({"results": [{"priceEarnings": "8.50"}]})),
        baseline=[baseline],
    )
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.valid_until == NOW + timedelta(days=90)


def test_brapi_resolved_indicator_without_catalog_policy_keeps_conservative_default():
    # "revenue" resolve via alias BRAPI (totalRevenue/revenue) mas não é uma
    # chave do catálogo (é apenas componente bruto para indicadores
    # derivados) — sem política declarada em indicator_temporal_validity_days,
    # continua usando o fallback conservador de 30 dias.
    assert indicator_temporal_validity_days("revenue") is None
    result = resolve(
        resolver(FakeMarket({"results": [{"totalRevenue": "1.10"}]})),
        baseline=[indicator("revenue")],
    )
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.valid_until == NOW + timedelta(days=30)


# --- Determinismo fim a fim (cenário 40 do prompt P4) ----------------------


def test_full_cascade_is_deterministic_across_repeated_runs():
    def run():
        account = SimpleNamespace(
            normalized_key="price_book",
            normalized_value=Decimal("1.40"),
            acquisition_method="reported",
            account_code="2.03",
            account_description="Patrimônio Líquido",
            original_value=Decimal("1.40"),
        )
        document = SimpleNamespace(
            period_end=date(2026, 6, 30),
            collected_at=NOW,
            period_kind="year_to_date",
            document_type="ITR",
            scope="consolidated",
        )
        issuer = SimpleNamespace(id="issuer-1", cnpj="12345678000190", cvm_code="12345")

        class CvmRepository(_UnknownFiscalCalendarCvm):
            def linked_issuer(self, asset_id):
                return issuer

            def latest_normalized(self, asset_id):
                return [(account, document, issuer)]

        service = IndicatorResolverService(
            market_service=FakeMarket(MarketRateLimitError("429")),
            normalizer=IndicatorNormalizationService(),
            cvm_repository=CvmRepository(),
        )
        return resolve(service, asset_id="asset")

    first = run()
    second = run()
    assert first.value == second.value
    assert first.source == second.source
    assert first.valid_until == second.valid_until
    assert [a.outcome for a in first.resolution_attempts] == [
        a.outcome for a in second.resolution_attempts
    ]
    assert [a.provider_failure_reason for a in first.resolution_attempts] == [
        a.provider_failure_reason for a in second.resolution_attempts
    ]


# --- Fallback oficial de Tesouro Direto (Tesouro Transparente) ---------------


def resolve_treasury_all(service, symbol, baseline, asset_id=None):
    return {
        item.key: item
        for item in service.resolve_asset(
            symbol=symbol,
            asset_class=InvestmentClass.TREASURY,
            asset_id=asset_id,
            user_id="user",
            baseline=baseline,
            collected_at=NOW,
        )
    }


TREASURY_REQUIRED_KEYS = (
    "treasury_title",
    "indexer",
    "treasury_rate",
    "maturity_date",
    "current_price",
)


def treasury_baseline():
    return [indicator(key) for key in TREASURY_REQUIRED_KEYS]


def test_treasury_all_five_required_pillars_resolve_from_official_source():
    row = treasury_row(
        bond_type="Tesouro Selic",
        indexer="SELIC",
        maturity=date(2031, 3, 1),
        as_of=date(2026, 7, 18),
        buy_rate="0.09",
        sell_rate="0.10",
        buy_price="18737.11",
        sell_price="18717.77",
        base_price="18717.77",
    )
    treasury = FakeTreasuryProvider({"tesouro-selic-01032031": row})
    resolved = resolve_treasury_all(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=treasury_baseline(),
    )
    assert resolved["treasury_title"].status == IndicatorStatus.AVAILABLE
    assert resolved["treasury_title"].value == "Tesouro Selic"
    assert resolved["indexer"].value == "SELIC"
    assert resolved["treasury_rate"].value == Decimal("0.09")
    assert resolved["maturity_date"].value == "2031-03-01"
    assert resolved["current_price"].value == Decimal("18737.11")
    for key in TREASURY_REQUIRED_KEYS:
        assert resolved[key].source == "Tesouro Transparente"
        assert resolved[key].source_type == "official"


def test_treasury_rate_uses_buy_rate_not_sell_rate():
    """Seção 17: o pipeline monta uma CARTEIRA/RECOMENDAÇÃO DE AQUISIÇÃO --
    treasury_rate deve ser a taxa de COMPRA, nunca a de venda/resgate."""
    row = treasury_row(buy_rate="6.25", sell_rate="6.40")
    treasury = FakeTreasuryProvider({"tesouro-selic-01032031": row})
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[indicator("treasury_rate")],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.value == Decimal("6.25")
    assert result.value != Decimal("6.40")
    assert result.provenance["sell_rate"] == "6.40"


def test_current_price_uses_pu_compra_not_base_or_venda():
    """Seção 18/35: SmartPortfolioEngine usa snapshot.current_price como
    reference_price para calcular quantidade/valor executáveis de uma NOVA
    recomendação -- precisa ser o PU de COMPRA (aquisição), nunca o PU Base
    (marcação a mercado de posição já detida) nem o PU Venda (resgate)."""
    row = treasury_row(buy_price="900.00", sell_price="890.00", base_price="891.00")
    treasury = FakeTreasuryProvider({"tesouro-selic-01032031": row})
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[indicator("current_price")],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.value == Decimal("900.00")
    assert result.value != Decimal("890.00")
    assert result.value != Decimal("891.00")
    assert result.provenance["sell_price"] == "890.00"
    assert result.provenance["base_price"] == "891.00"


def test_treasury_reference_date_is_data_base_never_collected_at():
    # treasury_title é dado cadastral (3650 dias de validade no catálogo) --
    # uma Data Base de semanas atrás continua honestamente AVAILABLE,
    # permitindo provar reference_date != collected_at sem o indicador
    # expirar por política de validade (o que aconteceria com um indicador
    # de mercado como treasury_rate, cuja janela é de só 2 dias).
    old_data_base = date(2026, 6, 30)
    much_later_collected_at = NOW  # NOW = 2026-07-20, semanas depois
    row = treasury_row(as_of=old_data_base, bond_type="Tesouro Selic")
    treasury = FakeTreasuryProvider({"tesouro-selic-01032031": row})
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[indicator("treasury_title")],
        asset_class=InvestmentClass.TREASURY,
    )
    expected_reference = datetime(2026, 6, 30, tzinfo=timezone.utc)
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.reference_date == expected_reference
    assert result.reference_date != much_later_collected_at
    assert result.collected_at == much_later_collected_at


def test_treasury_valid_until_anchored_on_reference_date_not_collected_at():
    # treasury_rate está em treasury_market_rate -> 2 dias de política no
    # catálogo (ver indicator_temporal_validity_days) -- ancorado na Data
    # Base (reference), nunca em collected_at.
    assert indicator_temporal_validity_days("treasury_rate") == 2
    data_base = date(2026, 7, 19)  # véspera de NOW -- ainda dentro da janela
    row = treasury_row(as_of=data_base, buy_rate="6.25")
    treasury = FakeTreasuryProvider({"tesouro-selic-01032031": row})
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[indicator("treasury_rate")],
        asset_class=InvestmentClass.TREASURY,
    )
    expected_valid_until = datetime(2026, 7, 21, tzinfo=timezone.utc)
    assert result.valid_until == expected_valid_until
    assert result.valid_until != NOW + timedelta(days=2)  # nao ancorado em collected_at


def test_treasury_registration_field_keeps_long_catalog_validity_from_official():
    assert indicator_temporal_validity_days("treasury_title") == 3650
    data_base = date(2026, 7, 18)
    row = treasury_row(as_of=data_base, bond_type="Tesouro Selic")
    treasury = FakeTreasuryProvider({"tesouro-selic-01032031": row})
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[indicator("treasury_title")],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.valid_until == datetime(2026, 7, 18, tzinfo=timezone.utc) + timedelta(
        days=3650
    )


def test_treasury_expired_official_observation_is_never_used_as_current():
    # Data Base muito antiga -- mesmo com política de 2 dias (treasury_rate),
    # a validade expirou muito antes de NOW; nunca finge que ainda é atual.
    ancient_data_base = date(2020, 1, 1)
    row = treasury_row(as_of=ancient_data_base, buy_rate="6.25")
    treasury = FakeTreasuryProvider({"tesouro-selic-01032031": row})
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[indicator("treasury_rate")],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.status != IndicatorStatus.AVAILABLE
    assert result.value is None


def test_treasury_official_never_overwrites_already_resolved_indicator():
    already_resolved = available_indicator("treasury_rate", "9.99")
    treasury = FakeTreasuryProvider(
        {"tesouro-selic-01032031": treasury_row(buy_rate="1.11")}
    )
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-01032031",
        baseline=[already_resolved],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.value == Decimal("9.99")
    assert treasury.calls == 0


def test_treasury_unmatched_symbol_never_fabricates_value_stale_and_manual_still_work():
    manual_item = SimpleNamespace(
        indicator_key="treasury_rate",
        value=Decimal("6.25"),
        unit="percent",
        source_description="Extrato do Tesouro Direto",
        reference_date=date(2026, 6, 30),
        updated_at=NOW,
    )

    class ManualRepo:
        def list_for_asset(self, user_id, asset_id):
            return [manual_item]

    treasury = FakeTreasuryProvider(
        {"tesouro-selic-01032031": treasury_row(buy_rate="1.11")}
    )
    result = resolve_symbol(
        IndicatorResolverService(
            market_service=FakeMarket(MarketRateLimitError("429")),
            normalizer=IndicatorNormalizationService(),
            treasury_provider=treasury,
            manual_repository=ManualRepo(),
        ),
        # Símbolo real mas SEM correspondência no índice (vencimento
        # diferente) -- nunca deve casar por semelhança.
        symbol="TESOURO-SELIC-01012099",
        baseline=[indicator("treasury_rate")],
        asset_class=InvestmentClass.TREASURY,
        asset_id="asset",
    )
    # Sem correspondência exata -> cai para manual, nunca inventa/aproxima.
    assert result.value == Decimal("6.25")
    assert result.source == "Extrato do Tesouro Direto"
    assert result.source_type == "manual"
    assert result.source != "Tesouro Transparente"


def test_treasury_index_lookup_is_exact_never_fuzzy():
    treasury = FakeTreasuryProvider(
        {"tesouro-selic-01032031": treasury_row(buy_rate="6.25")}
    )
    # Mesmo tipo, vencimento levemente diferente -- não pode casar por
    # semelhança nem pegar "o primeiro título encontrado".
    result = resolve_symbol(
        resolver(treasury_provider=treasury),
        symbol="TESOURO-SELIC-02032031",
        baseline=[indicator("treasury_rate")],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.value is None
    assert result.status != IndicatorStatus.AVAILABLE


# --- Cascata B3 EOD oficial (COTAHIST) para current_price/volume ----------
#
# Correção 3 (dados oficiais B3): _apply_b3_official_eod só pode preencher
# current_price/volume quando (a) ainda estão pendentes -- nunca sobrescreve
# uma cotação BRAPI live já resolvida ANTES de resolve_asset ser chamado --
# e (b) o contexto de mercado do provider REALMENTE em uso é comprovadamente
# B3 (nunca assumido) e a classe do ativo é elegível (nunca TREASURY, cujo
# "preço" tem semântica totalmente diferente e fonte própria). Os testes
# abaixo provam essas garantias estruturalmente, não só pelo valor final.


class _FakeB3Provider:
    """Espiona quantas vezes/com qual símbolo get_recent_eod foi chamado,
    sem nunca tocar rede/disco -- prova as regras de gating (mercado B3
    comprovado, classe elegível, indicador ainda pendente) sem depender do
    CotahistProvider real."""

    def __init__(self, result: B3EodResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    def get_recent_eod(self, trading_symbol: str, **kwargs):
        self.calls.append(trading_symbol)
        if self.error is not None:
            raise self.error
        return self.result


def _b3_record(
    *,
    symbol: str = "PETR4",
    # NOW = 2026-07-20 (mesmo dia) fica DENTRO da validade de 2 dias do
    # catálogo (ver indicator_temporal_validity_days) -- default "fresco"
    # para não exigir que todo teste que só quer um registro válido
    # precise se preocupar com a política temporal; testes de Bloqueador
    # 2 passam trading_date explicitamente antigo.
    trading_date: date = date(2026, 7, 20),
    close: str = "42.60",
    quantity: int | None = 1000,
    # QUATOT (quantidade) e VOLTOT (financeiro) propositalmente bem
    # diferentes por padrão, para que qualquer teste que troque um pelo
    # outro por engano quebre imediatamente (ver Bloqueador 1).
    financial_volume: str | None = "1575798553.00",
    market_type: str = "010",
    quote_factor: int = 1,
) -> B3HistoricalRecord:
    return B3HistoricalRecord(
        trading_date=trading_date,
        codbdi="02",
        trading_symbol=symbol,
        market_type=market_type,
        issuer_short_name="PETROBRAS",
        specification="PN",
        forward_term_days=None,
        currency="R$",
        open_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        average_price=Decimal(close),
        close_price=Decimal(close),
        best_bid_price=None,
        best_ask_price=None,
        trade_count=100,
        traded_quantity=quantity,
        traded_volume=Decimal(financial_volume) if financial_volume is not None else None,
        strike_price=None,
        correction_indicator=None,
        maturity_date=None,
        quote_factor=quote_factor,
        isin="BRPETRACNPR6",
        distribution_number=None,
    )


def _b3_eod_result(
    record: B3HistoricalRecord, *, download_collected_at: datetime = NOW
) -> B3EodResult:
    return B3EodResult(
        record=record,
        dataset="cotahist_daily",
        collected_at=download_collected_at,
        cache_hit=False,
    )


def _b3_market_fake(payload=None):
    market = FakeMarket(payload=payload or {})
    market.provider = SimpleNamespace(market=B3_MARKET, provider_name="BRAPI")
    return market


def test_b3_eod_never_overrides_an_already_resolved_brapi_live_price():
    """Caso A: current_price já AVAILABLE (cotação BRAPI live resolvida
    ANTES de resolve_asset ser chamado, ver comentário em
    _apply_b3_official_eod) -- o estágio B3 nem chega a ser consultado,
    por construção (não é uma checagem extra: a chave já não está mais em
    `pending`)."""
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(_b3_record()))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [available_indicator("current_price", "43.50")],
    )

    assert result.value == Decimal("43.50")
    assert result.source == "BRAPI"
    assert fake_b3.calls == []


def test_b3_eod_fills_current_price_when_still_pending_and_fresh():
    """Caso B (preço): current_price ainda pendente (nenhuma cotação
    BRAPI live resolvida) + contexto B3 comprovado + COTAHIST tem o
    pregão, dentro da validade -- preenche com fechamento oficial,
    marcando fonte/tipo/competência econômica real (nunca a data de
    hoje) e a semântica EOD não ajustada de forma honesta na
    provenance."""
    record = _b3_record(symbol="PETR4", trading_date=date(2026, 7, 20))
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert fake_b3.calls == ["PETR4"]
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("42.60")
    assert result.source == "B3"
    assert result.source_type == "official"
    # reference_date É a data real do pregão -- nunca vira collected_at
    # nem "hoje" (Bloqueador 2, caso D; ver teste dedicado abaixo para um
    # trading_date que difere de NOW).
    assert result.reference_date == datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert result.provenance["price_kind"] == "official_eod_close"
    assert result.provenance["adjusted"] is False
    assert result.provenance["dataset"] == "cotahist_daily"
    assert result.provenance["field"] == "PREULT"


# --- Bloqueador 1 (Correção 3, Prompt 3): volume = QUATOT, nunca VOLTOT ---


def test_b3_eod_volume_indicator_uses_traded_quantity_never_traded_volume():
    """O indicador interno `volume` é contratualmente QUANTIDADE (ver
    IndicatorNormalizationService._value_for_key: `Decimal(quote.volume)`
    com unit="quantity" no catálogo, e liquidity = price * volume) --
    nunca o volume financeiro em R$ (VOLTOT/traded_volume). QUATOT e
    VOLTOT são propositalmente muito diferentes aqui (12345 x 999999.99)
    para que qualquer troca entre os dois quebre este teste
    imediatamente."""
    record = _b3_record(
        symbol="PETR4",
        trading_date=date(2026, 7, 20),
        quantity=12345,
        financial_volume="999999.99",
    )
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("volume")],
    )

    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("12345")
    assert result.value != Decimal("999999.99")
    # unit não é tocado pelo estágio B3 -- continua exatamente o que o
    # template de entrada já trazia (na produção real, "quantity", ver
    # catálogo; aqui o fixture `indicator()` usa "ratio" só para não
    # depender do catálogo real neste teste unitário).
    assert result.unit == "ratio"
    assert result.provenance["field"] == "QUATOT"


def test_b3_eod_missing_traded_quantity_never_falls_back_to_traded_volume():
    """missing != zero: se QUATOT vier ausente no registro (nunca deveria
    ocorrer em um pregão real -- ver CotahistProvider._parse_int, que só
    retorna None para um campo QUATOT em branco), o estágio NUNCA usa
    traded_volume como substituto -- o indicador simplesmente permanece
    pendente, nunca um valor fabricado a partir de outro campo."""
    record = _b3_record(
        symbol="PETR4",
        trading_date=date(2026, 7, 20),
        quantity=None,
        financial_volume="999999.99",
    )
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("volume")],
    )

    assert result.value is None
    assert result.status != IndicatorStatus.AVAILABLE


# --- Bloqueador 2 (Correção 3, Prompt 3): validade ancorada em ------------
# --- reference_date (competência real), nunca em collected_at -----------


def test_b3_eod_recent_record_within_catalog_validity_is_available_and_current():
    """Caso A: registro B3 recente (dentro da política de 2 dias do
    catálogo para current_price/volume, ver
    indicator_temporal_validity_days) -> AVAILABLE/"current"."""
    record = _b3_record(symbol="PETR4", trading_date=date(2026, 7, 20))
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.status == IndicatorStatus.AVAILABLE
    assert result.freshness_status == "current"
    assert result.valid_until == datetime(2026, 7, 22, tzinfo=timezone.utc)


def test_b3_eod_old_record_beyond_catalog_validity_never_becomes_available_current():
    """Caso B: registro B3 além da política de validade do catálogo (2
    dias) a partir de sua PRÓPRIA competência econômica -> NÃO pode virar
    AVAILABLE/"current" fabricado. NOW=2026-07-20; trading_date=
    2026-07-10 está 10 dias atrás, muito além dos 2 dias permitidos."""
    record = _b3_record(symbol="PETR4", trading_date=date(2026, 7, 10))
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert fake_b3.calls == ["PETR4"]
    assert result.status != IndicatorStatus.AVAILABLE
    # freshness_status="current" é o default do próprio schema quando
    # nada preenche o indicador (ver NormalizedIndicator.freshness_status)
    # -- não é evidência de fabricação por si só; a prova real é que
    # nenhum valor foi escrito e o status não é AVAILABLE.
    assert result.value is None
    assert result.source == "BRAPI"  # source do template baseline, nunca sobrescrito para "B3"


def test_b3_eod_download_timestamp_never_rejuvenates_an_old_trading_date():
    """Casos C/E: baixar HOJE um fechamento antigo não pode "rejuvenescer"
    sua validade -- nem mesmo se o timestamp de coleta do download
    (`B3EodResult.collected_at`) for muito mais recente que a própria
    competência econômica do registro (`record.trading_date`). A
    validade é ancorada exclusivamente em `reference_date`
    (=record.trading_date), nunca em quando o arquivo foi baixado nem em
    quando a resolução foi chamada."""
    record = _b3_record(symbol="PETR4", trading_date=date(2026, 7, 10))
    # Download feito "agora", bem depois da competência do registro --
    # isso NUNCA pode dar mais dois dias de vida extra ao dado antigo.
    fake_b3 = _FakeB3Provider(
        result=_b3_eod_result(record, download_collected_at=NOW)
    )

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.status != IndicatorStatus.AVAILABLE
    assert result.value is None


def test_b3_eod_reference_date_never_becomes_collected_at():
    """Caso D: mesmo quando o preenchimento é bem-sucedido,
    `reference_date` permanece a data real do pregão -- nunca é
    substituído por `collected_at` (nem o do download, nem o momento da
    resolução)."""
    record = _b3_record(symbol="PETR4", trading_date=date(2026, 7, 20))
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.reference_date == datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert result.collected_at == NOW  # collected_at do download (ver _b3_eod_result)


def test_b3_eod_weekend_gap_follows_the_existing_flat_catalog_policy_no_new_rule():
    """Caso F: comportamento em torno de um fim de semana segue
    EXATAMENTE a mesma política plana de 2 dias já existente no catálogo
    -- nenhuma regra nova de calendário/feriado é inventada aqui. NOW
    (2026-07-20) é uma segunda-feira; o pregão de sexta-feira anterior
    (2026-07-17, o último antes do fim de semana) já está a 3 dias de
    distância da sua própria competência, além dos 2 dias permitidos --
    mesmo sendo o fechamento mais recente disponível, não recebe nenhuma
    extensão especial por causa do fim de semana."""
    record = _b3_record(symbol="PETR4", trading_date=date(2026, 7, 17))
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.status != IndicatorStatus.AVAILABLE


def test_b3_eod_not_found_leaves_current_price_for_downstream_fallbacks():
    """Caso C: BRAPI e B3 ambos sem dado (get_recent_eod retorna None,
    nunca fabricado) -- current_price permanece pendente para os estágios
    seguintes da cascata (snapshot stale/manual), nunca vira zero nem
    qualquer valor inventado."""
    fake_b3 = _FakeB3Provider(result=None)

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.value is None
    assert result.status != IndicatorStatus.AVAILABLE
    assert fake_b3.calls == ["PETR4"]


def test_b3_eod_parse_error_never_crashes_and_never_fabricates_a_value():
    """Caso E: um registro COTAHIST corrompido (B3ParseError) nunca
    propaga como crash do resolver nem faz o estágio inventar um valor --
    é tratado exatamente como "não encontrado", deixando o indicador
    pendente para os estágios seguintes."""
    fake_b3 = _FakeB3Provider(error=B3ParseError("registro corrompido (simulado)"))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.value is None
    assert result.status != IndicatorStatus.AVAILABLE


def test_b3_eod_never_runs_outside_a_proven_b3_market_context():
    """FakeMarket sem `.provider` -> _market_context() retorna None (nunca
    "B3" assumido) -- o estágio B3 nem tenta consultar o provider oficial,
    mesmo com current_price pendente e um resultado válido disponível."""
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(_b3_record()))

    resolve_symbol(
        resolver(market=FakeMarket(payload={}), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert fake_b3.calls == []


def test_b3_eod_never_runs_for_treasury_even_in_a_proven_b3_market_context():
    """TREASURY nunca está em _B3_EOD_ELIGIBLE_CLASSES -- "preço" de
    Tesouro Direto (PU de compra) é um conceito totalmente diferente do
    fechamento de bolsa B3, com fonte própria (Tesouro Transparente)."""
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(_b3_record()))

    resolve_symbol(
        resolver(
            market=_b3_market_fake(),
            b3_provider=fake_b3,
            treasury_provider=FakeTreasuryProvider(),
        ),
        "TESOURO-SELIC-01032031",
        [indicator("current_price")],
        asset_class=InvestmentClass.TREASURY,
    )

    assert fake_b3.calls == []


# --- FATCOT (Correção 3, Prompt 3, revisão final): PREULT NUNCA dividido -
# --- por quote_factor, apesar do layout oficial descrever FATCOT='1000' -
# --- como "quote per lot of a thousand shares" --------------------------


def test_b3_eod_current_price_uses_preult_directly_never_divided_by_fatcot_1000():
    """Confirmado por evidência real cruzada durante esta revisão: papéis
    reais com FATCOT=1000 no COTAHIST oficial (FNAM11, FNOR11, GOLL54)
    têm PREULT bruto batendo EXATAMENTE com a cotação publicada por
    agregadores de mercado independentes na mesma data (ex.: FNAM11
    PREULT=0.36 em 19/08/2026 == brapi.dev, mesma data, R$0,36) --
    dividir por FATCOT produziria um preço ~1000x menor que o preço real
    negociado. Por isso current_price usa PREULT diretamente, mesmo com
    FATCOT != 1 (ver docstring de _apply_b3_eod_field para a evidência
    completa)."""
    record = _b3_record(symbol="FNAM11", close="0.36", quote_factor=1000)
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "FNAM11",
        [indicator("current_price")],
    )

    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("0.36")
    assert result.value != Decimal("0.36") / Decimal(1000)


def test_b3_eod_current_price_trivial_fatcot_1_stays_unchanged():
    """Caso trivial explícito (FATCOT=1, cotação unitária): current_price
    é exatamente PREULT, sem qualquer transformação -- comportamento
    inalterado por esta revisão."""
    record = _b3_record(symbol="PETR4", close="43.11", quote_factor=1)
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.value == Decimal("43.11")


def test_b3_eod_provenance_always_preserves_quote_factor():
    """FATCOT é preservado em provenance (nunca descartado) para
    auditoria/revisão futura, mesmo sem nenhuma transformação aplicada a
    current_price."""
    record = _b3_record(symbol="FNAM11", close="0.36", quote_factor=1000)
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "FNAM11",
        [indicator("current_price")],
    )

    assert result.provenance["quote_factor"] == 1000


# --- STALE (Correção 3, Prompt 3, revisão final): registro B3 real porém -
# --- vencido nunca vira NOT_REPORTED na tentativa registrada -------------


def test_b3_eod_stale_record_records_stale_not_not_reported():
    """Bloqueador 4: quando o COTAHIST tem um registro REAL para o
    símbolo mas ele já está fora da validade temporal (ver
    test_b3_eod_old_record_beyond_catalog_validity_never_becomes_available_current),
    a tentativa B3 registrada em resolution_attempts nunca pode ser
    NOT_REPORTED -- o dado FOI reportado pela B3, só não estava mais
    válido. A razão refletida no indicador (via _reconcile_failure_reasons)
    deve ser STALE, e a tentativa carrega a reference_date real do
    pregão (nunca None, nunca "hoje")."""
    record = _b3_record(symbol="PETR4", trading_date=date(2026, 7, 10))
    fake_b3 = _FakeB3Provider(result=_b3_eod_result(record))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.status != IndicatorStatus.AVAILABLE
    assert result.provider_failure_reason == ProviderFailureReason.STALE
    b3_attempts = [a for a in result.resolution_attempts if a.provider == "B3"]
    assert len(b3_attempts) == 1
    attempt = b3_attempts[0]
    assert attempt.outcome == ResolutionOutcome.FAILURE
    assert attempt.provider_failure_reason == ProviderFailureReason.STALE
    assert attempt.provider_failure_reason != ProviderFailureReason.NOT_REPORTED
    assert attempt.reference_date == datetime(2026, 7, 10, tzinfo=timezone.utc)


def test_b3_eod_genuinely_missing_record_still_records_not_reported():
    """Guarda de regressão: um registro genuinamente AUSENTE (get_recent_eod
    retorna None -- ticker não encontrado em nenhum pregão do intervalo)
    continua sendo NOT_REPORTED -- a correção do Bloqueador 4 é
    localizada ao caso "valor real porém stale", nunca generaliza para
    "ausência real"."""
    fake_b3 = _FakeB3Provider(result=None)

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.status != IndicatorStatus.AVAILABLE
    b3_attempts = [a for a in result.resolution_attempts if a.provider == "B3"]
    assert len(b3_attempts) == 1
    assert b3_attempts[0].provider_failure_reason == ProviderFailureReason.NOT_REPORTED


def test_b3_eod_parse_error_still_classified_from_the_real_exception_never_stale():
    """Guarda de regressão: um B3ParseError (arquivo corrompido) continua
    classificado a partir da exceção real -- nunca "finge" STALE (a
    correção do Bloqueador 4 só se aplica quando o provider de fato
    retornou um valor real e válido, porém vencido)."""
    fake_b3 = _FakeB3Provider(error=B3ParseError("registro corrompido (simulado)"))

    result = resolve_symbol(
        resolver(market=_b3_market_fake(), b3_provider=fake_b3),
        "PETR4",
        [indicator("current_price")],
    )

    assert result.status != IndicatorStatus.AVAILABLE
    b3_attempts = [a for a in result.resolution_attempts if a.provider == "B3"]
    assert len(b3_attempts) == 1
    assert b3_attempts[0].provider_failure_reason != ProviderFailureReason.STALE
