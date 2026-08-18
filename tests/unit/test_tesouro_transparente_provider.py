from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.providers.exceptions import (
    MarketAssetNotFoundError,
    MarketAuthenticationError,
    MarketInvalidResponseError,
    MarketPermissionError,
    MarketProviderUnavailableError,
    MarketRateLimitError,
)
from app.providers.tesouro_transparente_provider import (
    TesouroTransparenteProvider,
    canonical_treasury_symbol,
)


@pytest.fixture
def safe_tmp_dir():
    """Diretório temporário próprio, fora da fixture `tmp_path` do pytest
    (PermissionError conhecido de limpeza compartilhada no Windows -- ver
    memória do projeto). Nome único (UUID), limpo explicitamente ao final
    de cada teste; nunca deixa nada persistente no repositório."""
    path = Path(tempfile.gettempdir()) / f"mesaqm_tesouro_test_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


HEADER = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha"
)

# Fixture sintética PEQUENA, mas fiel ao contrato oficial real confirmado
# na auditoria (colunas, delimitador `;`, decimal `,`, datas DD/MM/AAAA,
# rótulos exatos de Tipo Titulo -- inclusive Renda+/Educa+ com os rótulos
# REAIS observados no recurso oficial vigente, não os nomes "óbvios" que a
# documentação desatualizada sugeriria).
ROWS = [
    # Duas Data Base para a MESMA identidade (Selic 01/03/2031), fora de
    # ordem cronológica no arquivo -- a mais recente (18/08/2026) aparece
    # ANTES da mais antiga (15/08/2026), replicando o que a auditoria
    # confirmou no CSV real (não ordenado por Data Base).
    "Tesouro Selic;01/03/2031;18/08/2026;0,07;0,08;18750,00;18730,00;18730,00",
    "Tesouro Selic;01/03/2031;15/08/2026;0,09;0,10;18737,11;18717,77;18717,77",
    "Tesouro Prefixado;01/01/2029;18/08/2026;11,50;11,60;700,00;698,00;699,00",
    "Tesouro Prefixado com Juros Semestrais;01/01/2035;18/08/2026;12,00;12,10;900,00;890,00;891,00",
    "Tesouro IPCA+;15/05/2035;18/08/2026;6,20;6,30;3000,00;2990,00;2995,00",
    "Tesouro IPCA+ com Juros Semestrais;15/08/2040;18/08/2026;6,50;6,60;3500,00;3480,00;3490,00",
    "Tesouro Renda+ Aposentadoria Extra;15/12/2059;18/08/2026;6,91;7,03;1041,13;1015,92;1015,92",
    "Tesouro Educa+;15/12/2037;18/08/2026;7,30;7,42;2467,08;2441,14;2441,14",
    "Tesouro IGPM+ com Juros Semestrais;01/01/2031;18/08/2026;7,00;7,10;2000,00;1990,00;1995,00",
]


def csv_content(rows=None) -> bytes:
    body = "\n".join([HEADER, *(rows if rows is not None else ROWS)])
    return body.encode("utf-8")


def make_provider(safe_tmp_dir, handler=None, **kwargs) -> TesouroTransparenteProvider:
    client = None
    if handler is not None:
        client = httpx.Client(transport=httpx.MockTransport(handler))
    return TesouroTransparenteProvider(
        dataset_url="https://www.tesourotransparente.gov.br/ckan/dataset/x/download/y.csv",
        cache_dir=safe_tmp_dir / "cache",
        client=client,
        **kwargs,
    )


def ok_handler(body=None, headers=None):
    def handler(request):
        return httpx.Response(
            200,
            content=body if body is not None else csv_content(),
            headers=headers or {"ETag": '"abc"', "Last-Modified": "Tue, 18 Aug 2026 10:00:00 GMT"},
        )

    return handler


# --- Identidade canônica determinística --------------------------------


def test_canonical_symbol_matches_the_one_convention_already_in_the_codebase():
    assert canonical_treasury_symbol("Tesouro Selic", date(2031, 3, 1)) == (
        "tesouro-selic-01032031"
    )


@pytest.mark.parametrize(
    "bond_type,expected_slug",
    [
        ("Tesouro Selic", "selic"),
        ("Tesouro Prefixado", "prefixado"),
        ("Tesouro Prefixado com Juros Semestrais", "prefixado-juros-semestrais"),
        ("Tesouro IPCA+", "ipca-mais"),
        ("Tesouro IPCA+ com Juros Semestrais", "ipca-mais-juros-semestrais"),
        ("Tesouro Renda+ Aposentadoria Extra", "renda-mais"),
        ("Tesouro Educa+", "educa-mais"),
        ("Tesouro IGPM+ com Juros Semestrais", "igpm-mais-juros-semestrais"),
    ],
)
def test_canonical_symbol_covers_every_known_bond_type(bond_type, expected_slug):
    symbol = canonical_treasury_symbol(bond_type, date(2030, 1, 1))
    assert symbol == f"tesouro-{expected_slug}-01012030"


def test_canonical_symbol_returns_none_for_unknown_bond_type_never_fabricates():
    assert canonical_treasury_symbol("Tesouro Inexistente XYZ", date(2030, 1, 1)) is None


# --- Parsing: delimitador, decimal BR, datas, cabeçalho -----------------


def test_parses_semicolon_delimiter_and_brazilian_decimal(safe_tmp_dir):
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    index = provider.latest_by_identity()
    row = index["tesouro-selic-01032031"]
    assert row["buyRate"] == Decimal("0.07")
    assert row["buyPrice"] == Decimal("18750.00")
    # NUNCA 7,46 -> 746: a vírgula é decimal, nunca removida como se fosse
    # separador de milhar.
    assert row["buyRate"] != Decimal("7")


def test_parses_dd_mm_yyyy_dates_into_real_date_objects(safe_tmp_dir):
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    row = provider.latest_by_identity()["tesouro-selic-01032031"]
    assert row["maturityDate"] == date(2031, 3, 1)
    assert row["asOfDate"] == date(2026, 8, 18)


def test_valid_header_parses_successfully(safe_tmp_dir):
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    assert len(provider.latest_by_identity()) == len(ROWS) - 1  # 2 linhas colapsam em 1


def test_invalid_header_missing_column_fails_explicitly(safe_tmp_dir):
    bad_header = HEADER.replace("Taxa Compra Manha;", "")
    body = "\n".join([bad_header, ROWS[0]]).encode("utf-8")
    provider = make_provider(safe_tmp_dir, handler=ok_handler(body=body))
    with pytest.raises(MarketInvalidResponseError, match="Schema"):
        provider.latest_by_identity()


def test_empty_csv_never_crashes_returns_empty_index(safe_tmp_dir):
    provider = make_provider(safe_tmp_dir, handler=ok_handler(body=HEADER.encode("utf-8")))
    assert provider.latest_by_identity() == {}


def test_malformed_row_is_skipped_never_crashes_the_whole_parse(safe_tmp_dir):
    rows = [*ROWS, "linha completamente malformada sem delimitador correto"]
    provider = make_provider(safe_tmp_dir, handler=ok_handler(body=csv_content(rows)))
    index = provider.latest_by_identity()
    assert "tesouro-selic-01032031" in index


# --- Escolha da linha mais recente (maior Data Base) ---------------------


def test_picks_highest_data_base_never_first_physical_line(safe_tmp_dir):
    """CRÍTICO (seção 15): o CSV é histórico e não ordenado -- a fixture
    coloca a Data Base mais RECENTE (18/08) na PRIMEIRA linha física e a
    mais antiga (15/08) depois, para provar que a escolha é por
    comparação de Data Base, não por "primeira linha encontrada"."""
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    row = provider.latest_by_identity()["tesouro-selic-01032031"]
    assert row["asOfDate"] == date(2026, 8, 18)
    assert row["buyRate"] == Decimal("0.07")  # da linha de 18/08, nao 15/08


def test_older_data_base_never_wins_over_newer_even_if_it_appears_later(safe_tmp_dir):
    # Mesma identidade, mas agora a Data Base mais recente aparece POR
    # ÚLTIMO no arquivo -- também não pode vencer por ordem física.
    rows = [
        "Tesouro Selic;01/03/2031;15/08/2026;0,09;0,10;18737,11;18717,77;18717,77",
        "Tesouro Selic;01/03/2031;18/08/2026;0,07;0,08;18750,00;18730,00;18730,00",
    ]
    provider = make_provider(safe_tmp_dir, handler=ok_handler(body=csv_content(rows)))
    row = provider.latest_by_identity()["tesouro-selic-01032031"]
    assert row["asOfDate"] == date(2026, 8, 18)


# --- Cobertura dos tipos reais de título ---------------------------------


@pytest.mark.parametrize(
    "symbol,bond_type,indexer",
    [
        ("tesouro-selic-01032031", "Tesouro Selic", "SELIC"),
        ("tesouro-prefixado-01012029", "Tesouro Prefixado", "PREFIXADO"),
        (
            "tesouro-prefixado-juros-semestrais-01012035",
            "Tesouro Prefixado com Juros Semestrais",
            "PREFIXADO",
        ),
        ("tesouro-ipca-mais-15052035", "Tesouro IPCA+", "IPCA"),
        (
            "tesouro-ipca-mais-juros-semestrais-15082040",
            "Tesouro IPCA+ com Juros Semestrais",
            "IPCA",
        ),
        (
            "tesouro-renda-mais-15122059",
            "Tesouro Renda+ Aposentadoria Extra",
            "IPCA",
        ),
        ("tesouro-educa-mais-15122037", "Tesouro Educa+", "IPCA"),
        (
            "tesouro-igpm-mais-juros-semestrais-01012031",
            "Tesouro IGPM+ com Juros Semestrais",
            "IGP-M",
        ),
    ],
)
def test_every_real_bond_type_resolves_with_correct_derived_indexer(
    safe_tmp_dir, symbol, bond_type, indexer
):
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    row = provider.latest_by_identity()[symbol]
    assert row["bondType"] == bond_type
    assert row["indexer"] == indexer


def test_multiple_titles_all_present_in_the_same_index(safe_tmp_dir):
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    index = provider.latest_by_identity()
    assert len(index) == 8


# --- Campos preservados no payload canônico (compra/venda/base) ---------


def test_sell_rate_buy_price_sell_price_base_price_all_preserved(safe_tmp_dir):
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    row = provider.latest_by_identity()["tesouro-prefixado-juros-semestrais-01012035"]
    assert row["buyRate"] == Decimal("12.00")
    assert row["sellRate"] == Decimal("12.10")
    assert row["buyPrice"] == Decimal("900.00")
    assert row["sellPrice"] == Decimal("890.00")
    assert row["basePrice"] == Decimal("891.00")


def test_as_of_date_maps_to_data_base(safe_tmp_dir):
    provider = make_provider(safe_tmp_dir, handler=ok_handler())
    row = provider.latest_by_identity()["tesouro-selic-01032031"]
    assert row["asOfDate"] == date(2026, 8, 18)


# --- Limite de tamanho, timeout, HTTP 4xx/5xx ----------------------------


def test_declared_content_length_over_limit_is_rejected(safe_tmp_dir):
    def handler(request):
        return httpx.Response(
            200, content=csv_content(), headers={"Content-Length": "999999999"}
        )

    provider = make_provider(safe_tmp_dir, handler=handler, max_download_bytes=100)
    with pytest.raises(MarketInvalidResponseError, match="limite"):
        provider.latest_by_identity()


def test_actual_response_larger_than_limit_is_rejected_with_accurate_content_length(
    safe_tmp_dir,
):
    def handler(request):
        return httpx.Response(200, content=csv_content())

    provider = make_provider(safe_tmp_dir, handler=handler, max_download_bytes=10)
    with pytest.raises(MarketInvalidResponseError, match="limite"):
        provider.latest_by_identity()


def test_timeout_raises_provider_unavailable(safe_tmp_dir):
    def handler(request):
        raise httpx.TimeoutException("timeout", request=request)

    provider = make_provider(safe_tmp_dir, handler=handler)
    with pytest.raises(MarketProviderUnavailableError):
        provider.latest_by_identity()


@pytest.mark.parametrize(
    "status_code,expected_exception",
    [
        (401, MarketAuthenticationError),
        (403, MarketPermissionError),
        (404, MarketAssetNotFoundError),
        (429, MarketRateLimitError),
        (500, MarketProviderUnavailableError),
        (503, MarketProviderUnavailableError),
    ],
)
def test_http_error_status_codes_map_to_typed_exceptions(
    safe_tmp_dir, status_code, expected_exception
):
    provider = make_provider(
        safe_tmp_dir, handler=lambda request: httpx.Response(status_code)
    )
    with pytest.raises(expected_exception):
        provider.latest_by_identity()


# --- Cache: primeira consulta baixa, segunda reaproveita -----------------


def test_second_query_never_redownloads_within_ttl(safe_tmp_dir):
    calls = []

    def handler(request):
        calls.append(1)
        return ok_handler()(request)

    provider = make_provider(safe_tmp_dir, handler=handler, cache_ttl_hours=24)
    provider.latest_by_identity()
    provider.latest_by_identity()
    provider.latest_by_identity()
    assert len(calls) == 1


def test_different_titles_share_the_same_cached_download_and_parsed_index(safe_tmp_dir):
    """Anti-pattern proibido (seção 15): título A -> download completo,
    título B -> download completo de novo. Uma única leitura/parsing deve
    servir qualquer número de títulos."""
    calls = []

    def handler(request):
        calls.append(1)
        return ok_handler()(request)

    provider = make_provider(safe_tmp_dir, handler=handler)
    index = provider.latest_by_identity()
    assert "tesouro-selic-01032031" in index
    assert "tesouro-prefixado-01012029" in index
    assert "tesouro-educa-mais-15122037" in index
    assert len(calls) == 1


def test_cache_expired_by_ttl_triggers_new_download(safe_tmp_dir):
    calls = []

    def handler(request):
        calls.append(1)
        return ok_handler()(request)

    provider = make_provider(safe_tmp_dir, handler=handler, cache_ttl_hours=0)
    provider.latest_by_identity()
    provider2 = make_provider(safe_tmp_dir, handler=handler, cache_ttl_hours=0)
    provider2.latest_by_identity()
    assert len(calls) == 2


def test_conditional_get_sends_etag_and_last_modified_when_cache_present(safe_tmp_dir):
    cache_dir = safe_tmp_dir / "cache"
    cache_dir.mkdir(parents=True)
    archive = cache_dir / "precotaxatesourodireto.csv"
    archive.write_bytes(csv_content())
    (archive.with_suffix(".json")).write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00","collected_at":"2020-01-01T00:00:00+00:00",'
        '"etag":"abc123","last_modified":"Mon, 01 Jan 2020 00:00:00 GMT","size_bytes":100}',
        encoding="utf-8",
    )

    def handler(request):
        assert request.headers["if-none-match"] == "abc123"
        assert request.headers["if-modified-since"] == "Mon, 01 Jan 2020 00:00:00 GMT"
        return httpx.Response(304)

    provider = TesouroTransparenteProvider(
        dataset_url="https://x/y.csv",
        cache_dir=cache_dir,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_ttl_hours=0,
    )
    result = provider.ensure_dataset()
    assert result.cache_hit is True


def test_304_not_modified_reuses_existing_cached_file_content(safe_tmp_dir):
    cache_dir = safe_tmp_dir / "cache"
    cache_dir.mkdir(parents=True)
    archive = cache_dir / "precotaxatesourodireto.csv"
    archive.write_bytes(csv_content())
    (archive.with_suffix(".json")).write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00","collected_at":"2020-01-01T00:00:00+00:00",'
        '"etag":"abc123","last_modified":"y","size_bytes":100}',
        encoding="utf-8",
    )
    provider = TesouroTransparenteProvider(
        dataset_url="https://x/y.csv",
        cache_dir=cache_dir,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(304))
        ),
        cache_ttl_hours=0,
    )
    index = provider.latest_by_identity()
    assert "tesouro-selic-01032031" in index


def test_failed_refresh_never_destroys_existing_valid_cache(safe_tmp_dir):
    cache_dir = safe_tmp_dir / "cache"
    cache_dir.mkdir(parents=True)
    archive = cache_dir / "precotaxatesourodireto.csv"
    archive.write_bytes(csv_content())
    (archive.with_suffix(".json")).write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00","collected_at":"2020-01-01T00:00:00+00:00",'
        '"etag":"abc123","last_modified":"y","size_bytes":100}',
        encoding="utf-8",
    )
    provider = TesouroTransparenteProvider(
        dataset_url="https://x/y.csv",
        cache_dir=cache_dir,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        ),
        cache_ttl_hours=0,
    )
    with pytest.raises(MarketProviderUnavailableError):
        provider.latest_by_identity()
    # O arquivo cacheado anterior continua intacto -- uma falha de refresh
    # nunca apaga um cache válido existente.
    assert archive.exists()
    assert archive.read_bytes() == csv_content()


def test_injected_mock_transport_client_is_never_overridden_by_defaults(safe_tmp_dir):
    """Nenhum teste unitário deste arquivo depende de rede real -- todos
    usam httpx.MockTransport injetado via `client=`, nunca o client
    default de produção. A chamada só pode ter sucesso se o handler
    injetado (e não um socket real) tiver respondido."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return ok_handler()(request)

    provider = make_provider(safe_tmp_dir, handler=handler)
    provider.latest_by_identity()
    assert len(seen) == 1
    assert seen[0].startswith("https://www.tesourotransparente.gov.br/")


# --- Reparse entre instâncias (revisão de performance) -------------------


def test_two_separate_instances_share_the_same_cached_parsed_index(safe_tmp_dir):
    """CRÍTICO: cada request HTTP real da aplicação cria uma
    IndicatorResolverService/TesouroTransparenteProvider NOVOS (ver
    app/api/intelligence.py) -- um cache só de instância nunca seria
    reaproveitado entre requests, forçando reparse de ~175 mil linhas a
    cada chamada mesmo com o arquivo já em cache em disco. Prova
    comportamental: a instância 2 (abandonada e recriada, MESMO
    cache_dir) nunca chama `_build_index` de novo -- só a instância 1
    paga esse custo."""
    from app.providers import tesouro_transparente_provider as module

    build_calls = []
    original_build_index = module.TesouroTransparenteProvider._build_index

    def counting_build_index(self, path):
        build_calls.append(path)
        return original_build_index(self, path)

    module.TesouroTransparenteProvider._build_index = counting_build_index
    try:
        calls = []

        def handler(request):
            calls.append(1)
            return ok_handler()(request)

        cache_dir = safe_tmp_dir / "shared_cache"

        provider_a = TesouroTransparenteProvider(
            dataset_url="https://www.tesourotransparente.gov.br/x/y.csv",
            cache_dir=cache_dir,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        index_a = provider_a.latest_by_identity()
        assert "tesouro-selic-01032031" in index_a
        del provider_a  # instância 1 abandonada -- nada de estado sobrevive nela

        provider_b = TesouroTransparenteProvider(
            dataset_url="https://www.tesourotransparente.gov.br/x/y.csv",
            cache_dir=cache_dir,  # MESMO cache_dir -- simula outra request
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        index_b = provider_b.latest_by_identity()
        assert "tesouro-prefixado-01012029" in index_b

        assert len(calls) == 1  # 1 download HTTP no total (TTL ainda válido)
        assert len(build_calls) == 1  # 1 PARSE completo no total -- nunca 2
    finally:
        module.TesouroTransparenteProvider._build_index = original_build_index


def test_five_sequential_new_instances_parse_only_once(safe_tmp_dir):
    """Simula 5 requests HTTP sequenciais (5 instâncias novas do
    provider), mesmo cache_dir -- o parse completo (~175 mil linhas no
    dataset real) só pode acontecer 1 vez no total."""
    from app.providers import tesouro_transparente_provider as module

    build_calls = []
    original_build_index = module.TesouroTransparenteProvider._build_index

    def counting_build_index(self, path):
        build_calls.append(path)
        return original_build_index(self, path)

    module.TesouroTransparenteProvider._build_index = counting_build_index
    try:
        http_calls = []

        def handler(request):
            http_calls.append(1)
            return ok_handler()(request)

        cache_dir = safe_tmp_dir / "shared_cache_5x"
        for _ in range(5):
            provider = TesouroTransparenteProvider(
                dataset_url="https://www.tesourotransparente.gov.br/x/y.csv",
                cache_dir=cache_dir,
                client=httpx.Client(transport=httpx.MockTransport(handler)),
            )
            index = provider.latest_by_identity()
            assert len(index) == 8
            del provider

        assert len(http_calls) == 1
        assert len(build_calls) == 1
    finally:
        module.TesouroTransparenteProvider._build_index = original_build_index


def test_benchmark_parse_cost_first_vs_reused_vs_new_instance(safe_tmp_dir):
    """Benchmark simples (não microbenchmark): mede o custo aproximado de
    (1) primeira construção do índice, (2) consulta adicional na MESMA
    instância, (3) nova instância com cache/índice já existentes, (4) 5
    instâncias sequenciais simulando requests. A fixture é pequena (9
    linhas) -- o ganho real em produção escala com o tamanho do CSV
    oficial (~175 mil linhas), não com esta fixture.

    A prova de CORREÇÃO é por CONTAGEM de chamadas a `_build_index`
    (determinística), não por tempo de parede: em uma fixture de 9 linhas
    o custo absoluto é da ordem de microssegundos, dominado por ruído do
    agendador de threads/GC -- inadequado para asserção estrita de tempo.
    Os tempos abaixo são só informativos (print), não asserções."""
    from app.providers import tesouro_transparente_provider as module

    build_calls = []
    original_build_index = module.TesouroTransparenteProvider._build_index

    def counting_build_index(self, path):
        build_calls.append(path)
        return original_build_index(self, path)

    module.TesouroTransparenteProvider._build_index = counting_build_index
    try:
        def handler(request):
            return ok_handler()(request)

        cache_dir = safe_tmp_dir / "benchmark_cache"

        provider_1 = TesouroTransparenteProvider(
            dataset_url="https://www.tesourotransparente.gov.br/x/y.csv",
            cache_dir=cache_dir,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        t0 = time.perf_counter()
        provider_1.latest_by_identity()
        first_build_ms = (time.perf_counter() - t0) * 1000
        assert len(build_calls) == 1

        t0 = time.perf_counter()
        provider_1.latest_by_identity()
        same_instance_ms = (time.perf_counter() - t0) * 1000
        assert len(build_calls) == 1  # reuso -- nenhum parse adicional

        provider_2 = TesouroTransparenteProvider(
            dataset_url="https://www.tesourotransparente.gov.br/x/y.csv",
            cache_dir=cache_dir,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        t0 = time.perf_counter()
        provider_2.latest_by_identity()
        new_instance_ms = (time.perf_counter() - t0) * 1000
        assert len(build_calls) == 1  # nova instância, mesmo cache -- ainda 1

        five_instances_start = time.perf_counter()
        for _ in range(5):
            p = TesouroTransparenteProvider(
                dataset_url="https://www.tesourotransparente.gov.br/x/y.csv",
                cache_dir=cache_dir,
                client=httpx.Client(transport=httpx.MockTransport(handler)),
            )
            p.latest_by_identity()
        five_instances_ms = (time.perf_counter() - five_instances_start) * 1000
        assert len(build_calls) == 1  # 5 instâncias novas -- ainda só 1 parse total

        print(
            f"\n[benchmark, informativo -- fixture de 9 linhas] "
            f"primeira construcao={first_build_ms:.3f}ms "
            f"mesma instancia (reuso)={same_instance_ms:.3f}ms "
            f"nova instancia (reuso compartilhado)={new_instance_ms:.3f}ms "
            f"5 instancias sequenciais (total)={five_instances_ms:.3f}ms "
            f"parses completos no total={len(build_calls)}"
        )
    finally:
        module.TesouroTransparenteProvider._build_index = original_build_index


# --- Hard cap durante a transferência (nunca só depois de bufferizar) ---


def test_chunked_body_without_content_length_over_limit_aborts_mid_stream(
    safe_tmp_dir,
):
    """Seção 7/8: o limite precisa ser aplicado DURANTE a transferência,
    nunca só depois do corpo inteiro já estar em memória. Corpo servido
    via generator (transfer-encoding chunked, SEM Content-Length -- ver
    verificação de httpx.Response abaixo) maior que o limite configurado."""

    def big_body_generator():
        chunk = b"x" * 1024
        for _ in range(200):  # ~200 KiB, sem declarar Content-Length
            yield chunk

    def handler(request):
        response = httpx.Response(200, content=big_body_generator())
        assert "content-length" not in response.headers
        return response

    provider = make_provider(safe_tmp_dir, handler=handler, max_download_bytes=1024 * 50)
    with pytest.raises(MarketInvalidResponseError, match="limite"):
        provider.latest_by_identity()

    # Nenhum arquivo cacheado promovido a partir do download abortado --
    # nem o .part temporário nem um "precotaxatesourodireto.csv" parcial.
    cache_dir = safe_tmp_dir / "cache"
    assert not (cache_dir / "precotaxatesourodireto.csv").exists()
    assert not any(cache_dir.glob("*.part"))


def test_failed_hardcap_download_never_destroys_previously_valid_cache(safe_tmp_dir):
    cache_dir = safe_tmp_dir / "cache"
    cache_dir.mkdir(parents=True)
    archive = cache_dir / "precotaxatesourodireto.csv"
    archive.write_bytes(csv_content())
    (archive.with_suffix(".json")).write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00","collected_at":"2020-01-01T00:00:00+00:00",'
        '"etag":"abc123","last_modified":"y","size_bytes":100}',
        encoding="utf-8",
    )

    def big_body_generator():
        chunk = b"x" * 1024
        for _ in range(200):
            yield chunk

    provider = TesouroTransparenteProvider(
        dataset_url="https://x/y.csv",
        cache_dir=cache_dir,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=big_body_generator())
            )
        ),
        cache_ttl_hours=0,
        max_download_bytes=1024 * 50,
    )
    with pytest.raises(MarketInvalidResponseError):
        provider.latest_by_identity()
    assert archive.exists()
    assert archive.read_bytes() == csv_content()


# --- Redirects nunca seguidos automaticamente -----------------------------


def test_redirect_is_never_followed(safe_tmp_dir):
    """httpx não segue redirects por padrão -- este teste comprova que a
    implementação NUNCA habilitou follow_redirects=True no client de
    produção/testável. Um 302 apontando para um host arbitrário nunca
    deve virar uma segunda requisição nem um sucesso silencioso."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://127.0.0.1:12345/arquivo.csv"},
        )

    provider = make_provider(safe_tmp_dir, handler=handler)
    with pytest.raises(
        (MarketInvalidResponseError, MarketProviderUnavailableError, MarketAssetNotFoundError)
    ):
        provider.latest_by_identity()
    # Nunca uma segunda requisição (que seguiria o redirect).
    assert len(seen) == 1


def test_redirect_never_destroys_previously_valid_cache(safe_tmp_dir):
    cache_dir = safe_tmp_dir / "cache"
    cache_dir.mkdir(parents=True)
    archive = cache_dir / "precotaxatesourodireto.csv"
    archive.write_bytes(csv_content())
    (archive.with_suffix(".json")).write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00","collected_at":"2020-01-01T00:00:00+00:00",'
        '"etag":"abc123","last_modified":"y","size_bytes":100}',
        encoding="utf-8",
    )
    provider = TesouroTransparenteProvider(
        dataset_url="https://x/y.csv",
        cache_dir=cache_dir,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    302, headers={"Location": "http://127.0.0.1:12345/x.csv"}
                )
            )
        ),
        cache_ttl_hours=0,
    )
    with pytest.raises(Exception):
        provider.latest_by_identity()
    assert archive.exists()
    assert archive.read_bytes() == csv_content()


# --- TTL revisado (seção 11) ----------------------------------------------


def test_default_cache_ttl_is_six_hours_not_twenty_four(safe_tmp_dir):
    """Dataset publicado diariamente + treasury_rate/current_price com só
    2 dias de validade no catálogo -- 24h deixaria o cache defasado por
    quase um dia inteiro antes de sequer revalidar. Revalidação é barata
    (condicional, 304 sem redownload quando o ETag não mudou), então 6h é
    o menor ajuste coerente."""
    from datetime import timedelta

    provider = TesouroTransparenteProvider(dataset_url="https://x/y.csv")
    assert provider.cache_ttl == timedelta(hours=6)


# --- Zero negativo nunca exibido (seção 13) -------------------------------


def test_negative_zero_rate_is_normalized_to_positive_zero(safe_tmp_dir):
    rows = [
        "Tesouro Selic;01/03/2027;17/08/2026;-0,00;0,01;19681,49;19670,23;19670,23",
    ]
    provider = make_provider(safe_tmp_dir, handler=ok_handler(body=csv_content(rows)))
    row = provider.latest_by_identity()["tesouro-selic-01032027"]
    assert str(row["buyRate"]) == "0.00"
    assert row["buyRate"] == Decimal("0.00")


def test_real_negative_values_are_never_altered_by_zero_normalization(safe_tmp_dir):
    rows = [
        "Tesouro Selic;01/03/2027;17/08/2026;-0,05;0,01;19681,49;19670,23;19670,23",
    ]
    provider = make_provider(safe_tmp_dir, handler=ok_handler(body=csv_content(rows)))
    row = provider.latest_by_identity()["tesouro-selic-01032027"]
    assert row["buyRate"] == Decimal("-0.05")
    assert str(row["buyRate"]) == "-0.05"


# --- Invalidação do índice compartilhado quando o dataset muda -----------


def test_new_dataset_version_never_reuses_the_old_shared_index(safe_tmp_dir):
    """O índice compartilhado por processo (_PROCESS_INDEX_CACHE) é
    chaveado por (path, ETag, tamanho) -- quando o dataset oficial é
    republicado com conteúdo novo (novo ETag/tamanho), a chave muda
    automaticamente e o índice antigo nunca é reaproveitado
    incorretamente, mesmo com o MESMO cache_dir/path físico."""
    old_rows = ["Tesouro Selic;01/03/2031;15/08/2026;0,09;0,10;18737,11;18717,77;18717,77"]
    new_rows = ["Tesouro Selic;01/03/2031;18/08/2026;0,50;0,55;18999,00;18980,00;18980,00"]

    responses = [
        httpx.Response(
            200,
            content=csv_content(old_rows),
            headers={"ETag": '"v1"', "Last-Modified": "Mon, 17 Aug 2026 10:00:00 GMT"},
        ),
        httpx.Response(
            200,
            content=csv_content(new_rows),
            headers={"ETag": '"v2"', "Last-Modified": "Tue, 18 Aug 2026 10:00:00 GMT"},
        ),
    ]
    calls = []

    def handler(request):
        calls.append(1)
        return responses[len(calls) - 1]

    cache_dir = safe_tmp_dir / "cache"
    provider_v1 = TesouroTransparenteProvider(
        dataset_url="https://x/y.csv",
        cache_dir=cache_dir,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_ttl_hours=0,  # força revalidação a cada chamada, sem depender de tempo real
    )
    row_v1 = provider_v1.latest_by_identity()["tesouro-selic-01032031"]
    assert row_v1["asOfDate"] == date(2026, 8, 15)
    assert row_v1["buyRate"] == Decimal("0.09")

    # Segunda instância, MESMO cache_dir -- mas o "servidor" agora publicou
    # uma versão nova (ETag/conteúdo diferentes).
    provider_v2 = TesouroTransparenteProvider(
        dataset_url="https://x/y.csv",
        cache_dir=cache_dir,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_ttl_hours=0,
    )
    row_v2 = provider_v2.latest_by_identity()["tesouro-selic-01032031"]
    assert row_v2["asOfDate"] == date(2026, 8, 18)
    assert row_v2["buyRate"] == Decimal("0.50")
    # Nunca o valor antigo "vazando" para a consulta nova.
    assert row_v2["buyRate"] != row_v1["buyRate"]
    assert len(calls) == 2  # cada versão baixada exatamente uma vez


def test_different_cache_dirs_never_share_the_same_index(safe_tmp_dir):
    """Duas instâncias com cache_dir DIFERENTES (configurações
    independentes) nunca podem colidir no índice compartilhado -- a chave
    inclui o path físico do arquivo cacheado, que já é distinto por
    construção."""
    dir_a = safe_tmp_dir / "a"
    dir_b = safe_tmp_dir / "b"
    rows_a = ["Tesouro Selic;01/03/2031;18/08/2026;0,09;0,10;18737,11;18717,77;18717,77"]
    rows_b = ["Tesouro Selic;01/03/2031;18/08/2026;9,99;9,99;99999,99;99999,99;99999,99"]

    provider_a = TesouroTransparenteProvider(
        dataset_url="https://x/a.csv",
        cache_dir=dir_a,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: ok_handler(body=csv_content(rows_a))(r))
        ),
    )
    provider_b = TesouroTransparenteProvider(
        dataset_url="https://x/b.csv",
        cache_dir=dir_b,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: ok_handler(body=csv_content(rows_b))(r))
        ),
    )
    row_a = provider_a.latest_by_identity()["tesouro-selic-01032031"]
    row_b = provider_b.latest_by_identity()["tesouro-selic-01032031"]
    assert row_a["buyRate"] == Decimal("0.09")
    assert row_b["buyRate"] == Decimal("9.99")


def test_concurrent_first_access_never_corrupts_the_shared_index(safe_tmp_dir):
    """Duas instâncias tentando construir o índice pela primeira vez ao
    mesmo tempo (thread safety do _PROCESS_INDEX_CACHE_LOCK e do
    _DOWNLOAD_LOCK) -- nenhuma delas pode observar um índice
    parcial/corrompido nem falhar por PermissionError (Windows) ao
    substituir o arquivo cacheado, e o resultado final é consistente
    entre todas as threads."""
    cache_dir = safe_tmp_dir / "cache"
    results = {}
    errors = []

    def worker(name):
        try:
            provider = TesouroTransparenteProvider(
                dataset_url="https://x/y.csv",
                cache_dir=cache_dir,
                client=httpx.Client(transport=httpx.MockTransport(ok_handler())),
            )
            results[name] = provider.latest_by_identity()
        except Exception as exc:  # pragma: no cover - só popula errors se falhar
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 5
    first = results[0]
    for i in range(1, 5):
        assert results[i] == first
        assert len(results[i]) == 8


def test_new_dataset_without_etag_and_same_size_never_reuses_old_index(safe_tmp_dir):
    """BORDA: quando o servidor não envia ETag (não garantido por todo
    servidor) E a nova publicação coincide em TAMANHO de bytes com a
    antiga (linhas de mesmo comprimento, valores diferentes -- construído
    deliberadamente aqui para forçar exatamente esse caso raro), a chave
    do cache ainda precisa distinguir as duas versões. Só Last-Modified
    (diferente) e o mtime local do arquivo substituído (diferente a cada
    download real) fecham essa borda -- nunca reaproveitar o índice
    antigo silenciosamente."""
    row_a = "Tesouro Selic;01/03/2031;15/08/2026;0,09;0,10;18737,11;18717,77;18717,77"
    row_b = "Tesouro Selic;01/03/2031;18/08/2026;0,50;0,55;18999,00;18980,00;18980,00"
    assert len(row_a) == len(row_b)  # mesmo tamanho de linha, garantido pela fixture
    body_a = csv_content([row_a])
    body_b = csv_content([row_b])
    assert len(body_a) == len(body_b)  # mesmo tamanho de ARQUIVO -- o cenário exigido

    responses = [
        httpx.Response(
            200,
            content=body_a,
            headers={"Last-Modified": "Mon, 17 Aug 2026 10:00:00 GMT"},  # sem ETag
        ),
        httpx.Response(
            200,
            content=body_b,
            headers={"Last-Modified": "Tue, 18 Aug 2026 10:00:00 GMT"},  # sem ETag
        ),
    ]
    calls = []

    def handler(request):
        calls.append(1)
        return responses[len(calls) - 1]

    from app.providers import tesouro_transparente_provider as module

    build_calls = []
    original_build_index = module.TesouroTransparenteProvider._build_index

    def counting_build_index(self, path):
        build_calls.append(path)
        return original_build_index(self, path)

    module.TesouroTransparenteProvider._build_index = counting_build_index
    try:
        cache_dir = safe_tmp_dir / "cache"

        provider_a = TesouroTransparenteProvider(
            dataset_url="https://x/y.csv",
            cache_dir=cache_dir,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            cache_ttl_hours=0,  # força revalidação real a cada instância
        )
        index_a = provider_a.latest_by_identity()
        row_result_a = index_a["tesouro-selic-01032031"]
        assert row_result_a["asOfDate"] == date(2026, 8, 15)
        assert row_result_a["buyRate"] == Decimal("0.09")

        provider_b = TesouroTransparenteProvider(
            dataset_url="https://x/y.csv",
            cache_dir=cache_dir,  # MESMO cache_dir/path
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            cache_ttl_hours=0,
        )
        index_b = provider_b.latest_by_identity()
        row_result_b = index_b["tesouro-selic-01032031"]

        # A versão nova precisa aparecer -- nunca a antiga reaproveitada.
        assert row_result_b["asOfDate"] == date(2026, 8, 18)
        assert row_result_b["buyRate"] == Decimal("0.50")
        assert row_result_b["buyRate"] != row_result_a["buyRate"]
        assert len(calls) == 2  # os 2 downloads realmente aconteceram
        assert len(build_calls) == 2  # e cada versão foi parseada exatamente 1 vez
    finally:
        module.TesouroTransparenteProvider._build_index = original_build_index
