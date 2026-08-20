from __future__ import annotations

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

from app.providers.b3.exceptions import (
    B3ArchiveError,
    B3DownloadError,
    B3ParseError,
    B3SizeLimitError,
)
from app.providers.b3.models import B3HistoricalRecord

# Tamanho fixo de registro conforme layout oficial "FILE LAYOUT - HISTORICAL
# QUOTATIONS" (b3.com.br, "PUBLIC INFORMATION", Review 01, 17/04/2017):
# "Register Size: 245 bytes."
_RECORD_LENGTH = 245

# Offsets 0-indexados derivados EXATAMENTE das colunas INIT.POS./FINAL POS.
# (1-indexadas, inclusivas) do layout oficial -- nunca copiados de memória
# ou de terceiros. slice(a, b) em Python usa [a, b), então cada offset aqui
# é (INIT.POS. - 1, FINAL.POS.).
_TIPREG = slice(0, 2)
_DATA_PREGAO = slice(2, 10)
_CODBDI = slice(10, 12)
_CODNEG = slice(12, 24)
_TPMERC = slice(24, 27)
_NOMRES = slice(27, 39)
_ESPECI = slice(39, 49)
_PRAZOT = slice(49, 52)
_MODREF = slice(52, 56)
_PREABE = slice(56, 69)
_PREMAX = slice(69, 82)
_PREMIN = slice(82, 95)
_PREMED = slice(95, 108)
_PREULT = slice(108, 121)
_PREOFC = slice(121, 134)
_PREOFV = slice(134, 147)
_TOTNEG = slice(147, 152)
_QUATOT = slice(152, 170)
_VOLTOT = slice(170, 188)
_PREEXE = slice(188, 201)
_INDOPC = slice(201, 202)
_DATVEN = slice(202, 210)
_FATCOT = slice(210, 217)
_PTOEXE = slice(217, 230)
_CODISI = slice(230, 242)
_DISMES = slice(242, 245)

# Sentinela oficial de "não aplicável" para DATVEN em instrumentos sem
# vencimento (convenção observada e documentada em implementações fixed-
# width deste tipo: campo N(08) zerado, nunca uma data real "0000-00-00").
_NO_DATE = "00000000"

# Limite conservador de razão de compressão (descompactado / compactado)
# para o único membro do ZIP -- proteção contra zip bomb complementar ao
# limite absoluto de tamanho descompactado já existente. Arquivos
# COTAHIST reais (diário e anual, ver auditoria desta correção) têm razão
# ~8.5-8.7:1 (texto fixo-largura repetitivo via DEFLATE); 100:1 dá margem
# folgada para variação legítima sem abrir espaço para uma razão
# patológica de zip bomb (tipicamente >>1000:1).
_MAX_COMPRESSION_RATIO = 100

# Caminho de entrada ZIP inseguro: drive letter Windows ("C:", "D:", ...)
# no início do nome -- PurePosixPath.is_absolute() não reconhece essa
# forma como absoluta, então precisa de checagem própria além de
# is_absolute()/".." já aplicados.
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class CotahistDownloadResult:
    path: Path
    reference_date: date
    etag: str | None
    last_modified: str | None
    collected_at: datetime
    cache_hit: bool
    size_bytes: int


class CotahistProvider:
    """Coleta controlada dos arquivos oficiais COTAHIST da B3 (diário e
    anual), publicamente acessíveis sem autenticação -- confirmado por
    auditoria direta (HTTP GET real, sem token) antes desta implementação.

    Reaproveita o MESMO padrão de segurança/cache já testado em
    CvmOpenDataProvider/TesouroTransparenteProvider: cache local com
    metadata ETag/Last-Modified, download para arquivo temporário validado
    ANTES de qualquer substituição atômica, limites de tamanho aplicados
    tanto pelo Content-Length declarado quanto durante o streaming.
    """

    provider_name = "B3 COTAHIST"
    base_url = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"

    def __init__(
        self,
        cache_dir: Path | str = ".cache/b3",
        client: httpx.Client | None = None,
        timeout_seconds: float = 60,
        daily_max_download_bytes: int = 2 * 1024 * 1024,
        daily_max_uncompressed_bytes: int = 20 * 1024 * 1024,
        annual_max_download_bytes: int = 100 * 1024 * 1024,
        annual_max_uncompressed_bytes: int = 1024 * 1024 * 1024,
        cache_ttl_hours: int = 20,
    ):
        self.cache_dir = Path(cache_dir)
        # follow_redirects=False deliberadamente -- confirmado por checagem
        # real (HEAD contra o endpoint oficial) que o COTAHIST responde
        # 200 OK direto, sem nenhum redirect. Sem essa evidência de um
        # redirect legítimo, seguir 3xx automaticamente permitiria que uma
        # resposta comprometida/typosquat redirecionasse o download para
        # qualquer host -- ver _download(), que rejeita 3xx explicitamente
        # como B3DownloadError em vez de segui-los.
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
        self.daily_max_download_bytes = daily_max_download_bytes
        self.daily_max_uncompressed_bytes = daily_max_uncompressed_bytes
        self.annual_max_download_bytes = annual_max_download_bytes
        self.annual_max_uncompressed_bytes = annual_max_uncompressed_bytes
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    # --- Download -----------------------------------------------------

    def download_daily(self, reference_date: date) -> CotahistDownloadResult:
        filename = f"COTAHIST_D{reference_date:%d%m%Y}"
        return self._download(
            url=f"{self.base_url}/{filename}.ZIP",
            archive=self.cache_dir / f"{filename}.zip",
            reference_date=reference_date,
            max_download_bytes=self.daily_max_download_bytes,
            max_uncompressed_bytes=self.daily_max_uncompressed_bytes,
        )

    def download_annual(self, year: int) -> CotahistDownloadResult:
        filename = f"COTAHIST_A{year}"
        return self._download(
            url=f"{self.base_url}/{filename}.ZIP",
            archive=self.cache_dir / f"{filename}.zip",
            reference_date=date(year, 12, 31),
            max_download_bytes=self.annual_max_download_bytes,
            max_uncompressed_bytes=self.annual_max_uncompressed_bytes,
        )

    def _download(
        self,
        *,
        url: str,
        archive: Path,
        reference_date: date,
        max_download_bytes: int,
        max_uncompressed_bytes: int,
    ) -> CotahistDownloadResult:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = archive.with_suffix(".json")
        metadata = self._read_metadata(metadata_path)
        now = datetime.now(timezone.utc)
        if archive.exists() and metadata and self._cache_is_fresh(metadata, now):
            self.validate_archive(archive, max_uncompressed_bytes)
            return self._result(archive, reference_date, metadata, True)

        headers = {"User-Agent": "MesaQuantMaster/1.0 (+official-data-integration)"}
        if metadata.get("etag"):
            headers["If-None-Match"] = metadata["etag"]
        if metadata.get("last_modified"):
            headers["If-Modified-Since"] = metadata["last_modified"]

        temp_path: Path | None = None
        try:
            # follow_redirects=False passado EXPLICITAMENTE na requisição
            # (não só no __init__ do client) -- httpx aceita `client=`
            # injetado no construtor (ver __init__), e um client externo
            # configurado com follow_redirects=True sobrescreveria a
            # política do client interno se este override por-requisição
            # não existisse. Prevalece sempre sobre o default do client,
            # injetado ou não (ver testes com client injetado).
            with self.client.stream(
                "GET", url, headers=headers, follow_redirects=False
            ) as response:
                if response.status_code == 304 and archive.exists():
                    metadata["checked_at"] = now.isoformat()
                    self._write_metadata(metadata_path, metadata)
                    return self._result(archive, reference_date, metadata, True)
                if 300 <= response.status_code < 400:
                    # follow_redirects=False (ver __init__) -- nenhum 3xx
                    # (exceto 304, tratado acima) é seguido automaticamente.
                    # Sem evidência de que o endpoint COTAHIST oficial exige
                    # redirect legítimo (checagem real: HEAD contra produção
                    # retornou 200 direto), qualquer redirect é tratado como
                    # download inválido -- nunca uma navegação arbitrária
                    # para outro host.
                    raise B3DownloadError(
                        "Resposta de redirect (HTTP "
                        f"{response.status_code}) do servidor oficial "
                        "COTAHIST nunca é seguida automaticamente."
                    )
                response.raise_for_status()
                declared = int(response.headers.get("Content-Length", "0") or 0)
                if declared > max_download_bytes:
                    raise B3SizeLimitError(
                        "Arquivo COTAHIST excede o limite de download configurado."
                    )
                with NamedTemporaryFile(
                    "wb", delete=False, dir=self.cache_dir, suffix=".part"
                ) as temp:
                    temp_path = Path(temp.name)
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_download_bytes:
                            raise B3SizeLimitError(
                                "Arquivo COTAHIST excede o limite de download configurado."
                            )
                        temp.write(chunk)
                self.validate_archive(temp_path, max_uncompressed_bytes)
                temp_path.replace(archive)
                metadata = {
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "collected_at": now.isoformat(),
                    "checked_at": now.isoformat(),
                    "size_bytes": size,
                }
                self._write_metadata(metadata_path, metadata)
        except (B3ArchiveError, B3SizeLimitError):
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            raise
        except (httpx.HTTPError, OSError) as exc:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            raise B3DownloadError(
                "Não foi possível baixar o arquivo oficial COTAHIST da B3."
            ) from exc
        return self._result(archive, reference_date, metadata, False)

    # --- Segurança do ZIP -----------------------------------------------

    def validate_archive(self, path: Path, max_uncompressed_bytes: int) -> None:
        """Nunca usa extractall(). Exige exatamente UM membro no ZIP --
        confirmado por dado real (auditoria desta correção): tanto o ZIP
        diário quanto o anual oficiais contêm exatamente uma entrada
        (COTAHIST_D<data>.TXT / COTAHIST_A<ano>.TXT), nunca mais. Um
        segundo membro qualquer (ex.: COTAHIST.TXT + evil.txt) é
        rejeitado sem jamais ser lido -- não há evidência de que a B3
        publique entradas adicionais (diretórios inclusos) para justificar
        aceitá-las.

        Valida nome/path (path traversal, absolute path POSIX, drive
        letter Windows, UNC) ANTES de olhar qualquer conteúdo, soma o
        tamanho descompactado E a razão de compressão contra o tamanho
        compactado (proteção contra zip bomb em duas frentes: tamanho
        absoluto e razão suspeita) -- tudo antes de ler um único byte do
        conteúdo do membro.
        """
        try:
            with ZipFile(path) as archive:
                members = archive.infolist()
                if not members:
                    raise B3ArchiveError("ZIP COTAHIST está vazio.")
                if len(members) != 1:
                    raise B3ArchiveError(
                        "ZIP COTAHIST contém mais de um membro -- esperado "
                        "exatamente um arquivo COTAHIST*.TXT."
                    )
                entry = members[0]
                raw_name = entry.filename.replace("\\", "/")
                member = PurePosixPath(raw_name)
                if (
                    member.is_absolute()
                    or raw_name.startswith("/")
                    or _WINDOWS_DRIVE_PREFIX.match(raw_name)
                    or ".." in member.parts
                ):
                    raise B3ArchiveError("ZIP COTAHIST contém caminho inseguro.")
                if not (
                    member.name.upper().startswith("COTAHIST")
                    and member.suffix.upper() == ".TXT"
                ):
                    raise B3ArchiveError(
                        "ZIP COTAHIST não contém exatamente um arquivo COTAHIST*.TXT "
                        "esperado."
                    )
                if entry.file_size > max_uncompressed_bytes:
                    raise B3SizeLimitError(
                        "ZIP COTAHIST excede o limite descompactado configurado."
                    )
                if entry.compress_size > 0:
                    ratio = entry.file_size / entry.compress_size
                    if ratio > _MAX_COMPRESSION_RATIO:
                        raise B3SizeLimitError(
                            "ZIP COTAHIST tem razão de compressão suspeita "
                            f"({ratio:.1f}:1, limite {_MAX_COMPRESSION_RATIO}:1) -- "
                            "possível zip bomb."
                        )
                elif entry.file_size > 0:
                    # compress_size==0 com file_size>0 declarado -- razão
                    # infinita, nunca aceito (nunca divide por zero aqui).
                    raise B3SizeLimitError(
                        "ZIP COTAHIST declara conteúdo descompactado sem "
                        "nenhum dado compactado correspondente."
                    )
        except BadZipFile as exc:
            raise B3ArchiveError("Arquivo COTAHIST não é um ZIP válido.") from exc

    # --- Parsing ----------------------------------------------------------

    def iter_records(
        self, path: Path, max_uncompressed_bytes: int | None = None
    ) -> Iterator[B3HistoricalRecord]:
        """Itera os registros tipo 01 (cotação por papel) validando
        header/trailer conforme o layout oficial. Nunca aceita
        silenciosamente um arquivo truncado, fora de ordem ou com
        contagem de registros inconsistente -- levanta B3ParseError em
        vez de propagar dado financeiro fabricado."""
        self.validate_archive(path, max_uncompressed_bytes or self.daily_max_uncompressed_bytes)
        with ZipFile(path) as archive:
            entry = next(
                e
                for e in archive.infolist()
                if PurePosixPath(e.filename).name.upper().startswith("COTAHIST")
                and PurePosixPath(e.filename).suffix.upper() == ".TXT"
            )
            with archive.open(entry) as raw:
                header_seen = False
                trailer_seen = False
                detail_count = 0
                declared_total: int | None = None
                for raw_line in raw:
                    line = raw_line.decode("latin-1").rstrip("\r\n")
                    if not line:
                        continue
                    # Register Size: 245 bytes -- layout oficial não deixa
                    # margem para "maior que o esperado" ser legítimo
                    # (nunca só ">=", o excesso já seria um desvio do
                    # layout fixo, nunca dado extra honesto).
                    if len(line) != _RECORD_LENGTH:
                        raise B3ParseError(
                            f"Registro COTAHIST com tamanho inválido ({len(line)}, "
                            f"esperado exatamente {_RECORD_LENGTH})."
                        )
                    tipreg = line[_TIPREG]
                    if tipreg == "00":
                        if header_seen:
                            raise B3ParseError(
                                "Arquivo COTAHIST contém mais de um registro de "
                                "header (tipo 00)."
                            )
                        if detail_count or trailer_seen:
                            raise B3ParseError(
                                "Registro de header (tipo 00) fora de posição -- "
                                "deve ser o primeiro registro do arquivo."
                            )
                        header_seen = True
                        continue
                    if tipreg == "99":
                        if trailer_seen:
                            raise B3ParseError(
                                "Arquivo COTAHIST contém mais de um registro de "
                                "trailer (tipo 99)."
                            )
                        if not header_seen:
                            raise B3ParseError(
                                "Registro de trailer (tipo 99) antes do header "
                                "(tipo 00)."
                            )
                        trailer_seen = True
                        declared_total = self._parse_int(line[32:42])
                        continue
                    if tipreg != "01":
                        # Tipo de registro desconhecido/crítico: nunca
                        # ignorado silenciosamente como se o arquivo
                        # estivesse íntegro.
                        raise B3ParseError(f"Tipo de registro COTAHIST desconhecido: {tipreg!r}")
                    if not header_seen:
                        raise B3ParseError(
                            "Registro de detalhe (tipo 01) antes do header (tipo 00)."
                        )
                    if trailer_seen:
                        raise B3ParseError(
                            "Registro de detalhe (tipo 01) depois do trailer (tipo 99)."
                        )
                    detail_count += 1
                    yield self._parse_detail(line)

        if not header_seen:
            raise B3ParseError("Arquivo COTAHIST sem registro de header (tipo 00).")
        if not trailer_seen:
            raise B3ParseError("Arquivo COTAHIST sem registro de trailer (tipo 99).")
        if declared_total is not None and declared_total != detail_count:
            # TOTREG conta SOMENTE os registros tipo 01 (detalhe) -- NUNCA
            # inclui o próprio header/trailer, apesar do layout oficial
            # publicado ("FILE LAYOUT - HISTORICAL QUOTATIONS", B3, Review
            # 01, 17/04/2017) descrever literalmente o campo TOTAL
            # REGISTERS como "INCLUDE ALSO HEADER AND TRAILER REGISTERS".
            #
            # Reconfirmado de forma independente e reproduzível nesta
            # revisão (Correção 3, Prompt 3) com DOIS downloads ao vivo
            # distintos do endpoint oficial:
            #   - diário COTAHIST_D19082026.ZIP: TOTREG=19232, contagem
            #     manual de linhas tipo "01"=19232 (header=1, trailer=1,
            #     total de linhas=19234 -- TOTREG bate com detail_count,
            #     nunca com o total de linhas do arquivo);
            #   - anual COTAHIST_A2026.ZIP: TOTREG=2486436, contagem
            #     manual de linhas tipo "01"=2486436 (mesma semântica,
            #     mesma discrepância com o texto do PDF).
            # Diário e anual têm a MESMA semântica -- não há necessidade
            # de uma regra por variante. A documentação de 2017 está
            # desatualizada em relação à geração real atual do arquivo;
            # aceitar a suposição "declared_total - 2" (header+trailer
            # inclusos) rejeitaria TODO download real como corrompido.
            raise B3ParseError(
                "Contagem de registros do trailer COTAHIST não bate com o "
                f"arquivo: declarado={declared_total}, encontrado={detail_count}."
            )

    def _parse_detail(self, line: str) -> B3HistoricalRecord:
        try:
            trading_date = self._parse_date(line[_DATA_PREGAO], required=True)
            assert trading_date is not None
            # FATCOT (fator de cotação) é um campo numérico obrigatório do
            # layout oficial para todo registro tipo 01 -- nunca
            # legitimamente ausente/zerado para um instrumento realmente
            # cotado. Um valor em branco ou "0000000" indica um registro
            # corrompido/truncado, nunca um "sem fator declarado" que possa
            # ser honestamente assumido como 1 -- fabricar esse default
            # violaria a mesma regra "ausência nunca vira zero/inventado"
            # já aplicada a todos os outros campos deste parser.
            quote_factor = self._parse_int(line[_FATCOT])
            if not quote_factor:
                raise B3ParseError(
                    f"FATCOT ausente ou zerado ({line[_FATCOT]!r}) -- campo "
                    "obrigatório no layout oficial, nunca fabricado como 1."
                )
            return B3HistoricalRecord(
                trading_date=trading_date,
                codbdi=line[_CODBDI].strip(),
                trading_symbol=line[_CODNEG].strip(),
                market_type=line[_TPMERC],
                issuer_short_name=line[_NOMRES].strip(),
                specification=line[_ESPECI].strip(),
                forward_term_days=self._parse_text(line[_PRAZOT]),
                currency=line[_MODREF].strip(),
                open_price=self._parse_price(line[_PREABE]),
                high_price=self._parse_price(line[_PREMAX]),
                low_price=self._parse_price(line[_PREMIN]),
                average_price=self._parse_price(line[_PREMED]),
                close_price=self._parse_price(line[_PREULT]),
                best_bid_price=self._parse_price(line[_PREOFC]),
                best_ask_price=self._parse_price(line[_PREOFV]),
                trade_count=self._parse_int(line[_TOTNEG]),
                traded_quantity=self._parse_int(line[_QUATOT]),
                traded_volume=self._parse_price(line[_VOLTOT]),
                strike_price=self._parse_price(line[_PREEXE]),
                correction_indicator=self._parse_text(line[_INDOPC]),
                maturity_date=self._parse_date(line[_DATVEN], required=False),
                quote_factor=quote_factor,
                isin=self._parse_text(line[_CODISI]),
                distribution_number=self._parse_text(line[_DISMES]),
            )
        except (InvalidOperation, ValueError) as exc:
            raise B3ParseError(f"Registro COTAHIST inválido: {exc}") from exc

    @staticmethod
    def _parse_price(raw: str) -> Decimal | None:
        """(N)V99 -- valor implícito com 2 casas decimais, sem separador.
        Campo sempre numérico fixo neste layout (nunca espaço em branco
        para um registro tipo 01 válido); "0000000000000" é o valor
        oficial zero legítimo para campos não aplicáveis àquele
        instrumento (ex.: PREEXE fora do mercado de opções) -- nunca
        tratado como ausência aqui, e nunca inventado quando o campo
        realmente estiver vazio/espaço (nesse caso retorna None)."""
        text = raw.strip()
        if not text:
            return None
        return Decimal(text) / Decimal(100)

    @staticmethod
    def _parse_int(raw: str) -> int | None:
        text = raw.strip()
        if not text:
            return None
        return int(text)

    @staticmethod
    def _parse_text(raw: str) -> str | None:
        text = raw.strip()
        return text or None

    @staticmethod
    def _parse_date(raw: str, *, required: bool) -> date | None:
        text = raw.strip()
        if not text or text == _NO_DATE:
            if required:
                raise ValueError(f"Data obrigatória ausente/zerada: {raw!r}")
            return None
        return datetime.strptime(text, "%Y%m%d").date()

    # --- Cache metadata ----------------------------------------------------

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
    def _result(
        path: Path, reference_date: date, metadata: dict, cache_hit: bool
    ) -> CotahistDownloadResult:
        collected = datetime.fromisoformat(
            metadata.get("collected_at") or metadata["checked_at"]
        )
        if collected.tzinfo is None:
            collected = collected.replace(tzinfo=timezone.utc)
        return CotahistDownloadResult(
            path=path,
            reference_date=reference_date,
            etag=metadata.get("etag"),
            last_modified=metadata.get("last_modified"),
            collected_at=collected,
            cache_hit=cache_hit,
            size_bytes=int(metadata.get("size_bytes") or path.stat().st_size),
        )
