from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.enums import BusinessStage, Industry


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchant"

    merchant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_name: Mapped[str] = mapped_column(String(128), nullable=False)
    industry: Mapped[Industry] = mapped_column(String(32), nullable=False, index=True)
    sub_industry: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    business_stage: Mapped[BusinessStage] = mapped_column(String(32), nullable=False)
    gmv_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    industries: Mapped[List["MerchantIndustry"]] = relationship(
        back_populates="merchant",
        cascade="all, delete-orphan",
    )


class MerchantIndustry(Base):
    """Industry tags and industry membership of a merchant."""

    __tablename__ = "merchant_industry"
    __table_args__ = (
        UniqueConstraint(
            "merchant_id",
            "industry",
            "sub_industry",
            name="uq_merchant_industry_tag",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    merchant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("merchant.merchant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    industry: Mapped[Industry] = mapped_column(String(32), nullable=False)
    sub_industry: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    merchant: Mapped["Merchant"] = relationship(back_populates="industries")
