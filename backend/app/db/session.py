from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    connect_args={"connect_timeout": int(settings.db_connect_timeout_seconds)},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Best-effort startup initialization.

    Ensures the pgvector extension is available once PostgreSQL is reachable.
    Never raises: the API must stay up for /health even if the database is down.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.commit()
        logger.info("pgvector extension ensured")
    except Exception as exc:  # noqa: BLE001 - startup must not crash
        logger.warning("init_db skipped (database unreachable?): %s", exc)


def check_database() -> dict:
    """Return an honest, structured database + pgvector health report."""
    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version()")).scalar_one()
            extension_row = connection.execute(
                text(
                    "SELECT default_version, installed_version "
                    "FROM pg_available_extensions WHERE name = 'vector'"
                )
            ).first()
    except Exception as exc:  # noqa: BLE001 - health endpoint must not raise
        return {
            "status": "down",
            "pgvector": "unknown",
            "message": f"Database connection failed: {exc.__class__.__name__}",
        }

    if extension_row is None:
        pgvector_status = "unavailable"
        pgvector_message = "pgvector is not available on this PostgreSQL server"
    elif extension_row.installed_version is not None:
        pgvector_status = "installed"
        pgvector_message = f"vector extension installed ({extension_row.installed_version})"
    else:
        pgvector_status = "available"
        pgvector_message = (
            f"vector extension available ({extension_row.default_version}), not yet created"
        )

    return {
        "status": "up",
        "pgvector": pgvector_status,
        "message": pgvector_message,
        "server_version": version.split(",")[0] if version else None,
    }
