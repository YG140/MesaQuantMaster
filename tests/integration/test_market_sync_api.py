from app.api.market import get_market_sync_service
from app.main import app
from app.schemas.market_sync import MarketSyncReport


class FakeSyncService:
    def run(self, request, *, apply=False):
        return MarketSyncReport(
            dry_run=True,
            requested=len(request.tickers),
            processed=0,
            calls_used=0,
            snapshots_ready=0,
            snapshots_written=0,
        )


def test_common_user_cannot_run_market_sync(client):
    response = client.post("/market/sync", json={"tickers": ["PETR4"]})
    assert response.status_code == 403


def test_superuser_can_only_receive_dry_run(client, active_user, db_session):
    active_user.is_superuser = True
    db_session.commit()
    app.dependency_overrides[get_market_sync_service] = lambda: FakeSyncService()
    try:
        response = client.post("/market/sync", json={"tickers": ["PETR4"]})
    finally:
        app.dependency_overrides.pop(get_market_sync_service, None)

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["snapshots_written"] == 0
