from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.monitoring.service import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/overview")
def overview(
    window_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    return MonitoringService(db).overview(window_days=window_days)
