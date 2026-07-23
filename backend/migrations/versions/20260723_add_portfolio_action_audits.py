"""add portfolio action audits

Revision ID: 20260723_portfolio_audits
Revises: 20260721_cvm_financial
"""

from alembic import op
import sqlalchemy as sa

revision = "20260723_portfolio_audits"
down_revision = "20260721_cvm_financial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_action_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("operation_count", sa.Integer(), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_portfolio_action_audits_user_id", "portfolio_action_audits", ["user_id"])
    op.create_index("ix_portfolio_action_audits_asset_id", "portfolio_action_audits", ["asset_id"])
    op.create_index("ix_portfolio_action_audits_action", "portfolio_action_audits", ["action"])


def downgrade() -> None:
    op.drop_table("portfolio_action_audits")
