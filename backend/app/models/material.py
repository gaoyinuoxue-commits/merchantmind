from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.enums import MaterialStatus, MaterialType


class Material(TimestampMixin, Base):
    __tablename__ = "material"

    material_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("campaign.campaign_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    merchant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("merchant.merchant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_type: Mapped[MaterialType] = mapped_column(String(32), nullable=False)
    material_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[MaterialStatus] = mapped_column(String(32), nullable=False, index=True)
