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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
        index=True,
    )

    brokerage_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("brokerages.id"),
        nullable=True,
        index=True,
    )

    operation_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    operation_date: Mapped[datetime] = mapped_column(
        Date,
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    fees: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
    )

    taxes: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User")
    asset = relationship("Asset")
    brokerage = relationship("Brokerage")
