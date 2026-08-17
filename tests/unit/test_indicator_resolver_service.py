from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

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
from app.services.indicator_resolver_service import IndicatorResolverService
from app.services.market_service import MarketService


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


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


def test_rate_limited_on_one_source_and_success_on_official_fallback_end_to_end():
    baseline = indicator("treasury_rate")
    result = resolve(
        resolver(
            FakeMarket(MarketRateLimitError("429")),
            treasury_provider=SimpleNamespace(
                fetch_daily_dataset=lambda: [
                    {"symbol": "test3", "buyRate": "6.25"}
                ]
            ),
        ),
        baseline=[baseline],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("6.25")
    reasons = [a.provider_failure_reason for a in result.resolution_attempts]
    assert ProviderFailureReason.RATE_LIMITED in reasons
    outcomes = [a.outcome for a in result.resolution_attempts]
    assert outcomes[-1] == ResolutionOutcome.SUCCESS


def test_two_sources_fail_third_succeeds_full_trail_preserved():
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

    class FailingTreasury:
        def fetch_daily_dataset(self):
            raise MarketProviderUnavailableError("indisponivel")

    result = resolve(
        IndicatorResolverService(
            market_service=FakeMarket(MarketRateLimitError("429")),
            normalizer=IndicatorNormalizationService(),
            treasury_provider=FailingTreasury(),
            manual_repository=ManualRepo(),
        ),
        baseline=[indicator("treasury_rate")],
        asset_class=InvestmentClass.TREASURY,
        asset_id="asset",
    )
    assert result.status == IndicatorStatus.AVAILABLE
    assert result.value == Decimal("6.25")
    assert len(result.resolution_attempts) == 3
    assert [a.outcome for a in result.resolution_attempts] == [
        ResolutionOutcome.FAILURE,
        ResolutionOutcome.FAILURE,
        ResolutionOutcome.SUCCESS,
    ]
    assert result.resolution_attempts[0].provider_failure_reason == (
        ProviderFailureReason.RATE_LIMITED
    )
    assert result.resolution_attempts[1].provider_failure_reason == (
        ProviderFailureReason.PROVIDER_UNAVAILABLE
    )


def test_all_sources_fail_indicator_still_has_no_value_but_has_diagnostics():
    class Cvm:
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
    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")

    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
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

    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")

    class Cvm:
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
    assert result.valid_until == datetime(2026, 6, 30, tzinfo=timezone.utc) + timedelta(
        days=395
    )
    assert result.freshness_status == "current"
    assert result.source == "CVM Dados Abertos"
    assert result.source_type == "official"


# --- Vinculação automática de emissor CVM por CNPJ exato -------------------


def test_auto_links_issuer_by_exact_cnpj_when_profile_provides_one():
    issuer = SimpleNamespace(id="issuer-1", cnpj="33000167000101", cvm_code="9512")
    linked = {}

    class Cvm:
        def linked_issuer(self, asset_id):
            return linked.get(asset_id)

        def find_issuer_by_cnpj(self, cnpj):
            assert cnpj == "33000167000101"
            return issuer

        def link_asset(self, asset_id, issuer_id):
            linked[asset_id] = issuer
            return SimpleNamespace(asset_id=asset_id, issuer_id=issuer_id)

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
    # Sem dados sincronizados ainda -> NOT_SYNCED, mas a vinculação já
    # ocorreu (prova indireta: motivo deixou de ser IDENTIFIER_UNRESOLVED).
    assert result.provider_failure_reason == ProviderFailureReason.NOT_SYNCED
    assert linked["asset-1"] is issuer


def test_auto_link_never_matches_by_name_only_exact_cnpj():
    class Cvm:
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
    class Cvm:
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
    issuer = SimpleNamespace(cnpj="33000167000101", cvm_code="9512")

    class Cvm:
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


def _cvm_document(period_end=date(2026, 6, 30)):
    return SimpleNamespace(
        period_end=period_end,
        collected_at=NOW,
        period_kind="year_to_date",
        document_type="ITR",
        scope="consolidated",
    )


def test_derived_roe_computed_when_net_income_and_equity_share_same_period():
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    old_document = _cvm_document(period_end=date(2026, 3, 31))
    new_document = _cvm_document(period_end=date(2026, 6, 30))
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), old_document, issuer),
        (_cvm_account("equity", "10000", "2.03"), new_document, issuer),
    ]

    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("gross_debt", "5000", "2.01.04"), document, issuer),
        (_cvm_account("cash_and_equivalents", "1200", "1.01.01"), document, issuer),
        (_cvm_account("equity", "19000", "2.03"), document, issuer),
    ]

    class Cvm:
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


def test_derived_indicator_stays_available_for_a_full_annual_filing_cycle():
    # Bug real encontrado em sincronização real: DFP é anual, então um
    # indicador derivado de period_end=2025-12-31 não pode expirar antes da
    # CVM publicar a próxima DFP (~1 ano depois) — 100 dias o marcava STALE
    # já em abril, meses antes de qualquer dado novo existir.
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document(period_end=date(2025, 12, 31))
    rows = [
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm:
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
    assert result["roe"].status == IndicatorStatus.AVAILABLE
    assert result["roe"].valid_until == datetime(
        2025, 12, 31, tzinfo=timezone.utc
    ) + timedelta(days=395)


def test_derived_net_debt_itself_is_stored_when_pending():
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("gross_debt", "5000", "2.01.04"), document, issuer),
        (_cvm_account("cash_and_equivalents", "1200", "1.01.01"), document, issuer),
    ]

    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("total_liabilities", "30000", "2"), document, issuer),
        (_cvm_account("assets", "100000", "1"), document, issuer),
        (_cvm_account("current_assets", "15000", "1.01"), document, issuer),
        (_cvm_account("current_liabilities", "10000", "2.01"), document, issuer),
    ]

    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [(_cvm_account("net_income", "1000", "3.11"), document, issuer)]

    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")
    document = _cvm_document()
    rows = [
        (_cvm_account("roe", "999", "9.99"), document, issuer),
        (_cvm_account("net_income", "1000", "3.11"), document, issuer),
        (_cvm_account("equity", "10000", "2.03"), document, issuer),
    ]

    class Cvm:
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


def test_treasury_official_fallback():
    class Treasury:
        def fetch_daily_dataset(self):
            return [{"symbol": "test3", "buyRate": "6.25"}]

    baseline = indicator("treasury_rate")
    result = resolve(
        resolver(treasury_provider=Treasury()),
        baseline=[baseline],
        asset_class=InvestmentClass.TREASURY,
    )
    assert result.value == Decimal("6.25")
    assert result.source == "Tesouro Transparente"


def test_cvm_unavailability_does_not_break_basic_data():
    class Cvm:
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
    issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")

    class CvmRepository:
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
        issuer = SimpleNamespace(cnpj="12345678000190", cvm_code="12345")

        class CvmRepository:
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
