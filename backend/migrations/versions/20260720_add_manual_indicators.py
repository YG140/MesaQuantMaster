"""add user-owned manual indicators

Revision ID: 20260720_manual_indicators
Revises: 20261017_core_schema_bootstrap
"""
from alembic import op
import sqlalchemy as sa

revision = "20260720_manual_indicators"
down_revision = "20261017_core_schema_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_indicators",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("indicator_key", sa.String(60), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_description", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "asset_id", "indicator_key", name="uq_manual_indicator_owner_asset_key"),
    )
    op.create_index("ix_manual_indicators_user_id", "manual_indicators", ["user_id"])
    op.create_index("ix_manual_indicators_asset_id", "manual_indicators", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_manual_indicators_asset_id", table_name="manual_indicators")
    op.drop_index("ix_manual_indicators_user_id", table_name="manual_indicators")
    op.drop_table("manual_indicators")
