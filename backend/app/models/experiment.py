from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Experiment(Base):
    """One A/B experiment: the same case set run under several variant configs."""

    __tablename__ = "experiment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="done")
    case_ids: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    variants: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    results: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    label: Mapped[str] = mapped_column(String(16), nullable=False, default="SYNTHETIC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    runs: Mapped[List["ExperimentVariantRun"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentVariantRun.id"
    )


class ExperimentVariantRun(Base):
    """Metrics of one variant over the experiment case subset."""

    __tablename__ = "experiment_variant_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiment.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_name: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    cases: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    experiment: Mapped["Experiment"] = relationship(back_populates="runs")
