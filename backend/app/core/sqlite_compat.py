from __future__ import annotations

from sqlalchemy import Engine, inspect, text


def ensure_sqlite_compat_schema(engine: Engine) -> None:
    """Temporarily patch old local SQLite databases.

    Alembic migrations are the official schema evolution path. This helper only
    keeps pre-migration developer SQLite files usable when the app starts.
    """
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "operations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("operations")}
    indexes = {index["name"] for index in inspector.get_indexes("operations")}
    with engine.begin() as connection:
        if "brokerage_id" not in columns:
            connection.execute(
                text("ALTER TABLE operations ADD COLUMN brokerage_id UUID")
            )

        if "ix_operations_brokerage_id" not in indexes:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_operations_brokerage_id ON operations (brokerage_id)"
                )
            )

        if "source" not in columns:
            connection.execute(
                text("ALTER TABLE operations ADD COLUMN source VARCHAR(50)")
            )
