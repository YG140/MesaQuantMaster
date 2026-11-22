from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.cvm_financial import (
    AssetCvmIssuer,
    CvmFinancialAccount,
    CvmFinancialDocument,
    CvmFinancialCalculationLineage,
    CvmIssuer,
    CvmSyncRun,
)


class CvmFinancialRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_issuer(self, cnpj: str, cvm_code: str, official_name: str) -> CvmIssuer:
        issuer = self.db.query(CvmIssuer).filter(CvmIssuer.cnpj == cnpj).first()
        if issuer is None:
            issuer = CvmIssuer(
                cnpj=cnpj, cvm_code=cvm_code, official_name=official_name
            )
            self.db.add(issuer)
            self.db.flush()
        else:
            issuer.cvm_code = cvm_code
            issuer.official_name = official_name
        return issuer

    def upsert_document(self, issuer_id, account) -> CvmFinancialDocument:
        document = (
            self.db.query(CvmFinancialDocument)
            .filter(
                CvmFinancialDocument.issuer_id == issuer_id,
                CvmFinancialDocument.document_type == account.document_type,
                CvmFinancialDocument.reference_date == account.reference_date,
                CvmFinancialDocument.version == account.version,
                CvmFinancialDocument.statement_type == account.statement_type,
                CvmFinancialDocument.scope == account.scope,
                CvmFinancialDocument.period_end == account.period_end,
                CvmFinancialDocument.period_kind == account.period_kind,
            )
            .first()
        )
        if document is None:
            document = CvmFinancialDocument(
                issuer_id=issuer_id,
                document_type=account.document_type,
                reference_date=account.reference_date,
                version=account.version,
                statement_type=account.statement_type,
                scope=account.scope,
                period_start=account.period_start,
                period_end=account.period_end,
                period_kind=account.period_kind,
                currency=account.currency,
                scale=account.scale,
                collected_at=account.collected_at,
            )
            self.db.add(document)
            self.db.flush()
        return document

    def upsert_account(
        self,
        document_id,
        account,
        normalized_key: str | None,
        acquisition_method: str = "reported",
    ) -> bool:
        row = (
            self.db.query(CvmFinancialAccount)
            .filter(
                CvmFinancialAccount.document_id == document_id,
                CvmFinancialAccount.account_code == account.account_code,
            )
            .first()
        )
        created = row is None
        if row is None:
            row = CvmFinancialAccount(
                document_id=document_id, account_code=account.account_code
            )
            self.db.add(row)
        row.account_description = account.account_description
        row.original_value = account.original_value
        row.normalized_value = account.normalized_value
        row.normalized_key = normalized_key
        row.acquisition_method = acquisition_method
        row.is_fixed_account = account.is_fixed_account
        return created

    def upsert_calculation_lineage(
        self,
        derived_document: CvmFinancialDocument,
        current_source_document: CvmFinancialDocument,
        previous_source_document: CvmFinancialDocument,
    ) -> CvmFinancialCalculationLineage:
        """Persiste, de forma idempotente, a origem de um trimestre isolado."""
        lineage = (
            self.db.query(CvmFinancialCalculationLineage)
            .filter(
                CvmFinancialCalculationLineage.derived_document_id
                == derived_document.id
            )
            .first()
        )
        if lineage is None:
            lineage = CvmFinancialCalculationLineage(
                derived_document_id=derived_document.id,
            )
            self.db.add(lineage)
        lineage.current_source_document_id = current_source_document.id
        lineage.previous_source_document_id = previous_source_document.id
        lineage.current_source_version = current_source_document.version
        lineage.previous_source_version = previous_source_document.version
        lineage.current_collected_at = current_source_document.collected_at
        lineage.previous_collected_at = previous_source_document.collected_at
        lineage.selected_method = current_source_document.statement_type
        lineage.scope = current_source_document.scope
        lineage.calculation_rule = "ITR_YTD_CURRENT_MINUS_PREVIOUS_3M"
        self.db.flush()
        return lineage

    def linked_issuer(self, asset_id: UUID) -> CvmIssuer | None:
        link = (
            self.db.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset_id)
            .first()
        )
        return link.issuer if link else None

    def find_link(self, asset_id: UUID) -> AssetCvmIssuer | None:
        """Vínculo bruto ativo<->emissor (sem seguir o relacionamento até o
        CvmIssuer) — usado onde só o próprio `issuer_id` da linha importa,
        nunca os dados do emissor (ver IndicatorResolverService._resolve_
        concurrent_link_race: comparar o FK bruto evita depender de um
        lazy-load extra do CvmIssuer relacionado).
        """
        return (
            self.db.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset_id)
            .first()
        )

    def ensure_asset_link(self, asset_id: UUID, issuer_id: UUID) -> AssetCvmIssuer | None:
        """Cria o vínculo SOMENTE se ainda não existir nenhum -- nunca
        substitui um vínculo já existente para um issuer DIFERENTE (ao
        contrário de link_asset, que é create-or-update e serve ao fluxo
        MANUAL do superusuário, onde trocar o emissor é uma ação
        explicitamente autorizada). Usado pelo auto-link automático, onde
        sobrescrever silenciosamente a identidade de um emissor já
        vinculado seria uma corrupção de dados, nunca uma correção
        legítima.

        Retorna o AssetCvmIssuer quando o resultado é COMPATÍVEL com
        issuer_id: ou não havia vínculo nenhum e foi criado agora, ou já
        havia vínculo para o MESMO issuer_id (nada é alterado -- sem
        UPDATE desnecessário, idempotência real). Retorna None quando já
        existe um vínculo para um issuer_id DIFERENTE -- um conflito real
        que o chamador nunca deve resolver sobrescrevendo.
        """
        link = (
            self.db.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset_id)
            .first()
        )
        if link is None:
            link = AssetCvmIssuer(asset_id=asset_id, issuer_id=issuer_id)
            self.db.add(link)
            self.db.flush()
            self.db.refresh(link)
            return link
        if link.issuer_id == issuer_id:
            return link
        return None

    def find_issuer_by_cnpj(self, cnpj: str) -> CvmIssuer | None:
        """Busca um emissor CVM por CNPJ exato (somente dígitos).

        Usado para vinculação automática ativo<->emissor por identificador
        oficial — nunca por correspondência de nome (ver seção 7 do resolver
        híbrido: CNPJ exato é a prioridade determinística máxima).
        """
        if not cnpj:
            return None
        return self.db.query(CvmIssuer).filter(CvmIssuer.cnpj == cnpj).first()

    def link_asset(self, asset_id: UUID, issuer_id: UUID) -> AssetCvmIssuer:
        """Cria ou atualiza o vínculo ativo<->emissor CVM nesta sessão.

        Nunca comita: este método é usado tanto por um fluxo de escrita
        explícita (CvmFinancialService.link_asset, que decide seu próprio
        limite de transação) quanto por um fluxo automático embutido em uma
        resolução maior de indicadores (IndicatorResolverService), que usa
        uma sessão isolada própria exatamente para nunca comitar trabalho
        pendente alheio na sessão de resolução. Um repository não deve
        decidir a fronteira transacional de quem o chama — apenas garante
        que o vínculo fique visível (via flush) dentro da própria sessão.
        """
        link = (
            self.db.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset_id)
            .first()
        )
        if link is None:
            link = AssetCvmIssuer(asset_id=asset_id, issuer_id=issuer_id)
            self.db.add(link)
        else:
            link.issuer_id = issuer_id
        self.db.flush()
        self.db.refresh(link)
        return link

    def get_issuer(self, issuer_id: UUID) -> CvmIssuer | None:
        return self.db.get(CvmIssuer, issuer_id)

    def fiscal_year_end(self, issuer_id: UUID) -> date | None:
        """Encerramento do exercício social deste emissor, OBSERVADO nos
        próprios dados — nunca assumido como 31/12 para todo mundo.

        Uma DFP cobre sempre o exercício social completo, então seu
        period_end É o encerramento do exercício por definição regulatória
        (não é uma inferência). Usa a DFP consolidada mais recente
        disponível; retorna None se o emissor ainda não tiver nenhuma DFP
        sincronizada (ex.: apenas ITR disponível) — o chamador deve tratar
        isso como calendário fiscal desconhecido, nunca adivinhar.
        """
        document = (
            self.db.query(CvmFinancialDocument)
            .filter(
                CvmFinancialDocument.issuer_id == issuer_id,
                CvmFinancialDocument.document_type == "DFP",
                CvmFinancialDocument.scope == "consolidated",
            )
            .order_by(
                CvmFinancialDocument.reference_date.desc(),
                CvmFinancialDocument.version.desc(),
            )
            .first()
        )
        return document.period_end if document is not None else None

    def list_issuers(self, limit: int = 100) -> list[CvmIssuer]:
        return (
            self.db.query(CvmIssuer)
            .order_by(CvmIssuer.official_name)
            .limit(limit)
            .all()
        )

    def latest_normalized(self, asset_id: UUID) -> list[tuple]:
        issuer = self.linked_issuer(asset_id)
        if issuer is None:
            return []
        rows = (
            self.db.query(CvmFinancialAccount, CvmFinancialDocument)
            .join(
                CvmFinancialDocument,
                CvmFinancialAccount.document_id == CvmFinancialDocument.id,
            )
            .filter(
                CvmFinancialDocument.issuer_id == issuer.id,
                CvmFinancialDocument.scope == "consolidated",
                CvmFinancialAccount.normalized_key.is_not(None),
            )
            .order_by(
                CvmFinancialDocument.reference_date.desc(),
                CvmFinancialDocument.version.desc(),
            )
            .all()
        )
        period_priority = {
            "quarterly_calculated": 4,
            "quarterly_reported": 3,
            "year_to_date": 2,
            "annual": 1,
            "point_in_time": 1,
        }
        latest_markers = {}
        for account, document in rows:
            marker = (
                document.reference_date,
                document.version,
                period_priority.get(document.period_kind, 0),
            )
            latest_markers[account.normalized_key] = max(
                marker, latest_markers.get(account.normalized_key, marker)
            )
        return [
            (account, document, issuer)
            for account, document in rows
            if (
                document.reference_date,
                document.version,
                period_priority.get(document.period_kind, 0),
            )
            == latest_markers[account.normalized_key]
        ]

    def start_run(self, document_type: str, year: int) -> CvmSyncRun:
        run = CvmSyncRun(document_type=document_type, year=year, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_run(
        self,
        run: CvmSyncRun,
        *,
        documents: int,
        accounts: int,
        etag=None,
        last_modified=None,
    ) -> None:
        run.status = "completed"
        run.documents_imported = documents
        run.accounts_imported = accounts
        run.etag = etag
        run.last_modified = last_modified
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def fail_run(self, run: CvmSyncRun, message: str) -> None:
        self.db.rollback()
        run = self.db.merge(run)
        run.status = "failed"
        run.error_message = message[:500]
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def list_runs(self, limit: int = 20) -> list[CvmSyncRun]:
        return (
            self.db.query(CvmSyncRun)
            .order_by(CvmSyncRun.started_at.desc())
            .limit(limit)
            .all()
        )

    def available_documents(self) -> list[tuple[str, int]]:
        rows = (
            self.db.query(
                CvmFinancialDocument.document_type, CvmFinancialDocument.reference_date
            )
            .distinct()
            .all()
        )
        return sorted(
            {(kind, reference.year) for kind, reference in rows}, reverse=True
        )

    def commit(self) -> None:
        self.db.commit()

    def reported_itr_flow_rows(self) -> list[tuple]:
        return (
            self.db.query(CvmFinancialAccount, CvmFinancialDocument, CvmIssuer)
            .join(
                CvmFinancialDocument,
                CvmFinancialAccount.document_id == CvmFinancialDocument.id,
            )
            .join(CvmIssuer, CvmFinancialDocument.issuer_id == CvmIssuer.id)
            .filter(
                CvmFinancialDocument.document_type == "ITR",
                CvmFinancialDocument.statement_type.in_(
                    ["DRE", "DFC_MD", "DFC_MI", "DVA"]
                ),
                CvmFinancialAccount.acquisition_method == "reported",
            )
            .order_by(
                CvmFinancialDocument.issuer_id,
                CvmFinancialDocument.statement_type,
                CvmFinancialAccount.account_code,
                CvmFinancialDocument.period_end,
            )
            .all()
        )
