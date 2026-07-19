from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PortfolioPolicy(Base):
    __tablename__ = "portfolio_policies"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_portfolio_policies_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    objective: Mapped[str] = mapped_column(String(80), nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(40), nullable=False)
    investment_horizon: Mapped[str] = mapped_column(String(40), nullable=False)
    monthly_contribution: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    liquidity_need: Mapped[str] = mapped_column(String(40), nullable=False)
    income_need: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_reserve_months: Mapped[int] = mapped_column(nullable=False, default=6)
    maximum_weight_per_asset: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False
    )
    maximum_weight_per_sector: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False
    )
    maximum_weight_per_issuer: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False
    )
    rebalance_tolerance: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
    allocations = relationship(
        "PortfolioPolicyAllocation",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PortfolioPolicyAllocation.asset_class",
    )


class PortfolioPolicyAllocation(Base):
    __tablename__ = "portfolio_policy_allocations"
    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            "asset_class",
            name="uq_portfolio_policy_allocations_policy_class",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_class: Mapped[str] = mapped_column(String(80), nullable=False)
    target_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    minimum_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    maximum_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    policy = relationship("PortfolioPolicy", back_populates="allocations")
