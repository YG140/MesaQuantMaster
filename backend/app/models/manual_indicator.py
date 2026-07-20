from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ManualIndicator(Base):
    __tablename__ = "manual_indicators"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "asset_id",
            "indicator_key",
            name="uq_manual_indicator_owner_asset_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"), nullable=False, index=True
    )
    indicator_key: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual"
    )
    source_description: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    asset = relationship("Asset")
    user = relationship("User")
