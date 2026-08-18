from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FiiIssuer(Base):
    """Fundo/classe FII identificado pelo CNPJ oficial (CNPJ_Fundo_Classe
    da CVM) -- entidade distinta de CvmIssuer (companhias abertas), já que
    FIIs e companhias abertas são universos de registro separados na CVM.
    """

    __tablename__ = "fii_issuers"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    cnpj: Mapped[str] = mapped_column(
        String(14), nullable=False, unique=True, index=True
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


class AssetFiiIssuer(Base):
    __tablename__ = "asset_fii_issuers"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"), nullable=False, unique=True, index=True
    )
    issuer_id: Mapped[UUID] = mapped_column(
        ForeignKey("fii_issuers.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    asset = relationship("Asset")
    issuer = relationship("FiiIssuer")


class FiiPropertyVacancyDocument(Base):
    """Vacância física agregada de um fundo, por trimestre, derivada do
    Informe Trimestral Estruturado da CVM (ANEXO 39-II da Instrução CVM
    571/2015), tabela `imovel` (campo oficial Percentual_Vacancia por
    imóvel). Não é um campo oficial único -- é uma MÉDIA PONDERADA PELA
    ÁREA sobre os imóveis reportados no período, método explicitado em
    `aggregation_method` e nunca escondido do consumidor do dado.

    Mantém apenas a versão mais recente (Versao) por (issuer, reference)
    -- reapresentações substituem, nunca somam.
    """

    __tablename__ = "fii_property_vacancy_documents"
    __table_args__ = (
        UniqueConstraint(
            "issuer_id", "reference_date", name="uq_fii_vacancy_issuer_reference"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    issuer_id: Mapped[UUID] = mapped_column(
        ForeignKey("fii_issuers.id"), nullable=False, index=True
    )
    reference_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    property_count: Mapped[int] = mapped_column(Integer, nullable=False)
    area_weighted_vacancy_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False
    )
    aggregation_method: Mapped[str] = mapped_column(Text, nullable=False)
    source_resource: Mapped[str] = mapped_column(String(300), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    issuer = relationship("FiiIssuer")


class FiiSyncRun(Base):
    __tablename__ = "fii_sync_runs"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    document_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(200), nullable=True)
    documents_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
