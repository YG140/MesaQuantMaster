from __future__ import annotations

import csv
import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx

from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketAuthenticationError,
    MarketInvalidResponseError,
    MarketPermissionError,
    MarketProviderUnavailableError,
    MarketRateLimitError,
)

# Domínio fechado REAL confirmado por leitura direta do recurso oficial
# vigente (auditoria desta tarefa) -- rótulos exatos observados no CSV,
# nunca inferidos do PDF de metodologia (que está desatualizado: grafa
# "IGP-M +" com hífen/espaço, enquanto o CSV real usa "IGPM+"; e não lista
# Renda+/Educa+, cujos rótulos reais só foram confirmados lendo o dataset).
# "Tesouro IGPM+ com Juros Semestrais" é histórico -- não ofertado
# atualmente, mas ainda presente no arquivo consolidado.
BOND_TYPE_SLUGS: dict[str, str] = {
    "Tesouro Selic": "selic",
    "Tesouro Prefixado": "prefixado",
    "Tesouro Prefixado com Juros Semestrais": "prefixado-juros-semestrais",
    "Tesouro IPCA+": "ipca-mais",
    "Tesouro IPCA+ com Juros Semestrais": "ipca-mais-juros-semestrais",
    "Tesouro IGPM+ com Juros Semestrais": "igpm-mais-juros-semestrais",
    "Tesouro Renda+ Aposentadoria Extra": "renda-mais",
    "Tesouro Educa+": "educa-mais",
}

# Indexador real de cada tipo -- determinístico a partir do domínio fechado
# acima, nunca adivinhado. Renda+ e Educa+ são indexados ao IPCA (confirmado
# pela documentação oficial do Tesouro Direto, e o rótulo de Tipo Titulo
# usado aqui foi confirmado por leitura direta do CSV vigente).
BOND_TYPE_INDEXER: dict[str, str] = {
    "Tesouro Selic": "SELIC",
    "Tesouro Prefixado": "PREFIXADO",
    "Tesouro Prefixado com Juros Semestrais": "PREFIXADO",
    "Tesouro IPCA+": "IPCA",
    "Tesouro IPCA+ com Juros Semestrais": "IPCA",
    "Tesouro IGPM+ com Juros Semestrais": "IGP-M",
    "Tesouro Renda+ Aposentadoria Extra": "IPCA",
    "Tesouro Educa+": "IPCA",
}

# Colunas mínimas exigidas do CSV oficial (ver auditoria) -- se o cabeçalho
# real não contiver todas, o schema mudou e o parser deve falhar de forma
# explícita, nunca interpretar posição de coluna sem cabeçalho.
REQUIRED_COLUMNS = (
    "Tipo Titulo",
    "Data Vencimento",
    "Data Base",
    "Taxa Compra Manha",
    "Taxa Venda Manha",
    "PU Compra Manha",
    "PU Venda Manha",
    "PU Base Manha",
)


def canonical_treasury_symbol(bond_type: str, maturity: date) -> str | None:
    """Identidade determinística oficial: Tipo Titulo (domínio fechado) +
    Data Vencimento -- nunca fuzzy matching, nunca "título mais parecido".
    Retorna None para um Tipo Titulo fora do domínio conhecido (nunca
    inventa um slug para um tipo não confirmado).

    Preserva o único formato já em uso no projeto (ver
    MarketService.provider_capabilities probe e
    test_extended_market_providers.py): "tesouro-selic-01032031" para
    Tesouro Selic com vencimento 01/03/2031.
    """
    slug = BOND_TYPE_SLUGS.get(bond_type)
    if slug is None:
        return None
    return f"tesouro-{slug}-{maturity:%d%m%Y}"


@dataclass(frozen=True)
class TesouroDownloadResult:
    path: Path
    etag: str | None
    last_modified: str | None
    collected_at: datetime
    cache_hit: bool
    size_bytes: int


# Índice parseado compartilhado por TODO O PROCESSO (nunca por instância de
# TesouroTransparenteProvider) -- cada request HTTP da aplicação cria uma
# nova IndicatorResolverService -> um novo TesouroTransparenteProvider (ver
# app/api/intelligence.py), então um cache por instância nunca seria
# reaproveitado entre requests, obrigando um re-parse completo de ~175 mil
# linhas a cada chamada mesmo com o arquivo já em cache em disco.
#
# Chave = identidade de VERSÃO do arquivo cacheado (path, ETag,
# Last-Modified, tamanho, mtime local -- ver latest_by_identity) -- nunca
# dados de usuário, nunca sessão de banco: só o resultado do parse de um
# dataset público do Tesouro Nacional. Qualquer publicação nova do dataset
# oficial (mesmo sem ETag) invalida naturalmente a entrada antiga (chave
# nova), sem nenhuma limpeza explícita necessária -- o volume é pequeno
# (uma entrada por versão já vista, cada uma com só ~1 linha por título,
# não as ~175 mil linhas históricas).
#
# FRONTEIRA MULTI-WORKER: isto é um dict de módulo, dentro do processo
# Python -- cada worker do Uvicorn (processo separado) tem sua PRÓPRIA
# cópia em memória, o que é esperado e aceitável (nunca cruza processos,
# nunca precisa de Redis/memcached para este dado público e de baixo
# volume). O que este cache elimina é o re-parse REDUNDANTE a cada request
# dentro do MESMO processo/worker, não a duplicação entre processos.
#
# Lock só serializa a seção crítica "checar cache, senão parsear e
# guardar" -- consultas repetidas com cache já populado (o caso comum)
# custam só um lookup de dict sob o lock, não o parse inteiro.
_PROCESS_INDEX_CACHE: dict[tuple, dict[str, dict]] = {}
_PROCESS_INDEX_CACHE_LOCK = threading.Lock()

# Lock separado para o download/escrita do arquivo em cache
# (ensure_dataset). Sem ele, duas threads do MESMO processo verificando
# "cache fresco?" ao mesmo tempo podem ambas decidir baixar e escrever o
# mesmo arquivo de destino simultaneamente -- no Windows isso pode falhar
# com PermissionError no Path.replace() final (o destino fica
# momentaneamente bloqueado pela troca da outra thread), confirmado nesta
# revisão por um teste de concorrência real. Serializa só a checagem de
# TTL + download + substituição atômica -- nunca o parse (protegido
# separadamente por _PROCESS_INDEX_CACHE_LOCK).
_DOWNLOAD_LOCK = threading.Lock()


class TesouroTransparenteProvider:
    """Coleta controlada do CSV oficial diário de preços e taxas do Tesouro
    Direto (dataset "Taxas dos Títulos Ofertados pelo Tesouro Direto",
    Tesouro Transparente/Tesouro Nacional).

    Fronteira de adaptação do contrato externo (ver AGENTS.md): converte o
    CSV oficial (`;`, decimal `,`, datas DD/MM/AAAA, colunas em português)
    para um payload canônico interno -- nenhum service/engine deve conhecer
    os nomes de coluna originais.

    Espelha a filosofia de cache/segurança já validada em
    CvmOpenDataProvider/CvmFiiOpenDataProvider: cache local com metadata
    ETag/Last-Modified, TTL, limite de download, substituição atômica do
    arquivo cacheado. Diferença deliberada: o cliente HTTP aqui NUNCA
    segue redirects (padrão do httpx, preservado explicitamente) -- não
    há necessidade oficial comprovada de redirecionamento para este
    recurso, e um client explicitamente injetado (testes,
    httpx.MockTransport) nunca é afetado por esta escolha de produção.
    """

    provider_name = "Tesouro Transparente"
    resource_name = "taxas-dos-titulos-ofertados-pelo-tesouro-direto"

    def __init__(
        self,
        dataset_url: str,
        cache_dir: Path | str = ".cache/tesouro_transparente",
        client: httpx.Client | None = None,
        timeout_seconds: float = 30,
        max_download_bytes: int = 40 * 1024 * 1024,
        # 6h, não 24h: o dataset é publicado diariamente, e treasury_rate/
        # current_price têm política de validade de só 2 dias no catálogo
        # (ver indicator_temporal_validity_days) -- um TTL de 24h poderia
        # manter uma publicação anterior em cache por quase um dia inteiro
        # antes de sequer TENTAR revalidar. Como a revalidação é barata
        # (condicional via ETag/Last-Modified -- 304 quando o dataset não
        # mudou, sem redownload), 6h reduz esse pior caso para poucas horas
        # sem gerar tráfego desnecessário (4 checagens condicionais/dia).
        cache_ttl_hours: int = 6,
    ):
        self.dataset_url = dataset_url
        self.cache_dir = Path(cache_dir)
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self.max_download_bytes = max_download_bytes
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def ensure_dataset(self) -> TesouroDownloadResult:
        """Garante o CSV oficial em cache local, respeitando TTL e
        validação condicional (ETag/Last-Modified, 304). Nunca baixa de
        novo só porque um título diferente foi consultado -- ver
        latest_by_identity, que reaproveita o mesmo arquivo cacheado para
        qualquer número de consultas.

        Serializado por _DOWNLOAD_LOCK: duas threads do mesmo processo
        checando TTL e decidindo baixar ao mesmo tempo poderiam escrever o
        mesmo arquivo de destino simultaneamente -- no Windows isso falha
        com PermissionError no Path.replace() final."""
        with _DOWNLOAD_LOCK:
            return self._ensure_dataset_locked()

    def _ensure_dataset_locked(self) -> TesouroDownloadResult:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        archive = self.cache_dir / "precotaxatesourodireto.csv"
        metadata_path = archive.with_suffix(".json")
        metadata = self._read_metadata(metadata_path)
        now = datetime.now(timezone.utc)
        if archive.exists() and metadata and self._cache_is_fresh(metadata, now):
            return self._download_result(archive, metadata, True)

        headers = {}
        if metadata.get("etag"):
            headers["If-None-Match"] = metadata["etag"]
        if metadata.get("last_modified"):
            headers["If-Modified-Since"] = metadata["last_modified"]

        temp_path: Path | None = None
        try:
            with self._client.stream(
                "GET", self.dataset_url, headers=headers
            ) as response:
                if response.status_code == 304 and archive.exists():
                    metadata["checked_at"] = now.isoformat()
                    self._write_metadata(metadata_path, metadata)
                    return self._download_result(archive, metadata, True)
                self._raise_for_status(response)
                declared = int(response.headers.get("Content-Length", "0") or 0)
                if declared > self.max_download_bytes:
                    raise MarketInvalidResponseError(
                        "Arquivo do Tesouro Transparente excede o limite de "
                        "download configurado."
                    )
                with NamedTemporaryFile(
                    "wb", delete=False, dir=self.cache_dir, suffix=".part"
                ) as temp:
                    temp_path = Path(temp.name)
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.max_download_bytes:
                            raise MarketInvalidResponseError(
                                "Arquivo do Tesouro Transparente excede o "
                                "limite de download configurado."
                            )
                        temp.write(chunk)
                temp_path.replace(archive)
                metadata = {
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "collected_at": now.isoformat(),
                    "checked_at": now.isoformat(),
                    "size_bytes": size,
                }
                self._write_metadata(metadata_path, metadata)
        except (MarketInvalidResponseError, MarketAssetNotFoundError,
                MarketAuthenticationError, MarketPermissionError,
                MarketRateLimitError, MarketProviderUnavailableError):
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            raise
        except (httpx.HTTPError, OSError) as exc:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            raise MarketProviderUnavailableError(
                "Não foi possível baixar o arquivo oficial do Tesouro "
                "Transparente."
            ) from exc
        return self._download_result(archive, metadata, False)

    def latest_by_identity(self) -> dict[str, dict]:
        """Retorna {symbol_canonico: linha_canonica}, apenas a observação
        de MAIOR Data Base por (Tipo Titulo, Data Vencimento) -- nunca a
        primeira linha física do arquivo (o CSV não é ordenado
        cronologicamente por título; a mesma identidade pode ter dezenas
        de Data Base espalhadas fora de ordem). Nunca mantém as ~175 mil
        linhas históricas em memória: um único passe constrói só o índice
        final (uma linha por identidade).

        Reaproveita um índice já calculado, compartilhado por PROCESSO (ver
        _PROCESS_INDEX_CACHE), enquanto o arquivo em cache não mudar (mesma
        identidade de versão -- ver cache_key abaixo) -- nunca por
        instância: cada request HTTP real da aplicação cria uma
        IndicatorResolverService/TesouroTransparenteProvider novos (ver
        app/api/intelligence.py), então um cache só de instância nunca
        seria reaproveitado entre requests.
        """
        result = self.ensure_dataset()
        # Identidade de VERSÃO do arquivo, não só de conteúdo "aproximado":
        # ETag (quando o servidor o envia) já basta sozinho na prática, mas
        # nem todo servidor garante ETag em toda resposta -- por isso
        # last_modified também entra na chave (já coletado do cabeçalho
        # oficial, sem custo adicional). Mesmo se AMBOS estiverem ausentes
        # e o tamanho coincidir entre duas publicações diferentes
        # (conteúdo genuinamente diferente, tamanho igual por coincidência
        # -- cenário raro mas não impossível), st_mtime_ns do arquivo local
        # ainda distingue as versões: toda substituição real do cache
        # (temp_path.replace(archive), só ocorre em um download 200 novo,
        # nunca em cache_hit nem em 304) atualiza o mtime do arquivo no
        # sistema de arquivos -- nunca um hash de 14 MB por request, só
        # metadados já disponíveis/uma chamada stat() barata.
        cache_key = (
            str(result.path),
            result.etag,
            result.last_modified,
            result.size_bytes,
            result.path.stat().st_mtime_ns,
        )
        with _PROCESS_INDEX_CACHE_LOCK:
            cached = _PROCESS_INDEX_CACHE.get(cache_key)
            if cached is not None:
                return cached
            index = self._build_index(result.path)
            _PROCESS_INDEX_CACHE[cache_key] = index
            return index

    def _build_index(self, path: Path) -> dict[str, dict]:
        index: dict[str, dict] = {}
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            self._validate_header(reader.fieldnames)
            for row in reader:
                parsed = self._parse_row(row)
                if parsed is None:
                    continue
                existing = index.get(parsed["symbol"])
                if existing is None or parsed["asOfDate"] > existing["asOfDate"]:
                    index[parsed["symbol"]] = parsed
        return index

    @staticmethod
    def _validate_header(fieldnames) -> None:
        present = set(fieldnames or ())
        missing = [column for column in REQUIRED_COLUMNS if column not in present]
        if missing:
            raise MarketInvalidResponseError(
                "Schema do Tesouro Transparente mudou -- colunas ausentes: "
                + ", ".join(missing)
            )

    @staticmethod
    def _parse_row(row: dict) -> dict | None:
        bond_type = (row.get("Tipo Titulo") or "").strip()
        maturity = TesouroTransparenteProvider._parse_date(row.get("Data Vencimento"))
        as_of = TesouroTransparenteProvider._parse_date(row.get("Data Base"))
        if not bond_type or maturity is None or as_of is None:
            return None
        symbol = canonical_treasury_symbol(bond_type, maturity)
        if symbol is None:
            return None
        return {
            "symbol": symbol,
            "bondType": bond_type,
            "indexer": BOND_TYPE_INDEXER.get(bond_type),
            "maturityDate": maturity,
            "asOfDate": as_of,
            "buyRate": TesouroTransparenteProvider._parse_decimal(
                row.get("Taxa Compra Manha")
            ),
            "sellRate": TesouroTransparenteProvider._parse_decimal(
                row.get("Taxa Venda Manha")
            ),
            "buyPrice": TesouroTransparenteProvider._parse_decimal(
                row.get("PU Compra Manha")
            ),
            "sellPrice": TesouroTransparenteProvider._parse_decimal(
                row.get("PU Venda Manha")
            ),
            "basePrice": TesouroTransparenteProvider._parse_decimal(
                row.get("PU Base Manha")
            ),
        }

    @staticmethod
    def _parse_date(value) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _parse_decimal(value) -> Decimal | None:
        # Decimal brasileiro (vírgula) -- confirmado por leitura direta do
        # recurso oficial vigente que NUNCA usa separador de milhar (nem
        # mesmo em PUs > 1000, ex.: "18737,11"), apesar do PDF de
        # metodologia descrever um separador de milhar por ponto. Nunca
        # remove pontos aqui: fazê-lo por suposição corromperia um valor
        # real caso o formato mude para incluir separador de milhar no
        # futuro sem essa suposição ter sido reconfirmada.
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = Decimal(text.replace(",", "."))
        except InvalidOperation:
            return None
        # Normaliza APENAS zero negativo ("-0,00", real na fonte oficial
        # para títulos com spread comprimido perto do vencimento) -- nunca
        # um valor negativo genuíno (ex.: -0,01 permanece -0,01). Evita
        # exibir "-0,00%"/"-0.00" na interface, sem alterar magnitude nem
        # sinal de nenhum outro valor.
        return abs(parsed) if parsed == 0 else parsed

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 300:
            return
        if 300 <= status_code < 400:
            # 304 já é tratado explicitamente ANTES desta chamada (fluxo
            # de cache condicional -- ver ensure_dataset). Qualquer outro
            # 3xx chegando aqui (301/302/303/307/308) significa que o
            # servidor tentou redirecionar -- o client de produção nunca
            # habilita follow_redirects=True, então o corpo desta resposta
            # NUNCA é o CSV real (pode ser vazio ou uma página HTML de
            # redirecionamento). Tratar como sucesso aqui promoveria esse
            # corpo a cache válido antes de qualquer validação de schema
            # -- por isso falha aqui, antes de ler/gravar qualquer byte.
            raise MarketInvalidResponseError(
                "Tesouro Transparente respondeu com redirecionamento -- "
                "não seguido por política de segurança."
            )
        if status_code == 401:
            raise MarketAuthenticationError(
                "Acesso ao Tesouro Transparente não autorizado."
            )
        if status_code == 403:
            raise MarketPermissionError(
                "Recurso do Tesouro Transparente não permitido."
            )
        if status_code == 404:
            raise MarketAssetNotFoundError(
                "Recurso do Tesouro Transparente não encontrado."
            )
        if status_code == 429:
            raise MarketRateLimitError(
                "Limite de consultas ao Tesouro Transparente atingido."
            )
        raise MarketProviderUnavailableError(
            "Tesouro Transparente temporariamente indisponível."
        )

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
    ) -> TesouroDownloadResult:
        collected = datetime.fromisoformat(
            metadata.get("collected_at") or metadata["checked_at"]
        )
        return TesouroDownloadResult(
            path=path,
            etag=metadata.get("etag"),
            last_modified=metadata.get("last_modified"),
            collected_at=collected,
            cache_hit=cache_hit,
            size_bytes=int(metadata.get("size_bytes") or path.stat().st_size),
        )
