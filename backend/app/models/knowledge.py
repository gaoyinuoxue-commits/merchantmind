from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.config.settings import get_settings
from app.db.session import Base
from app.models.base import TimestampMixin

EMBEDDING_DIM = get_settings().embedding_dim
DEEP_EMBEDDING_DIM = 512


class KnowledgeItem(TimestampMixin, Base):
    """Versioned industry knowledge (RAG corpus). Merchant-agnostic by design."""

    __tablename__ = "knowledge_item"
    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_knowledge_slug_version"),
        Index(
            "ix_knowledge_item_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_knowledge_item_embedding_deep_hnsw",
            "embedding_deep",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_deep": "vector_cosine_ops"},
        ),
    )

    knowledge_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_deep: Mapped[Optional[List[float]]] = mapped_column(
        Vector(DEEP_EMBEDDING_DIM), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate", index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="curated")
    merchant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
