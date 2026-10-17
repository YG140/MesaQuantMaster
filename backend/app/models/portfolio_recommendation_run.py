"""Registro append-only de uma montagem de carteira por usuário autenticado.

Guarda apenas decisões financeiras e evidências dos ativos selecionados;
não guarda respostas do questionário, renda, dívidas nem tokens de acesso.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PortfolioRecommendationRun(Base):
    __tablename__ = "portfolio_recommendation_runs"
    __table_args__ = (
        Index("ix_portfolio_recommendation_runs_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_id: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    considered_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record_json: Mapped[str] = mapped_column(Text, nullable=False)
