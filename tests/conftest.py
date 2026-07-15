from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

Path(".pytest_cache").mkdir(exist_ok=True)

os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = "sqlite:///./.pytest_cache/test_mesa_quant_master.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

from app.api.deps import get_current_active_user  # noqa: E402
from app.core.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.asset import Asset  # noqa: E402
from app.models.operation import Operation  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def active_user(db_session) -> User:
    user = User(
        name="Test User",
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(active_user: User) -> Generator[TestClient]:
    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_current_user():
        return active_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def asset_factory(db_session):
    def create_asset(
        ticker: str = "PETR4",
        name: str = "Petrobras PN",
        asset_type: str = "STOCK",
    ) -> Asset:
        asset = Asset(
            ticker=ticker,
            name=name,
            asset_type=asset_type,
            currency="BRL",
            is_active=True,
        )
        db_session.add(asset)
        db_session.commit()
        db_session.refresh(asset)
        return asset

    return create_asset


@pytest.fixture
def operation_factory(db_session, active_user: User):
    def create_operation(
        asset: Asset,
        operation_type: str,
        operation_date,
        quantity,
        unit_price,
        fees="0",
        taxes="0",
    ) -> Operation:
        operation = Operation(
            user_id=active_user.id,
            asset_id=asset.id,
            operation_type=operation_type,
            operation_date=operation_date,
            quantity=quantity,
            unit_price=unit_price,
            fees=fees,
            taxes=taxes,
        )
        db_session.add(operation)
        db_session.commit()
        db_session.refresh(operation)
        return operation

    return create_operation
