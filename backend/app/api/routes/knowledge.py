from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.knowledge.service import KnowledgeService
from app.models.knowledge import KnowledgeItem
from app.schemas.knowledge import (
    KnowledgeCandidateIn,
    KnowledgeOut,
    KnowledgeQuery,
    ScoredKnowledge,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/query", response_model=List[ScoredKnowledge])
def query_knowledge(payload: KnowledgeQuery, db: Session = Depends(get_db)) -> List[dict]:
    service = KnowledgeService(db)
    return service.retrieve(
        query=payload.query,
        industry=payload.industry,
        top_k=payload.top_k,
        types=payload.types,
    )


@router.get("", response_model=List[KnowledgeOut])
def list_knowledge(
    status_filter: Optional[str] = None,
    ktype: Optional[str] = None,
    industry: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[KnowledgeItem]:
    stmt = select(KnowledgeItem)
    if status_filter:
        stmt = stmt.where(KnowledgeItem.status == status_filter)
    if ktype:
        stmt = stmt.where(KnowledgeItem.type == ktype)
    if industry:
        stmt = stmt.where(KnowledgeItem.industry == industry)
    stmt = stmt.order_by(KnowledgeItem.slug, KnowledgeItem.version.desc())
    return list(db.scalars(stmt).all())


@router.post("/propose", response_model=KnowledgeOut, status_code=status.HTTP_201_CREATED)
def propose_candidate(
    payload: KnowledgeCandidateIn, db: Session = Depends(get_db)
) -> KnowledgeItem:
    service = KnowledgeService(db)
    return service.propose_candidate(payload.model_dump())


@router.post("/scan-patterns", response_model=KnowledgeOut)
def scan_patterns(db: Session = Depends(get_db)):
    service = KnowledgeService(db)
    candidate = service.propose_from_merchant_patterns()
    if candidate is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return candidate


@router.post("/{knowledge_id}/verify", response_model=KnowledgeOut)
def verify_knowledge(knowledge_id: str, db: Session = Depends(get_db)) -> KnowledgeItem:
    service = KnowledgeService(db)
    try:
        return service.verify(knowledge_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="knowledge item not found")
