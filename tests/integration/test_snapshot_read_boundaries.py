from datetime import datetime, timezone
from decimal import Decimal

from app.models.indicator_snapshot import IndicatorSnapshot
from app.models.manual_indicator import ManualIndicator
from app.repositories.asset_repository import AssetRepository
from app.repositories.manual_indicator_repository import ManualIndicatorRepository
from app.schemas.manual_indicator import ManualIndicatorCreate
from app.schemas.market import QuoteResponse, QuotesResponse
from app.services.manual_indicator_service import ManualIndicatorService
from app.services.market_service import MarketService


def test_get_intelligence_asset_does_not_write_snapshot(
    client, db_session, monkeypatch
):
    def fake_quotes(_self, symbols):
        return QuotesResponse(
            quotes=[
                QuoteResponse(
                    ticker=symbols[0],
                    requested_symbol=symbols[0],
                    current_price=Decimal("39.89"),
                    currency="BRL",
                    market_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
                    source="FAKE",
                    provider="FAKE",
                    asset_type="Ação",
                )
            ],
            provider="FAKE",
        )

    monkeypatch.setattr(MarketService, "get_quotes", fake_quotes)
    monkeypatch.setattr(
        MarketService,
        "get_stock_dataset",
        lambda *_args, **_kwargs: [],
    )
    before = db_session.query(IndicatorSnapshot).count()

    response = client.get("/intelligence/assets/PETR4")

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(IndicatorSnapshot).count() == before


def test_explicit_manual_indicator_write_does_not_create_snapshot(
    db_session, active_user, asset_factory
):
    asset_factory(ticker="PETR4", asset_type="STOCK")
    snapshots_before = db_session.query(IndicatorSnapshot).count()
    service = ManualIndicatorService(
        ManualIndicatorRepository(db_session), AssetRepository(db_session)
    )

    created = service.create(
        active_user.id,
        "PETR4",
        ManualIndicatorCreate(
            indicator_key="pe",
            value="8.75",
            unit="ratio",
            reference_date="2026-01-31",
            source_description="Fixture controlada",
        ),
    )

    assert created.value == Decimal("8.75")
    db_session.expire_all()
    assert db_session.query(ManualIndicator).count() == 1
    assert db_session.query(IndicatorSnapshot).count() == snapshots_before
