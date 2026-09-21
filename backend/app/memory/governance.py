"""Memory lifecycle governance: dedup, conflict resolution, promotion, expiry."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.llm.embeddings import cosine_similarity, get_embedder
from app.memory.extractor import extract_memories
from app.models.memory import MemoryConflict, MemoryItem


def _new_id() -> str:
    return f"MM{uuid.uuid4().hex[:14]}"


def _strength(memory: MemoryItem) -> float:
    return (
        memory.confidence * 0.6
        + memory.importance * 0.3
        + min(memory.evidence_count, 5) * 0.02
    )


class MemoryGovernanceService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.embedder = get_embedder("local")

    def _existing_pool(self, merchant_id: str, mtype: str) -> List[MemoryItem]:
        stmt = select(MemoryItem).where(
            MemoryItem.merchant_id == merchant_id,
            MemoryItem.type == mtype,
            MemoryItem.status.in_(["candidate", "active"]),
        )
        return list(self.db.scalars(stmt).all())

    def ingest_candidate(
        self,
        merchant_id: str,
        mtype: str,
        content: str,
        tags: Optional[List[str]] = None,
        importance: float = 0.6,
        confidence: float = 0.6,
        source: str = "conversation",
    ) -> MemoryItem:
        tags = tags or []
        vector = self.embedder.embed(content)
        pool = self._existing_pool(merchant_id, mtype)

        duplicate = None
        best_sim = 0.0
        for item in pool:
            if item.embedding is None:
                continue
            sim = cosine_similarity(vector, list(item.embedding))
            if sim > best_sim:
                best_sim, duplicate = sim, item

        if duplicate is not None and best_sim >= self.settings.memory_dedup_threshold:
            duplicate.evidence_count += 1
            duplicate.last_seen_at = datetime.now(timezone.utc)
            duplicate.confidence = min(0.99, duplicate.confidence + 0.05)
            if importance > duplicate.importance:
                duplicate.importance = importance
            if duplicate.status == "candidate" and self._can_promote(duplicate):
                duplicate.status = "active"
            self.db.flush()
            return duplicate

        conflicting = self._find_conflict(pool, tags)

        now = datetime.now(timezone.utc)
        status = (
            "active"
            if confidence >= self.settings.memory_candidate_confidence
            and importance >= 0.5
            else "candidate"
        )
        memory = MemoryItem(
            memory_id=_new_id(),
            merchant_id=merchant_id,
            type=mtype,
            content=content,
            embedding=vector,
            importance=importance,
            confidence=confidence,
            status=status,
            evidence_count=1,
            source=source,
            tags=tags,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.db.add(memory)
        self.db.flush()

        if conflicting is not None:
            self._resolve_conflict(memory, conflicting, conflicting.tags[0])
        self.db.flush()
        return memory

    def _find_conflict(
        self,
        pool: List[MemoryItem],
        tags: List[str],
    ) -> Optional[MemoryItem]:
        slot = tags[0] if tags else None
        slot_value = tags[1] if len(tags) >= 2 else None
        if slot is None or slot_value is None:
            return None
        for item in pool:
            if len(item.tags) < 2:
                continue
            if item.tags[0] == slot and item.tags[1] != slot_value:
                return item
        return None

    def _resolve_conflict(
        self, new_memory: MemoryItem, previous: MemoryItem, reason: str
    ) -> None:
        conflict = MemoryConflict(
            memory_id=new_memory.memory_id,
            previous_memory_id=previous.memory_id,
            reason=f"slot '{reason}' value changed: {previous.content} -> {new_memory.content}",
            resolution="pending",
        )
        self.db.add(conflict)
        if _strength(new_memory) >= _strength(previous):
            previous.status = "superseded"
            new_memory.status = "active"
            conflict.resolution = "newer_wins"
        else:
            new_memory.status = "rejected"
            conflict.resolution = "existing_kept"

    def _can_promote(self, memory: MemoryItem) -> bool:
        return (
            memory.confidence >= self.settings.memory_active_confidence
            or memory.evidence_count >= 2
            and memory.confidence >= self.settings.memory_candidate_confidence
        )

    def promote(self, memory_id: str) -> MemoryItem:
        memory = self.db.get(MemoryItem, memory_id)
        if memory is None:
            raise KeyError(memory_id)
        memory.status = "active"
        self.db.flush()
        return memory

    def extract_from_text(self, merchant_id: str, text: str) -> List[MemoryItem]:
        results = []
        for candidate in extract_memories(text):
            results.append(
                self.ingest_candidate(
                    merchant_id=merchant_id,
                    mtype=candidate["type"],
                    content=candidate["content"],
                    tags=candidate["tags"],
                    importance=candidate["importance"],
                    confidence=candidate["confidence"],
                    source="conversation",
                )
            )
        self.db.commit()
        return results

    def expire_stale(self, reference_time: Optional[datetime] = None) -> int:
        now = reference_time or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self.settings.memory_expiry_days)
        stmt = select(MemoryItem).where(
            MemoryItem.status == "active",
            MemoryItem.last_seen_at < cutoff,
        )
        count = 0
        for memory in self.db.scalars(stmt).all():
            memory.status = "expired"
            count += 1
        self.db.commit()
        return count
