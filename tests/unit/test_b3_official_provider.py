from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest

from app.providers.b3.cotahist import CotahistProvider
from app.providers.b3.daily_price import B3DailyPriceSource
from app.providers.b3.exceptions import (
    B3ArchiveError,
    B3DownloadError,
    B3NotConfiguredError,
    B3ParseError,
    B3SizeLimitError,
)
from app.providers.b3.instruments import B3InstrumentRegistrySource
from app.providers.b3_official_provider import B3EodResult, B3OfficialDataProvider

# --- Construtor de linha COTAHIST sintética, EXATAMENTE nos offsets do
#     layout oficial validado na auditoria (b3.com.br, "FILE LAYOUT -
#     HISTORICAL QUOTATIONS", Review 01, 17/04/2017). Nunca copia um
#     arquivo oficial real para o repositório -- apenas reproduz o layout
#     com dados sintéticos. --------------------------------------------


def _num(value, width: int) -> str:
    return str(value).rjust(width, "0")


def _txt(value: str, width: int) -> str:
    return value.ljust(width)[:width]


def _price(value: str, width: int) -> str:
    """Recebe uma string decimal (ex. "42.60") e formata como (N)V99."""
    cents = int((Decimal(value) * 100).to_integral_value())
    return _num(cents, width)


def cotahist_header(*, filename_year: int = 2026, generation_date: str = "20260819") -> str:
    return (
        "00"
        + _txt(f"COTAHIST.{filename_year}", 13)
        + _txt("BOVESPA", 8)
        + _num(generation_date, 8)
        + _txt("", 214)
    )


def cotahist_detail(
    *,
    trading_date: str = "20260819",
    codbdi: str = "02",
    codneg: str = "PETR4",
    tpmerc: str = "010",
    nomres: str = "PETROBRAS",
    especi: str = "PN",
    prazot: str = "",
    modref: str = "R$",
    preabe: str = "42.50",
    premax: str = "43.00",
    premin: str = "42.40",
    premed: str = "42.70",
    preult: str = "42.60",
    preofc: str = "42.59",
    preofv: str = "42.61",
    totneg: int = 46224,
    quatot: int = 36838100,
    voltot: str = "1575798553.00",
    preexe: str = "0",
    indopc: str = "0",
    datven: str = "00000000",
    fatcot: int = 1,
    ptoexe: str = "0",
    codisi: str = "BRPETRACNPR6",
    dismes: str = "0",
) -> str:
    return (
        "01"
        + _num(trading_date, 8)
        + _txt(codbdi, 2)
        + _txt(codneg, 12)
        + _txt(tpmerc, 3)
        + _txt(nomres, 12)
        + _txt(especi, 10)
        + _txt(prazot, 3)
        + _txt(modref, 4)
        + _price(preabe, 13)
        + _price(premax, 13)
        + _price(premin, 13)
        + _price(premed, 13)
        + _price(preult, 13)
        + _price(preofc, 13)
        + _price(preofv, 13)
        + _num(totneg, 5)
        + _num(quatot, 18)
        + _price(voltot, 18)
        + _price(preexe, 13)
        + _txt(indopc, 1)
        + _num(datven, 8)
        + _num(fatcot, 7)
        + _price(ptoexe, 13)
        + _txt(codisi, 12)
        + _num(dismes, 3)
    )


def cotahist_trailer(*, total_registers: int, filename_year: int = 2026, generation_date: str = "20260819") -> str:
    # O parser só lê TIPREG (line[0:2]) e o total de registros em
    # line[32:42] (offset fixo confirmado em cotahist.py) -- os demais
    # campos do trailer não são interpretados, então o preenchimento
    # entre eles é irrelevante para este teste.
    return "99" + _txt("", 30) + _num(total_registers, 10) + _txt("", 203)


def make_cotahist_zip(
    tmp_path: Path, lines: list[str], *, entry_name: str = "COTAHIST_D19082026.TXT"
) -> Path:
    archive = tmp_path / "COTAHIST_D19082026.ZIP"
    with ZipFile(archive, "w") as zf:
        zf.writestr(entry_name, "\n".join(lines) + "\n")
    return archive


def valid_lines(detail_lines: list[str]) -> list[str]:
    # TOTREG conta SOMENTE os registros tipo 01 (detalhe) -- nunca inclui
    # o próprio header/trailer (confirmado por dado real, ver
    # cotahist.py: um download ao vivo trouxe TOTREG=19232 para
    # exatamente 19232 registros tipo 01, nunca 19230).
    return [
        cotahist_header(),
        *detail_lines,
        cotahist_trailer(total_registers=len(detail_lines)),
    ]


# --- Header / trailer / registro válido --------------------------------


def test_valid_file_parses_header_detail_trailer(tmp_path):
    detail = cotahist_detail()
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    records = list(provider.iter_records(archive))
    assert len(records) == 1
    record = records[0]
    assert record.trading_date == date(2026, 8, 19)
    assert record.trading_symbol == "PETR4"
    assert record.close_price == Decimal("42.60")
    assert record.isin == "BRPETRACNPR6"


def test_decimal_scaling_is_applied_correctly(tmp_path):
    detail = cotahist_detail(preult="123.45", voltot="9999999999.99")
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.close_price == Decimal("123.45")
    assert record.traded_volume == Decimal("9999999999.99")
    assert isinstance(record.close_price, Decimal)


def test_fatcot_is_preserved_as_official_quote_factor(tmp_path):
    detail = cotahist_detail(fatcot=1000)
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.quote_factor == 1000


def test_zero_maturity_date_is_treated_as_not_applicable_never_a_fabricated_date(tmp_path):
    detail = cotahist_detail(datven="00000000")
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.maturity_date is None


def test_real_maturity_date_is_parsed(tmp_path):
    detail = cotahist_detail(datven="20261218")
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.maturity_date == date(2026, 12, 18)


def test_codbdi_codneg_tpmerc_totneg_quatot_are_extracted_verbatim(tmp_path):
    detail = cotahist_detail(codbdi="02", codneg="VALE3", tpmerc="010", totneg=31014, quatot=12466800)
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.codbdi == "02"
    assert record.trading_symbol == "VALE3"
    assert record.market_type == "010"
    assert record.trade_count == 31014
    assert record.traded_quantity == 12466800


# --- Mercado fracionário -------------------------------------------------


def test_fractional_market_record_is_recognized_via_official_tpmerc_and_codbdi(tmp_path):
    detail = cotahist_detail(
        codneg="PETR4F", tpmerc="020", codbdi="96", preult="42.75", codisi="BRPETRACNPR6"
    )
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.trading_symbol == "PETR4F"
    assert record.is_fractional_market is True
    assert record.codbdi == "96"


def test_standard_and_fractional_records_share_the_same_isin_but_different_price(tmp_path):
    standard = cotahist_detail(codneg="PETR4", tpmerc="010", codbdi="02", preult="42.60", codisi="BRPETRACNPR6")
    fractional = cotahist_detail(codneg="PETR4F", tpmerc="020", codbdi="96", preult="42.75", codisi="BRPETRACNPR6")
    archive = make_cotahist_zip(tmp_path, valid_lines([standard, fractional]))
    provider = CotahistProvider(cache_dir=tmp_path)
    records = {r.trading_symbol: r for r in provider.iter_records(archive)}
    assert records["PETR4"].isin == records["PETR4F"].isin
    assert records["PETR4"].close_price != records["PETR4F"].close_price
    assert records["PETR4"].is_fractional_market is False
    assert records["PETR4F"].is_fractional_market is True


def test_never_strips_f_globally_a_plain_stock_record_stays_standard(tmp_path):
    detail = cotahist_detail(codneg="ITUB4", tpmerc="010", codbdi="02")
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.trading_symbol == "ITUB4"
    assert record.is_fractional_market is False


# --- Registros inválidos / missing != zero ------------------------------


def test_truncated_line_raises_parse_error_never_silently_accepted(tmp_path):
    bad = cotahist_detail()[:-10]  # linha mais curta que 245 bytes
    archive = make_cotahist_zip(tmp_path, [cotahist_header(), bad, cotahist_trailer(total_registers=1)])
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_invalid_numeric_character_raises_parse_error(tmp_path):
    detail = cotahist_detail()
    # corrompe o campo PREULT (offset 108:121) com caracteres não numéricos
    corrupted = detail[:108] + "X" * 13 + detail[121:]
    archive = make_cotahist_zip(tmp_path, valid_lines([corrupted]))
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_missing_header_raises_parse_error(tmp_path):
    detail = cotahist_detail()
    archive = make_cotahist_zip(tmp_path, [detail, cotahist_trailer(total_registers=1)])
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="header"):
        list(provider.iter_records(archive))


def test_missing_trailer_raises_parse_error(tmp_path):
    detail = cotahist_detail()
    archive = make_cotahist_zip(tmp_path, [cotahist_header(), detail])
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="trailer"):
        list(provider.iter_records(archive))


# --- Tamanho exato do registro (Correção 3, Prompt 3, revisão final): -----
# --- "Register Size: 245 bytes" no layout oficial -- nunca só ">=" -------


def test_record_with_244_bytes_is_rejected(tmp_path):
    short = cotahist_detail()[:-1]
    assert len(short) == 244
    archive = make_cotahist_zip(tmp_path, [cotahist_header(), short, cotahist_trailer(total_registers=1)])
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_record_with_246_bytes_is_rejected_never_silently_accepted(tmp_path):
    """Antes desta correção, o parser só rejeitava linhas MENORES que 245
    bytes (`< _RECORD_LENGTH`) -- uma linha maior passava despercebida.
    O layout oficial declara "Register Size: 245 bytes" sem margem para
    "maior que o esperado" ser dado extra honesto."""
    long_line = cotahist_detail() + "X"
    assert len(long_line) == 246
    archive = make_cotahist_zip(
        tmp_path, [cotahist_header(), long_line, cotahist_trailer(total_registers=1)]
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_record_with_exactly_245_bytes_is_accepted(tmp_path):
    detail = cotahist_detail()
    assert len(detail) == 245
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    records = list(provider.iter_records(archive))
    assert len(records) == 1


# --- Ordem e unicidade header/trailer (Correção 3, Prompt 3, revisão -----
# --- final): "00 Header, 01 detalhes, 99 Trailer" -- nunca fora de ordem -


def test_second_header_is_rejected(tmp_path):
    detail = cotahist_detail()
    archive = make_cotahist_zip(
        tmp_path,
        [cotahist_header(), cotahist_header(), detail, cotahist_trailer(total_registers=1)],
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_second_trailer_is_rejected(tmp_path):
    detail = cotahist_detail()
    archive = make_cotahist_zip(
        tmp_path,
        [
            cotahist_header(),
            detail,
            cotahist_trailer(total_registers=1),
            cotahist_trailer(total_registers=1),
        ],
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_detail_record_before_header_is_rejected_even_when_a_header_exists_later(tmp_path):
    """Distinto de test_missing_header_raises_parse_error: aqui existe um
    header no arquivo, mas ele vem DEPOIS de um registro de detalhe --
    ordem errada, não ausência."""
    detail = cotahist_detail()
    archive = make_cotahist_zip(
        tmp_path, [detail, cotahist_header(), cotahist_trailer(total_registers=1)]
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_detail_record_after_trailer_is_rejected(tmp_path):
    detail = cotahist_detail()
    archive = make_cotahist_zip(
        tmp_path, [cotahist_header(), cotahist_trailer(total_registers=1), detail]
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_trailer_count_mismatch_raises_parse_error_never_silently_accepted(tmp_path):
    detail = cotahist_detail()
    archive = make_cotahist_zip(
        tmp_path, [cotahist_header(), detail, cotahist_trailer(total_registers=999)]
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="[Cc]ontagem"):
        list(provider.iter_records(archive))


def test_trailer_count_matches_only_type01_records_never_including_header_and_trailer(
    tmp_path,
):
    """Regressão real (Correção 3, Prompt 3): TOTREG do trailer conta
    SOMENTE os registros tipo 01 (detalhe) -- nunca o header/trailer em
    si. Confirmado por um download AO VIVO do arquivo diário oficial
    durante esta correção: TOTREG=19232 batia exatamente com 19232
    registros tipo 01 reais, nunca 19230 (=TOTREG-2). Uma suposição
    anterior de "declared_total - 2" fazia TODO arquivo real ser
    rejeitado como corrompido -- este teste prova a semântica correta com
    3 registros de detalhe e TOTREG=3 (nunca 5)."""
    details = [
        cotahist_detail(codneg="PETR4"),
        cotahist_detail(codneg="VALE3"),
        cotahist_detail(codneg="ITUB4"),
    ]
    archive = make_cotahist_zip(
        tmp_path, [cotahist_header(), *details, cotahist_trailer(total_registers=3)]
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    records = list(provider.iter_records(archive))
    assert len(records) == 3
    assert {r.trading_symbol for r in records} == {"PETR4", "VALE3", "ITUB4"}


# --- TOTREG: diário e anual têm a MESMA semântica -- reverificado nesta --
# --- revisão (Correção 3, Prompt 3, revisão final) com DOIS downloads ----
# --- reais e independentes (ver comentário em cotahist.py, iter_records) -
# --- contra a suspeita de que o layout oficial ("INCLUDE ALSO HEADER AND -
# --- TRAILER REGISTERS") exigiria uma regra diferente por variante -------


def test_totreg_semantics_hold_for_a_daily_style_file(tmp_path):
    """Caso B do Bloqueador TOTREG: arquivo no padrão diário
    (COTAHIST_D<data>.TXT, poucos registros) -- TOTREG = contagem de
    registros tipo 01, nunca header+trailer inclusos."""
    details = [cotahist_detail(codneg="PETR4"), cotahist_detail(codneg="VALE3")]
    archive = make_cotahist_zip(
        tmp_path,
        [cotahist_header(), *details, cotahist_trailer(total_registers=2)],
        entry_name="COTAHIST_D19082026.TXT",
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    records = list(provider.iter_records(archive))
    assert len(records) == 2


def test_totreg_semantics_hold_for_an_annual_style_file(tmp_path):
    """Caso A do Bloqueador TOTREG: arquivo no padrão anual
    (COTAHIST_A<ano>.TXT, muitos registros) -- mesma semântica do
    diário, sem regra própria por variante (confirmado por dado real:
    diário TOTREG=19232 e anual TOTREG=2486436 batem, cada um, com sua
    própria contagem de registros tipo 01, nunca com header+trailer
    inclusos)."""
    details = [cotahist_detail(codneg=f"PAPEL{i:02d}") for i in range(10)]
    archive = make_cotahist_zip(
        tmp_path,
        [cotahist_header(), *details, cotahist_trailer(total_registers=10)],
        entry_name="COTAHIST_A2026.TXT",
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    records = list(provider.iter_records(archive))
    assert len(records) == 10


def test_totreg_mismatch_rejected_for_a_daily_style_file(tmp_path):
    """Caso D do Bloqueador TOTREG: TOTREG incompatível no padrão
    diário -- rejeitado, nunca aceito silenciosamente."""
    detail = cotahist_detail(codneg="PETR4")
    archive = make_cotahist_zip(
        tmp_path,
        [cotahist_header(), detail, cotahist_trailer(total_registers=42)],
        entry_name="COTAHIST_D19082026.TXT",
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="[Cc]ontagem"):
        list(provider.iter_records(archive))


def test_totreg_mismatch_rejected_for_an_annual_style_file(tmp_path):
    """Caso C do Bloqueador TOTREG: TOTREG incompatível no padrão
    anual -- rejeitado, nunca aceito silenciosamente."""
    details = [cotahist_detail(codneg=f"PAPEL{i:02d}") for i in range(5)]
    archive = make_cotahist_zip(
        tmp_path,
        [cotahist_header(), *details, cotahist_trailer(total_registers=999999)],
        entry_name="COTAHIST_A2026.TXT",
    )
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="[Cc]ontagem"):
        list(provider.iter_records(archive))


def test_unknown_critical_record_type_raises_parse_error(tmp_path):
    detail = cotahist_detail()
    bogus = "42" + detail[2:]  # TIPREG desconhecido
    archive = make_cotahist_zip(tmp_path, [cotahist_header(), bogus, cotahist_trailer(total_registers=1)])
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError):
        list(provider.iter_records(archive))


def test_empty_file_raises_parse_error(tmp_path):
    # Um arquivo com só uma linha em branco (sem header nem detail nem
    # trailer) não é rejeitado como ZIP malformado -- é rejeitado por não
    # ter registro de header/trailer, exatamente como um arquivo real
    # truncado/corrompido seria: nunca aceito silenciosamente.
    archive = make_cotahist_zip(tmp_path, [])
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="header"):
        list(provider.iter_records(archive))


def test_missing_optional_text_field_is_none_never_a_fabricated_value(tmp_path):
    detail = cotahist_detail(prazot="")
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    record = next(provider.iter_records(archive))
    assert record.forward_term_days is None


# --- Segurança de ZIP ------------------------------------------------------


def test_zip_with_path_traversal_entry_is_rejected(tmp_path):
    archive = tmp_path / "evil.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("../../evil.TXT", "not cotahist data")
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_zip_with_absolute_path_entry_is_rejected(tmp_path):
    archive = tmp_path / "evil_abs.zip"
    with ZipFile(archive, "w") as zf:
        # zipfile normaliza barras iniciais na escrita; simulamos via
        # ZipInfo diretamente para forçar um nome absoluto no cabeçalho.
        from zipfile import ZipInfo

        zf.writestr(ZipInfo("/etc/passwd"), "not cotahist data")
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_zip_with_unexpected_single_file_is_rejected(tmp_path):
    archive = tmp_path / "unexpected.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "not cotahist data")
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_zip_with_multiple_cotahist_files_is_rejected(tmp_path):
    archive = tmp_path / "multi.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("COTAHIST_A.TXT", cotahist_header())
        zf.writestr("COTAHIST_B.TXT", cotahist_header())
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_zip_with_cotahist_plus_an_extra_unexpected_file_is_rejected(tmp_path):
    """Bloqueador 5 (Correção 3, Prompt 3, revisão final): um ZIP com
    COTAHIST_D19082026.TXT válido MAIS um segundo membro qualquer (aqui
    "evil.txt") era aceito antes desta correção -- `cotahist_entries`
    contava só o membro que batia com o padrão COTAHIST*.TXT, ignorando
    que havia um SEGUNDO membro estranho no arquivo. Agora len(members)
    != 1 rejeita o ZIP inteiro sem nunca abrir/ler nenhum membro."""
    archive = tmp_path / "cotahist_plus_evil.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("COTAHIST_D19082026.TXT", cotahist_header())
        zf.writestr("evil.txt", "payload")
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_zip_with_windows_drive_letter_path_entry_is_rejected(tmp_path):
    from zipfile import ZipInfo

    archive = tmp_path / "evil_drive.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr(ZipInfo(r"C:\evil\COTAHIST.TXT"), "not cotahist data")
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_zip_with_unc_path_entry_is_rejected(tmp_path):
    from zipfile import ZipInfo

    archive = tmp_path / "evil_unc.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr(ZipInfo(r"\\server\share\COTAHIST.TXT"), "not cotahist data")
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_zip_bomb_uncompressed_limit_is_enforced(tmp_path):
    archive = tmp_path / "bomb.zip"
    with ZipFile(archive, "w") as zf:
        # Um conteúdo pequeno comprimido, mas o limite configurado é
        # propositalmente menor que o tamanho descompactado real.
        zf.writestr("COTAHIST_X.TXT", "0" * 5000)
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3SizeLimitError):
        provider.validate_archive(archive, max_uncompressed_bytes=100)


def test_zip_with_a_suspicious_compression_ratio_is_rejected(tmp_path):
    """Bloqueador 6 (Correção 3, Prompt 3, revisão final): razão de
    compressão, complementar ao limite absoluto de tamanho já existente.
    10MB de um caractere repetido comprime, via DEFLATE, a uma fração
    minúscula do tamanho original -- ratio bem acima do limite
    configurado (100:1) mesmo com o tamanho descompactado (10MB) dentro
    do limite absoluto permitido (20MB), isolando especificamente a
    checagem de razão (nunca a checagem de tamanho absoluto)."""
    import zipfile

    archive = tmp_path / "ratio_bomb.zip"
    with ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("COTAHIST_D19082026.TXT", "0" * 10_000_000)
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3SizeLimitError):
        provider.validate_archive(archive, max_uncompressed_bytes=20_000_000)


def test_zip_with_a_realistic_compression_ratio_is_accepted(tmp_path):
    """Contraprova do teste anterior: um ZIP comprimido de forma
    realista (razão próxima da observada em arquivos COTAHIST reais
    durante a auditoria, ~8.5:1 -- ver comentário de _MAX_COMPRESSION_RATIO
    em cotahist.py) nunca é rejeitado pela checagem de razão."""
    import zipfile

    details = [cotahist_detail(codneg=f"PAPEL{i:02d}") for i in range(50)]
    content = "\n".join(valid_lines(details)) + "\n"
    archive = tmp_path / "realistic.zip"
    with ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("COTAHIST_D19082026.TXT", content)
    provider = CotahistProvider(cache_dir=tmp_path)
    # Não deve levantar B3SizeLimitError nem B3ArchiveError.
    provider.validate_archive(archive, max_uncompressed_bytes=20_000_000)


def test_corrupted_zip_is_rejected(tmp_path):
    archive = tmp_path / "corrupted.zip"
    archive.write_bytes(b"this is not a zip file at all")
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ArchiveError):
        provider.validate_archive(archive, 10_000_000)


def test_missing_file_raises_download_or_os_error(tmp_path):
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(Exception):
        provider.validate_archive(tmp_path / "does_not_exist.zip", 10_000_000)


# --- BVBG.186 (EquitiesSimplifiedPriceReport) -----------------------------


def _bvbg186_xml(records: list[dict]) -> bytes:
    entries = ""
    for r in records:
        entries += (
            "<PricRpt>"
            f"<TradDt><Dt>{r['date']}</Dt></TradDt>"
            f"<SctyId><TckrSymb>{r['symbol']}</TckrSymb></SctyId>"
            "<FinInstrmAttrbts>"
            f"<FrstPric>{r.get('open', '')}</FrstPric>"
            f"<MaxPric>{r.get('high', '')}</MaxPric>"
            f"<MinPric>{r.get('low', '')}</MinPric>"
            f"<TradAvrgPric>{r.get('avg', '')}</TradAvrgPric>"
            f"<LastPric>{r.get('close', '')}</LastPric>"
            f"<RglrTxsQty>{r.get('trades', '')}</RglrTxsQty>"
            f"<FinInstrmQty>{r.get('qty', '')}</FinInstrmQty>"
            f"<NtlFinVol>{r.get('vol', '')}</NtlFinVol>"
            "</FinInstrmAttrbts>"
            "</PricRpt>"
        )
    return f"<PriceReport>{entries}</PriceReport>".encode("utf-8")


def test_bvbg186_parses_valid_record_with_official_tag_names():
    xml_bytes = _bvbg186_xml(
        [
            {
                "date": "2026-08-19",
                "symbol": "PETR4",
                "open": "42.84",
                "high": "43.97",
                "low": "42.84",
                "avg": "43.20",
                "close": "43.11",
                "trades": "46224",
                "qty": "36838100",
                "vol": "1575798553.00",
            }
        ]
    )
    records = B3DailyPriceSource.parse(xml_bytes)
    assert len(records) == 1
    record = records[0]
    assert record.trading_symbol == "PETR4"
    assert record.reference_date == date(2026, 8, 19)
    assert record.close_price == Decimal("43.11")
    assert record.trade_count == 46224
    assert record.adjusted is False


def test_bvbg186_missing_ticker_raises_parse_error():
    xml_bytes = b"<PriceReport><PricRpt><TradDt><Dt>2026-08-19</Dt></TradDt></PricRpt></PriceReport>"
    with pytest.raises(B3ParseError):
        B3DailyPriceSource.parse(xml_bytes)


def test_bvbg186_invalid_decimal_raises_parse_error():
    xml_bytes = _bvbg186_xml(
        [{"date": "2026-08-19", "symbol": "PETR4", "close": "not-a-number"}]
    )
    with pytest.raises(B3ParseError):
        B3DailyPriceSource.parse(xml_bytes)


def test_bvbg186_fetch_without_url_raises_not_configured():
    source = B3DailyPriceSource(url=None)
    assert source.is_configured() is False
    with pytest.raises(B3NotConfiguredError):
        source.fetch()


# --- BVBG.028 (InstrumentReport) ------------------------------------------


def _bvbg028_xml(records: list[dict]) -> bytes:
    entries = ""
    for r in records:
        maturity = f"<MtrtyDt>{r['maturity']}</MtrtyDt>" if r.get("maturity") else ""
        entries += (
            "<Instrm>"
            f"<TckrSymb>{r['symbol']}</TckrSymb>"
            f"<ISIN>{r.get('isin', '')}</ISIN>"
            f"<MktIdrCd>{r.get('mic', 'BVMF')}</MktIdrCd>"
            f"<TradgCcy>{r.get('currency', 'BRL')}</TradgCcy>"
            f"<CFICd>{r.get('cfi', '')}</CFICd>"
            f"<Sgmt>{r.get('segment', '')}</Sgmt>"
            f"<Mkt>{r.get('market', '')}</Mkt>"
            f"{maturity}"
            "</Instrm>"
        )
    return f"<InstrumentReport>{entries}</InstrumentReport>".encode("utf-8")


def test_bvbg028_parses_valid_instrument_records():
    xml_bytes = _bvbg028_xml(
        [
            {"symbol": "PETR4", "isin": "BRPETRACNPR6", "cfi": "ESVUFR", "segment": "1", "market": "1"},
            {"symbol": "PETR4F", "isin": "BRPETRACNPR6", "cfi": "ESVUFR", "segment": "1", "market": "20"},
            {"symbol": "MXRF11", "isin": "BRMXRFCTF008", "cfi": "CIS", "segment": "1", "market": "1"},
            {"symbol": "BOVA11", "isin": "BRBOVACTF003", "cfi": "CIS", "segment": "1", "market": "1"},
        ]
    )
    instruments = {i.trading_symbol: i for i in B3InstrumentRegistrySource.parse(xml_bytes)}
    assert instruments["PETR4"].isin == instruments["PETR4F"].isin
    assert instruments["PETR4"].is_fractional_market is False
    assert instruments["PETR4F"].is_fractional_market is True
    assert instruments["MXRF11"].currency == "BRL"
    assert instruments["BOVA11"].market_identifier_code == "BVMF"


def test_bvbg028_missing_ticker_raises_parse_error():
    xml_bytes = b"<InstrumentReport><Instrm><ISIN>BR0000000000</ISIN></Instrm></InstrumentReport>"
    with pytest.raises(B3ParseError):
        B3InstrumentRegistrySource.parse(xml_bytes)


def test_bvbg028_fetch_without_url_raises_not_configured():
    source = B3InstrumentRegistrySource(url=None)
    assert source.is_configured() is False
    with pytest.raises(B3NotConfiguredError):
        source.fetch()


# --- B3OfficialDataProvider: cascata de EOD recente -----------------------


class _FakeCotahist:
    """Fake do CotahistProvider: simula um calendário de pregões com
    arquivos disponíveis só em determinadas datas, sem rede/disco real."""

    def __init__(self, records_by_date: dict[date, list]):
        self.records_by_date = records_by_date
        self.daily_max_uncompressed_bytes = 10_000_000
        self.annual_max_uncompressed_bytes = 10_000_000
        self.download_calls: list[date] = []

    def download_daily(self, reference_date: date):
        self.download_calls.append(reference_date)
        if reference_date not in self.records_by_date:
            raise B3ArchiveError("sem pregão nesta data (simulado)")
        return _FakeDownloadResult(reference_date)

    def iter_records(self, path, max_uncompressed_bytes=None):
        return iter(self.records_by_date[path.reference_date])


class _FakeDownloadResult:
    def __init__(self, reference_date: date):
        self.reference_date = reference_date
        self.path = self
        self.collected_at = datetime(2026, 8, 19, 21, 0, tzinfo=timezone.utc)
        self.cache_hit = False


def _record(symbol: str, trading_date: date, close: str = "42.60") -> object:
    from app.providers.b3.models import B3HistoricalRecord

    return B3HistoricalRecord(
        trading_date=trading_date,
        codbdi="02",
        trading_symbol=symbol,
        market_type="010",
        issuer_short_name="TEST",
        specification="PN",
        forward_term_days=None,
        currency="R$",
        open_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        average_price=Decimal(close),
        close_price=Decimal(close),
        best_bid_price=None,
        best_ask_price=None,
        trade_count=100,
        traded_quantity=1000,
        traded_volume=Decimal("42600.00"),
        strike_price=None,
        correction_indicator=None,
        maturity_date=None,
        quote_factor=1,
        isin="BRTEST0000001",
        distribution_number=None,
    )


def test_get_recent_eod_finds_symbol_on_anchor_date():
    anchor = date(2026, 8, 19)
    fake = _FakeCotahist({anchor: [_record("PETR4", anchor)]})
    provider = B3OfficialDataProvider(cotahist=fake)
    result = provider.get_recent_eod("PETR4", anchor_date=anchor)
    assert isinstance(result, B3EodResult)
    assert result.record.trading_symbol == "PETR4"
    assert result.dataset == "cotahist_daily"


def test_get_recent_eod_walks_back_over_weekend_and_missing_days():
    # Anchor numa terça-feira; o pregão só existe na sexta anterior --
    # segunda/domingo/sábado devem ser pulados corretamente.
    anchor = date(2026, 8, 18)  # terça-feira
    friday = date(2026, 8, 14)
    fake = _FakeCotahist({friday: [_record("VALE3", friday, close="71.55")]})
    provider = B3OfficialDataProvider(cotahist=fake)
    result = provider.get_recent_eod("VALE3", anchor_date=anchor)
    assert result is not None
    assert result.record.trading_date == friday
    # Fins de semana nunca contam como tentativa real (nunca baixados).
    assert date(2026, 8, 16) not in fake.download_calls  # domingo
    assert date(2026, 8, 15) not in fake.download_calls  # sábado


def test_get_recent_eod_returns_none_when_not_found_within_lookback_never_fabricates():
    anchor = date(2026, 8, 19)
    fake = _FakeCotahist({})
    provider = B3OfficialDataProvider(cotahist=fake)
    result = provider.get_recent_eod("PETR4", anchor_date=anchor, max_lookback_days=3)
    assert result is None


def test_get_recent_eod_continues_past_a_single_bad_day():
    anchor = date(2026, 8, 19)
    fake = _FakeCotahist({date(2026, 8, 18): [_record("ITUB4", date(2026, 8, 18))]})
    provider = B3OfficialDataProvider(cotahist=fake)
    result = provider.get_recent_eod("ITUB4", anchor_date=anchor)
    assert result is not None
    assert result.record.trading_date == date(2026, 8, 18)


# --- FATCOT (Correção 3, Prompt 3, seção 6): campo obrigatório, nunca -----
# --- fabricado como 1 quando ausente/zerado -------------------------------


def test_fatcot_blank_raises_parse_error_never_fabricates_a_default_of_one(tmp_path):
    detail = cotahist_detail()
    # corrompe o campo FATCOT (offset 210:217, ver cotahist.py) com espaços
    blanked = detail[:210] + " " * 7 + detail[217:]
    archive = make_cotahist_zip(tmp_path, valid_lines([blanked]))
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="FATCOT"):
        list(provider.iter_records(archive))


def test_fatcot_zero_raises_parse_error_never_fabricates_a_default_of_one(tmp_path):
    detail = cotahist_detail(fatcot=0)
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    provider = CotahistProvider(cache_dir=tmp_path)
    with pytest.raises(B3ParseError, match="FATCOT"):
        list(provider.iter_records(archive))


# --- Bloqueador 3 (Correção 3, Prompt 3): nenhum registro é utilizável ----
# --- antes da integridade do arquivo INTEIRO ser confirmada --------------


class _FixedFileCotahist:
    """download_daily sempre aponta para o MESMO arquivo ZIP sintético já
    em disco (sem rede) -- mas iter_records delega para um
    CotahistProvider REAL (`_real`), então o parser genuíno (com suas
    validações de header/trailer/contagem de registros, todas executadas
    SOMENTE após o laço de leitura terminar) é exercitado de ponta a
    ponta. Prova que B3OfficialDataProvider.get_recent_eod nunca expõe um
    ticker antes de a integridade completa do arquivo ter sido
    confirmada -- mesmo quando o ticker procurado aparece ANTES de um
    problema mais adiante no arquivo (trailer ausente, registro
    corrompido, contagem incompatível)."""

    def __init__(self, archive_path: Path, real_provider: CotahistProvider):
        from app.providers.b3.cotahist import CotahistDownloadResult

        self._archive_path = archive_path
        self._real = real_provider
        self._result_cls = CotahistDownloadResult
        self.daily_max_uncompressed_bytes = real_provider.daily_max_uncompressed_bytes
        self.annual_max_uncompressed_bytes = real_provider.annual_max_uncompressed_bytes

    def download_daily(self, reference_date):
        return self._result_cls(
            path=self._archive_path,
            reference_date=reference_date,
            etag=None,
            last_modified=None,
            collected_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            cache_hit=False,
            size_bytes=self._archive_path.stat().st_size,
        )

    def iter_records(self, path, max_uncompressed_bytes=None):
        return self._real.iter_records(path, max_uncompressed_bytes)


def test_get_recent_eod_never_returns_a_ticker_from_a_file_missing_its_trailer(tmp_path):
    detail = cotahist_detail(codneg="PETR4")
    archive = make_cotahist_zip(tmp_path, [cotahist_header(), detail])  # sem trailer
    real = CotahistProvider(cache_dir=tmp_path)
    provider = B3OfficialDataProvider(cotahist=_FixedFileCotahist(archive, real))

    result = provider.get_recent_eod(
        "PETR4", anchor_date=date(2026, 8, 19), max_lookback_days=1
    )

    assert result is None


def test_get_recent_eod_never_returns_a_ticker_from_a_file_with_a_corrupted_later_record(
    tmp_path,
):
    valid_detail = cotahist_detail(codneg="PETR4")
    vale_detail = cotahist_detail(codneg="VALE3")
    corrupted = vale_detail[:108] + "X" * 13 + vale_detail[121:]
    lines = valid_lines([valid_detail, corrupted])
    archive = make_cotahist_zip(tmp_path, lines)
    real = CotahistProvider(cache_dir=tmp_path)
    provider = B3OfficialDataProvider(cotahist=_FixedFileCotahist(archive, real))

    result = provider.get_recent_eod(
        "PETR4", anchor_date=date(2026, 8, 19), max_lookback_days=1
    )

    # PETR4 aparece ANTES do registro corrompido no arquivo -- mas isso
    # nunca é suficiente: a integridade do arquivo inteiro precisa ser
    # confirmada antes de qualquer registro virar utilizável.
    assert result is None


def test_get_recent_eod_never_returns_a_ticker_from_a_file_with_a_bad_trailer_count(
    tmp_path,
):
    detail = cotahist_detail(codneg="PETR4")
    lines = [cotahist_header(), detail, cotahist_trailer(total_registers=999)]
    archive = make_cotahist_zip(tmp_path, lines)
    real = CotahistProvider(cache_dir=tmp_path)
    provider = B3OfficialDataProvider(cotahist=_FixedFileCotahist(archive, real))

    result = provider.get_recent_eod(
        "PETR4", anchor_date=date(2026, 8, 19), max_lookback_days=1
    )

    assert result is None


def test_get_recent_eod_returns_the_ticker_from_a_fully_valid_file(tmp_path):
    detail = cotahist_detail(codneg="PETR4", preult="43.11")
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    real = CotahistProvider(cache_dir=tmp_path)
    provider = B3OfficialDataProvider(cotahist=_FixedFileCotahist(archive, real))

    result = provider.get_recent_eod(
        "PETR4", anchor_date=date(2026, 8, 19), max_lookback_days=1
    )

    assert result is not None
    assert result.record.trading_symbol == "PETR4"
    assert result.record.close_price == Decimal("43.11")


def test_get_recent_eod_returns_none_for_a_ticker_absent_from_a_valid_file(tmp_path):
    detail = cotahist_detail(codneg="PETR4")
    archive = make_cotahist_zip(tmp_path, valid_lines([detail]))
    real = CotahistProvider(cache_dir=tmp_path)
    provider = B3OfficialDataProvider(cotahist=_FixedFileCotahist(archive, real))

    result = provider.get_recent_eod(
        "VALE3", anchor_date=date(2026, 8, 19), max_lookback_days=1
    )

    assert result is None


# --- Bloqueador 4 (Correção 3, Prompt 3): redirects nunca seguidos -------
# --- automaticamente; checagem real (HEAD contra o endpoint oficial) -----
# --- confirmou 200 direto, sem nenhum redirect, então não há evidência ---
# --- de que um redirect legítimo seja necessário --------------------------


def test_client_never_configures_follow_redirects_true():
    """Guarda estrutural contra uma regressão futura reintroduzindo
    follow_redirects=True no client de produção."""
    provider = CotahistProvider(cache_dir=Path("."))
    assert provider.client.follow_redirects is False


def test_redirect_is_never_followed_and_is_rejected_as_invalid_download(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            302, headers={"Location": "http://127.0.0.1:12345/arquivo.zip"}
        )

    provider = CotahistProvider(
        cache_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(B3DownloadError):
        provider.download_daily(date(2026, 8, 19))

    # Nunca uma segunda requisição -- o redirect nunca é seguido.
    assert len(seen) == 1
    # Nenhum arquivo .part deixado para trás.
    assert list(tmp_path.glob("*.part")) == []


def test_redirect_is_rejected_even_with_an_injected_client_configured_to_follow_redirects(
    tmp_path,
):
    """Bloqueador 10 (Correção 3, Prompt 3, revisão final): `client=`
    injetado no construtor com follow_redirects=True não pode burlar a
    política -- o override é passado EXPLICITAMENTE em cada requisição
    (ver _download), prevalecendo sobre o default do client, injetado ou
    não."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            302, headers={"Location": "http://127.0.0.1:12345/arquivo.zip"}
        )

    injected_client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    assert injected_client.follow_redirects is True  # o client em si permite -- a política vem do request
    provider = CotahistProvider(cache_dir=tmp_path, client=injected_client)

    with pytest.raises(B3DownloadError):
        provider.download_daily(date(2026, 8, 19))

    # Uma única requisição -- o redirect nunca é seguido, mesmo com o
    # client injetado permitindo follow_redirects por padrão.
    assert len(seen) == 1
    assert list(tmp_path.glob("*.part")) == []


def test_rejected_redirect_never_destroys_a_previously_valid_cache(tmp_path):
    archive = tmp_path / "COTAHIST_D19082026.zip"
    lines = valid_lines([cotahist_detail(codneg="PETR4")])
    with ZipFile(archive, "w") as zf:
        zf.writestr("COTAHIST_D19082026.TXT", "\n".join(lines) + "\n")
    original_bytes = archive.read_bytes()
    metadata_path = archive.with_suffix(".json")
    metadata_path.write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00",'
        '"collected_at":"2020-01-01T00:00:00+00:00",'
        '"etag":"abc123","last_modified":"y","size_bytes":100}',
        encoding="utf-8",
    )
    provider = CotahistProvider(
        cache_dir=tmp_path,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    302, headers={"Location": "http://127.0.0.1:12345/x.zip"}
                )
            )
        ),
        cache_ttl_hours=0,
    )

    with pytest.raises(B3DownloadError):
        provider.download_daily(date(2026, 8, 19))

    assert archive.exists()
    assert archive.read_bytes() == original_bytes
    assert list(tmp_path.glob("*.part")) == []


# --- Hardening XML: DTD/entities are rejected before parsing --------------

@pytest.mark.parametrize(
    ("parser", "payload"),
    [
        (
            B3DailyPriceSource.parse,
            b'<!DOCTYPE x [<!ENTITY secret "expanded">]><PriceReport><PricRpt><TckrSymb>&secret;</TckrSymb><Dt>2026-08-19</Dt></PricRpt></PriceReport>',
        ),
        (
            B3InstrumentRegistrySource.parse,
            b'<!DOCTYPE x [<!ENTITY secret "expanded">]><InstrumentReport><Instrm><TckrSymb>&secret;</TckrSymb></Instrm></InstrumentReport>',
        ),
    ],
)
def test_b3_xml_parsers_reject_dtd_and_entity_declarations(parser, payload):
    with pytest.raises(B3ParseError, match="XML .* inválido ou inseguro"):
        parser(payload)


@pytest.mark.parametrize(
    ("parser", "payload"),
    [
        (
            B3DailyPriceSource.parse,
            b'<PriceReport><PricRpt><TckrSymb>PETR4</TckrSymb><Dt>2026-08-19</Dt></PricRpt>',
        ),
        (
            B3InstrumentRegistrySource.parse,
            b'<InstrumentReport><Instrm><TckrSymb>PETR4</TckrSymb></InstrumentReport>',
        ),
    ],
)
def test_b3_xml_parsers_keep_rejecting_malformed_xml(parser, payload):
    with pytest.raises(B3ParseError, match="XML .* inválido ou inseguro"):
        parser(payload)
