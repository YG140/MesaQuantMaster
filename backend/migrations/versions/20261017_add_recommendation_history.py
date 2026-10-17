"""Persist append-only recommendations without modifying existing user portfolios.

Revision ID: 20261017_recommendation_history
Revises: 20261017_financial_goal
"""
from alembic import op
import sqlalchemy as sa

revision = "20261017_recommendation_history"
down_revision = "20261017_financial_goal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_recommendation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("engine_version", sa.String(length=80), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("considered_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("record_json", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_portfolio_recommendation_runs_user_created",
        "portfolio_recommendation_runs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    # This table holds immutable user research history. An accidental
    # migration rollback MUST NOT erase these personal records.
    pass
