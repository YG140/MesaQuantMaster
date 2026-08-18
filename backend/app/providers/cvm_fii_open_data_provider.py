from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Iterator
from zipfile import BadZipFile, ZipFile

import httpx


class CvmFiiProviderError(RuntimeError):
    pass


class CvmFiiDownloadError(CvmFiiProviderError):
    pass


class CvmFiiArchiveError(CvmFiiProviderError):
    pass


class CvmFiiSizeLimitError(CvmFiiProviderError):
    pass


@dataclass(frozen=True)
class CvmFiiDownloadResult:
    path: Path
    etag: str | None
    last_modified: str | None
    collected_at: datetime
    cache_hit: bool
    size_bytes: int


@dataclass(frozen=True)
class CvmFiiRawFundName:
    """Identidade oficial (Nome_Fundo_Classe) de um fundo/classe em um
    trimestre de referência, vinda da tabela `geral` -- usada apenas para
    dar um nome real ao FiiIssuer, nunca inventado."""

    cnpj: str
    official_name: str
    reference_date: date
    version: int


@dataclass(frozen=True)
class CvmFiiRawProperty:
    """Uma linha bruta da tabela `imovel` do Informe Trimestral Estruturado
    de FII (ANEXO 39-II da Instrução CVM 571/2015) -- um imóvel de um fundo
    em um trimestre de referência. `vacancy_rate` é None quando o campo
    oficial Percentual_Vacancia vier vazio (nunca convertido para 0)."""

    cnpj: str
    reference_date: date
    version: int
    property_class: str
    area: Decimal | None
    vacancy_rate: Decimal | None
    source_resource: str
    collected_at: datetime


class CvmFiiOpenDataProvider:
    """Coleta controlada do Informe Trimestral Estruturado de FII da CVM
    (dataset fii-doc-inf_trimestral, tabela `imovel` -- única tabela
    estruturada confirmada, por inspeção real do dicionário de dados e de
    linhas reais, a conter o campo oficial Percentual_Vacancia por imóvel).

    Mesma filosofia de segurança do CvmOpenDataProvider (corporativo):
    download limitado, validação de ZIP contra path traversal, limite de
    tamanho descompactado, cache com ETag/Last-Modified, nenhuma execução
    de conteúdo do ZIP, parsing explícito com encoding declarado pela
    fonte (cp1252), falha segura.
    """

    provider_name = "CVM Dados Abertos (FII)"
    base_url = "https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS"
    imovel_pattern = re.compile(r"inf_trimestral_fii_imovel_\d{4}\.csv$", re.IGNORECASE)
    geral_pattern = re.compile(r"inf_trimestral_fii_geral_\d{4}\.csv$", re.IGNORECASE)

    def __init__(
        self,
        cache_dir: Path | str = ".cache/cvm_fii",
        client: httpx.Client | None = None,
        timeout_seconds: float = 60,
        max_download_bytes: int = 40 * 1024 * 1024,
        max_uncompressed_bytes: int = 512 * 1024 * 1024,
        cache_ttl_hours: int = 24,
    ):
        self.cache_dir = Path(cache_dir)
        self.client = client or httpx.Client(
            timeout=timeout_seconds, follow_redirects=True
        )
        self.max_download_bytes = max_download_bytes
        self.max_uncompressed_bytes = max_uncompressed_bytes
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def download_year(self, year: int) -> CvmFiiDownloadResult:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        archive = self.cache_dir / f"inf_trimestral_fii_{year}.zip"
        metadata_path = archive.with_suffix(".json")
        metadata = self._read_metadata(metadata_path)
        now = datetime.now(timezone.utc)
        if archive.exists() and metadata and self._cache_is_fresh(metadata, now):
            self.validate_archive(archive)
            return self._download_result(archive, metadata, True)

        headers = {}
        if metadata.get("etag"):
            headers["If-None-Match"] = metadata["etag"]
        if metadata.get("last_modified"):
            headers["If-Modified-Since"] = metadata["last_modified"]
        url = f"{self.base_url}/inf_trimestral_fii_{year}.zip"
        try:
            with self.client.stream("GET", url, headers=headers) as response:
                if response.status_code == 304 and archive.exists():
                    metadata["checked_at"] = now.isoformat()
                    self._write_metadata(metadata_path, metadata)
                    return self._download_result(archive, metadata, True)
                response.raise_for_status()
                declared = int(response.headers.get("Content-Length", "0") or 0)
                if declared > self.max_download_bytes:
                    raise CvmFiiSizeLimitError(
                        "Arquivo CVM FII excede o limite de download."
                    )
                with NamedTemporaryFile(
                    "wb", delete=False, dir=self.cache_dir, suffix=".part"
                ) as temp:
                    temp_path = Path(temp.name)
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_download_bytes:
                            raise CvmFiiSizeLimitError(
                                "Arquivo CVM FII excede o limite de download."
                            )
                        temp.write(chunk)
                self.validate_archive(temp_path)
                temp_path.replace(archive)
                metadata = {
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "collected_at": now.isoformat(),
                    "checked_at": now.isoformat(),
                    "size_bytes": size,
                }
                self._write_metadata(metadata_path, metadata)
        except CvmFiiProviderError:
            if "temp_path" in locals() and temp_path.exists():
                temp_path.unlink()
            raise
        except (httpx.HTTPError, OSError) as exc:
            if "temp_path" in locals() and temp_path.exists():
                temp_path.unlink()
            raise CvmFiiDownloadError(
                "Não foi possível baixar o arquivo oficial da CVM (FII)."
            ) from exc
        return self._download_result(archive, metadata, False)

    def validate_archive(self, path: Path) -> None:
        try:
            with ZipFile(path) as archive:
                total = 0
                for entry in archive.infolist():
                    member = PurePosixPath(entry.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        raise CvmFiiArchiveError("ZIP CVM FII contém caminho inseguro.")
                    total += entry.file_size
                    if total > self.max_uncompressed_bytes:
                        raise CvmFiiSizeLimitError(
                            "ZIP CVM FII excede o limite descompactado."
                        )
        except BadZipFile as exc:
            raise CvmFiiArchiveError("Arquivo CVM FII não é um ZIP válido.") from exc

    def iter_properties(
        self, path: Path, collected_at: datetime | None = None
    ) -> Iterator[CvmFiiRawProperty]:
        collected = collected_at or datetime.now(timezone.utc)
        self.validate_archive(path)
        with ZipFile(path) as archive:
            for entry in archive.infolist():
                if not self.imovel_pattern.search(entry.filename):
                    continue
                with archive.open(entry) as raw:
                    text = (line.decode("cp1252") for line in raw)
                    reader = csv.DictReader(text, delimiter=";")
                    for row in reader:
                        parsed = self._parse_row(row, entry.filename, collected)
                        if parsed is not None:
                            yield parsed

    def iter_fund_names(self, path: Path) -> Iterator[CvmFiiRawFundName]:
        self.validate_archive(path)
        with ZipFile(path) as archive:
            for entry in archive.infolist():
                if not self.geral_pattern.search(entry.filename):
                    continue
                with archive.open(entry) as raw:
                    text = (line.decode("cp1252") for line in raw)
                    reader = csv.DictReader(text, delimiter=";")
                    for row in reader:
                        parsed = self._parse_name_row(row)
                        if parsed is not None:
                            yield parsed

    def _parse_name_row(self, row) -> CvmFiiRawFundName | None:
        try:
            cnpj = self.normalize_cnpj(row["CNPJ_Fundo_Classe"])
            reference = date.fromisoformat(row["Data_Referencia"])
            version = int(row["Versao"])
        except (KeyError, ValueError):
            return None
        name = (row.get("Nome_Fundo_Classe") or "").strip()
        if not cnpj or not name:
            return None
        return CvmFiiRawFundName(
            cnpj=cnpj, official_name=name, reference_date=reference, version=version
        )

    def _parse_row(self, row, source_resource, collected) -> CvmFiiRawProperty | None:
        try:
            cnpj = self.normalize_cnpj(row["CNPJ_Fundo_Classe"])
            reference = date.fromisoformat(row["Data_Referencia"])
            version = int(row["Versao"])
        except (KeyError, ValueError):
            return None
        if not cnpj:
            return None
        return CvmFiiRawProperty(
            cnpj=cnpj,
            reference_date=reference,
            version=version,
            property_class=row.get("Classe", "").strip(),
            area=self._decimal(row.get("Area")),
            vacancy_rate=self._decimal(row.get("Percentual_Vacancia")),
            source_resource=source_resource,
            collected_at=collected,
        )

    @staticmethod
    def _decimal(value: str | None) -> Decimal | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text.replace(",", "."))
        except InvalidOperation:
            return None

    @staticmethod
    def normalize_cnpj(value: str) -> str:
        return "".join(character for character in value if character.isdigit())

    @staticmethod
    def _read_metadata(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write_metadata(path: Path, metadata: dict) -> None:
        path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    def _cache_is_fresh(self, metadata: dict, now: datetime) -> bool:
        try:
            checked = datetime.fromisoformat(metadata["checked_at"])
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
            return now - checked < self.cache_ttl
        except (KeyError, ValueError):
            return False

    @staticmethod
    def _download_result(
        path: Path, metadata: dict, cache_hit: bool
    ) -> CvmFiiDownloadResult:
        collected = datetime.fromisoformat(
            metadata.get("collected_at") or metadata["checked_at"]
        )
        return CvmFiiDownloadResult(
            path=path,
            etag=metadata.get("etag"),
            last_modified=metadata.get("last_modified"),
            collected_at=collected,
            cache_hit=cache_hit,
            size_bytes=int(metadata.get("size_bytes") or path.stat().st_size),
        )
