from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.trace.service import TraceService

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("")
def list_traces(
    merchant_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    runs = TraceService(db).list_runs(merchant_id=merchant_id, limit=limit)
    return {"items": runs, "label": "SYNTHETIC"}


@router.get("/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)) -> dict:
    summary = TraceService(db).summary(trace_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return summary
