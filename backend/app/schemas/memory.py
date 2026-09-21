from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MemoryCandidateIn(BaseModel):
    merchant_id: str
    type: str = Field(pattern="^(fact|profile|preference|derived_insight)$")
    content: str = Field(min_length=1, max_length=2000)
    tags: List[str] = Field(default_factory=list)
    importance: float = Field(default=0.6, ge=0.0, le=1.0)
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    source: str = Field(default="manual", pattern="^(conversation|event|derived|manual)$")


class MemoryExtractIn(BaseModel):
    merchant_id: str
    text: str = Field(min_length=1, max_length=4000)


class MemoryRecallQuery(BaseModel):
    merchant_id: str
    query: str = Field(min_length=1, max_length=2000)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    types: Optional[List[str]] = None


class MemoryOut(BaseModel):
    memory_id: str
    merchant_id: str
    type: str
    content: str
    importance: float
    confidence: float
    status: str
    evidence_count: int
    source: str
    tags: List[str]
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class ScoredMemory(BaseModel):
    memory_id: str
    type: str
    content: str
    tags: List[str]
    importance: float
    confidence: float
    evidence_count: int
    status: str
    last_seen_at: str
    score: float
    score_breakdown: Dict[str, float]


class ConflictOut(BaseModel):
    id: int
    memory_id: str
    previous_memory_id: str
    reason: str
    resolution: str
    created_at: datetime

    model_config = {"from_attributes": True}
