from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.cvm_fii import (
    AssetFiiIssuer,
    FiiIssuer,
    FiiPropertyVacancyDocument,
    FiiSyncRun,
)


class CvmFiiRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_issuer(self, cnpj: str, official_name: str) -> FiiIssuer:
        issuer = self.db.query(FiiIssuer).filter(FiiIssuer.cnpj == cnpj).first()
        if issuer is None:
            issuer = FiiIssuer(cnpj=cnpj, official_name=official_name)
            self.db.add(issuer)
            self.db.flush()
        elif official_name and issuer.official_name != official_name:
            issuer.official_name = official_name
        return issuer

    def find_issuer_by_cnpj(self, cnpj: str) -> FiiIssuer | None:
        """Busca um fundo FII por CNPJ exato (somente dígitos) -- nunca por
        correspondência de nome (mesma regra do resolver híbrido corporativo).
        """
        if not cnpj:
            return None
        return self.db.query(FiiIssuer).filter(FiiIssuer.cnpj == cnpj).first()

    def linked_issuer(self, asset_id: UUID) -> FiiIssuer | None:
        link = (
            self.db.query(AssetFiiIssuer)
            .filter(AssetFiiIssuer.asset_id == asset_id)
            .first()
        )
        return link.issuer if link else None

    def find_link(self, asset_id: UUID) -> AssetFiiIssuer | None:
        return (
            self.db.query(AssetFiiIssuer)
            .filter(AssetFiiIssuer.asset_id == asset_id)
            .first()
        )

    def link_asset(self, asset_id: UUID, issuer_id: UUID) -> AssetFiiIssuer:
        """Cria ou atualiza o vínculo ativo<->fundo FII nesta sessão. Nunca
        comita (mesma razão do CvmFinancialRepository.link_asset: quem
        chama decide a fronteira transacional). Usado pelo fluxo manual;
        o auto-link automático usa ensure_asset_link.
        """
        link = (
            self.db.query(AssetFiiIssuer)
            .filter(AssetFiiIssuer.asset_id == asset_id)
            .first()
        )
        if link is None:
            link = AssetFiiIssuer(asset_id=asset_id, issuer_id=issuer_id)
            self.db.add(link)
        else:
            link.issuer_id = issuer_id
        self.db.flush()
        self.db.refresh(link)
        return link

    def ensure_asset_link(self, asset_id: UUID, issuer_id: UUID) -> AssetFiiIssuer | None:
        """Cria o vínculo SOMENTE se ainda não existir nenhum -- nunca
        substitui um vínculo já existente para um fundo DIFERENTE (mesma
        semântica de CvmFinancialRepository.ensure_asset_link). Retorna
        None em caso de conflito de identidade real.
        """
        link = (
            self.db.query(AssetFiiIssuer)
            .filter(AssetFiiIssuer.asset_id == asset_id)
            .first()
        )
        if link is None:
            link = AssetFiiIssuer(asset_id=asset_id, issuer_id=issuer_id)
            self.db.add(link)
            self.db.flush()
            self.db.refresh(link)
            return link
        if link.issuer_id == issuer_id:
            return link
        return None

    def upsert_vacancy_document(
        self,
        issuer_id: UUID,
        *,
        reference_date: date,
        version: int,
        property_count: int,
        area_weighted_vacancy_rate: Decimal,
        aggregation_method: str,
        source_resource: str,
        collected_at: datetime,
    ) -> FiiPropertyVacancyDocument:
        """Cria ou substitui (reapresentação: versão mais recente vence,
        nunca soma) o documento agregado de vacância de um fundo em um
        trimestre de referência."""
        document = (
            self.db.query(FiiPropertyVacancyDocument)
            .filter(
                FiiPropertyVacancyDocument.issuer_id == issuer_id,
                FiiPropertyVacancyDocument.reference_date == reference_date,
            )
            .first()
        )
        if document is not None and document.version >= version:
            return document
        if document is None:
            document = FiiPropertyVacancyDocument(
                issuer_id=issuer_id, reference_date=reference_date
            )
            self.db.add(document)
        document.version = version
        document.property_count = property_count
        document.area_weighted_vacancy_rate = area_weighted_vacancy_rate
        document.aggregation_method = aggregation_method
        document.source_resource = source_resource
        document.collected_at = collected_at
        self.db.flush()
        self.db.refresh(document)
        return document

    def latest_vacancy_document(self, issuer_id: UUID) -> FiiPropertyVacancyDocument | None:
        return (
            self.db.query(FiiPropertyVacancyDocument)
            .filter(FiiPropertyVacancyDocument.issuer_id == issuer_id)
            .order_by(FiiPropertyVacancyDocument.reference_date.desc())
            .first()
        )

    def start_run(self, document_type: str, year: int) -> FiiSyncRun:
        run = FiiSyncRun(document_type=document_type, year=year, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_run(self, run: FiiSyncRun, *, documents: int) -> None:
        run.status = "completed"
        run.documents_imported = documents
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def fail_run(self, run: FiiSyncRun, message: str) -> None:
        self.db.rollback()
        run = self.db.merge(run)
        run.status = "failed"
        run.error_message = message[:500]
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()
