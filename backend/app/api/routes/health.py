from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import get_settings
from app.db.session import check_database
from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter(tags=["health"])


def _build_health_response() -> HealthResponse:
    settings = get_settings()
    db_report = check_database()
    database = DatabaseHealth(**db_report)
    return HealthResponse(
        status="ok" if database.status == "up" else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database=database,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return _build_health_response()
