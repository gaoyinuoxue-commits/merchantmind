from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EvalRun(Base):
    """One offline evaluation batch over the ground-truth case set."""

    __tablename__ = "eval_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    judge: Mapped[str] = mapped_column(String(16), nullable=False, default="rule")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    label: Mapped[str] = mapped_column(String(16), nullable=False, default="SYNTHETIC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cases: Mapped[List["EvalCaseResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="EvalCaseResult.id"
    )


class EvalCaseResult(Base):
    """Per-case verdict of an evaluation run."""

    __tablename__ = "eval_case_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_type: Mapped[str] = mapped_column(String(24), nullable=False)
    merchant_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prediction: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    trace_id: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    judge_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    human_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    human_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    judged_by: Mapped[str] = mapped_column(String(32), nullable=False, default="rule")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["EvalRun"] = relationship(back_populates="cases")
