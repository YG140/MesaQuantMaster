"""add brokerages and operation metadata

Revision ID: 20260716_add_brokerages_operation_metadata
Revises: 20260711_expand_alembic_version
Create Date: 2026-07-16 13:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "20260716_add_brokerages_operation_metadata"
down_revision: str | Sequence[str] | None = "20260711_expand_alembic_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "brokerages"):
        op.create_table(
            "brokerages",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_brokerages_user_name"),
        )
        inspector = inspect(bind)

    if not _has_index(inspector, "brokerages", "ix_brokerages_user_id"):
        op.create_index("ix_brokerages_user_id", "brokerages", ["user_id"])
        inspector = inspect(bind)

    if _has_table(inspector, "operations"):
        if not _has_column(inspector, "operations", "brokerage_id"):
            op.add_column(
                "operations",
                sa.Column("brokerage_id", sa.UUID(), nullable=True),
            )
            inspector = inspect(bind)

        if not _has_column(inspector, "operations", "source"):
            op.add_column(
                "operations",
                sa.Column("source", sa.String(length=50), nullable=True),
            )
            inspector = inspect(bind)

        if not _has_index(inspector, "operations", "ix_operations_brokerage_id"):
            op.create_index(
                "ix_operations_brokerage_id",
                "operations",
                ["brokerage_id"],
            )
            inspector = inspect(bind)

        if (
            bind.dialect.name != "sqlite"
            and not _has_foreign_key(
                inspector,
                "operations",
                "fk_operations_brokerage_id_brokerages",
            )
        ):
            op.create_foreign_key(
                "fk_operations_brokerage_id_brokerages",
                "operations",
                "brokerages",
                ["brokerage_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "operations"):
        if bind.dialect.name != "sqlite" and _has_foreign_key(
            inspector,
            "operations",
            "fk_operations_brokerage_id_brokerages",
        ):
            op.drop_constraint(
                "fk_operations_brokerage_id_brokerages",
                "operations",
                type_="foreignkey",
            )
            inspector = inspect(bind)

        if _has_index(inspector, "operations", "ix_operations_brokerage_id"):
            op.drop_index("ix_operations_brokerage_id", table_name="operations")
            inspector = inspect(bind)

        if _has_column(inspector, "operations", "source"):
            op.drop_column("operations", "source")
            inspector = inspect(bind)

        if _has_column(inspector, "operations", "brokerage_id"):
            op.drop_column("operations", "brokerage_id")
            inspector = inspect(bind)

    if _has_table(inspector, "brokerages"):
        if _has_index(inspector, "brokerages", "ix_brokerages_user_id"):
            op.drop_index("ix_brokerages_user_id", table_name="brokerages")
        op.drop_table("brokerages")


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _has_foreign_key(inspector, table_name: str, constraint_name: str) -> bool:
    return constraint_name in {
        foreign_key["name"] for foreign_key in inspector.get_foreign_keys(table_name)
    }
