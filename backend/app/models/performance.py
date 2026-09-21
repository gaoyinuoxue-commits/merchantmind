from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PerformanceDaily(Base):
    """Daily business performance snapshot for one merchant."""

    __tablename__ = "performance_daily"
    __table_args__ = (
        UniqueConstraint("merchant_id", "date", name="merchant_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("merchant.merchant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    gmv: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ad_spend: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cvr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aov: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
