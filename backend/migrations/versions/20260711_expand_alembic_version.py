"""expand the Alembic version column

Revision ID: 20260711_expand_alembic_version
Revises: 17f115172169
"""

from alembic import op
import sqlalchemy as sa


revision = "20260711_expand_alembic_version"
down_revision = "17f115172169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=128),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
