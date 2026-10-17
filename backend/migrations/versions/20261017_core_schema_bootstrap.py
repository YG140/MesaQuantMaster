"""Bootstrap legacy ORM core tables before migrations that reference assets.

Revision ID: 20261017_core_schema_bootstrap
Revises: 20260717_add_portfolio_policy

Legacy local installs relied on Base.metadata.create_all() at API import,
which cannot help an initially empty cloud Postgres: Alembic executes
first and manual_indicators/cvm references to assets fail. Install the four
unversioned core tables before manual_indicators without touching user data.

This additive revision runs after 20260717_add_portfolio_policy so existing
Neon instances that stopped there can resume with `alembic upgrade head`.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261017_core_schema_bootstrap"
down_revision = "20260717_add_portfolio_policy"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # Keep this migration self-contained; ORM metadata may evolve later.
    # Do not recreate or discard legacy tables already present.
    if not _has_table("assets"):
        op.create_table(
            "assets",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("ticker", sa.String(20), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("asset_type", sa.String(50), nullable=False),
            sa.Column("sector", sa.String(100), nullable=True),
            sa.Column("country", sa.String(100), nullable=True),
            sa.Column("currency", sa.String(10), nullable=False),
            sa.Column("exchange", sa.String(50), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_assets_ticker", "assets", ["ticker"], unique=True)
        op.create_index("ix_assets_asset_type", "assets", ["asset_type"])

    if not _has_table("operations"):
        op.create_table(
            "operations",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("asset_id", sa.Uuid(), nullable=False),
            sa.Column("brokerage_id", sa.Uuid(), nullable=True),
            sa.Column("operation_type", sa.String(30), nullable=False),
            sa.Column("operation_date", sa.Date(), nullable=False),
            sa.Column("quantity", sa.Numeric(18, 8), nullable=False),
            sa.Column("unit_price", sa.Numeric(18, 8), nullable=False),
            sa.Column("fees", sa.Numeric(18, 2), nullable=False),
            sa.Column("taxes", sa.Numeric(18, 2), nullable=False),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("source", sa.String(50), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
            sa.ForeignKeyConstraint(["brokerage_id"], ["brokerages.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for key in ("user_id", "asset_id", "brokerage_id", "operation_type"):
            op.create_index(f"ix_operations_{key}", "operations", [key])

    if not _has_table("watchlists"):
        op.create_table(
            "watchlists",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("asset_id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "asset_id", name="uq_watchlist_user_asset"),
        )
        op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])
        op.create_index("ix_watchlists_asset_id", "watchlists", ["asset_id"])

    if not _has_table("alerts"):
        op.create_table(
            "alerts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("asset_id", sa.Uuid(), nullable=False),
            sa.Column("alert_type", sa.String(50), nullable=False),
            sa.Column("target_value", sa.Numeric(18, 8), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("triggered", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for key in ("user_id", "asset_id", "alert_type"):
            op.create_index(f"ix_alerts_{key}", "alerts", [key])


def downgrade() -> None:
    # These tables may predate Alembic in existing installs and contain
    # actual portfolio data. Deliberately never drop them during rollback.
    pass
