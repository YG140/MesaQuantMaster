from sqlalchemy.engine import make_url


def assert_safe_test_database(database_url: str) -> None:
    parsed = make_url(database_url)
    database = (parsed.database or "").replace("\\", "/").lower()
    if "mesa_quant_master_v2" in database:
        raise RuntimeError("Testes recusados: DATABASE_URL aponta para o banco real.")
    if parsed.drivername.startswith("sqlite"):
        if database == ":memory:" or "/.pytest_cache/test_" in f"/{database}":
            return
    elif database.startswith("test_") or database.endswith("_test"):
        return
    raise RuntimeError(
        "Testes destrutivos exigem SQLite em memória/.pytest_cache/test_* "
        "ou banco cujo nome comece com test_ ou termine com _test."
    )
