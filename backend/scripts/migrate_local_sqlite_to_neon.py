#!/usr/bin/env python3
"""Conservative local SQLite -> existing Neon PostgreSQL recovery (run on PC).

- The SQLite source is opened read-only. Backup uses the SQLite online backup API.
- Neon must already have the application's Alembic schema and zero user data.
- Dry run is the default. --apply backs up locally and requires console confirmation.
- A single PostgreSQL transaction inserts all records in FK dependency order.
- Never reads or prints plaintext passwords; password hashes remain unchanged.
- No DROP / DELETE / TRUNCATE / upsert / changes to the SQLite source.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, Date, DateTime, Integer, JSON, MetaData, Numeric, Uuid,
    create_engine, func, inspect, select,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine
from sqlalchemy.sql.sqltypes import NullType

IGNORED_TABLES = {"alembic_version", "sqlite_sequence"}
BATCH_SIZE = 250


class MigrationSafetyError(RuntimeError):
    pass


def source_connection(source: Path) -> sqlite3.Connection:
    if not source.is_file():
        raise MigrationSafetyError(f"Arquivo SQLite não encontrado: {source}")
    with source.open("rb") as f:
        if f.read(16) != b"SQLite format 3\\x00":
            raise MigrationSafetyError("Arquivo informado não é um banco SQLite válido.")
    # Immutable backup is not assumed: mode=ro supports a live local database.
    from urllib.parse import quote
    db = sqlite3.connect(f"file:{quote(str(source.resolve()))}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    status = db.execute("PRAGMA quick_check").fetchone()[0]
    if status != "ok":
        db.close()
        raise MigrationSafetyError("Integridade SQLite falhou; não iniciar migração.")
    return db


def source_tables(db: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        if not row[0].startswith("sqlite_") and row[0] not in IGNORED_TABLES
    }


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(db: sqlite3.Connection, name: str) -> set[str]:
    return {
        str(row["name"])
        for row in db.execute(f"PRAGMA table_info({quote_identifier(name)})")
    }


def source_count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0])


def column_value(col, raw):
    if raw is None:
        return None
    kind = col.type
    if isinstance(kind, Uuid):
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    if isinstance(kind, Boolean):
        return bool(raw)
    if isinstance(kind, DateTime):
        if isinstance(raw, datetime):
            return raw
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if isinstance(kind, Date):
        return raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    if isinstance(kind, Numeric):
        return Decimal(str(raw))
    if isinstance(kind, JSON):
        return json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(kind, Integer):
        return int(raw)
    return raw


def plan_migration(db: sqlite3.Connection, engine: Engine):
    local_tables = source_tables(db)
    if not local_tables or "users" not in local_tables:
        raise MigrationSafetyError(
            "Banco SQLite não tem tabela users. Confirme qual banco antigo contém sua carteira."
        )
    metadata = MetaData()
    metadata.reflect(bind=engine)
    remote_tables = set(metadata.tables) - IGNORED_TABLES
    extra = local_tables - remote_tables
    if extra:
        raise MigrationSafetyError(
            "Há tabelas locais sem equivalente na Neon: " + ", ".join(sorted(extra))
            + ". Migração interrompida para não perder registros."
        )
    if "users" not in remote_tables:
        raise MigrationSafetyError("Neon não tem o esquema da aplicação; execute Alembic primeiro.")

    tables = [t for t in metadata.sorted_tables if t.name in local_tables]
    # Validate all source columns, not just the familiar portfolio tables.
    counts: dict[str, int] = {}
    for table in tables:
        local_columns = table_columns(db, table.name)
        unknown = local_columns - set(table.columns.keys())
        if unknown:
            raise MigrationSafetyError(
                f"{table.name}: campos locais ausentes do destino: {sorted(unknown)}"
            )
        missing_required = [
            c.name for c in table.columns
            if c.name not in local_columns
            and not c.nullable and c.server_default is None
            and not (c.primary_key and c.autoincrement is True)
        ]
        if missing_required:
            raise MigrationSafetyError(
                f"{table.name}: faltam campos obrigatórios: {missing_required}. "
                "Atualize o esquema local de forma segura após fazer backup."
            )
        counts[table.name] = source_count(db, table.name)
    if counts.get("users", 0) == 0:
        raise MigrationSafetyError(
            "Este arquivo não possui usuários. Localize o banco antigo correto, sem importar arquivo vazio."
        )

    # Import into strictly empty application tables. No merging and no overwriting.
    with engine.connect() as conn:
        occupied = [
            name for name in sorted(remote_tables)
            if conn.execute(select(func.count()).select_from(metadata.tables[name])).scalar_one() > 0
        ]
    if occupied:
        raise MigrationSafetyError(
            "Neon já contém dados nas tabelas " + ", ".join(occupied)
            + ". Não haverá sobrescrita nem mistura de carteiras."
        )
    return tables, counts


def sqlite_backup(db: sqlite3.Connection, source: Path) -> tuple[Path, str]:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = source.with_name(f"{source.name}.backup-{suffix}-{uuid4().hex[:8]}.sqlite3")
    if backup.exists():
        raise MigrationSafetyError("Nome de backup já existe; operação bloqueada.")
    dest = sqlite3.connect(str(backup))
    try:
        db.backup(dest)
        result = dest.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise MigrationSafetyError("Backup local falhou na verificação de integridade.")
    except Exception:
        dest.close()
        backup.unlink(missing_ok=True)
        raise
    finally:
        dest.close()
    sha = hashlib.sha256(backup.read_bytes()).hexdigest()
    return backup, sha


def migrate(db: sqlite3.Connection, engine: Engine, tables, counts) -> None:
    # Atomic, fail-closed import. One broken row rolls back the whole transfer.
    with engine.begin() as conn:
        # Recheck emptiness under the same transaction. Not safe for concurrent
        # writers; keep the app unused until confirmation of completion.
        for table in tables:
            if conn.execute(select(func.count()).select_from(table)).scalar_one() != 0:
                raise MigrationSafetyError("Destino deixou de estar vazio; abortando.")
        for table in tables:
            cols = [c for c in table.columns if c.name in table_columns(db, table.name)]
            if not cols:
                continue
            names = [c.name for c in cols]
            query = "SELECT " + ", ".join(quote_identifier(n) for n in names)
            query += " FROM " + quote_identifier(table.name)
            cursor = db.execute(query)
            transferred = 0
            while True:
                group = cursor.fetchmany(BATCH_SIZE)
                if not group:
                    break
                data = [
                    {col.name: column_value(col, row[col.name]) for col in cols}
                    for row in group
                ]
                conn.execute(table.insert(), data)
                transferred += len(data)
            if transferred != counts[table.name]:
                raise MigrationSafetyError(f"Contagem alterada durante leitura de {table.name}.")
            remote_count = conn.execute(select(func.count()).select_from(table)).scalar_one()
            if remote_count != counts[table.name]:
                raise MigrationSafetyError(f"Contagem pós-importação incorreta em {table.name}.")
    # No modifications to source, transaction committed only after all validation.


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Caminho do banco SQLite local antigo")
    parser.add_argument("--apply", action="store_true", help="Aplicar somente após backup e confirmação local")
    args = parser.parse_args(argv)
    db = None
    engine = None
    try:
        db = source_connection(args.source)
        url = os.environ.get("MESA_NEON_DATABASE_URL", "").strip()
        if not url:
            raise MigrationSafetyError(
                "Defina MESA_NEON_DATABASE_URL apenas no terminal do seu computador. "
                "Nunca coloque a senha da Neon no GitHub nem no chat."
            )
        from sqlalchemy.engine import make_url
        parsed = make_url(url)
        if not parsed.drivername.startswith("postgresql"):
            raise MigrationSafetyError("Destino deve ser PostgreSQL Neon, não SQLite.")
        if not (parsed.host or "").endswith(".neon.tech"):
            raise MigrationSafetyError("Destino não parece ser o hostname da Neon.")
        if parsed.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
            raise MigrationSafetyError("A conexão da Neon precisa de sslmode=require ou superior.")
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 15})
        tables, counts = plan_migration(db, engine)
        print("Prévia da migração (sem mostrar emails, senhas ou valores):")
        for table in tables:
            print(f"  {table.name}: {counts[table.name]} registros")
        print("Nenhuma alteração foi feita no destino.")
        if not args.apply:
            print("Para transferir, execute novamente com --apply após revisar as contagens.")
            return 0
        backup, sha = sqlite_backup(db, args.source)
        print(f"Backup SQLite criado: {backup}")
        print(f"SHA-256: {sha}")
        if input("Confirme digitando MIGRAR (não inclua sua senha): ").strip() != "MIGRAR":
            print("Cancelado; backup mantido; Neon inalterada.")
            return 1
        migrate(db, engine, tables, counts)
        print("Migração concluída; contagens conferidas. Backup preservado.")
        print("Faça login com o e-mail/senha antigos. Se não funcionar, NÃO altere as hashes manualmente.")
        return 0
    except (MigrationSafetyError, SQLAlchemyError, ValueError, sqlite3.Error, OSError) as exc:
        # Do not print DB credentials or row values inside backend exceptions.
        if isinstance(exc, MigrationSafetyError):
            print(f"Bloqueado com segurança: {exc}", file=sys.stderr)
        else:
            print("Falha de banco ou formato. Importação transacional cancelada; revise "
                  "log local sem compartilhar credenciais. O backup não foi apagado.", file=sys.stderr)
        return 2
    finally:
        if db is not None:
            db.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
