def test_authorized_origin_receives_cors_headers(client):
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_loopback_origin_receives_cors_headers(client):
    response = client.get(
        "/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_unauthorized_origin_does_not_receive_cors_permission(client):
    response = client.get(
        "/health",
        headers={"Origin": "http://malicious.localhost:5173"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_options_allows_authorization_header(client):
    response = client.options(
        "/portfolio",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "Authorization" in response.headers["access-control-allow-headers"]


def test_protected_endpoints_still_require_authentication(unauthenticated_client):
    response = unauthenticated_client.get(
        "/portfolio",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 401
