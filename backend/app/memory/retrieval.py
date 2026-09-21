"""Weighted memory retrieval: semantic 0.35 / recency 0.25 / importance 0.20 / relevance 0.20."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.llm.embeddings import cosine_similarity, get_embedder, tokenize
from app.models.memory import MemoryItem


def _recency_score(last_seen_at: datetime, now: datetime, expiry_days: int) -> float:
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - last_seen_at).total_seconds() / 86400.0)
    return math.exp(-2.0 * age_days / max(1, expiry_days))


def _relevance_score(query_tokens: set, tags: List[str], content: str) -> float:
    if not query_tokens:
        return 0.5
    tag_tokens = set()
    for tag in tags:
        tag_tokens.update(tokenize(tag))
    content_tokens = set(tokenize(content))
    tag_hits = len(query_tokens & tag_tokens)
    content_hits = len(query_tokens & content_tokens)
    denominator = min(6, len(query_tokens))
    return min(1.0, (0.7 * tag_hits + 0.3 * content_hits) / denominator)


class MemoryRetrievalService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.embedder = get_embedder("local")

    def recall(
        self,
        merchant_id: str,
        query: str,
        top_k: Optional[int] = None,
        memory_types: Optional[List[str]] = None,
        weight_overrides: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        top_k = top_k or self.settings.memory_top_k
        stmt = select(MemoryItem).where(
            MemoryItem.merchant_id == merchant_id,
            MemoryItem.status == "active",
        )
        if memory_types:
            stmt = stmt.where(MemoryItem.type.in_(memory_types))
        memories = list(self.db.scalars(stmt).all())
        if not memories:
            return []

        query_vector = self.embedder.embed(query)
        query_tokens = set(tokenize(query))
        now = datetime.now(timezone.utc)
        s = self.settings
        weights = {
            "semantic": s.memory_weight_semantic,
            "recency": s.memory_weight_recency,
            "importance": s.memory_weight_importance,
            "relevance": s.memory_weight_relevance,
        }
        if weight_overrides:
            weights.update({k: float(v) for k, v in weight_overrides.items() if k in weights})

        scored = []
        for memory in memories:
            semantic = (
                cosine_similarity(query_vector, list(memory.embedding))
                if memory.embedding is not None
                else 0.0
            )
            semantic = max(0.0, semantic)
            recency = _recency_score(memory.last_seen_at, now, s.memory_expiry_days)
            relevance = _relevance_score(query_tokens, list(memory.tags), memory.content)
            score = (
                weights["semantic"] * semantic
                + weights["recency"] * recency
                + weights["importance"] * memory.importance
                + weights["relevance"] * relevance
            )
            scored.append(
                {
                    "memory_id": memory.memory_id,
                    "type": memory.type,
                    "content": memory.content,
                    "tags": memory.tags,
                    "importance": memory.importance,
                    "confidence": memory.confidence,
                    "evidence_count": memory.evidence_count,
                    "status": memory.status,
                    "last_seen_at": memory.last_seen_at.isoformat(),
                    "score": round(score, 4),
                    "score_breakdown": {
                        "semantic": round(semantic, 4),
                        "recency": round(recency, 4),
                        "importance": round(memory.importance, 4),
                        "relevance": round(relevance, 4),
                    },
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]
