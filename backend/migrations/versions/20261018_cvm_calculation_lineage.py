"""Persist source-document lineage for isolated CVM quarters.

Revision ID: 20261018_cvm_calculation_lineage
Revises: 20261017_recommendation_history
"""
from alembic import op
import sqlalchemy as sa


revision = "20261018_cvm_calculation_lineage"
down_revision = "20261017_recommendation_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cvm_financial_calculation_lineage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("derived_document_id", sa.Uuid(), nullable=False),
        sa.Column("current_source_document_id", sa.Uuid(), nullable=False),
        sa.Column("previous_source_document_id", sa.Uuid(), nullable=False),
        sa.Column("current_source_version", sa.Integer(), nullable=False),
        sa.Column("previous_source_version", sa.Integer(), nullable=False),
        sa.Column("current_collected_at", sa.DateTime(), nullable=False),
        sa.Column("previous_collected_at", sa.DateTime(), nullable=False),
        sa.Column("selected_method", sa.String(length=10), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("calculation_rule", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["derived_document_id"], ["cvm_financial_documents.id"]
        ),
        sa.ForeignKeyConstraint(
            ["current_source_document_id"], ["cvm_financial_documents.id"]
        ),
        sa.ForeignKeyConstraint(
            ["previous_source_document_id"], ["cvm_financial_documents.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "derived_document_id",
            name="uq_cvm_calculation_lineage_derived_document",
        ),
    )
    op.create_index(
        "ix_cvm_calc_lineage_derived_doc",
        "cvm_financial_calculation_lineage",
        ["derived_document_id"],
    )
    op.create_index(
        "ix_cvm_calc_lineage_current_src_doc",
        "cvm_financial_calculation_lineage",
        ["current_source_document_id"],
    )
    op.create_index(
        "ix_cvm_calc_lineage_previous_src_doc",
        "cvm_financial_calculation_lineage",
        ["previous_source_document_id"],
    )


def downgrade() -> None:
    op.drop_table("cvm_financial_calculation_lineage")
