"""Test recovery against a disposable PostgreSQL created by GitHub Actions.

No real user data, passwords, or Neon credentials are used.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select

from app.core.database import Base
from app.models.asset import Asset
from app.models.brokerage import Brokerage
from app.models.operation import Operation
from app.models.user import User
from scripts.migrate_local_sqlite_to_neon import (
    MigrationSafetyError, migrate, plan_migration, source_connection, sqlite_backup,
)


def test_local_sqlite_backup_and_atomic_recovery(tmp_path, monkeypatch):
    pg_url = __import__("os").environ.get("DATABASE_URL")
    if not pg_url or not pg_url.startswith("postgresql"):
        pytest.skip("Needs disposable postgres, never a real Neon database")
    path = tmp_path / "original-local.db"
    source_engine = create_engine(f"sqlite:///{path}")
    import app.models  # noqa: F401
    Base.metadata.create_all(source_engine)
    user_id, asset_id, brokerage_id = uuid4(), uuid4(), uuid4()
    hash_value = "$argon2id$v=19$m=65536,t=3,p=4$test-only-not-a-real-password"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with source_engine.begin() as conn:
        conn.execute(User.__table__.insert().values(
            id=user_id, name="Pessoa Teste", email="local@example.invalid",
            hashed_password=hash_value, is_active=True, is_superuser=False,
            is_email_verified=True, auth_version=4,
            created_at=now, updated_at=now,
        ))
        conn.execute(Asset.__table__.insert().values(
            id=asset_id, ticker="FAKE3", name="Ativo fictício", asset_type="STOCK",
            sector="Simulado", country="BR", currency="BRL", is_active=True,
            created_at=now, updated_at=now,
        ))
        conn.execute(Brokerage.__table__.insert().values(
            id=brokerage_id, user_id=user_id, name="Corretora fictícia",
            created_at=now, updated_at=now,
        ))
        conn.execute(Operation.__table__.insert().values(
            id=uuid4(), user_id=user_id, asset_id=asset_id,
            brokerage_id=brokerage_id, operation_type="BUY",
            operation_date=date(2026, 10, 1),
            quantity=Decimal("2.5"), unit_price=Decimal("10.12345678"),
            fees=Decimal("1.11"), taxes=Decimal("0.22"),
            source="MANUAL", created_at=now, updated_at=now,
        ))
    source_engine.dispose()

    target = create_engine(pg_url)
    with source_connection(path) as local:
        tables, counts = plan_migration(local, target)
        assert counts["users"] == 1
        assert counts["operations"] == 1
        assert counts["assets"] == 1
        assert counts["brokerages"] == 1
        backup, sha = sqlite_backup(local, path)
        assert backup.is_file() and backup != path and len(sha) == 64
        with sqlite3.connect(backup) as saved:
            assert saved.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1

        migrate(local, target, tables, counts)
        with pytest.raises(MigrationSafetyError, match="Neon já contém dados"):
            plan_migration(local, target)

    with target.connect() as conn:
        stored = conn.execute(select(User.__table__).where(User.id == user_id)).mappings().one()
        assert stored["hashed_password"] == hash_value
        assert stored["email"] == "local@example.invalid"
        assert stored["is_email_verified"] is True
        assert stored["auth_version"] == 4
        record = conn.execute(select(Operation.__table__)).mappings().one()
        assert record["asset_id"] == asset_id
        assert record["user_id"] == user_id
        assert record["quantity"] == Decimal("2.50000000")
        assert record["unit_price"] == Decimal("10.12345678")
    with sqlite3.connect(path) as original:
        assert original.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 1
    target.dispose()


def test_missing_source_file_never_created(tmp_path):
    missing = tmp_path / "nonexistent.db"
    with pytest.raises(MigrationSafetyError, match="não encontrado"):
        source_connection(missing)
    assert not missing.exists()


def test_fake_database_never_opened(tmp_path):
    invalid = tmp_path / "not-sqlite.db"
    invalid.write_bytes(b"not really a sqlite database")
    with pytest.raises(MigrationSafetyError, match="não é um banco SQLite"):
        source_connection(invalid)
