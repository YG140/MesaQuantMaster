"""add CVM DFP and ITR financial import

Revision ID: 20260721_cvm_financial
Revises: 20260720_indicator_snapshots
"""
from alembic import op
import sqlalchemy as sa

revision = "20260721_cvm_financial"
down_revision = "20260720_indicator_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("indicator_snapshots", sa.Column("provenance_json", sa.Text(), nullable=True))
    op.create_table(
        "cvm_issuers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("cvm_code", sa.String(20), nullable=False),
        sa.Column("official_name", sa.String(250), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cnpj"),
        sa.UniqueConstraint("cvm_code"),
    )
    op.create_index("ix_cvm_issuers_cnpj", "cvm_issuers", ["cnpj"])
    op.create_index("ix_cvm_issuers_cvm_code", "cvm_issuers", ["cvm_code"])
    op.create_table(
        "asset_cvm_issuers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("issuer_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["issuer_id"], ["cvm_issuers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
    )
    op.create_index("ix_asset_cvm_issuers_asset_id", "asset_cvm_issuers", ["asset_id"])
    op.create_index("ix_asset_cvm_issuers_issuer_id", "asset_cvm_issuers", ["issuer_id"])
    op.create_table(
        "cvm_financial_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issuer_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(3), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("statement_type", sa.String(10), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_kind", sa.String(30), nullable=False),
        sa.Column("currency", sa.String(20), nullable=False),
        sa.Column("scale", sa.String(20), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["issuer_id"], ["cvm_issuers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer_id", "document_type", "reference_date", "version", "statement_type", "scope", "period_end", "period_kind", name="uq_cvm_document_identity"),
    )
    op.create_index("ix_cvm_financial_documents_issuer_id", "cvm_financial_documents", ["issuer_id"])
    op.create_index("ix_cvm_financial_documents_reference_date", "cvm_financial_documents", ["reference_date"])
    op.create_index("ix_cvm_financial_documents_document_type", "cvm_financial_documents", ["document_type"])
    op.create_table(
        "cvm_financial_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("account_code", sa.String(40), nullable=False),
        sa.Column("account_description", sa.String(500), nullable=False),
        sa.Column("original_value", sa.Numeric(28, 8), nullable=False),
        sa.Column("normalized_value", sa.Numeric(28, 8), nullable=False),
        sa.Column("normalized_key", sa.String(80), nullable=True),
        sa.Column("acquisition_method", sa.String(20), nullable=False),
        sa.Column("is_fixed_account", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["cvm_financial_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "account_code", name="uq_cvm_document_account"),
    )
    op.create_index("ix_cvm_financial_accounts_document_id", "cvm_financial_accounts", ["document_id"])
    op.create_index("ix_cvm_financial_accounts_normalized_key", "cvm_financial_accounts", ["normalized_key"])
    op.create_table(
        "cvm_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(3), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("etag", sa.String(200), nullable=True),
        sa.Column("last_modified", sa.String(200), nullable=True),
        sa.Column("documents_imported", sa.Integer(), nullable=False),
        sa.Column("accounts_imported", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cvm_sync_runs_document_type", "cvm_sync_runs", ["document_type"])
    op.create_index("ix_cvm_sync_runs_year", "cvm_sync_runs", ["year"])
    op.create_index("ix_cvm_sync_runs_status", "cvm_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_table("cvm_sync_runs")
    op.drop_table("cvm_financial_accounts")
    op.drop_table("cvm_financial_documents")
    op.drop_table("asset_cvm_issuers")
    op.drop_table("cvm_issuers")
    op.drop_column("indicator_snapshots", "provenance_json")
