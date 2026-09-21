from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.enums import CampaignObjective, CampaignStatus


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaign"

    campaign_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("merchant.merchant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_name: Mapped[str] = mapped_column(String(256), nullable=False)
    objective: Mapped[CampaignObjective] = mapped_column(String(32), nullable=False)
    budget: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(String(32), nullable=False, index=True)
