"""add brokerages and operation metadata"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260715_add_brokerages"
down_revision = "create_alerts_table"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "brokerages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_brokerages_user_name"),
    )
    op.create_index("ix_brokerages_user_id", "brokerages", ["user_id"])

    op.add_column(
        "operations",
        sa.Column(
            "brokerage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brokerages.id"),
            nullable=True,
        ),
    )
    op.add_column("operations", sa.Column("source", sa.String(length=50), nullable=True))
    op.create_index("ix_operations_brokerage_id", "operations", ["brokerage_id"])


def downgrade():
    op.drop_index("ix_operations_brokerage_id", table_name="operations")
    op.drop_column("operations", "source")
    op.drop_column("operations", "brokerage_id")
    op.drop_index("ix_brokerages_user_id", table_name="brokerages")
    op.drop_table("brokerages")
