from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from datetime import date
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
        preferred_dfc_method = {}
        for account in self.provider.iter_accounts(path, document_type, collected_at):
            is_dfc = account.statement_type in {"DFC_MD", "DFC_MI"}
            # Preserva cada versão CVM no histórico. A escolha de escopo
            # ocorre dentro da versão; para DFC, MD/MI continuam agrupados
            # para selecionar um único método por versão.
            document_key = (
                account.cnpj,
                account.reference_date,
                account.period_start,
                account.period_end,
                account.version,
            ) if is_dfc else (
                account.cnpj,
                account.reference_date,
                account.statement_type,
                account.period_end,
                account.version,
            )
            priority = (1 if account.scope == "consolidated" else 0,)
            if priority > winners.get(document_key, (-1, -1) if is_dfc else (-1,)):
                winners[document_key] = priority

            # A versão vigente é selecionada antes da preferência do método.
            # MD e MI são alternativas dentro do mesmo documento/período/versão.
            if is_dfc:
                method_key = (
                    account.cnpj, account.reference_date, account.period_start,
                    account.period_end, account.scope, account.version,
                )
                method_priority = 2 if account.statement_type == "DFC_MD" else 1
                if method_priority > preferred_dfc_method.get(method_key, 0):
                    preferred_dfc_method[method_key] = method_priority

        document_ids = set()
        accounts_imported = 0
        # O CSV oficial da CVM pode conter linhas literalmente duplicadas
        # para a mesma (empresa, período, demonstração, conta, escopo,
        # versão) — observado em sincronização real. upsert_account()
        # consulta o banco para decidir INSERT vs UPDATE, mas essa consulta
        # não enxerga um INSERT ainda não commitado dentro deste mesmo loop;
        # sem esta deduplicação em memória, a segunda ocorrência tentaria
        # inserir a mesma chave natural (document_id, account_code) de novo e
        # violaria a constraint de unicidade. Mantém apenas a primeira
        # ocorrência — nunca soma nem inventa um valor entre duplicatas.
        seen_accounts: set[tuple] = set()
        for account in self.provider.iter_accounts(path, document_type, collected_at):
            is_dfc = account.statement_type in {"DFC_MD", "DFC_MI"}
            # Preserva cada versão CVM no histórico. A escolha de escopo
            # ocorre dentro da versão; para DFC, MD/MI continuam agrupados
            # para selecionar um único método por versão.
            document_key = (
                account.cnpj,
                account.reference_date,
                account.period_start,
                account.period_end,
            ) if is_dfc else (
                account.cnpj,
                account.reference_date,
                account.statement_type,
                account.period_end,
                account.version,
            )
            priority = (
                account.version,
                1 if account.scope == "consolidated" else 0,
            ) if is_dfc else (
                1 if account.scope == "consolidated" else 0,
            )
            if winners.get(document_key) != priority:
                continue
            if is_dfc:
                method_key = (
                    account.cnpj, account.reference_date, account.period_start,
                    account.period_end, account.scope, account.version,
                )
                selected_method = "DFC_MD" if preferred_dfc_method[method_key] == 2 else "DFC_MI"
                if account.statement_type != selected_method:
                    continue
            if not account.cnpj or not account.cvm_code:
                continue
            account_dedup_key = (document_key, account.scope, account.version, account.account_code)
            if account_dedup_key in seen_accounts:
                continue
            seen_accounts.add(account_dedup_key)
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
        previous_document_by_key = {}
        document_ids = set()
        accounts_created = 0

        # Reapresentações podem deixar várias versões do mesmo período no
        # banco. Selecionamos a maior versão por período antes de percorrer
        # a série cronologicamente e calcular diferenças.
        latest_by_period = {}
        for account, document, issuer in self.repository.reported_itr_flow_rows():
            period_key = (
                document.issuer_id, document.statement_type, document.scope,
                account.account_code, document.period_start, document.period_end,
            )
            priority = (document.version, document.collected_at)
            previous = latest_by_period.get(period_key)
            if previous is None or priority > (previous[1].version, previous[1].collected_at):
                latest_by_period[period_key] = (account, document, issuer)

        ordered_rows = sorted(
            latest_by_period.values(),
            key=lambda row: (
                str(row[1].issuer_id), row[1].statement_type, row[1].scope,
                row[0].account_code, row[1].period_start or date.min, row[1].period_end,
            ),
        )
        for account, document, issuer in ordered_rows:
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
            previous_raw = previous_by_key.get(key)
            previous_document = previous_document_by_key.get(key)
            isolated = CvmFinancialEngine.isolated_quarter(raw, previous_raw)
            previous_by_key[key] = raw
            previous_document_by_key[key] = document
            if isolated is None or previous_document is None:
                continue
            calculated_document = self.repository.upsert_document(
                document.issuer_id, isolated
            )
            document_ids.add(calculated_document.id)
            self.repository.upsert_calculation_lineage(
                calculated_document,
                current_source_document=document,
                previous_source_document=previous_document,
            )
            if self.repository.upsert_account(
                calculated_document.id,
                isolated,
                CvmFinancialEngine.normalized_key(isolated),
                acquisition_method="calculated",
            ):
                accounts_created += 1
        return document_ids, accounts_created

    def link_asset(self, asset_id: UUID, issuer_id: UUID):
        """Vínculo manual explícito (endpoint de superusuário).

        O repository agora só dá flush (ver CvmFinancialRepository.link_asset)
        — este serviço é quem decide a fronteira de commit desta operação de
        escrita autônoma, no mesmo padrão já usado em import_archive().
        """
        if self.asset_repository.get_by_id(asset_id) is None:
            raise ValueError("Ativo não encontrado.")
        if self.repository.get_issuer(issuer_id) is None:
            raise ValueError("Emissor CVM não encontrado.")
        link = self.repository.link_asset(asset_id, issuer_id)
        self.repository.commit()
        return link

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
            key = account.normalized_key
            if account.account_code == "2" and key == "total_liabilities":
                key = "total_liabilities_and_equity"
            grouped[key].append((account, document, issuer))
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
