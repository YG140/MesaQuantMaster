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


class CvmProviderError(RuntimeError):
    pass


class CvmDownloadError(CvmProviderError):
    pass


class CvmArchiveError(CvmProviderError):
    pass


class CvmSizeLimitError(CvmProviderError):
    pass


@dataclass(frozen=True)
class CvmDownloadResult:
    path: Path
    etag: str | None
    last_modified: str | None
    collected_at: datetime
    cache_hit: bool
    size_bytes: int


@dataclass(frozen=True)
class CvmRawAccount:
    document_type: str
    statement_type: str
    scope: str
    cnpj: str
    cvm_code: str
    issuer_name: str
    reference_date: date
    version: int
    period_start: date | None
    period_end: date
    period_kind: str
    currency: str
    scale: str
    account_code: str
    account_description: str
    original_value: Decimal
    normalized_value: Decimal
    is_fixed_account: bool
    collected_at: datetime


class CvmOpenDataProvider:
    """Coleta controlada dos ZIPs oficiais DFP e ITR da CVM."""

    provider_name = "CVM Dados Abertos"
    base_url = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
    statement_pattern = re.compile(
        r"_(BPA|BPP|DRE|DFC_MD|DFC_MI|DVA)_(con|ind)_\d{4}\.csv$",
        re.IGNORECASE,
    )
    scale_multipliers = {
        "UNIDADE": Decimal("1"),
        "MIL": Decimal("1000"),
        "MILHAR": Decimal("1000"),
        "MILHÃO": Decimal("1000000"),
        "MILHAO": Decimal("1000000"),
    }

    def __init__(
        self,
        cache_dir: Path | str = ".cache/cvm",
        client: httpx.Client | None = None,
        timeout_seconds: float = 60,
        max_download_bytes: int = 80 * 1024 * 1024,
        max_uncompressed_bytes: int = 1024 * 1024 * 1024,
        cache_ttl_hours: int = 24,
    ):
        self.cache_dir = Path(cache_dir)
        self.client = client or httpx.Client(
            timeout=timeout_seconds, follow_redirects=True
        )
        self.max_download_bytes = max_download_bytes
        self.max_uncompressed_bytes = max_uncompressed_bytes
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def synchronization_metadata(self) -> dict:
        return {
            "provider": self.provider_name,
            "mode": "controlled",
            "supports": ["DFP", "ITR"],
            "source": "dados.cvm.gov.br",
            "checked_at": datetime.now(timezone.utc),
        }

    def download_year(self, document_type: str, year: int) -> CvmDownloadResult:
        kind = self._document_type(document_type)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        archive = self.cache_dir / f"{kind.lower()}_cia_aberta_{year}.zip"
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
        url = f"{self.base_url}/{kind}/DADOS/{kind.lower()}_cia_aberta_{year}.zip"
        try:
            with self.client.stream("GET", url, headers=headers) as response:
                if response.status_code == 304 and archive.exists():
                    metadata["checked_at"] = now.isoformat()
                    self._write_metadata(metadata_path, metadata)
                    return self._download_result(archive, metadata, True)
                response.raise_for_status()
                declared = int(response.headers.get("Content-Length", "0") or 0)
                if declared > self.max_download_bytes:
                    raise CvmSizeLimitError("Arquivo CVM excede o limite de download.")
                with NamedTemporaryFile(
                    "wb", delete=False, dir=self.cache_dir, suffix=".part"
                ) as temp:
                    temp_path = Path(temp.name)
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_download_bytes:
                            raise CvmSizeLimitError(
                                "Arquivo CVM excede o limite de download."
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
        except CvmProviderError:
            if "temp_path" in locals() and temp_path.exists():
                temp_path.unlink()
            raise
        except (httpx.HTTPError, OSError) as exc:
            if "temp_path" in locals() and temp_path.exists():
                temp_path.unlink()
            raise CvmDownloadError(
                "Não foi possível baixar o arquivo oficial da CVM."
            ) from exc
        return self._download_result(archive, metadata, False)

    def validate_archive(self, path: Path) -> None:
        try:
            with ZipFile(path) as archive:
                total = 0
                for entry in archive.infolist():
                    member = PurePosixPath(entry.filename.replace("\\", "/"))
                    if member.is_absolute() or ".." in member.parts:
                        raise CvmArchiveError("ZIP CVM contém caminho inseguro.")
                    total += entry.file_size
                    if total > self.max_uncompressed_bytes:
                        raise CvmSizeLimitError(
                            "ZIP CVM excede o limite descompactado."
                        )
        except BadZipFile as exc:
            raise CvmArchiveError("Arquivo CVM não é um ZIP válido.") from exc

    def iter_accounts(
        self, path: Path, document_type: str, collected_at: datetime | None = None
    ) -> Iterator[CvmRawAccount]:
        kind = self._document_type(document_type)
        collected = collected_at or datetime.now(timezone.utc)
        self.validate_archive(path)
        with ZipFile(path) as archive:
            for entry in archive.infolist():
                match = self.statement_pattern.search(entry.filename)
                if not match:
                    continue
                statement = match.group(1).upper()
                scope = (
                    "consolidated" if match.group(2).lower() == "con" else "individual"
                )
                with archive.open(entry) as raw:
                    text = (line.decode("cp1252") for line in raw)
                    reader = csv.DictReader(text, delimiter=";")
                    for row in reader:
                        parsed = self._parse_row(row, kind, statement, scope, collected)
                        if parsed is not None:
                            yield parsed

    def _parse_row(self, row, kind, statement, scope, collected):
        if row.get("ORDEM_EXERC", "").strip().upper() not in {"ÚLTIMO", "ULTIMO"}:
            return None
        scale = row.get("ESCALA_MOEDA", "").strip().upper()
        multiplier = self.scale_multipliers.get(scale)
        if multiplier is None:
            return None
        try:
            original = Decimal(row["VL_CONTA"].strip().replace(",", "."))
            reference = date.fromisoformat(row["DT_REFER"])
            period_end = date.fromisoformat(row["DT_FIM_EXERC"])
            period_start = (
                date.fromisoformat(row["DT_INI_EXERC"])
                if row.get("DT_INI_EXERC")
                else None
            )
            version = int(row["VERSAO"])
        except (KeyError, ValueError, InvalidOperation):
            return None
        return CvmRawAccount(
            document_type=kind,
            statement_type=statement,
            scope=scope,
            cnpj=self.normalize_cnpj(row.get("CNPJ_CIA", "")),
            cvm_code=row.get("CD_CVM", "").strip(),
            issuer_name=row.get("DENOM_CIA", "").strip(),
            reference_date=reference,
            version=version,
            period_start=period_start,
            period_end=period_end,
            period_kind=self._period_kind(kind, period_start, period_end),
            currency=row.get("MOEDA", "").strip(),
            scale=scale,
            account_code=row.get("CD_CONTA", "").strip(),
            account_description=row.get("DS_CONTA", "").strip(),
            original_value=original,
            normalized_value=original * multiplier,
            is_fixed_account=row.get("ST_CONTA_FIXA", "").strip().upper() == "S",
            collected_at=collected,
        )

    @staticmethod
    def normalize_cnpj(value: str) -> str:
        return "".join(character for character in value if character.isdigit())

    @staticmethod
    def _period_kind(kind: str, start: date | None, end: date) -> str:
        if kind == "DFP":
            return "annual"
        if start is None:
            return "point_in_time"
        # DT_INI_EXERC representa o início do exercício da companhia,
        # que pode não coincidir com janeiro. Os valores de fluxo do ITR
        # são acumulados desde esse início, inclusive no primeiro trimestre.
        return "year_to_date"

    @staticmethod
    def _document_type(value: str) -> str:
        normalized = value.upper().strip()
        if normalized not in {"DFP", "ITR"}:
            raise ValueError("Tipo de documento CVM deve ser DFP ou ITR.")
        return normalized

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
    ) -> CvmDownloadResult:
        collected = datetime.fromisoformat(
            metadata.get("collected_at") or metadata["checked_at"]
        )
        return CvmDownloadResult(
            path=path,
            etag=metadata.get("etag"),
            last_modified=metadata.get("last_modified"),
            collected_at=collected,
            cache_hit=cache_hit,
            size_bytes=int(metadata.get("size_bytes") or path.stat().st_size),
        )
