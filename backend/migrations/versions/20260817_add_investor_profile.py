"""add investor profile

Revision ID: 20260817_investor_profile
Revises: 20260727_email_auth_tokens
"""

from alembic import op
import sqlalchemy as sa

revision = "20260817_investor_profile"
down_revision = "20260727_email_auth_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investor_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("primary_objective", sa.String(length=80), nullable=True),
        sa.Column("secondary_objectives", sa.JSON(), nullable=True),
        sa.Column("horizon", sa.String(length=30), nullable=True),
        sa.Column("initial_contribution", sa.Numeric(18, 2), nullable=True),
        sa.Column("monthly_contribution", sa.Numeric(18, 2), nullable=True),
        sa.Column("contribution_stability", sa.String(length=20), nullable=True),
        sa.Column("income_range", sa.String(length=30), nullable=True),
        sa.Column("investable_net_worth_range", sa.String(length=30), nullable=True),
        sa.Column("emergency_reserve_months", sa.Integer(), nullable=True),
        sa.Column("has_relevant_debt", sa.Boolean(), nullable=True),
        sa.Column("dependents", sa.Integer(), nullable=True),
        sa.Column("liquidity_need", sa.String(length=20), nullable=True),
        sa.Column("income_need", sa.String(length=20), nullable=True),
        sa.Column("allowed_classes", sa.JSON(), nullable=True),
        sa.Column("restricted_classes", sa.JSON(), nullable=True),
        sa.Column("risk_tolerance_score", sa.Integer(), nullable=True),
        sa.Column("risk_capacity_score", sa.Integer(), nullable=True),
        sa.Column("horizon_score", sa.Integer(), nullable=True),
        sa.Column("liquidity_need_score", sa.Integer(), nullable=True),
        sa.Column("income_need_score", sa.Integer(), nullable=True),
        sa.Column("knowledge_score", sa.Integer(), nullable=True),
        sa.Column("emergency_reserve_adequacy_score", sa.Integer(), nullable=True),
        sa.Column("overall_classification", sa.String(length=30), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("dimension_explanations", sa.JSON(), nullable=True),
        sa.Column("policy_preview", sa.JSON(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_investor_profiles_user_id", "investor_profiles", ["user_id"]
    )
    op.create_unique_constraint(
        "uq_investor_profiles_user_id", "investor_profiles", ["user_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_investor_profiles_user_id", "investor_profiles", type_="unique"
    )
    op.drop_index("ix_investor_profiles_user_id", table_name="investor_profiles")
    op.drop_table("investor_profiles")
