"""Isolated PostgreSQL 16 integration test for the account recovery script.

Only runs in the GitHub Actions ephemeral database service. No real Neon
project or original local Mesa Quant Master database is touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from pwdlib import PasswordHash
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import make_url

from scripts.migrate_local_account_to_neon import (
    MigrationBlocked,
    assert_endpoints,
    migrate,
)

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.environ.get("ACCOUNT_RECOVERY_CI") != "1",
    reason="PostgreSQL recovery regression only runs in isolated GitHub Actions service.",
)


def table(connection, name):
    return Table(name, MetaData(), autoload_with=connection)


def test_endpoint_safety_rules():
    source = "postgresql://example:secret@127.0.0.1:5432/mesa_quant_master_v2"
    neon = "postgresql://example:secret@ep-demo.neon.tech/neondb?sslmode=require"
    assert_endpoints(source, neon)
    for bad in [
        "postgresql://example:secret@ep-demo.neon.tech/neondb",
        "postgresql://example:secret@another.example/neondb?sslmode=require",
        "sqlite:///neondb.sqlite",
    ]:
        with pytest.raises(MigrationBlocked):
            assert_endpoints(source, bad)
    with pytest.raises(MigrationBlocked):
        assert_endpoints(neon, neon)


def test_full_user_and_portfolio_recovery_without_other_users():
    src_url = os.environ["ACCOUNT_RECOVERY_SOURCE_URL"]
    parsed = make_url(src_url)
    # Never allow this integration fixture against a real local or hosted DB.
    assert (parsed.host or "") in ("127.0.0.1", "localhost")
    assert parsed.database == "mesa_quant_ci"
    target_db = "mesa_quant_recovery_ci"
    target_url = parsed.set(database=target_db).render_as_string(hide_password=False)

    engine = create_engine(src_url)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if not conn.exec_driver_sql(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = %s)",
            (target_db,),
        ).scalar_one():
            conn.exec_driver_sql(f'CREATE DATABASE "{target_db}"')
    engine.dispose()

    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "DATABASE_URL": target_url},
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr[-1200:]

    one, another, asset, other_asset, brokerage, policy = (uuid4() for _ in range(6))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    passwd = PasswordHash.recommended().hash("ci-example-password-not-real")
    source = create_engine(src_url)
    with source.begin() as conn:
        assert conn.execute(select(text("COUNT(*)")).select_from(table(conn, "users"))).scalar_one() == 0
        conn.execute(table(conn, "users").insert(), [
            dict(id=one, name="Conta pessoal", email="owner@example.invalid",
                 hashed_password=passwd, is_active=True, is_superuser=False,
                 is_email_verified=True, auth_version=3, created_at=now, updated_at=now),
            dict(id=another, name="Outra conta", email="other@example.invalid",
                 hashed_password=passwd, is_active=True, is_superuser=False,
                 is_email_verified=True, auth_version=0, created_at=now, updated_at=now),
        ])
        conn.execute(table(conn, "assets").insert(), [
            dict(id=asset,ticker="TEST11",name="Exemplo FII",asset_type="FII",sector="Papel",
                 country="BR",currency="BRL",exchange="B3",is_active=True,
                 created_at=now,updated_at=now),
            dict(id=other_asset,ticker="OTHER3",name="Outra ação",asset_type="STOCK",
                 sector="Bancos",country="BR",currency="BRL",exchange="B3",is_active=True,
                 created_at=now,updated_at=now),
        ])
        conn.execute(table(conn, "brokerages").insert(), [
            dict(id=brokerage,user_id=one,name="Corretora de teste",created_at=now,updated_at=now)
        ])
        conn.execute(table(conn, "operations").insert(), [
            dict(id=uuid4(),user_id=one,asset_id=asset,brokerage_id=brokerage,
                 operation_type="buy",operation_date=date.today(),quantity=Decimal("4"),
                 unit_price=Decimal("24.30"),fees=Decimal("0.25"),taxes=Decimal("0"),
                 notes="compras anteriores",source="manual",created_at=now,updated_at=now),
            dict(id=uuid4(),user_id=another,asset_id=other_asset,brokerage_id=None,
                 operation_type="buy",operation_date=date.today(),quantity=Decimal("2"),
                 unit_price=Decimal("17.00"),fees=Decimal("0"),taxes=Decimal("0"),
                 notes=None,source=None,created_at=now,updated_at=now),
        ])
        conn.execute(table(conn, "watchlists").insert(), [
            dict(id=uuid4(),user_id=one,asset_id=asset,created_at=now)
        ])
        conn.execute(table(conn, "alerts").insert(), [
            dict(id=uuid4(),user_id=one,asset_id=asset,alert_type="price_above",
                 target_value=Decimal("30.00"),is_active=True,triggered=False,
                 created_at=now,updated_at=now)
        ])
        conn.execute(table(conn, "portfolio_policies").insert(), [
            dict(id=policy,user_id=one,name="Carteira antiga",objective="retirement",
                 risk_profile="moderado",investment_horizon="longo",monthly_contribution=Decimal("500"),
                 liquidity_need="baixa",income_need=False,emergency_reserve_months=6,
                 maximum_weight_per_asset=Decimal("25"),maximum_weight_per_sector=Decimal("40"),
                 maximum_weight_per_issuer=Decimal("30"),rebalance_tolerance=Decimal("5"),
                 created_at=now,updated_at=now)
        ])
        conn.execute(table(conn, "portfolio_policy_allocations").insert(), [
            dict(id=uuid4(),policy_id=policy,asset_class="FII",
                 target_percentage=Decimal("20"),minimum_percentage=Decimal("5"),
                 maximum_percentage=Decimal("35"),enabled=True)
        ])
        conn.execute(table(conn, "investor_profiles").insert(), [
            dict(id=uuid4(),user_id=one,status="confirmed",version=1,
                 overall_classification="moderado",created_at=now,updated_at=now)
        ])
        conn.execute(table(conn, "manual_indicators").insert(), [
            dict(id=uuid4(),user_id=one,asset_id=asset,indicator_key="vacancy",
                 value=Decimal("0.10"),unit="ratio",reference_date=date.today(),
                 source_type="manual",source_description="Documentos",
                 created_at=now,updated_at=now)
        ])
        conn.execute(table(conn, "portfolio_action_audits").insert(), [
            dict(id=uuid4(),user_id=one,asset_id=asset,action="test",
                 operation_count=1,before_json="{}",after_json="{}",created_at=now)
        ])
    source.dispose()

    with patch("scripts.migrate_local_account_to_neon.assert_endpoints"):
        preview = migrate(src_url,target_url,"OWNER@example.invalid")
        assert preview["users"] == 1
        assert preview["assets"] == 1
        assert preview["operations"] == 1
        assert preview["portfolio_policies"] == 1
        assert preview["portfolio_policy_allocations"] == 1
        target = create_engine(target_url)
        with target.connect() as conn:
            assert conn.execute(select(text("COUNT(*)")).select_from(table(conn,"users"))).scalar_one() == 0

        imported = migrate(src_url,target_url,"owner@example.invalid",apply=True,
                           confirmed=True,expected_counts=preview)
        assert imported == preview
        with target.connect() as conn:
            user = conn.execute(select(table(conn,"users"))).mappings().one()
            assert user["id"] == one
            assert user["hashed_password"] == passwd
            assert user["auth_version"] == 3
            assert user["is_email_verified"] is True
            assert conn.execute(select(table(conn,"operations").c.quantity)).scalar_one() == Decimal("4")
            assets = conn.execute(select(table(conn,"assets").c.ticker)).scalars().all()
            assert assets == ["TEST11"]
            assert set(inspect(conn).get_table_names()) >= {"users","operations","assets"}
        target.dispose()
        with pytest.raises(MigrationBlocked,match="já possui registros"):
            migrate(src_url,target_url,"owner@example.invalid",apply=True,confirmed=True)
