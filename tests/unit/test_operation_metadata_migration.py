from __future__ import annotations

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


migration = importlib.import_module(
    "backend.migrations.versions.20260716_add_brokerages_and_operation_metadata"
)


def run_migration(connection, fn) -> None:
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        fn()


def create_legacy_schema(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE users (
                id UUID PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                email VARCHAR(255) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                is_active BOOLEAN NOT NULL,
                is_superuser BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE operations (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL,
                asset_id UUID NOT NULL,
                operation_type VARCHAR(30) NOT NULL,
                operation_date DATE NOT NULL,
                quantity NUMERIC(18, 8) NOT NULL,
                unit_price NUMERIC(18, 8) NOT NULL,
                fees NUMERIC(18, 2) NOT NULL,
                taxes NUMERIC(18, 2) NOT NULL,
                notes VARCHAR(500),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO operations (
                id,
                user_id,
                asset_id,
                operation_type,
                operation_date,
                quantity,
                unit_price,
                fees,
                taxes,
                created_at,
                updated_at
            )
            VALUES (
                'operation-1',
                'user-1',
                'asset-1',
                'BUY',
                '2026-01-01',
                10,
                20,
                0,
                0,
                '2026-01-01',
                '2026-01-01'
            )
            """
        )
    )


def table_columns(connection, table_name: str) -> set[str]:
    return {
        row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
    }


def table_indexes(connection, table_name: str) -> set[str]:
    return {
        row[1] for row in connection.execute(text(f"PRAGMA index_list({table_name})"))
    }


def test_upgrade_adds_operation_metadata_and_preserves_existing_data():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_legacy_schema(connection)

        run_migration(connection, migration.upgrade)

        assert "brokerage_id" in table_columns(connection, "operations")
        assert "source" in table_columns(connection, "operations")
        assert "brokerages" in {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            )
        }
        assert "ix_operations_brokerage_id" in table_indexes(
            connection,
            "operations",
        )
        assert connection.execute(text("SELECT COUNT(*) FROM operations")).scalar() == 1


def test_upgrade_is_idempotent_when_schema_is_already_updated():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_legacy_schema(connection)

        run_migration(connection, migration.upgrade)
        run_migration(connection, migration.upgrade)

        assert "brokerage_id" in table_columns(connection, "operations")
        assert "source" in table_columns(connection, "operations")


def test_downgrade_removes_added_metadata_without_dropping_operations():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_legacy_schema(connection)
        run_migration(connection, migration.upgrade)

        run_migration(connection, migration.downgrade)

        columns = table_columns(connection, "operations")
        assert "brokerage_id" not in columns
        assert "source" not in columns
        assert connection.execute(text("SELECT COUNT(*) FROM operations")).scalar() == 1
