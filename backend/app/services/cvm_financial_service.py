from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from app.engines.cvm_financial_engine import CvmFinancialEngine
from app.providers.cvm_open_data_provider import CvmOpenDataProvider
from app.providers.cvm_open_data_provider import CvmRawAccount
from app.repositories.asset_repository import AssetRepository
from app.repositories.cvm_financial_repository import CvmFinancialRepository


class CvmFinancialService:
    def __init__(
        self,
        repository: CvmFinancialRepository,
        asset_repository: AssetRepository,
        provider: CvmOpenDataProvider,
    ):
        self.repository = repository
        self.asset_repository = asset_repository
        self.provider = provider

    def synchronize(self, document_type: str, year: int) -> dict:
        kind = document_type.upper().strip()
        run = self.repository.start_run(kind, year)
        try:
            download = self.provider.download_year(kind, year)
            result = self.import_archive(download.path, kind, download.collected_at)
            self.repository.finish_run(
                run,
                documents=result["documents_imported"],
                accounts=result["accounts_imported"],
                etag=download.etag,
                last_modified=download.last_modified,
            )
            return {**result, "cache_hit": download.cache_hit, "run_id": run.id}
        except Exception as exc:
            self.repository.fail_run(run, self._public_error(exc))
            raise

    def import_archive(self, path: Path, document_type: str, collected_at) -> dict:
        winners = {}
        for account in self.provider.iter_accounts(path, document_type, collected_at):
            document_key = (
                account.cnpj,
                account.reference_date,
                account.statement_type,
                account.period_end,
            )
            priority = (1 if account.scope == "consolidated" else 0, account.version)
            if priority > winners.get(document_key, (-1, -1)):
                winners[document_key] = priority

        document_ids = set()
        accounts_imported = 0
        for account in self.provider.iter_accounts(path, document_type, collected_at):
            document_key = (
                account.cnpj,
                account.reference_date,
                account.statement_type,
                account.period_end,
            )
            priority = (1 if account.scope == "consolidated" else 0, account.version)
            if winners.get(document_key) != priority:
                continue
            if not account.cnpj or not account.cvm_code:
                continue
            issuer = self.repository.upsert_issuer(
                account.cnpj, account.cvm_code, account.issuer_name
            )
            document = self.repository.upsert_document(issuer.id, account)
            document_ids.add(document.id)
            if self.repository.upsert_account(
                document.id,
                account,
                CvmFinancialEngine.normalized_key(account),
            ):
                accounts_imported += 1
        self.repository.commit()
        if document_type.upper() == "ITR":
            calculated_documents, calculated_accounts = self._calculate_quarters()
            document_ids.update(calculated_documents)
            accounts_imported += calculated_accounts
            self.repository.commit()
        return {
            "documents_imported": len(document_ids),
            "accounts_imported": accounts_imported,
        }

    def _calculate_quarters(self) -> tuple[set, int]:
        previous_by_key = {}
        document_ids = set()
        accounts_created = 0
        for account, document, issuer in self.repository.reported_itr_flow_rows():
            raw = CvmRawAccount(
                document_type=document.document_type,
                statement_type=document.statement_type,
                scope=document.scope,
                cnpj=issuer.cnpj,
                cvm_code=issuer.cvm_code,
                issuer_name=issuer.official_name,
                reference_date=document.reference_date,
                version=document.version,
                period_start=document.period_start,
                period_end=document.period_end,
                period_kind=document.period_kind,
                currency=document.currency,
                scale=document.scale,
                account_code=account.account_code,
                account_description=account.account_description,
                original_value=Decimal(account.original_value),
                normalized_value=Decimal(account.normalized_value),
                is_fixed_account=account.is_fixed_account,
                collected_at=document.collected_at,
            )
            key = (
                document.issuer_id,
                document.statement_type,
                document.scope,
                account.account_code,
                document.period_start,
            )
            isolated = CvmFinancialEngine.isolated_quarter(
                raw, previous_by_key.get(key)
            )
            previous_by_key[key] = raw
            if isolated is None:
                continue
            calculated_document = self.repository.upsert_document(
                document.issuer_id, isolated
            )
            document_ids.add(calculated_document.id)
            if self.repository.upsert_account(
                calculated_document.id,
                isolated,
                CvmFinancialEngine.normalized_key(isolated),
                acquisition_method="calculated",
            ):
                accounts_created += 1
        return document_ids, accounts_created

    def link_asset(self, asset_id: UUID, issuer_id: UUID):
        if self.asset_repository.get_by_id(asset_id) is None:
            raise ValueError("Ativo não encontrado.")
        if self.repository.get_issuer(issuer_id) is None:
            raise ValueError("Emissor CVM não encontrado.")
        return self.repository.link_asset(asset_id, issuer_id)

    def asset_link(self, asset_id: UUID) -> dict:
        if self.asset_repository.get_by_id(asset_id) is None:
            raise ValueError("Ativo não encontrado.")
        issuer = self.repository.linked_issuer(asset_id)
        if issuer is None:
            return {
                "asset_id": asset_id,
                "status": "pending",
                "reason": "Ativo sem vínculo explícito com emissor CVM.",
                "issuer": None,
            }
        return {
            "asset_id": asset_id,
            "status": "linked",
            "reason": None,
            "issuer": issuer,
        }

    def normalized_for_asset(self, asset_id: UUID) -> list[dict]:
        grouped = defaultdict(list)
        for account, document, issuer in self.repository.latest_normalized(asset_id):
            grouped[account.normalized_key].append((account, document, issuer))
        results = []
        for key, rows in grouped.items():
            value = sum(
                (Decimal(row[0].normalized_value) for row in rows), Decimal("0")
            )
            account, document, issuer = rows[0]
            results.append(
                {
                    "key": key,
                    "value": value,
                    "unit": "currency",
                    "period": document.period_kind,
                    "source": "CVM Dados Abertos",
                    "source_type": "official",
                    "reference_date": document.period_end,
                    "collected_at": document.collected_at,
                    "document_type": document.document_type,
                    "scope": document.scope,
                    "method": account.acquisition_method,
                    "cnpj": issuer.cnpj,
                    "cvm_code": issuer.cvm_code,
                    "accounts": [
                        {
                            "code": item.account_code,
                            "description": item.account_description,
                            "original_value": item.original_value,
                        }
                        for item, _, _ in rows
                    ],
                }
            )
        return results

    @staticmethod
    def _public_error(exc: Exception) -> str:
        name = type(exc).__name__
        messages = {
            "CvmDownloadError": "Falha ao baixar dados oficiais da CVM.",
            "CvmArchiveError": "Arquivo oficial da CVM inválido.",
            "CvmSizeLimitError": "Arquivo oficial da CVM excede o limite permitido.",
        }
        return messages.get(name, "Falha ao importar dados oficiais da CVM.")
