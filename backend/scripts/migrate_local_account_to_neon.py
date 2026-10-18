"""Recover ONE account and its portfolio from the legacy local PostgreSQL.

No raw passwords, database URIs or account data are ever printed.
Source is forcibly restricted to loopback PostgreSQL; target to Neon TLS.
Default mode is a read-only dry run. --apply requires explicit confirmation.
"""
from __future__ import annotations

import argparse
import os
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

# Insert in foreign-key dependency order. Public indicator snapshots/CVM cache
# and short-lived auth reset tokens are intentionally not user-account data.
TABLES = (
    "users",
    "assets",
    "brokerages",
    "operations",
    "watchlists",
    "alerts",
    "portfolio_policies",
    "portfolio_policy_allocations",
    "investor_profiles",
    "manual_indicators",
    "portfolio_action_audits",
)
USER_TABLES = (
    "brokerages",
    "operations",
    "watchlists",
    "alerts",
    "portfolio_policies",
    "investor_profiles",
    "manual_indicators",
    "portfolio_action_audits",
)
NON_ACCOUNT_TABLES = {"auth_tokens"}
USER_DEFAULTS = {"is_email_verified": True, "auth_version": 0}
ASSET_DEFAULTS = {"currency": "BRL", "is_active": True}


class MigrationBlocked(RuntimeError):
    """A safety condition was not met; no data should be copied."""


def assert_endpoints(source_url: str, target_url: str) -> None:
    source = make_url(source_url)
    target = make_url(target_url)
    if not source.drivername.startswith("postgresql") or source.host not in (
        "127.0.0.1", "localhost", "::1"
    ):
        raise MigrationBlocked(
            "Origem deve ser PostgreSQL LOCAL (127.0.0.1/localhost), nunca uma nuvem."
        )
    if (
        not target.drivername.startswith("postgresql")
        or not (target.host or "").endswith(".neon.tech")
        or target.query.get("sslmode") not in ("require", "verify-ca", "verify-full")
    ):
        raise MigrationBlocked("Destino deve ser Neon PostgreSQL com sslmode=require.")
    if source_url == target_url:
        raise MigrationBlocked("Origem e destino não podem ser iguais.")


def source_from_local_env() -> str:
    # Read the ignored local .env without importing app.core.config or
    # connecting to the global ORM engine. Never print the contents.
    backend_env = Path(__file__).resolve().parents[1] / ".env"
    value = os.environ.get("SOURCE_DATABASE_URL") or dotenv_values(backend_env).get(
        "DATABASE_URL"
    )
    if not value:
        raise MigrationBlocked(
            "Banco local ausente: configure SOURCE_DATABASE_URL ou backend/.env no PC."
        )
    return str(value)


def _reflected(conn, name: str) -> Table:
    if not inspect(conn).has_table(name):
        raise MigrationBlocked(f"Tabela obrigatória ausente: {name}")
    return Table(name, MetaData(), autoload_with=conn)


def _rows(conn, table: Table, column: str, values) -> list[dict]:
    if column not in table.c:
        raise MigrationBlocked(f"Tabela {table.name} não contém coluna {column}.")
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    if not values:
        return []
    stmt = select(table).where(table.c[column].in_(list(values)))
    return [dict(row._mapping) for row in conn.execute(stmt).all()]


def plan_for_email(conn, email: str) -> OrderedDict[str, list[dict]]:
    # Fail closed if older/future versions contain new owner-linked data.
    inspector = inspect(conn)
    unknown = []
    for name in inspector.get_table_names():
        if name in TABLES or name in NON_ACCOUNT_TABLES:
            continue
        if "user_id" in {col["name"] for col in inspector.get_columns(name)}:
            unknown.append(name)
    if unknown:
        raise MigrationBlocked(
            "Há tabelas do usuário ainda não suportadas: " + ", ".join(sorted(unknown))
        )

    users = _reflected(conn, "users")
    matches = conn.execute(
        select(users).where(func.lower(users.c.email) == email.strip().lower())
    ).mappings().all()
    if len(matches) != 1:
        raise MigrationBlocked(
            "Conta não encontrada exatamente uma vez no banco LOCAL. Não foi alterado nada."
        )
    user = dict(matches[0])
    if not user.get("hashed_password"):
        raise MigrationBlocked("Conta local sem hash de senha; migração bloqueada.")
    user_id = user["id"]
    manifest: OrderedDict[str, list[dict]] = OrderedDict()
    manifest["users"] = [user]
    for name in USER_TABLES:
        if inspector.has_table(name):
            manifest[name] = _rows(conn, _reflected(conn, name), "user_id", user_id)
        else:
            manifest[name] = []

    policy_ids = [row["id"] for row in manifest["portfolio_policies"]]
    if inspector.has_table("portfolio_policy_allocations"):
        manifest["portfolio_policy_allocations"] = _rows(
            conn, _reflected(conn, "portfolio_policy_allocations"), "policy_id", policy_ids
        )
    else:
        manifest["portfolio_policy_allocations"] = []

    asset_ids = {
        row["asset_id"]
        for name in USER_TABLES
        for row in manifest[name]
        if row.get("asset_id") is not None
    }
    manifest["assets"] = _rows(conn, _reflected(conn, "assets"), "id", asset_ids)
    if {row["id"] for row in manifest["assets"]} != asset_ids:
        raise MigrationBlocked("Faltam ativos referenciados na carteira local.")

    broker_ids = {
        row["brokerage_id"]
        for row in manifest["operations"]
        if row.get("brokerage_id") is not None
    }
    if not broker_ids <= {row["id"] for row in manifest["brokerages"]}:
        raise MigrationBlocked("Há operações com corretoras ausentes ou de outro usuário.")
    return OrderedDict((name, manifest[name]) for name in TABLES)


def _compatible_data(name: str, row: dict, target_table: Table) -> dict:
    target_names = set(target_table.c.keys())
    unexpected = set(row) - target_names
    if unexpected:
        raise MigrationBlocked(
            f"Campos locais não reconhecidos na Neon em {name}: {sorted(unexpected)}"
        )
    record = dict(row)
    if name == "users":
        for key, default in USER_DEFAULTS.items():
            if key in target_names and key not in record:
                record[key] = default
    if name == "assets":
        for key, default in ASSET_DEFAULTS.items():
            if key in target_names and key not in record:
                record[key] = default
    for col in target_table.columns:
        if (
            col.name not in record and not col.nullable
            and col.server_default is None and col.default is None
            and not col.primary_key
        ):
            raise MigrationBlocked(
                f"Campo obrigatório {name}.{col.name} não existe no banco antigo."
            )
    return record


def preflight(conn, manifest) -> dict[str, Table]:
    # New Neon is known to be schema-only, but enforce this at runtime to
    # prevent accidental replacement of user accounts or a later migration.
    tables = {name: _reflected(conn, name) for name in TABLES}
    for name in TABLES:
        if conn.execute(select(func.count()).select_from(tables[name])).scalar_one():
            raise MigrationBlocked(
                f"Destino Neon já possui registros em {name}. "
                "Não misture contas: faça uma migração assistida."
            )
        for row in manifest[name]:
            _compatible_data(name, row, tables[name])
    return tables


def operation_signature(rows: list[dict]) -> tuple[int, Decimal, Decimal]:
    return (
        len(rows),
        sum((Decimal(str(x["quantity"])) for x in rows), Decimal("0")),
        sum(
            (
                Decimal(str(x["quantity"])) * Decimal(str(x["unit_price"]))
                for x in rows
            ),
            Decimal("0"),
        ),
    )


def import_atomically(conn, manifest, tables) -> None:
    # Called inside a transaction that rolls back if any step fails.
    for name in TABLES:
        rows = [_compatible_data(name, row, tables[name]) for row in manifest[name]]
        if rows:
            conn.execute(tables[name].insert(), rows)
    for name in TABLES:
        count = conn.execute(select(func.count()).select_from(tables[name])).scalar_one()
        if count != len(manifest[name]):
            raise MigrationBlocked(f"Verificação pós-importação falhou: {name}.")
    if manifest["operations"]:
        imported = [
            dict(row._mapping)
            for row in conn.execute(
                select(
                    tables["operations"].c.quantity,
                    tables["operations"].c.unit_price,
                )
            ).all()
        ]
        if operation_signature(imported) != operation_signature(
            manifest["operations"]
        ):
            raise MigrationBlocked(
                "Quantidade ou valor das operações diferem após importação."
            )
    saved_user = conn.execute(select(tables["users"])).mappings().one()
    if saved_user["hashed_password"] != manifest["users"][0]["hashed_password"]:
        raise MigrationBlocked("Hash da senha não foi preservado.")


def migrate(
    source_url: str, target_url: str, email: str, *, apply: bool = False,
    confirmed: bool = False, expected_counts: dict[str, int] | None = None,
) -> dict[str, int]:
    assert_endpoints(source_url, target_url)
    source_engine = create_engine(source_url, poolclass=NullPool)
    target_engine = create_engine(target_url, poolclass=NullPool)
    try:
        with source_engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as source:
            with source.begin():
                source.exec_driver_sql("SET TRANSACTION READ ONLY")
                manifest = plan_for_email(source, email)
                counts = {name: len(rows) for name, rows in manifest.items()}
                if expected_counts is not None and counts != expected_counts:
                    raise MigrationBlocked("A carteira local mudou desde a prévia. Reinicie a conferência.")
                # Target never changes on dry run or on failed preflight.
                if apply and confirmed:
                    with target_engine.begin() as destination:
                        tables = preflight(destination, manifest)
                        import_atomically(destination, manifest, tables)
                else:
                    with target_engine.connect() as destination:
                        preflight(destination, manifest)
                return counts
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrar uma conta local PostgreSQL para Neon sem sobrescrever dados."
    )
    parser.add_argument("--apply", action="store_true", help="Gravar após confirmação.")
    parser.add_argument("--email", default="", help="E-mail da conta antiga local.")
    options = parser.parse_args()
    email = options.email.strip() or input("E-mail de login antigo (no PC): ").strip()
    if not email:
        raise MigrationBlocked("E-mail obrigatório.")
    src = source_from_local_env()
    dst = os.environ.get("NEON_DATABASE_URL")
    if not dst:
        raise MigrationBlocked(
            "NEON_DATABASE_URL ausente. Configure temporariamente no PC, sem publicá-la."
        )
    assert_endpoints(src, dst)
    # Always run a read-only dry run first, including schema compatibility.
    counts = migrate(src, dst, email, apply=False)
    print("Prévia (não houve gravação na Neon):")
    for name, amount in counts.items():
        print(f"  {name}: {amount}")
    if not options.apply:
        print("Prévia concluída. Para importar, executar novamente com --apply.")
        return 0
    phrase = input("Digite MIGRAR para autorizar a importação: ").strip()
    if phrase != "MIGRAR":
        print("Importação cancelada sem alteração.")
        return 2
    migrate(src, dst, email, apply=True, confirmed=True, expected_counts=counts)
    print("Importação confirmada. IDs, operações e hash da senha preservados.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationBlocked as exc:
        print(f"IMPORTAÇÃO INTERROMPIDA: {exc}")
        raise SystemExit(1)
    except Exception:
        # psycopg2/SQLAlchemy exceptions can include database hosts and
        # sensitive connection details. Do not print raw tracebacks.
        print("ERRO: conexão ou esquema incompatível. Nenhuma senha foi exibida. "
              "Verifique o arquivo de log LOCAL com um técnico de confiança.")
        raise SystemExit(1)
