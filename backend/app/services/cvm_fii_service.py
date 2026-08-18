from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.providers.cvm_fii_open_data_provider import CvmFiiOpenDataProvider
from app.repositories.cvm_fii_repository import CvmFiiRepository


AGGREGATION_METHOD = (
    "Média ponderada pela área (campo oficial Area) do campo oficial "
    "Percentual_Vacancia por imóvel, tabela imovel do Informe Trimestral "
    "Estruturado de FII (CVM, ANEXO 39-II da Instrução CVM 571/2015). "
    "Imóveis sem Percentual_Vacancia ou sem Area informados são excluídos "
    "do cálculo -- nunca tratados como vacância zero."
)


class CvmFiiService:
    def __init__(self, repository: CvmFiiRepository, provider: CvmFiiOpenDataProvider):
        self.repository = repository
        self.provider = provider

    def synchronize(self, year: int) -> dict:
        run = self.repository.start_run("INF_TRIMESTRAL", year)
        try:
            download = self.provider.download_year(year)
            result = self.import_archive(download.path, download.collected_at)
            self.repository.finish_run(run, documents=result["documents_imported"])
            return {**result, "cache_hit": download.cache_hit, "run_id": run.id}
        except Exception as exc:
            self.repository.fail_run(run, self._public_error(exc))
            raise

    def import_archive(self, path: Path, collected_at: datetime) -> dict:
        names_by_cnpj = self._latest_fund_names(path)
        groups: dict[tuple[str, date], dict] = {}
        for row in self.provider.iter_properties(path, collected_at):
            key = (row.cnpj, row.reference_date)
            bucket = groups.get(key)
            if bucket is None:
                groups[key] = {"version": row.version, "rows": [row]}
                continue
            if row.version > bucket["version"]:
                bucket["version"] = row.version
                bucket["rows"] = [row]
            elif row.version == bucket["version"]:
                bucket["rows"].append(row)
            # linhas de versão mais antiga (reapresentação superada) são
            # descartadas por já não corresponderem a bucket["version"].

        documents_imported = 0
        for (cnpj, reference_date), bucket in groups.items():
            rows = bucket["rows"]
            weighted = self._area_weighted_vacancy(rows)
            if weighted is None:
                continue
            official_name = names_by_cnpj.get(cnpj)
            if not official_name:
                # Sem nome oficial comprovado para este CNPJ neste arquivo
                # -- não inventa um nome, não importa este fundo agora.
                continue
            issuer = self.repository.upsert_issuer(cnpj, official_name)
            self.repository.upsert_vacancy_document(
                issuer.id,
                reference_date=reference_date,
                version=bucket["version"],
                property_count=len(rows),
                area_weighted_vacancy_rate=weighted,
                aggregation_method=AGGREGATION_METHOD,
                source_resource=rows[0].source_resource,
                collected_at=collected_at,
            )
            documents_imported += 1
        self.repository.commit()
        return {"documents_imported": documents_imported}

    def _latest_fund_names(self, path: Path) -> dict[str, str]:
        latest: dict[str, tuple[date, int, str]] = {}
        for entry in self.provider.iter_fund_names(path):
            current = latest.get(entry.cnpj)
            marker = (entry.reference_date, entry.version)
            if current is None or marker > (current[0], current[1]):
                latest[entry.cnpj] = (entry.reference_date, entry.version, entry.official_name)
        return {cnpj: value[2] for cnpj, value in latest.items()}

    @staticmethod
    def _area_weighted_vacancy(rows) -> Decimal | None:
        total_area = Decimal("0")
        weighted_sum = Decimal("0")
        for row in rows:
            if row.vacancy_rate is None or row.area is None or row.area <= 0:
                continue
            total_area += row.area
            weighted_sum += row.vacancy_rate * row.area
        if total_area <= 0:
            return None
        return weighted_sum / total_area

    @staticmethod
    def _public_error(exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"
