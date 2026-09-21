from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.experiments.service import ExperimentService

router = APIRouter(prefix="/experiments", tags=["experiments"])


class ExperimentIn(BaseModel):
    name: Optional[str] = None
    variants: Optional[List[Dict[str, Any]]] = None
    case_ids: Optional[List[str]] = None


@router.post("")
def create_experiment(payload: ExperimentIn, db: Session = Depends(get_db)) -> dict:
    service = ExperimentService(db)
    try:
        return service.create_experiment(
            name=payload.name or "默认 A/B 实验",
            variants=payload.variants,
            case_ids=payload.case_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
def list_experiments(db: Session = Depends(get_db)) -> dict:
    return {"items": ExperimentService(db).list_experiments(), "label": "SYNTHETIC"}


@router.get("/{experiment_id}")
def get_experiment(experiment_id: int, db: Session = Depends(get_db)) -> dict:
    result = ExperimentService(db).get_experiment(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return result
