from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    status: Literal["up", "down"]
    pgvector: Literal["installed", "available", "unavailable", "unknown"]
    message: str
    server_version: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    database: DatabaseHealth
