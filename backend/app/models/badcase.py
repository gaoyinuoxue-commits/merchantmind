from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Feedback(Base):
    """User feedback on an agent turn (rating 1-5 / helpful flag)."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(48), ForeignKey("trace_run.trace_id", ondelete="SET NULL"), nullable=True, index=True
    )
    merchant_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Badcase(Base):
    """Failure record auto-classified into Routing/Retrieval/Tool/Reasoning/Hallucination."""

    __tablename__ = "badcase"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="eval")
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(48), ForeignKey("trace_run.trace_id", ondelete="SET NULL"), nullable=True, index=True
    )
    feedback_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("feedback.id", ondelete="SET NULL"), nullable=True, index=True
    )
    eval_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("eval_run.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    merchant_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    error_type: Mapped[str] = mapped_column(String(24), nullable=False)
    affected_module: Mapped[str] = mapped_column(String(64), nullable=False)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="medium")
    reporter: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
