"""create alerts table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "create_alerts_table"
down_revision = "<SUA_REVISION_ANTERIOR>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id"),
            nullable=False,
        ),
        sa.Column(
            "alert_type",
            sa.String(50),
            nullable=False,
        ),
        sa.Column(
            "target_value",
            sa.Numeric(18, 8),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "triggered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_alerts_user_id",
        "alerts",
        ["user_id"],
    )

    op.create_index(
        "ix_alerts_asset_id",
        "alerts",
        ["asset_id"],
    )

    op.create_index(
        "ix_alerts_alert_type",
        "alerts",
        ["alert_type"],
    )


def downgrade():
    op.drop_table("alerts")