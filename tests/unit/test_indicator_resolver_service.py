from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.providers.exceptions import MarketPermissionError
from app.schemas.market_intelligence import (
    ConfidenceLevel,
    IndicatorLayer,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
)
from app.services.indicator_normalization_service import IndicatorNormalizationService
from app.services.indicator_resolver_service import IndicatorResolverService
from app.services.market_service import MarketService


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def indicator(key="price_to_book"):
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
    def __init__(self, payload=None):
        self.payload = payload
        self.calls = 0

    def get_stock_dataset(self, dataset, symbols, **params):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload or {}

    def get_fii_dataset(self, dataset, symbols, **params):
        return self.get_stock_dataset(dataset, symbols, **params)


class FakeSnapshots:
    def __init__(self, rows):
        self.rows = rows

    def valid_for_symbol(self, symbol, now):
        return self.rows


def snapshot(value="1.25", valid=True):
    return SimpleNamespace(
        indicator_key="price_to_book",
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
        indicator_key="price_to_book",
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
        indicator_key="price_to_book",
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
