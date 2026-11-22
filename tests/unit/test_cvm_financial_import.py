from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest

from app.core.database import SessionLocal
from app.engines.cvm_financial_engine import CvmFinancialEngine
from app.models.asset import Asset
from app.models.cvm_financial import (
    AssetCvmIssuer,
    CvmFinancialAccount,
    CvmFinancialDocument,
)
from app.providers.cvm_open_data_provider import (
    CvmArchiveError,
    CvmOpenDataProvider,
    CvmRawAccount,
    CvmSizeLimitError,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.cvm_financial_repository import CvmFinancialRepository
from app.services.cvm_financial_service import CvmFinancialService


COLLECTED = datetime(2026, 7, 20, tzinfo=timezone.utc)
HEADER_BALANCE = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA\n"
HEADER_FLOW = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA\n"


def row(
    statement="BPA",
    *,
    version=1,
    scope="con",
    code="1",
    value="123.45",
    order="ÚLTIMO",
    start=None,
    reference="2025-12-31",
    end="2025-12-31",
):
    group = f"DF {'Consolidado' if scope == 'con' else 'Individual'} - {statement}"
    fields = [
        "12.345.678/0001-90",
        reference,
        str(version),
        "COMPANHIA AÇÃO S.A.",
        "012345",
        group,
        "REAL",
        "MIL",
        order,
    ]
    if start is not None:
        fields.append(start)
    fields.extend([end, code, "Descrição çã", value, "S"])
    return ";".join(fields) + "\n"


def archive_bytes(entries: dict[str, str | bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(
                name, content.encode("cp1252") if isinstance(content, str) else content
            )
    return output.getvalue()


def write_archive(tmp_path: Path, entries: dict[str, str | bytes]) -> Path:
    path = tmp_path / "sample.zip"
    path.write_bytes(archive_bytes(entries))
    return path


def provider(tmp_path, **kwargs):
    return CvmOpenDataProvider(cache_dir=tmp_path / "cache", **kwargs)


def test_valid_dfp_parses_encoding_scale_decimal_cnpj_and_cvm_code(tmp_path):
    path = write_archive(
        tmp_path, {"dfp_cia_aberta_BPA_con_2025.csv": HEADER_BALANCE + row()}
    )
    account = list(provider(tmp_path).iter_accounts(path, "DFP", COLLECTED))[0]
    assert account.account_description == "Descrição çã"
    assert account.original_value == Decimal("123.45")
    assert account.normalized_value == Decimal("123450.00")
    assert account.cnpj == "12345678000190"
    assert account.cvm_code == "012345"
    assert account.period_kind == "annual"


def test_valid_itr_preserves_year_to_date_period(tmp_path):
    path = write_archive(
        tmp_path,
        {
            "itr_cia_aberta_DRE_con_2025.csv": HEADER_FLOW
            + row("DRE", code="3.01", start="2025-01-01")
        },
    )
    account = list(provider(tmp_path).iter_accounts(path, "ITR", COLLECTED))[0]
    assert account.period_kind == "year_to_date"
    assert account.period_start == date(2025, 1, 1)


def test_penultimate_exercise_is_not_imported(tmp_path):
    path = write_archive(
        tmp_path,
        {"dfp_cia_aberta_BPA_con_2025.csv": HEADER_BALANCE + row(order="PENÚLTIMO")},
    )
    assert list(provider(tmp_path).iter_accounts(path, "DFP")) == []


def test_direct_and_indirect_cash_flow_are_supported(tmp_path):
    entries = {
        "dfp_cia_aberta_DFC_MD_con_2025.csv": HEADER_FLOW
        + row("DFC_MD", code="6.01", start="2025-01-01"),
        "dfp_cia_aberta_DFC_MI_con_2025.csv": HEADER_FLOW
        + row("DFC_MI", code="6.03", start="2025-01-01"),
    }
    accounts = list(
        provider(tmp_path).iter_accounts(write_archive(tmp_path, entries), "DFP")
    )
    assert {item.statement_type for item in accounts} == {"DFC_MD", "DFC_MI"}
    assert {CvmFinancialEngine.normalized_key(item) for item in accounts} == {
        "operating_cash_flow",
        "financing_cash_flow",
    }


@pytest.mark.parametrize(
    "expected_method",
    ["DFC_MD", "DFC_MI"],
)
def test_import_selects_one_cash_flow_method_per_period(
    tmp_path, db_session, expected_method
):
    direct = row(
        "DFC_MD", code="6.01", value="100", start="2025-01-01",
        reference="2025-12-31", end="2025-12-31",
    )
    indirect = row(
        "DFC_MI", code="6.01", value="200", start="2025-01-01",
        reference="2025-12-31", end="2025-12-31",
    )
    entries = {}
    if expected_method == "DFC_MD":
        entries["dfp_cia_aberta_DFC_MD_con_2025.csv"] = HEADER_FLOW + direct
        entries["dfp_cia_aberta_DFC_MI_con_2025.csv"] = HEADER_FLOW + indirect
    else:
        entries["dfp_cia_aberta_DFC_MI_con_2025.csv"] = HEADER_FLOW + indirect

    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )
    service.import_archive(write_archive(tmp_path, entries), "DFP", COLLECTED)

    documents = db_session.query(CvmFinancialDocument).all()
    assert {document.statement_type for document in documents} == {expected_method}
    accounts = db_session.query(CvmFinancialAccount).all()
    assert len(accounts) == 1
    assert accounts[0].normalized_value == (
        Decimal("100000") if expected_method == "DFC_MD" else Decimal("200000")
    )


def test_bpp_total_passivo_is_not_mapped_as_liabilities_only(tmp_path):
    path = write_archive(
        tmp_path, {"dfp_cia_aberta_BPP_con_2025.csv": HEADER_BALANCE + row("BPP", code="2")}
    )
    account = list(provider(tmp_path).iter_accounts(path, "DFP"))[0]
    assert CvmFinancialEngine.normalized_key(account) == "total_liabilities_and_equity"


def test_unmapped_or_non_fixed_account_remains_unmapped(tmp_path):
    path = write_archive(
        tmp_path, {"dfp_cia_aberta_BPA_con_2025.csv": HEADER_BALANCE + row(code="1.99")}
    )
    account = list(provider(tmp_path).iter_accounts(path, "DFP"))[0]
    assert CvmFinancialEngine.normalized_key(account) is None


def raw_itr(value, end, start=date(2025, 1, 1)):
    return CvmRawAccount(
        "ITR",
        "DRE",
        "consolidated",
        "123",
        "1",
        "CIA",
        end,
        1,
        start,
        end,
        "year_to_date",
        "REAL",
        "MIL",
        "3.11",
        "Lucro",
        Decimal(value),
        Decimal(value) * 1000,
        True,
        COLLECTED,
    )


def test_isolated_quarter_is_calculated_only_from_compatible_accumulated_periods():
    previous = raw_itr("10", date(2025, 3, 31))
    current = raw_itr("25", date(2025, 6, 30))
    result = CvmFinancialEngine.isolated_quarter(current, previous)
    assert result is not None
    assert result.normalized_value == Decimal("15000")
    assert result.period_kind == "quarterly_calculated"


def test_isolated_quarter_rejects_non_adjacent_accumulated_periods():
    first_quarter = raw_itr("10", date(2025, 3, 31))
    third_quarter = raw_itr("45", date(2025, 9, 30))
    assert CvmFinancialEngine.isolated_quarter(third_quarter, first_quarter) is None


def test_isolated_quarter_is_not_calculated_when_periods_are_incompatible():
    previous = raw_itr("10", date(2025, 3, 31), date(2025, 2, 1))
    assert (
        CvmFinancialEngine.isolated_quarter(raw_itr("25", date(2025, 6, 30)), previous)
        is None
    )


def test_invalid_zip_and_path_traversal_are_rejected(tmp_path):
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"not a zip")
    with pytest.raises(CvmArchiveError):
        provider(tmp_path).validate_archive(invalid)
    traversal = write_archive(tmp_path, {"../escape.csv": "x"})
    with pytest.raises(CvmArchiveError, match="inseguro"):
        provider(tmp_path).validate_archive(traversal)


def test_uncompressed_size_limit_is_enforced(tmp_path):
    path = write_archive(tmp_path, {"large.csv": b"x" * 100})
    with pytest.raises(CvmSizeLimitError):
        provider(tmp_path, max_uncompressed_bytes=50).validate_archive(path)


def test_download_uses_fresh_cache_without_http_call(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    archive = cache / "dfp_cia_aberta_2025.zip"
    archive.write_bytes(archive_bytes({"ok.csv": "x"}))
    (cache / "dfp_cia_aberta_2025.json").write_text(
        '{"checked_at":"2026-07-20T00:00:00+00:00","collected_at":"2026-07-20T00:00:00+00:00","size_bytes":100}',
        encoding="utf-8",
    )
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    cvm = CvmOpenDataProvider(
        cache_dir=cache,
        cache_ttl_hours=99999,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = cvm.download_year("DFP", 2025)
    assert result.cache_hit is True
    assert calls == 0


def test_stale_cache_uses_conditional_headers_and_304(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    archive = cache / "dfp_cia_aberta_2025.zip"
    archive.write_bytes(archive_bytes({"ok.csv": "x"}))
    (cache / "dfp_cia_aberta_2025.json").write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00","collected_at":"2020-01-01T00:00:00+00:00","etag":"abc","last_modified":"y"}',
        encoding="utf-8",
    )

    def handler(request):
        assert request.headers["if-none-match"] == "abc"
        assert request.headers["if-modified-since"] == "y"
        return httpx.Response(304)

    cvm = CvmOpenDataProvider(
        cache_dir=cache,
        cache_ttl_hours=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert cvm.download_year("DFP", 2025).cache_hit is True


def test_import_is_idempotent_and_prefers_latest_consolidated_version(
    tmp_path, db_session
):
    content = HEADER_BALANCE + row(version=1, value="10") + row(version=2, value="20")
    individual = HEADER_BALANCE + row(version=3, scope="ind", value="99")
    path = write_archive(
        tmp_path,
        {
            "dfp_cia_aberta_BPA_con_2025.csv": content,
            "dfp_cia_aberta_BPA_ind_2025.csv": individual,
        },
    )
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )
    first = service.import_archive(path, "DFP", COLLECTED)
    second = service.import_archive(path, "DFP", COLLECTED)
    assert first["accounts_imported"] == 1
    assert second["accounts_imported"] == 0
    stored = CvmFinancialRepository(db_session).list_issuers()
    assert len(stored) == 1
    stored_account = db_session.query(CvmFinancialAccount).one()
    stored_document = db_session.get(CvmFinancialDocument, stored_account.document_id)
    assert stored_account.normalized_value == Decimal("20000")
    assert stored_document.scope == "consolidated"
    assert stored_document.version == 2


def test_import_handles_literal_duplicate_rows_in_the_same_document(tmp_path, db_session):
    # Observado em sincronização real contra dados.cvm.gov.br: o CSV oficial
    # pode conter duas linhas idênticas para a mesma (empresa, período,
    # demonstração, conta, escopo, versão) — sem deduplicação em memória,
    # isso violava a constraint de unicidade uq_cvm_document_account no
    # meio do import (a consulta de upsert_account não via seu próprio
    # INSERT ainda não commitado dentro do mesmo loop).
    duplicated_line = row(code="1", value="4500413")
    content = HEADER_BALANCE + duplicated_line + duplicated_line
    path = write_archive(tmp_path, {"dfp_cia_aberta_BPA_con_2025.csv": content})
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )
    result = service.import_archive(path, "DFP", COLLECTED)
    assert result["accounts_imported"] == 1
    stored_account = db_session.query(CvmFinancialAccount).one()
    assert stored_account.normalized_value == Decimal("4500413000")


def test_import_duplicate_rows_does_not_affect_idempotent_reimport(tmp_path, db_session):
    duplicated_line = row(code="1", value="10")
    content = HEADER_BALANCE + duplicated_line + duplicated_line
    path = write_archive(tmp_path, {"dfp_cia_aberta_BPA_con_2025.csv": content})
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )
    first = service.import_archive(path, "DFP", COLLECTED)
    second = service.import_archive(path, "DFP", COLLECTED)
    assert first["accounts_imported"] == 1
    assert second["accounts_imported"] == 0
    assert db_session.query(CvmFinancialAccount).count() == 1


def _seed_document(repository, *, cnpj, document_type, period_end, version=1):
    issuer = repository.upsert_issuer(cnpj, "12345", "COMPANHIA ACAO S.A.")
    account = raw_itr("1", period_end) if document_type == "ITR" else CvmRawAccount(
        document_type="DFP",
        statement_type="BPA",
        scope="consolidated",
        cnpj=cnpj,
        cvm_code="12345",
        issuer_name="COMPANHIA ACAO S.A.",
        reference_date=period_end,
        version=version,
        period_start=None,
        period_end=period_end,
        period_kind="annual",
        currency="REAL",
        scale="MIL",
        account_code="1",
        account_description="Ativo Total",
        original_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        is_fixed_account=True,
        collected_at=COLLECTED,
    )
    document = repository.upsert_document(issuer.id, account)
    repository.commit()
    return issuer, document


def test_fiscal_year_end_returns_most_recent_dfp_period_end(db_session):
    repository = CvmFinancialRepository(db_session)
    issuer, _ = _seed_document(
        repository, cnpj="12345678000190", document_type="DFP", period_end=date(2024, 12, 31)
    )
    _seed_document(
        repository, cnpj="12345678000190", document_type="DFP", period_end=date(2025, 12, 31)
    )
    assert repository.fiscal_year_end(issuer.id) == date(2025, 12, 31)


def test_fiscal_year_end_returns_none_when_issuer_has_only_itr(db_session):
    repository = CvmFinancialRepository(db_session)
    issuer, _ = _seed_document(
        repository, cnpj="98765432000199", document_type="ITR", period_end=date(2026, 3, 31)
    )
    assert repository.fiscal_year_end(issuer.id) is None


def test_asset_without_explicit_issuer_link_is_pending(db_session):
    asset = Asset(ticker="TEST3", name="Teste", asset_type="STOCK", currency="BRL")
    db_session.add(asset)
    db_session.commit()
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(Path(".pytest_cache")),
    )
    result = service.asset_link(asset.id)
    assert result["status"] == "pending"
    assert result["issuer"] is None


def test_itr_compatible_accumulated_values_persist_calculated_quarter(
    tmp_path, db_session
):
    content = (
        HEADER_FLOW
        + row(
            "DRE",
            code="3.11",
            value="10",
            start="2025-01-01",
            reference="2025-03-31",
            end="2025-03-31",
        )
        + row(
            "DRE",
            code="3.11",
            value="25",
            start="2025-01-01",
            reference="2025-06-30",
            end="2025-06-30",
        )
    )
    path = write_archive(tmp_path, {"itr_cia_aberta_DRE_con_2025.csv": content})
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )
    service.import_archive(path, "ITR", COLLECTED)
    calculated = (
        db_session.query(CvmFinancialAccount)
        .filter(CvmFinancialAccount.acquisition_method == "calculated")
        .one()
    )
    document = db_session.get(CvmFinancialDocument, calculated.document_id)
    assert calculated.normalized_value == Decimal("15000")
    assert document.period_kind == "quarterly_calculated"


def test_link_asset_does_not_commit_and_rollback_undoes_link_and_unrelated_change(
    db_session,
):
    """Fronteira transacional de CvmFinancialRepository.link_asset(): o
    repository nunca decide quando comitar (ver docstring de link_asset).
    Prova por comportamento, não só por ausência de chamada: um flush
    torna o vínculo visível NA MESMA sessão, mas um rollback desfaz tanto
    o vínculo quanto um trabalho pendente não relacionado criado antes
    dele -- se link_asset tivesse comitado, o rollback não teria efeito
    algum sobre nenhum dos dois.
    """
    asset = Asset(ticker="LNK14", name="Vinculo Teste", asset_type="STOCK", currency="BRL")
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    issuer = repository.upsert_issuer("33444555000143", "66666", "EMISSOR VINCULO S.A.")
    db_session.commit()

    unrelated = Asset(
        ticker="LNK24", name="Nao Relacionado", asset_type="STOCK", currency="BRL"
    )
    db_session.add(unrelated)
    db_session.flush()

    link = repository.link_asset(asset.id, issuer.id)
    assert link.issuer_id == issuer.id
    assert (
        db_session.query(AssetCvmIssuer)
        .filter(AssetCvmIssuer.asset_id == asset.id)
        .first()
        is not None
    )

    db_session.rollback()

    assert (
        db_session.query(AssetCvmIssuer)
        .filter(AssetCvmIssuer.asset_id == asset.id)
        .first()
        is None
    )
    assert db_session.query(Asset).filter(Asset.ticker == "LNK24").first() is None


def test_link_asset_updates_existing_link_without_committing(db_session):
    asset = Asset(ticker="LNK34", name="Vinculo Atualiza", asset_type="STOCK", currency="BRL")
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    first_issuer = repository.upsert_issuer("55666777000105", "44444", "EMISSOR UM S.A.")
    second_issuer = repository.upsert_issuer("66777888000186", "33333", "EMISSOR DOIS S.A.")
    db_session.commit()

    repository.link_asset(asset.id, first_issuer.id)
    db_session.commit()

    repository.link_asset(asset.id, second_issuer.id)
    db_session.rollback()

    persisted = (
        db_session.query(AssetCvmIssuer)
        .filter(AssetCvmIssuer.asset_id == asset.id)
        .first()
    )
    assert persisted.issuer_id == first_issuer.id


def test_service_link_asset_persists_the_link_as_an_explicit_write(db_session):
    """Fluxo manual (endpoint de superusuário): o serviço decide sua
    própria fronteira de commit, no mesmo padrão de import_archive().
    """
    asset = Asset(ticker="SVLK4", name="Vinculo Servico", asset_type="STOCK", currency="BRL")
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    issuer = repository.upsert_issuer("44555666000124", "55555", "EMISSOR SERVICO S.A.")
    db_session.commit()

    service = CvmFinancialService(
        repository, AssetRepository(db_session), provider(Path(".pytest_cache"))
    )
    service.link_asset(asset.id, issuer.id)

    fresh = SessionLocal()
    try:
        link = (
            fresh.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset.id)
            .first()
        )
        assert link is not None
        assert link.issuer_id == issuer.id
    finally:
        fresh.close()


def test_service_link_asset_can_change_an_existing_link_to_a_different_issuer(
    db_session,
):
    """Fluxo manual (endpoint de superusuário): pode trocar explicitamente
    o emissor de um vínculo já existente -- ao contrário do auto-link
    automático (IndicatorResolverService, via CvmFinancialRepository.
    ensure_asset_link), que nunca substitui silenciosamente um vínculo
    para um emissor diferente. Essa capacidade de troca deliberada
    continua exclusiva do fluxo manual.
    """
    asset = Asset(
        ticker="SVLK5", name="Vinculo Troca Manual", asset_type="STOCK", currency="BRL"
    )
    db_session.add(asset)
    db_session.commit()

    repository = CvmFinancialRepository(db_session)
    issuer_a = repository.upsert_issuer("12312312000100", "10001", "EMISSOR A S.A.")
    issuer_b = repository.upsert_issuer("32132132000100", "10002", "EMISSOR B S.A.")
    db_session.commit()

    service = CvmFinancialService(
        repository, AssetRepository(db_session), provider(Path(".pytest_cache"))
    )
    service.link_asset(asset.id, issuer_a.id)
    service.link_asset(asset.id, issuer_b.id)

    fresh = SessionLocal()
    try:
        link = (
            fresh.query(AssetCvmIssuer)
            .filter(AssetCvmIssuer.asset_id == asset.id)
            .first()
        )
        assert link is not None
        assert link.issuer_id == issuer_b.id
    finally:
        fresh.close()


def test_import_selects_latest_version_before_cash_flow_method(tmp_path, db_session):
    direct_v1 = row(
        "DFC_MD", version=1, code="6.01", value="100",
        start="2025-01-01", reference="2025-12-31", end="2025-12-31",
    )
    indirect_v2 = row(
        "DFC_MI", version=2, code="6.01", value="250",
        start="2025-01-01", reference="2025-12-31", end="2025-12-31",
    )
    entries = {
        "dfp_cia_aberta_DFC_MD_con_2025.csv": HEADER_FLOW + direct_v1,
        "dfp_cia_aberta_DFC_MI_con_2025.csv": HEADER_FLOW + indirect_v2,
    }
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )
    service.import_archive(write_archive(tmp_path, entries), "DFP", COLLECTED)

    documents = db_session.query(CvmFinancialDocument).all()
    assert len(documents) == 1
    assert documents[0].version == 2
    assert documents[0].statement_type == "DFC_MI"
    accounts = db_session.query(CvmFinancialAccount).all()
    assert len(accounts) == 1
    assert accounts[0].normalized_value == Decimal("250000")
