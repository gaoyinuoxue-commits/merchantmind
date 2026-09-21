from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.simulator import AdvanceRequest, AdvanceResponse, SimulatorState
from app.simulator.engine import SimulatorService

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.get("/state/{merchant_id}", response_model=SimulatorState)
def get_state(merchant_id: str, db: Session = Depends(get_db)) -> SimulatorState:
    service = SimulatorService(db)
    try:
        return SimulatorState(**service.state(merchant_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/advance", response_model=AdvanceResponse)
def advance(request: AdvanceRequest, db: Session = Depends(get_db)) -> AdvanceResponse:
    service = SimulatorService(db)
    effects = [effect.model_dump(exclude_none=True) for effect in request.effects]
    try:
        result = service.advance(request.merchant_id, request.days, effects)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdvanceResponse(**result)
