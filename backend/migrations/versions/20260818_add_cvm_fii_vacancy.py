"""add CVM FII official vacancy data (inf_trimestral)

Revision ID: 20260818_cvm_fii_vacancy
Revises: 20260817_investor_profile
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_cvm_fii_vacancy"
down_revision = "20260817_investor_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fii_issuers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("official_name", sa.String(250), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cnpj"),
    )
    op.create_index("ix_fii_issuers_cnpj", "fii_issuers", ["cnpj"])
    op.create_table(
        "asset_fii_issuers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["issuer_id"], ["fii_issuers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
    )
    op.create_index("ix_asset_fii_issuers_asset_id", "asset_fii_issuers", ["asset_id"])
    op.create_index("ix_asset_fii_issuers_issuer_id", "asset_fii_issuers", ["issuer_id"])
    op.create_table(
        "fii_property_vacancy_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issuer_id", sa.Uuid(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("property_count", sa.Integer(), nullable=False),
        sa.Column("area_weighted_vacancy_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("aggregation_method", sa.Text(), nullable=False),
        sa.Column("source_resource", sa.String(300), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["issuer_id"], ["fii_issuers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issuer_id", "reference_date", name="uq_fii_vacancy_issuer_reference"
        ),
    )
    op.create_index(
        "ix_fii_property_vacancy_documents_issuer_id",
        "fii_property_vacancy_documents",
        ["issuer_id"],
    )
    op.create_index(
        "ix_fii_property_vacancy_documents_reference_date",
        "fii_property_vacancy_documents",
        ["reference_date"],
    )
    op.create_table(
        "fii_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("etag", sa.String(200), nullable=True),
        sa.Column("last_modified", sa.String(200), nullable=True),
        sa.Column("documents_imported", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fii_sync_runs_document_type", "fii_sync_runs", ["document_type"])
    op.create_index("ix_fii_sync_runs_year", "fii_sync_runs", ["year"])
    op.create_index("ix_fii_sync_runs_status", "fii_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_table("fii_sync_runs")
    op.drop_table("fii_property_vacancy_documents")
    op.drop_table("asset_fii_issuers")
    op.drop_table("fii_issuers")
