import json

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import BASE_DIR, settings


def main() -> int:
    engine = create_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current = MigrationContext.configure(connection).get_current_revision()
        config = Config(str(BASE_DIR / "alembic.ini"))
        expected = ScriptDirectory.from_config(config).get_current_head()
    except Exception:
        print(json.dumps({"database": "unavailable"}))
        return 2
    finally:
        engine.dispose()

    migrations_match = current == expected
    print(
        json.dumps(
            {
                "database": "available",
                "migrations_match": migrations_match,
                "current_revision": current,
                "expected_revision": expected,
            }
        )
    )
    return 0 if migrations_match else 3


if __name__ == "__main__":
    raise SystemExit(main())
