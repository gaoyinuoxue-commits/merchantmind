from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ToolCallLog(Base):
    """Audit record for every agent tool invocation."""

    __tablename__ = "tool_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    merchant_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(48), nullable=True, index=True)
    arguments: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result_summary: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
