from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.memory.governance import MemoryGovernanceService
from app.memory.retrieval import MemoryRetrievalService
from app.models.memory import MemoryConflict, MemoryItem
from app.models.merchant import Merchant
from app.schemas.memory import (
    ConflictOut,
    MemoryCandidateIn,
    MemoryExtractIn,
    MemoryOut,
    MemoryRecallQuery,
    ScoredMemory,
)

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("/ingest", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def ingest_candidate(payload: MemoryCandidateIn, db: Session = Depends(get_db)) -> MemoryItem:
    merchant = db.get(Merchant, payload.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="merchant not found")
    service = MemoryGovernanceService(db)
    memory = service.ingest_candidate(
        merchant_id=payload.merchant_id,
        mtype=payload.type,
        content=payload.content,
        tags=payload.tags,
        importance=payload.importance,
        confidence=payload.confidence,
        source=payload.source,
    )
    db.commit()
    db.refresh(memory)
    return memory


@router.post("/extract", response_model=List[MemoryOut], status_code=status.HTTP_201_CREATED)
def extract_from_conversation(
    payload: MemoryExtractIn, db: Session = Depends(get_db)
) -> List[MemoryItem]:
    if db.get(Merchant, payload.merchant_id) is None:
        raise HTTPException(status_code=404, detail="merchant not found")
    service = MemoryGovernanceService(db)
    return service.extract_from_text(payload.merchant_id, payload.text)


@router.post("/recall", response_model=List[ScoredMemory])
def recall(payload: MemoryRecallQuery, db: Session = Depends(get_db)) -> List[dict]:
    service = MemoryRetrievalService(db)
    return service.recall(
        merchant_id=payload.merchant_id,
        query=payload.query,
        top_k=payload.top_k,
        memory_types=payload.types,
    )


@router.get("", response_model=List[MemoryOut])
def list_memories(
    merchant_id: str,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[MemoryItem]:
    stmt = select(MemoryItem).where(MemoryItem.merchant_id == merchant_id)
    if status_filter:
        stmt = stmt.where(MemoryItem.status == status_filter)
    stmt = stmt.order_by(MemoryItem.updated_at.desc())
    return list(db.scalars(stmt).all())


@router.post("/{memory_id}/promote", response_model=MemoryOut)
def promote_memory(memory_id: str, db: Session = Depends(get_db)) -> MemoryItem:
    service = MemoryGovernanceService(db)
    try:
        memory = service.promote(memory_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found")
    db.commit()
    db.refresh(memory)
    return memory


@router.get("/conflicts", response_model=List[ConflictOut])
def list_conflicts(
    merchant_id: Optional[str] = None, db: Session = Depends(get_db)
) -> List[MemoryConflict]:
    stmt = select(MemoryConflict)
    if merchant_id:
        stmt = stmt.join(MemoryItem).where(MemoryItem.merchant_id == merchant_id)
    stmt = stmt.order_by(MemoryConflict.created_at.desc())
    return list(db.scalars(stmt).all())
