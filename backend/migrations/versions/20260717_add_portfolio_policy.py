"""add portfolio policy

Revision ID: 20260717_add_portfolio_policy
Revises: 20260716_add_brokerages_operation_metadata
Create Date: 2026-07-17 21:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "20260717_add_portfolio_policy"
down_revision: str | Sequence[str] | None = "20260716_add_brokerages_operation_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "portfolio_policies"):
        op.create_table(
            "portfolio_policies",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("objective", sa.String(length=80), nullable=False),
            sa.Column("risk_profile", sa.String(length=40), nullable=False),
            sa.Column("investment_horizon", sa.String(length=40), nullable=False),
            sa.Column("monthly_contribution", sa.Numeric(18, 2), nullable=False),
            sa.Column("liquidity_need", sa.String(length=40), nullable=False),
            sa.Column("income_need", sa.Boolean(), nullable=False),
            sa.Column("emergency_reserve_months", sa.Integer(), nullable=False),
            sa.Column("maximum_weight_per_asset", sa.Numeric(8, 2), nullable=False),
            sa.Column("maximum_weight_per_sector", sa.Numeric(8, 2), nullable=False),
            sa.Column("maximum_weight_per_issuer", sa.Numeric(8, 2), nullable=False),
            sa.Column("rebalance_tolerance", sa.Numeric(8, 2), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_portfolio_policies_user_id"),
        )
        inspector = inspect(bind)

    if not _has_index(inspector, "portfolio_policies", "ix_portfolio_policies_user_id"):
        op.create_index(
            "ix_portfolio_policies_user_id",
            "portfolio_policies",
            ["user_id"],
        )
        inspector = inspect(bind)

    if not _has_table(inspector, "portfolio_policy_allocations"):
        op.create_table(
            "portfolio_policy_allocations",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("policy_id", sa.UUID(), nullable=False),
            sa.Column("asset_class", sa.String(length=80), nullable=False),
            sa.Column("target_percentage", sa.Numeric(8, 2), nullable=False),
            sa.Column("minimum_percentage", sa.Numeric(8, 2), nullable=False),
            sa.Column("maximum_percentage", sa.Numeric(8, 2), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(
                ["policy_id"],
                ["portfolio_policies.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "policy_id",
                "asset_class",
                name="uq_portfolio_policy_allocations_policy_class",
            ),
        )
        inspector = inspect(bind)

    if not _has_index(
        inspector,
        "portfolio_policy_allocations",
        "ix_portfolio_policy_allocations_policy_id",
    ):
        op.create_index(
            "ix_portfolio_policy_allocations_policy_id",
            "portfolio_policy_allocations",
            ["policy_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "portfolio_policy_allocations"):
        if _has_index(
            inspector,
            "portfolio_policy_allocations",
            "ix_portfolio_policy_allocations_policy_id",
        ):
            op.drop_index(
                "ix_portfolio_policy_allocations_policy_id",
                table_name="portfolio_policy_allocations",
            )
        op.drop_table("portfolio_policy_allocations")
        inspector = inspect(bind)

    if _has_table(inspector, "portfolio_policies"):
        if _has_index(inspector, "portfolio_policies", "ix_portfolio_policies_user_id"):
            op.drop_index("ix_portfolio_policies_user_id", table_name="portfolio_policies")
        op.drop_table("portfolio_policies")


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}
