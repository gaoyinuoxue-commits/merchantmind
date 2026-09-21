from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.badcase.service import BadcaseService
from app.db.session import get_db

router = APIRouter(tags=["badcase"])


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    trace_id: Optional[str] = None
    merchant_id: Optional[str] = None
    conversation_id: Optional[str] = None


class BadcaseUpdateIn(BaseModel):
    status: Optional[str] = None
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None
    severity: Optional[str] = None


def _badcase_dict(item) -> dict:
    return {
        "id": item.id,
        "source": item.source,
        "trace_id": item.trace_id,
        "feedback_id": item.feedback_id,
        "eval_run_id": item.eval_run_id,
        "case_id": item.case_id,
        "merchant_id": item.merchant_id,
        "title": item.title,
        "error_type": item.error_type,
        "affected_module": item.affected_module,
        "root_cause": item.root_cause,
        "suggested_fix": item.suggested_fix,
        "evidence": item.evidence,
        "status": item.status,
        "severity": item.severity,
        "reporter": item.reporter,
        "occurrence_count": item.occurrence_count,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "resolved_at": item.resolved_at,
        "label": "SYNTHETIC",
    }


@router.post("/feedback")
def submit_feedback(payload: FeedbackIn, db: Session = Depends(get_db)) -> dict:
    return BadcaseService(db).create_feedback(
        rating=payload.rating,
        comment=payload.comment,
        trace_id=payload.trace_id,
        merchant_id=payload.merchant_id,
        conversation_id=payload.conversation_id,
    )


@router.get("/feedback")
def list_feedback(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> dict:
    items = BadcaseService(db).list_feedback(limit=limit)
    return {
        "items": [
            {
                "id": item.id,
                "trace_id": item.trace_id,
                "merchant_id": item.merchant_id,
                "conversation_id": item.conversation_id,
                "rating": item.rating,
                "helpful": item.helpful,
                "comment": item.comment,
                "created_at": item.created_at,
                "label": "SYNTHETIC",
            }
            for item in items
        ],
        "label": "SYNTHETIC",
    }


@router.get("/badcases")
def list_badcases(
    status: Optional[str] = None,
    error_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    items = BadcaseService(db).list_badcases(status=status, error_type=error_type, limit=limit)
    return {"items": [_badcase_dict(item) for item in items], "label": "SYNTHETIC"}


@router.get("/badcases/{badcase_id}")
def get_badcase(badcase_id: int, db: Session = Depends(get_db)) -> dict:
    item = BadcaseService(db).get_badcase(badcase_id)
    if item is None:
        raise HTTPException(status_code=404, detail="badcase not found")
    return _badcase_dict(item)


@router.patch("/badcases/{badcase_id}")
def update_badcase(badcase_id: int, payload: BadcaseUpdateIn, db: Session = Depends(get_db)) -> dict:
    service = BadcaseService(db)
    try:
        item = service.update_badcase(badcase_id, payload.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(status_code=404, detail="badcase not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _badcase_dict(item)
