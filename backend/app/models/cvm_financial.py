from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CvmIssuer(Base):
    __tablename__ = "cvm_issuers"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    cnpj: Mapped[str] = mapped_column(
        String(14), nullable=False, unique=True, index=True
    )
    cvm_code: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )
    official_name: Mapped[str] = mapped_column(String(250), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AssetCvmIssuer(Base):
    __tablename__ = "asset_cvm_issuers"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"), nullable=False, unique=True, index=True
    )
    issuer_id: Mapped[UUID] = mapped_column(
        ForeignKey("cvm_issuers.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    asset = relationship("Asset")
    issuer = relationship("CvmIssuer")


class CvmFinancialDocument(Base):
    __tablename__ = "cvm_financial_documents"
    __table_args__ = (
        UniqueConstraint(
            "issuer_id",
            "document_type",
            "reference_date",
            "version",
            "statement_type",
            "scope",
            "period_end",
            "period_kind",
            name="uq_cvm_document_identity",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    issuer_id: Mapped[UUID] = mapped_column(
        ForeignKey("cvm_issuers.id"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    version: Mapped[int] = mapped_column(nullable=False)
    statement_type: Mapped[str] = mapped_column(String(10), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    currency: Mapped[str] = mapped_column(String(20), nullable=False)
    scale: Mapped[str] = mapped_column(String(20), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    issuer = relationship("CvmIssuer")


class CvmFinancialAccount(Base):
    __tablename__ = "cvm_financial_accounts"
    __table_args__ = (
        UniqueConstraint("document_id", "account_code", name="uq_cvm_document_account"),
    )
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("cvm_financial_documents.id"), nullable=False, index=True
    )
    account_code: Mapped[str] = mapped_column(String(40), nullable=False)
    account_description: Mapped[str] = mapped_column(String(500), nullable=False)
    original_value: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    normalized_value: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    normalized_key: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    acquisition_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="reported"
    )
    is_fixed_account: Mapped[bool] = mapped_column(nullable=False, default=False)
    document = relationship("CvmFinancialDocument")


class CvmSyncRun(Base):
    __tablename__ = "cvm_sync_runs"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    document_type: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    year: Mapped[int] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(200), nullable=True)
    documents_imported: Mapped[int] = mapped_column(nullable=False, default=0)
    accounts_imported: Mapped[int] = mapped_column(nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
