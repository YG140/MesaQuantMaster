"""Store the user's wealth target separately from the investor risk assessment.

Revision ID: 20261017_financial_goal
Revises: 20260818_cvm_fii_vacancy

Additive, nullable column. Existing portfolios and investor profiles are preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261017_financial_goal"
down_revision = "20260818_cvm_fii_vacancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investor_profiles",
        sa.Column("wealth_goal_amount", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    # Keep financial goals rather than destructively erasing account data
    # during an accidental rollback.
    pass
