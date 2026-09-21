from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KnowledgeCandidateIn(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    type: str = Field(
        pattern="^(business_rule|diagnostic_rule|industry_insight|best_practice|metric_definition|case)$"
    )
    industry: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    condition: Optional[str] = None
    recommendation: Optional[str] = None
    evidence: Optional[str] = None
    merchant_count: int = Field(default=0, ge=0)
    quality_score: float = Field(default=0.6, ge=0.0, le=1.0)
    source: str = Field(default="manual_proposal", max_length=32)


class KnowledgeQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    industry: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    types: Optional[List[str]] = None


class KnowledgeOut(BaseModel):
    knowledge_id: str
    slug: str
    version: int
    type: str
    industry: Optional[str]
    title: str
    content: str
    condition: Optional[str]
    recommendation: Optional[str]
    evidence: Optional[str]
    status: str
    source: str
    merchant_count: int
    quality_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScoredKnowledge(BaseModel):
    knowledge_id: str
    slug: str
    version: int
    type: str
    industry: Optional[str]
    title: str
    content: str
    recommendation: Optional[str]
    evidence: Optional[str]
    score: float
    score_breakdown: Dict[str, Any]
