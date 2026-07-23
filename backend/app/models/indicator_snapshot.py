from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    symbol: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(40), nullable=False)
    indicator_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="provider"
    )
    reference_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    provenance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
