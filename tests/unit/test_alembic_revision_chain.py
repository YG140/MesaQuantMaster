import importlib
import os
from pathlib import Path
import re
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPOSITORY_ROOT / "backend" / "alembic.ini"
MIGRATIONS_DIR = REPOSITORY_ROOT / "backend" / "migrations"
EXPANSION_REVISION = "20260711_expand_alembic_version"
EXPECTED_CHAIN = (
    "17f115172169",
    EXPANSION_REVISION,
    "20260716_add_brokerages_operation_metadata",
    "20260717_add_portfolio_policy",
    "20260720_manual_indicators",
    "20260720_indicator_snapshots",
    "20260721_cvm_financial",
    "20260723_portfolio_audits",
    "20260727_email_auth_tokens",
)
REQUIRED_SECURITY_FILES = {
    "backend/alembic.ini",
    "backend/app/config/settings.py",
    "backend/app/core/config.py",
}
CREDENTIAL_URL_PATTERN = re.compile(
    r"[a-z][a-z0-9+.-]*://[^\s/@:'\"]+:[^\s/@'\"]+@",
    re.IGNORECASE,
)


def load_script_directory() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config)


def ordered_revision_ids(script: ScriptDirectory) -> tuple[str, ...]:
    return tuple(
        revision.revision for revision in reversed(list(script.walk_revisions()))
    )


def test_alembic_revision_chain_is_complete_linear_and_acyclic() -> None:
    script = load_script_directory()
    revisions = list(script.walk_revisions())
    revision_ids = {revision.revision for revision in revisions}

    assert len(revision_ids) == len(revisions), "Existem revision IDs duplicados."
    assert len(script.get_heads()) == 1, "A cadeia deve possuir exatamente um head."

    visited: set[str] = set()
    current = script.get_revision(script.get_current_head())
    while current is not None:
        assert (
            current.revision not in visited
        ), "A cadeia de migrations possui um ciclo."
        visited.add(current.revision)
        down_revisions = current._normalized_down_revisions
        assert len(down_revisions) <= 1, "Não são esperadas ramificações na cadeia."
        for down_revision in down_revisions:
            assert down_revision in revision_ids, (
                f"A migration {current.revision} referencia a revisão ausente "
                f"{down_revision}."
            )
        current = script.get_revision(down_revisions[0]) if down_revisions else None

    assert visited == revision_ids, "Existem migrations desconectadas do head."


def test_alembic_revision_chain_has_the_complete_expected_order() -> None:
    script = load_script_directory()

    assert ordered_revision_ids(script) == EXPECTED_CHAIN
    assert script.get_current_head() == EXPECTED_CHAIN[-1]


def test_version_column_is_expanded_before_every_long_revision_id() -> None:
    script = load_script_directory()
    ordered = ordered_revision_ids(script)
    expansion_index = ordered.index(EXPANSION_REVISION)

    assert len(EXPANSION_REVISION) <= 32
    for index, revision_id in enumerate(ordered):
        if len(revision_id) > 32:
            assert (
                index > expansion_index
            ), f"{revision_id} aparece antes da ampliação de alembic_version."


def test_version_column_migration_expands_from_32_to_128(monkeypatch) -> None:
    migration = importlib.import_module(
        "backend.migrations.versions.20260711_expand_alembic_version"
    )
    calls: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda table, column, **kwargs: calls.append((table, column, kwargs)),
    )

    migration.upgrade()

    assert len(calls) == 1
    table, column, options = calls[0]
    assert (table, column) == ("alembic_version", "version_num")
    assert options["existing_type"].length == 32
    assert options["type_"].length == 128
    assert options["existing_nullable"] is False


def test_tracked_configuration_files_contain_no_database_credentials() -> None:
    tracked_files = set(
        subprocess.run(
            ["git", "ls-files"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    )
    assert REQUIRED_SECURITY_FILES <= tracked_files

    configuration_files = {
        relative_path
        for relative_path in tracked_files
        if relative_path in REQUIRED_SECURITY_FILES
        or Path(relative_path).name in {"settings.py", "config.py"}
        or Path(relative_path).suffix == ".ini"
        or ".env" in Path(relative_path).name
    }
    compromised_files = []
    for relative_path in sorted(configuration_files):
        contents = (REPOSITORY_ROOT / relative_path).read_text(
            encoding="utf-8", errors="replace"
        )
        if CREDENTIAL_URL_PATTERN.search(contents):
            compromised_files.append(relative_path)

    assert not compromised_files, "URLs com credenciais encontradas em: " + ", ".join(
        compromised_files
    )


def test_legacy_and_core_settings_use_the_same_environment_database_url(
    monkeypatch,
) -> None:
    from app.config.settings import Settings as LegacySettings
    from app.core.config import Settings as CoreSettings

    test_database_url = "sqlite:///configuration-compatibility.db"
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("SECRET_KEY", "configuration-test-only")
    monkeypatch.setenv("DEBUG", "false")

    legacy = LegacySettings(_env_file=None)
    core = CoreSettings(_env_file=None)

    assert legacy.DATABASE_URL == test_database_url
    assert core.DATABASE_URL == test_database_url


def test_alembic_env_honors_database_url(tmp_path: Path) -> None:
    database_path = tmp_path / "alembic_database_url.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(128) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) " "VALUES ('17f115172169')")
        )
    engine.dispose()

    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "DEBUG": "false",
            "SECRET_KEY": "alembic-test-only",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "current",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "17f115172169" in result.stdout
