from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Unit tests must be deterministic and never depend on a real external LLM,
# network, API key, or billing balance. This env var takes precedence over
# the local .env file. Tests that exercise LLM behavior monkeypatch the chat
# layer explicitly, so they are unaffected by this default.
os.environ["LLM_PROVIDER"] = "local"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.session import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]

BUSINESS_TABLES = [
    "experiment_variant_run",
    "experiment",
    "badcase",
    "feedback",
    "eval_case_result",
    "eval_run",
    "trace_span",
    "trace_run",
    "message",
    "conversation",
    "memory_conflict",
    "memory_item",
    "knowledge_item",
    "tool_call_log",
    "business_event",
    "material",
    "performance_daily",
    "product",
    "campaign",
    "merchant_industry",
    "merchant",
]


def _require_db() -> bool:
    return os.getenv("MM_REQUIRE_DB") == "1"


def _admin_engine():
    """Connect to the server for CREATE/DROP DATABASE.

    Prefers the configured database; falls back to the maintenance "postgres"
    database for minimal servers where the application database is missing.
    """
    configured = make_url(get_settings().database_url)
    candidates = [configured]
    if configured.database != "postgres":
        candidates.append(configured.set(database="postgres"))
    last_error: Optional[OperationalError] = None
    for candidate in candidates:
        engine = create_engine(
            candidate.render_as_string(hide_password=False),
            isolation_level="AUTOCOMMIT",
            connect_args={"connect_timeout": 3},
        )
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except OperationalError as exc:
            last_error = exc
            engine.dispose()
    assert last_error is not None
    raise last_error


def _database_url(base_url: URL, database_name: str) -> str:
    return base_url.set(database=database_name).render_as_string(hide_password=False)


def _create_database(admin_engine, database_name: str) -> None:
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": database_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        conn.execute(text(f'CREATE DATABASE "{database_name}"'))


def _drop_database(admin_engine, database_name: str) -> None:
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": database_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))


def _run_alembic(test_url: str, *arguments: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": test_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(arguments)} failed:\n{result.stdout}\n{result.stderr}"
    )
    return result


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def db_engine():
    """A real, isolated PostgreSQL database migrated to head via Alembic."""
    base_url = make_url(get_settings().database_url)
    database_name = f"{base_url.database or 'merchantmind'}_test"
    try:
        admin = _admin_engine()
    except OperationalError:
        if _require_db():
            pytest.fail("MM_REQUIRE_DB=1 but PostgreSQL is unreachable")
        pytest.skip("PostgreSQL is unreachable; skipping database tests")

    try:
        _create_database(admin, database_name)
        test_url = _database_url(base_url, database_name)
        _run_alembic(test_url, "upgrade", "head")
        engine = create_engine(test_url)
        try:
            yield engine
        finally:
            engine.dispose()
        _drop_database(admin, database_name)
    finally:
        admin.dispose()


@pytest.fixture()
def db(db_engine):
    """Function-scoped session; business tables are truncated afterwards."""
    session = Session(bind=db_engine)
    try:
        yield session
    finally:
        session.close()
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE TABLE "
                    + ", ".join(BUSINESS_TABLES)
                    + " RESTART IDENTITY CASCADE"
                )
            )


@pytest.fixture()
def api_client(db):
    """TestClient with get_db overridden onto the isolated test database."""
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def migration_database():
    """A scratch database plus alembic runner for migration round-trip tests."""
    base_url = make_url(get_settings().database_url)
    database_name = f"{base_url.database or 'merchantmind'}_test_mig"
    try:
        admin = _admin_engine()
    except OperationalError:
        if _require_db():
            pytest.fail("MM_REQUIRE_DB=1 but PostgreSQL is unreachable")
        pytest.skip("PostgreSQL is unreachable; skipping migration tests")

    try:
        _create_database(admin, database_name)
        test_url = _database_url(base_url, database_name)

        def run(*arguments: str) -> subprocess.CompletedProcess:
            return _run_alembic(test_url, *arguments)

        engine = create_engine(test_url)
        try:
            yield engine, run
        finally:
            engine.dispose()
        _drop_database(admin, database_name)
    finally:
        admin.dispose()
