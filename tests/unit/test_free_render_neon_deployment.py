"""Regression tests for Render + Neon zero-fixed-monthly-fee deployment.

Tests never provision any cloud resource or connect to a live database.
"""
from pathlib import Path
from subprocess import run
from types import SimpleNamespace

import pytest

from app.core.production_guard import assert_production_ready

ROOT = Path(__file__).resolve().parents[2]


def production_settings(url):
    return SimpleNamespace(
        APP_ENV="production", DATABASE_URL=url, SECRET_KEY="k" * 64,
        DEBUG=False, API_DOCS_ENABLED=False, SECURITY_HSTS_ENABLED=True,
        FRONTEND_ORIGINS=["https://localhost"],
    )


def test_render_blueprint_only_provisions_free_api_and_static_web():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "plan: free" in blueprint
    assert "name: mesa-quant-master-api" in blueprint
    assert "runtime: static" in blueprint
    assert "name: mesa-quant-master-web" in blueprint
    assert "preDeployCommand:" not in [
        line.strip() for line in blueprint.splitlines()
        if not line.strip().startswith("#")
    ]
    assert not any(line.lstrip().startswith("databases:") for line in blueprint.splitlines())
    assert "fromDatabase:" not in blueprint
    assert "name: mesa-quant-master-db" not in blueprint
    assert "key: DATABASE_URL\n        sync: false" in blueprint
    assert "key: SECRET_KEY\n        generateValue: true" in blueprint
    assert "bash scripts/start-free.sh" in blueprint
    assert "healthCheckPath: /ready" in blueprint


def test_free_start_script_runs_migrations_before_server_and_does_not_log_secrets():
    start = ROOT / "backend" / "scripts" / "start-free.sh"
    content = start.read_text(encoding="utf-8")
    assert "set -euo pipefail" in content
    assert "python -m alembic upgrade head" in content
    assert "assert_production_ready(settings)" in content
    assert content.index("assert_production_ready(settings)") < content.index(
        "python -m alembic upgrade head"
    )
    assert "exec uvicorn app.main:app" in content
    assert content.index("python -m alembic upgrade head") < content.index(
        "exec uvicorn app.main:app"
    )
    assert "echo ${DATABASE_URL}" not in content
    result = run(["bash", "-n", str(start)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_production_neon_requires_tls():
    base = "postgresql://test:example@ep-test.eu-west-2.aws.neon.tech/test"
    with pytest.raises(RuntimeError, match="sslmode"):
        assert_production_ready(production_settings(base))
    assert_production_ready(production_settings(base + "?sslmode=require"))
    assert_production_ready(production_settings(base + "?sslmode=verify-full"))


def test_production_never_accepts_ephemeral_database():
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        assert_production_ready(production_settings("sqlite:///tmp/portfolio.db"))


def test_deployment_guide_does_not_advertise_paid_neon_free_as_guaranteed_zero():
    guide = (ROOT / "DEPLOY_ANDROID_NUVEM.md").read_text(encoding="utf-8")
    assert "Render Free" in guide
    assert "Neon Free" in guide
    assert "15 minutos" in guide
    assert "SMTP" in guide
    assert "backup" in guide.casefold()
    assert "cotas" in guide
