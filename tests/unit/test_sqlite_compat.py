from sqlalchemy import create_engine, text

from app.core.sqlite_compat import ensure_sqlite_compat_schema


def test_ensure_sqlite_compat_schema_adds_operation_metadata_columns():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
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

    ensure_sqlite_compat_schema(engine)

    with engine.connect() as connection:
        columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(operations)"))
        }
        indexes = {
            row[1] for row in connection.execute(text("PRAGMA index_list(operations)"))
        }

    assert "brokerage_id" in columns
    assert "source" in columns
    assert "ix_operations_brokerage_id" in indexes


def test_ensure_sqlite_compat_schema_does_not_run_for_postgresql():
    class FakeDialect:
        name = "postgresql"

    class FakeEngine:
        dialect = FakeDialect()

        def begin(self):
            raise AssertionError("compat schema should not inspect or mutate")

    ensure_sqlite_compat_schema(FakeEngine())


def test_ensure_sqlite_compat_schema_adds_missing_index_when_column_exists():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE operations (
                    id UUID PRIMARY KEY,
                    brokerage_id UUID,
                    source VARCHAR(50)
                )
                """
            )
        )

    ensure_sqlite_compat_schema(engine)

    with engine.connect() as connection:
        indexes = {
            row[1] for row in connection.execute(text("PRAGMA index_list(operations)"))
        }

    assert "ix_operations_brokerage_id" in indexes
