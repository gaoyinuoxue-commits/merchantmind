from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TraceRun(Base):
    """One end-to-end agent run (a single Observe→Think→Act cycle)."""

    __tablename__ = "trace_run"

    trace_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    merchant_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    primary_cause: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    needs_clarification: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(16), nullable=False, default="SYNTHETIC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    spans: Mapped[List["TraceSpan"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="TraceSpan.span_order",
    )


class TraceSpan(Base):
    """One stage within a run: intent/plan/tool_call/hook/diagnosis/action."""

    __tablename__ = "trace_span"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(
        String(48),
        ForeignKey("trace_run.trace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    span_order: Mapped[int] = mapped_column(Integer, nullable=False)
    span_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["TraceRun"] = relationship(back_populates="spans")
