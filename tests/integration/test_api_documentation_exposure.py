import json
import os
import subprocess
import sys


def test_documentation_enabled_by_default_and_api_routes_work(
    unauthenticated_client,
):
    assert unauthenticated_client.get("/docs").status_code == 200
    assert unauthenticated_client.get("/redoc").status_code == 200
    assert unauthenticated_client.get("/openapi.json").status_code == 200
    assert unauthenticated_client.get("/health").status_code == 200
    assert unauthenticated_client.get("/assets").status_code == 401


def test_documentation_can_be_disabled_without_disabling_api(tmp_path):
    database_path = (tmp_path / "docs-disabled.db").as_posix()
    script = """
import json
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    print(json.dumps({
        "docs": client.get("/docs").status_code,
        "redoc": client.get("/redoc").status_code,
        "openapi": client.get("/openapi.json").status_code,
        "health": client.get("/health").status_code,
        "authenticated_route": client.get("/assets").status_code,
        "headers": {
            "nosniff": client.get("/health").headers.get("x-content-type-options"),
            "referrer": client.get("/health").headers.get("referrer-policy"),
            "frame": client.get("/health").headers.get("x-frame-options"),
            "csp": client.get("/health").headers.get("content-security-policy"),
        },
    }))
"""
    environment = {
        **os.environ,
        "DEBUG": "false",
        "APP_ENV": "test",
        "API_DOCS_ENABLED": "false",
        "DATABASE_URL": f"sqlite:///{database_path}",
        "SECRET_KEY": "test-only-secret-key",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(result.stdout.strip().splitlines()[-1])

    assert response == {
        "docs": 404,
        "redoc": 404,
        "openapi": 404,
        "health": 200,
        "authenticated_route": 401,
        "headers": {
            "nosniff": "nosniff",
            "referrer": "strict-origin-when-cross-origin",
            "frame": "DENY",
            "csp": "frame-ancestors 'none'",
        },
    }
