from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.config.settings import get_settings
from app.db.session import Base
from app.models.base import TimestampMixin

EMBEDDING_DIM = get_settings().embedding_dim


class MemoryItem(TimestampMixin, Base):
    """Merchant-specific long-term memory (kept strictly separate from knowledge)."""

    __tablename__ = "memory_item"
    __table_args__ = (
        Index(
            "ix_memory_item_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    memory_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("merchant.merchant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate", index=True)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="conversation")
    tags: Mapped[List[str]] = mapped_column(
        "tags",
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conflicts: Mapped[List["MemoryConflict"]] = relationship(
        back_populates="memory", cascade="all, delete-orphan"
    )


class MemoryConflict(Base):
    """Conflict record: new memory never silently overwrites the old one."""

    __tablename__ = "memory_conflict"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[str] = mapped_column(
        String(48),
        ForeignKey("memory_item.memory_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_memory_id: Mapped[str] = mapped_column(String(48), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    memory: Mapped["MemoryItem"] = relationship(back_populates="conflicts")
