"""add indicator snapshots

Revision ID: 20260720_indicator_snapshots
Revises: 20260720_manual_indicators
"""
from alembic import op
import sqlalchemy as sa

revision = "20260720_indicator_snapshots"
down_revision = "20260720_manual_indicators"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "indicator_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(60), nullable=False),
        sa.Column("asset_class", sa.String(40), nullable=False),
        sa.Column("indicator_key", sa.String(80), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=True),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("period", sa.String(40), nullable=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("reference_date", sa.DateTime(), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_indicator_snapshots_symbol", "indicator_snapshots", ["symbol"])
    op.create_index("ix_indicator_snapshots_indicator_key", "indicator_snapshots", ["indicator_key"])
    op.create_index("ix_indicator_snapshots_collected_at", "indicator_snapshots", ["collected_at"])
    op.create_index("ix_indicator_snapshots_valid_until", "indicator_snapshots", ["valid_until"])


def downgrade() -> None:
    op.drop_table("indicator_snapshots")
