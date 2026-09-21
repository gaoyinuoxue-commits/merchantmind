from __future__ import annotations

import os


def test_root_is_health_alias(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "MerchantMind"
    assert "version" in body
    assert body["status"] in {"ok", "degraded"}
    assert body["database"]["status"] in {"up", "down"}


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "status",
        "service",
        "version",
        "environment",
        "database",
    }
    assert set(body["database"].keys()) >= {
        "status",
        "pgvector",
        "message",
    }


def test_health_stays_available_without_database(client):
    """The API must still serve /health when PostgreSQL is unreachable."""
    response = client.get("/api/health")
    assert response.status_code == 200
    db = response.json()["database"]
    if os.getenv("MM_REQUIRE_DB") == "1":
        assert db["status"] == "up", db
        assert db["pgvector"] == "installed", db
    else:
        assert db["status"] in {"up", "down"}


def test_openapi_contains_health(client):
    schema = client.get("/openapi.json").json()
    assert "/api/health" in schema["paths"]
