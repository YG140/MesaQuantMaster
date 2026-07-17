from __future__ import annotations

from decimal import Decimal

from app.models.asset import Asset
from app.models.operation import Operation
from app.models.user import User
from app.repositories.brokerage_repository import BrokerageRepository
from app.services.brokerage_service import BrokerageService


def test_add_investment_creates_asset_and_operation(client, db_session):
    brokerage = client.post("/brokerages", json={"name": "NuInvest"}).json()

    response = client.post(
        "/portfolio/investments",
        json={
            "brokerage_id": brokerage["id"],
            "ticker": "B3SA3",
            "name": "B3",
            "asset_type": "STOCK",
            "operation_date": "2026-07-15",
            "quantity": "10",
            "unit_price": "12.50",
            "fees": "1",
            "taxes": "0",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["asset_created"] is True

    asset = db_session.query(Asset).filter(Asset.ticker == "B3SA3").one()
    operation = db_session.query(Operation).filter(Operation.asset_id == asset.id).one()
    assert str(operation.brokerage_id) == brokerage["id"]
    assert operation.operation_type == "BUY"
    assert operation.source == "manual_investment"


def test_add_investment_reuses_existing_asset(client, asset_factory, db_session):
    asset_factory(ticker="ITUB4", name="Itau")
    brokerage = client.post("/brokerages", json={"name": "XP"}).json()

    response = client.post(
        "/portfolio/investments",
        json={
            "brokerage_id": brokerage["id"],
            "ticker": "ITUB4",
            "name": "Itau Unibanco",
            "asset_type": "STOCK",
            "operation_date": "2026-07-15",
            "quantity": "2",
            "unit_price": "30",
        },
    )

    assert response.status_code == 201
    assert response.json()["asset_created"] is False
    assert db_session.query(Asset).filter(Asset.ticker == "ITUB4").count() == 1


def test_brokerages_are_isolated_by_user(db_session, active_user):
    other_user = User(
        name="Other User",
        email="other@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    service = BrokerageService(BrokerageRepository(db_session))
    service.create(active_user.id, "XP")
    service.create(other_user.id, "XP")

    assert len(service.list_by_user(active_user.id)) == 1
    assert len(service.list_by_user(other_user.id)) == 1
    assert service.list_by_user(active_user.id)[0].user_id == active_user.id


def test_duplicate_brokerage_name_returns_error(client):
    first = client.post("/brokerages", json={"name": "XP"})
    second = client.post("/brokerages", json={"name": " xp "})

    assert first.status_code == 201
    assert second.status_code == 400
    assert second.json()["detail"] == "Corretora ja cadastrada."


def test_import_initial_portfolio_creates_many_positions(client):
    brokerage = client.post("/brokerages", json={"name": "Rico"}).json()

    response = client.post(
        "/portfolio/import-initial",
        json={
            "brokerage_id": brokerage["id"],
            "positions": [
                {
                    "ticker": "VALE3",
                    "name": "Vale",
                    "asset_type": "STOCK",
                    "quantity": "10",
                    "average_price": "60",
                    "reference_date": "2026-07-15",
                },
                {
                    "ticker": "BBAS3",
                    "name": "Banco do Brasil",
                    "asset_type": "STOCK",
                    "quantity": "5",
                    "average_price": "24",
                    "reference_date": "2026-07-15",
                },
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["operations_created"] == 2

    portfolio = client.get("/portfolio").json()
    tickers = {position["ticker"] for position in portfolio["positions"]}
    assert tickers == {"BBAS3", "VALE3"}


def test_invalid_import_line_blocks_entire_import(client, db_session):
    brokerage = client.post("/brokerages", json={"name": "Clear"}).json()

    response = client.post(
        "/portfolio/import-initial",
        json={
            "brokerage_id": brokerage["id"],
            "positions": [
                {
                    "ticker": "ABEV3",
                    "name": "Ambev",
                    "asset_type": "STOCK",
                    "quantity": "10",
                    "average_price": "12",
                },
                {
                    "ticker": "WEGE3",
                    "name": "Weg",
                    "asset_type": "STOCK",
                    "quantity": "0",
                    "average_price": "40",
                },
            ],
        },
    )

    assert response.status_code == 400
    assert db_session.query(Operation).count() == 0
    assert db_session.query(Asset).count() == 0


def test_imported_positions_use_invested_allocation_when_no_quotes(client):
    brokerage = client.post("/brokerages", json={"name": "BTG"}).json()
    client.post(
        "/portfolio/import-initial",
        json={
            "brokerage_id": brokerage["id"],
            "positions": [
                {
                    "ticker": "EGIE3",
                    "quantity": "10",
                    "average_price": "10",
                },
                {
                    "ticker": "TAEE11",
                    "quantity": "5",
                    "average_price": "20",
                },
            ],
        },
    )

    portfolio = client.get("/portfolio").json()
    assert portfolio["valuation_basis"] == "invested_amount"
    assert {
        item["ticker"]: Decimal(str(item["allocation"]))
        for item in portfolio["allocation"]
    } == {"EGIE3": Decimal("50.00"), "TAEE11": Decimal("50.00")}


def test_empty_portfolio_does_not_create_invalid_allocation(client):
    portfolio = client.get("/portfolio").json()

    assert portfolio["positions"] == []
    assert portfolio["allocation"] == []
    assert portfolio["valuation_basis"] is None
