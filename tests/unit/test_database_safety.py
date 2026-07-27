import pytest

from app.core.database_guard import assert_safe_test_database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/mesa_quant_master_v2",
        "postgresql://localhost/production",
        "sqlite:///./mesa_quant_master.db",
    ],
)
def test_destructive_test_database_guard_rejects_unsafe_urls(url):
    with pytest.raises(RuntimeError):
        assert_safe_test_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///:memory:",
        "sqlite:///./.pytest_cache/test_safe.db",
        "postgresql://localhost/test_mesa_quant",
        "postgresql://localhost/mesa_quant_test",
    ],
)
def test_destructive_test_database_guard_accepts_explicit_test_urls(url):
    assert_safe_test_database(url)
