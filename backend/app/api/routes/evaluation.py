from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.eval.service import EvaluationService

router = APIRouter(prefix="/eval", tags=["evaluation"])


class HumanVerdictIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback: Optional[str] = None


@router.post("/runs")
def create_eval_run(
    judge: str = Query("rule", pattern="^(rule|heuristic)$"),
    db: Session = Depends(get_db),
) -> dict:
    return EvaluationService(db).run_evaluation(judge=judge)


@router.get("/runs")
def list_eval_runs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> dict:
    return {"items": EvaluationService(db).list_runs(limit=limit), "label": "SYNTHETIC"}


@router.get("/runs/{run_id}")
def get_eval_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    result = EvaluationService(db).get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    return result


@router.post("/cases/{case_result_id}/human")
def record_human_verdict(
    case_result_id: int, payload: HumanVerdictIn, db: Session = Depends(get_db)
) -> dict:
    try:
        return EvaluationService(db).record_human_verdict(
            case_result_id, payload.rating, payload.feedback
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="case result not found")
