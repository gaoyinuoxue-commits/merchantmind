from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.enums import BusinessEventType, EventSource


class BusinessEvent(TimestampMixin, Base):
    """Business events that drive the synthetic world and diagnosis."""

    __tablename__ = "business_event"

    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("merchant.merchant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[BusinessEventType] = mapped_column(String(32), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    structured_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    source: Mapped[EventSource] = mapped_column(String(32), nullable=False)
