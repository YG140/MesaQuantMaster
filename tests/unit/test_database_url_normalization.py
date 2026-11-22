import pytest

from app.core.database import normalize_database_url


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        (
            "postgresql://mesa:secret@db.example.com:5432/mesa_quant?sslmode=require",
            "postgresql+psycopg2://mesa:secret@db.example.com:5432/mesa_quant?sslmode=require",
        ),
        (
            "postgresql+psycopg2://mesa:secret@db.example.com/mesa_quant",
            "postgresql+psycopg2://mesa:secret@db.example.com/mesa_quant",
        ),
        (
            "postgresql+psycopg://mesa:secret@db.example.com/mesa_quant",
            "postgresql+psycopg://mesa:secret@db.example.com/mesa_quant",
        ),
        ("sqlite:///./test.db", "sqlite:///./test.db"),
    ],
)
def test_normalize_database_url_preserves_explicit_driver_and_non_postgres(
    database_url: str,
    expected: str,
) -> None:
    assert normalize_database_url(database_url) == expected
