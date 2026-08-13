import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.asset import Asset
from app.models.indicator_snapshot import IndicatorSnapshot
from app.repositories.asset_repository import AssetRepository
from app.repositories.market_sync_repository import MarketSyncRepository
from app.schemas.market import QuoteResponse, QuotesResponse
from app.schemas.market_sync import MarketSyncRequest
from app.services.market_sync_service import MarketSyncService

NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)
REFERENCE_TIME = NOW - timedelta(hours=3)


class FakeProvider:
    def __init__(self, quotes):
        self.quotes = quotes
        self.calls = 0

    def get_quotes(self, tickers):
        self.calls += 1
        return QuotesResponse(
            quotes=self.quotes,
            provider="BRAPI",
            unavailable_symbols=[item for item in tickers if item != "PETR4"],
        )


def quote(value=Decimal("30.25"), currency="BRL"):
    return QuoteResponse(
        ticker="PETR4",
        requested_symbol="PETR4",
        current_price=value,
        currency=currency,
        market_time=REFERENCE_TIME,
        source="BRAPI",
        provider="BRAPI",
    )


def service(db_session, provider):
    return MarketSyncService(
        asset_repository=AssetRepository(db_session),
        sync_repository=MarketSyncRepository(db_session),
        provider=provider,
        now=lambda: NOW,
    )


def add_asset(db_session):
    db_session.add(
        Asset(
            ticker="PETR4",
            name="Petrobras",
            asset_type="STOCK",
            currency="BRL",
            is_active=True,
        )
    )
    db_session.commit()


def request(**updates):
    values = {"tickers": [" petr4 ", "PETR4"], "max_calls": 1}
    values.update(updates)
    return MarketSyncRequest(**values)


def test_dry_run_does_not_write_and_preserves_decimal_and_provenance(db_session):
    add_asset(db_session)
    provider = FakeProvider([quote()])
    report = service(db_session, provider).run(request())

    assert report.dry_run is True
    assert report.snapshots_written == 0
    assert db_session.query(IndicatorSnapshot).count() == 0
    snapshot = report.snapshots[0]
    assert snapshot.value == Decimal("30.25")
    assert isinstance(snapshot.value, Decimal)
    assert snapshot.unit == "currency"
    assert snapshot.currency_code == "BRL"
    assert snapshot.provider == "BRAPI"
    assert snapshot.reference_date == REFERENCE_TIME
    assert snapshot.reference_date == REFERENCE_TIME
    assert snapshot.collected_at == NOW
    assert snapshot.valid_until == NOW + timedelta(seconds=120)
    assert snapshot.reference_date != snapshot.collected_at
    assert snapshot.reference_date.tzinfo is not None
    assert snapshot.collected_at.tzinfo is not None
    assert snapshot.valid_until.tzinfo is not None
    assert provider.calls == 1


def test_apply_is_idempotent_and_keeps_provenance(db_session):
    add_asset(db_session)
    provider = FakeProvider([quote()])
    sync = service(db_session, provider)

    sync.run(request(), apply=True)
    sync.run(request(), apply=True)
    db_session.commit()

    rows = db_session.query(IndicatorSnapshot).all()
    assert len(rows) == 1
    assert rows[0].value == Decimal("30.25")
    provenance = json.loads(rows[0].provenance_json)
    assert provenance["provider"] == "BRAPI"
    assert provenance["currency_code"] == "BRL"
    assert provenance["valid_until"]


def test_repository_flushes_but_never_commits_batch(db_session, monkeypatch):
    add_asset(db_session)
    commit_calls = 0
    flush_calls = 0
    original_flush = db_session.flush

    def count_commit(*args, **kwargs):
        nonlocal commit_calls
        commit_calls += 1

    def count_flush(*args, **kwargs):
        nonlocal flush_calls
        flush_calls += 1
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "commit", count_commit)
    monkeypatch.setattr(db_session, "flush", count_flush)

    report = service(db_session, FakeProvider([quote()])).run(request(), apply=True)

    assert report.snapshots_written == 1
    assert flush_calls >= 1
    assert commit_calls == 0


def test_provider_currency_is_preserved_without_assuming_brl(db_session):
    add_asset(db_session)
    report = service(db_session, FakeProvider([quote(currency="USD")])).run(request())

    snapshot = report.snapshots[0]
    assert snapshot.unit == "currency"
    assert snapshot.currency_code == "USD"
    assert snapshot.value == Decimal("30.25")
    assert not report.warnings


def test_missing_currency_stays_missing_and_warns(db_session):
    add_asset(db_session)
    report = service(db_session, FakeProvider([quote(currency=None)])).run(request())

    snapshot = report.snapshots[0]
    assert snapshot.unit == "currency"
    assert snapshot.currency_code is None
    assert snapshot.value == Decimal("30.25")
    assert any("moeda ausente" in item for item in report.warnings)


def test_missing_price_is_not_converted_to_zero(db_session):
    add_asset(db_session)
    provider = FakeProvider([quote(None)])

    report = service(db_session, provider).run(request(), apply=True)

    assert report.snapshots_ready == 0
    assert db_session.query(IndicatorSnapshot).count() == 0
    assert any("cotação ausente" in item for item in report.warnings)


def test_offline_mode_and_asset_limit_make_no_calls(db_session):
    provider = FakeProvider([])
    report = service(db_session, provider).run(
        request(tickers=["A", "B", "C"], max_assets=2, offline=True)
    )

    assert report.requested == 2
    assert report.calls_used == 0
    assert provider.calls == 0


def test_failure_does_not_commit_partial_batch(db_session, monkeypatch):
    add_asset(db_session)
    repository = MarketSyncRepository(db_session)
    original_flush = db_session.flush

    def fail_flush(*args, **kwargs):
        raise RuntimeError("controlled failure")

    monkeypatch.setattr(db_session, "flush", fail_flush)
    sync = MarketSyncService(
        asset_repository=AssetRepository(db_session),
        sync_repository=repository,
        provider=FakeProvider([quote()]),
        now=lambda: NOW,
    )
    with pytest.raises(RuntimeError, match="controlled failure"):
        sync.run(request(), apply=True)
    monkeypatch.setattr(db_session, "flush", original_flush)
    db_session.rollback()
    assert db_session.query(IndicatorSnapshot).count() == 0
