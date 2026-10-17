from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class InvestorProfile(Base):
    """Perfil do investidor: representação persistente e explicável do usuário,
    separada da PortfolioPolicy (que representa a política operacional
    derivada). Vínculo 1:1 com users, mesmo padrão de portfolio_policies."""

    __tablename__ = "investor_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_investor_profiles_user_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- Fatos estruturais coletados no questionário -----------------------
    primary_objective: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secondary_objectives: Mapped[list | None] = mapped_column(JSON, nullable=True)
    horizon: Mapped[str | None] = mapped_column(String(30), nullable=True)
    initial_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    monthly_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    wealth_goal_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    contribution_stability: Mapped[str | None] = mapped_column(String(20), nullable=True)
    income_range: Mapped[str | None] = mapped_column(String(30), nullable=True)
    investable_net_worth_range: Mapped[str | None] = mapped_column(String(30), nullable=True)
    emergency_reserve_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_relevant_debt: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dependents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    liquidity_need: Mapped[str | None] = mapped_column(String(20), nullable=True)
    income_need: Mapped[str | None] = mapped_column(String(20), nullable=True)
    allowed_classes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    restricted_classes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- Dimensões calculadas (escala 0..100), determinísticas -------------
    risk_tolerance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_capacity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    horizon_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    liquidity_need_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    income_need_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    knowledge_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    emergency_reserve_adequacy_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_classification: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # --- Dados brutos normalizados (JSON, minimizado) -----------------------
    # `answers` guarda somente as respostas estruturadas por seção (nunca texto
    # livre arbitrário); `dimension_explanations` guarda o traço
    # regra->dimensão->resultado usado para explicar a classificação;
    # `policy_preview` guarda a última política derivada calculada, para a
    # tela de revisão não recalcular (e possivelmente divergir) do que foi
    # efetivamente mostrado ao usuário antes da confirmação.
    answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dimension_explanations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    policy_preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
