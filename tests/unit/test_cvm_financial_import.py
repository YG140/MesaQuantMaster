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
    CvmFinancialCalculationLineage,
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


def raw_itr(
    value, end, start=date(2025, 1, 1), code="3.11", statement_type="DRE",
    period_kind="year_to_date",
):
    return CvmRawAccount(
        "ITR",
        statement_type,
        "consolidated",
        "123",
        "1",
        "CIA",
        end,
        1,
        start,
        end,
        period_kind,
        "REAL",
        "MIL",
        code,
        "Conta de teste",
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


def test_import_is_idempotent_and_preserves_versions_with_scope_preference(
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
    assert first["accounts_imported"] == 3
    assert second["accounts_imported"] == 0
    stored = CvmFinancialRepository(db_session).list_issuers()
    assert len(stored) == 1
    stored_accounts = db_session.query(CvmFinancialAccount).all()
    assert len(stored_accounts) == 3
    stored_documents = [
        db_session.get(CvmFinancialDocument, item.document_id)
        for item in stored_accounts
    ]
    # As versões 1 e 2 têm escopo consolidado e descartam o individual
    # concorrente; a versão 3 só existe no escopo individual e deve ser
    # preservada para não apagar uma versão histórica disponível.
    assert {item.version for item in stored_documents} == {1, 2, 3}
    assert {
        (item.version, item.scope) for item in stored_documents
    } == {
        (1, "consolidated"),
        (2, "consolidated"),
        (3, "individual"),
    }
    latest = max(stored_documents, key=lambda item: item.version)
    latest_account = next(
        item for item in stored_accounts if item.document_id == latest.id
    )
    assert latest_account.normalized_value == Decimal("99000")


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
    # Reimportar o mesmo arquivo não pode duplicar a linhagem nem trocar as fontes.
    service.import_archive(path, "ITR", COLLECTED)
    calculated = (
        db_session.query(CvmFinancialAccount)
        .filter(CvmFinancialAccount.acquisition_method == "calculated")
        .one()
    )
    document = db_session.get(CvmFinancialDocument, calculated.document_id)
    assert calculated.normalized_value == Decimal("15000")
    assert document.period_kind == "quarterly_calculated"

    assert (
        db_session.query(CvmFinancialCalculationLineage)
        .filter(
            CvmFinancialCalculationLineage.derived_document_id == document.id
        )
        .count()
        == 1
    )
    lineage = (
        db_session.query(CvmFinancialCalculationLineage)
        .filter(
            CvmFinancialCalculationLineage.derived_document_id == document.id
        )
        .one()
    )
    current_source = db_session.get(
        CvmFinancialDocument, lineage.current_source_document_id
    )
    previous_source = db_session.get(
        CvmFinancialDocument, lineage.previous_source_document_id
    )
    assert current_source.period_end == date(2025, 6, 30)
    assert previous_source.period_end == date(2025, 3, 31)
    assert lineage.current_source_version == current_source.version == 1
    assert lineage.previous_source_version == previous_source.version == 1
    assert lineage.current_collected_at == current_source.collected_at
    assert lineage.previous_collected_at == previous_source.collected_at
    assert lineage.selected_method == "DRE"
    assert lineage.scope == "consolidated"
    assert lineage.calculation_rule == "ITR_YTD_CURRENT_MINUS_PREVIOUS_3M"


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
    individual_v2 = row(
        "DFC_MI", version=2, scope="ind", code="6.01", value="999",
        start="2025-01-01", reference="2025-12-31", end="2025-12-31",
    )
    entries = {
        "dfp_cia_aberta_DFC_MD_con_2025.csv": HEADER_FLOW + direct_v1,
        "dfp_cia_aberta_DFC_MI_con_2025.csv": HEADER_FLOW + indirect_v2,
        "dfp_cia_aberta_DFC_MI_ind_2025.csv": HEADER_FLOW + individual_v2,
    }
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )
    service.import_archive(write_archive(tmp_path, entries), "DFP", COLLECTED)

    documents = db_session.query(CvmFinancialDocument).order_by(
        CvmFinancialDocument.version
    ).all()
    # C4: a versão anterior continua preservada para auditoria; a versão
    # mais recente é a vigente para consumo.
    assert [
        (item.version, item.statement_type, item.scope) for item in documents
    ] == [
        (1, "DFC_MD", "consolidated"),
        (2, "DFC_MI", "consolidated"),
    ]
    accounts = db_session.query(CvmFinancialAccount).order_by(
        CvmFinancialAccount.normalized_value
    ).all()
    assert [item.normalized_value for item in accounts] == [
        Decimal("100000"),
        Decimal("250000"),
    ]


@pytest.mark.parametrize(
    ("statement_type", "account_code"),
    [
        ("BPA", "1.01.01"),
        ("DRE", "3.99"),
        ("DFC_MD", "6.99"),
        ("DFC_MI", "6.99"),
    ],
)
def test_isolated_quarter_rejects_balance_and_unclassified_accounts(
    statement_type, account_code
):
    previous = raw_itr(
        "10", date(2025, 3, 31), code=account_code,
        statement_type=statement_type,
    )
    current = raw_itr(
        "25", date(2025, 6, 30), code=account_code,
        statement_type=statement_type,
    )
    assert CvmFinancialEngine.isolated_quarter(current, previous) is None


def test_itr_non_calendar_fiscal_year_is_classified_as_year_to_date(tmp_path):
    path = write_archive(
        tmp_path,
        {
            "itr_cia_aberta_DRE_con_2025.csv": HEADER_FLOW
            + row(
                "DRE", code="3.11", start="2025-04-01",
                reference="2025-09-30", end="2025-09-30",
            )
        },
    )
    account = list(provider(tmp_path).iter_accounts(path, "ITR", COLLECTED))[0]
    assert account.period_kind == "year_to_date"
    assert account.period_start == date(2025, 4, 1)


def test_isolated_quarter_requires_both_periods_to_be_fiscal_ytd():
    previous = raw_itr(
        "10", date(2025, 6, 30), start=date(2025, 4, 1),
        period_kind="quarterly_reported",
    )
    current = raw_itr(
        "25", date(2025, 9, 30), start=date(2025, 4, 1),
    )
    assert CvmFinancialEngine.isolated_quarter(current, previous) is None


def test_isolated_quarter_accepts_non_calendar_fiscal_year():
    previous = raw_itr("90", date(2025, 6, 30), start=date(2025, 4, 1))
    current = raw_itr("200", date(2025, 9, 30), start=date(2025, 4, 1))
    result = CvmFinancialEngine.isolated_quarter(current, previous)
    assert result is not None
    assert result.normalized_value == Decimal("110000")
    assert result.period_start == date(2025, 6, 30)


def test_isolated_quarter_rejects_non_month_end_periods():
    previous = raw_itr("10", date(2025, 3, 15))
    current = raw_itr("25", date(2025, 6, 15))
    assert CvmFinancialEngine.isolated_quarter(current, previous) is None

def test_isolated_quarter_preserves_negative_cash_flow():
    previous = raw_itr(
        "100", date(2025, 3, 31), code="6.01", statement_type="DFC_MD"
    )
    current = raw_itr(
        "70", date(2025, 6, 30), code="6.01", statement_type="DFC_MD"
    )
    result = CvmFinancialEngine.isolated_quarter(current, previous)
    assert result is not None
    assert result.original_value == Decimal("-30")
    assert result.normalized_value == Decimal("-30000")


def test_isolated_quarter_uses_decimal_without_float_rounding():
    previous = raw_itr(
        "0.01", date(2025, 3, 31), code="3.11"
    )
    current = raw_itr(
        "12345678901234567.88", date(2025, 6, 30), code="3.11"
    )
    result = CvmFinancialEngine.isolated_quarter(current, previous)
    assert result is not None
    assert result.original_value == Decimal("12345678901234567.87")
    assert result.normalized_value == Decimal("12345678901234567870.00")


@pytest.mark.parametrize(
    "field, previous_value",
    [
        ("cnpj", "99999999000199"),
        ("scope", "individual"),
        ("account_code", "3.01"),
    ],
)
def test_isolated_quarter_rejects_mismatched_source_identity(field, previous_value):
    previous = raw_itr("10", date(2025, 3, 31))
    current = raw_itr("25", date(2025, 6, 30))
    previous = __import__("dataclasses").replace(
        previous, **{field: previous_value}
    )
    assert CvmFinancialEngine.isolated_quarter(current, previous) is None


def test_restatement_selects_winning_document_before_its_accounts(tmp_path, db_session):
    # Q1 v1 publica A+B; a reapresentação v2 publica somente A.
    # Q2 acumulado publica A+B. B não pode ser recuperada de Q1 v1.
    q1_v1 = (
        row("DRE", version=1, code="3.01", value="10",
            start="2025-01-01", reference="2025-03-31", end="2025-03-31")
        + row("DRE", version=1, code="3.11", value="20",
              start="2025-01-01", reference="2025-03-31", end="2025-03-31")
    )
    q1_v2 = row(
        "DRE", version=2, code="3.01", value="12",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    q2 = (
        row("DRE", version=1, code="3.01", value="30",
            start="2025-01-01", reference="2025-06-30", end="2025-06-30")
        + row("DRE", version=1, code="3.11", value="50",
              start="2025-01-01", reference="2025-06-30", end="2025-06-30")
    )
    path = write_archive(
        tmp_path,
        {"itr_cia_aberta_DRE_con_2025.csv": HEADER_FLOW + q1_v1 + q1_v2 + q2},
    )
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )

    service.import_archive(path, "ITR", COLLECTED)
    # Reimportar a mesma fonte não pode restaurar a conta B da v1.
    service.import_archive(path, "ITR", COLLECTED)

    calculated = (
        db_session.query(CvmFinancialAccount, CvmFinancialDocument)
        .join(
            CvmFinancialDocument,
            CvmFinancialAccount.document_id == CvmFinancialDocument.id,
        )
        .filter(CvmFinancialAccount.acquisition_method == "calculated")
        .all()
    )
    assert len(calculated) == 1
    calculated_account, calculated_document = calculated[0]
    assert calculated_account.account_code == "3.01"
    assert calculated_account.normalized_value == Decimal("18000")
    assert calculated_document.period_end == date(2025, 6, 30)

    lineage = (
        db_session.query(CvmFinancialCalculationLineage)
        .filter(
            CvmFinancialCalculationLineage.derived_document_id
            == calculated_document.id
        )
        .one()
    )
    previous_source = db_session.get(
        CvmFinancialDocument, lineage.previous_source_document_id
    )
    assert previous_source.period_end == date(2025, 3, 31)
    assert previous_source.version == 2


def test_newer_non_ytd_restatement_blocks_fallback_to_older_ytd_document(
    tmp_path, db_session
):
    q1_v1 = row(
        "DRE", version=1, code="3.01", value="10",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    # A versão 2 do mesmo período não contém início do exercício e,
    # portanto, não pode ser usada para derivar trimestre. Ela ainda assim
    # substitui a v1: não se deve voltar silenciosamente à versão antiga.
    q1_v2 = row(
        "DRE", version=2, code="3.01", value="12",
        start="", reference="2025-03-31", end="2025-03-31",
    )
    q2 = row(
        "DRE", version=1, code="3.01", value="30",
        start="2025-01-01", reference="2025-06-30", end="2025-06-30",
    )
    path = write_archive(
        tmp_path,
        {"itr_cia_aberta_DRE_con_2025.csv": HEADER_FLOW + q1_v1 + q1_v2 + q2},
    )
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )

    service.import_archive(path, "ITR", COLLECTED)

    calculated = (
        db_session.query(CvmFinancialAccount)
        .filter(CvmFinancialAccount.acquisition_method == "calculated")
        .all()
    )
    assert calculated == []


@pytest.mark.parametrize(
    ("first_method", "second_method"),
    [("DFC_MD", "DFC_MI"), ("DFC_MI", "DFC_MD")],
)
def test_itr_cash_flow_method_switch_starts_a_new_series_without_mixing(
    tmp_path, db_session, first_method, second_method
):
    # Q1 é reapresentado com troca de método. A série nova começa em Q1;
    # Q2 só pode ser isolado contra Q1 do mesmo método, nunca contra a série
    # anterior. A linhagem deve apontar para o método vigente.
    first_q1 = row(
        first_method, version=1, code="6.01", value="10",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    replacement_q1 = row(
        second_method, version=2, code="6.01", value="12",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    q2 = row(
        second_method, version=1, code="6.01", value="25",
        start="2025-01-01", reference="2025-06-30", end="2025-06-30",
    )
    entries = {
        f"itr_cia_aberta_{first_method}_con_2025.csv": HEADER_FLOW + first_q1,
        f"itr_cia_aberta_{second_method}_con_2025.csv": HEADER_FLOW
        + replacement_q1 + q2,
    }
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )

    service.import_archive(write_archive(tmp_path, entries), "ITR", COLLECTED)

    calculated = (
        db_session.query(CvmFinancialAccount, CvmFinancialDocument)
        .join(
            CvmFinancialDocument,
            CvmFinancialAccount.document_id == CvmFinancialDocument.id,
        )
        .filter(CvmFinancialAccount.acquisition_method == "calculated")
        .all()
    )
    assert len(calculated) == 1
    calculated_account, calculated_document = calculated[0]
    assert calculated_account.account_code == "6.01"
    assert calculated_account.normalized_value == Decimal("13000")
    assert calculated_document.statement_type == second_method
    assert calculated_document.period_end == date(2025, 6, 30)

    lineage = (
        db_session.query(CvmFinancialCalculationLineage)
        .filter(
            CvmFinancialCalculationLineage.derived_document_id
            == calculated_document.id
        )
        .one()
    )
    current_source = db_session.get(
        CvmFinancialDocument, lineage.current_source_document_id
    )
    previous_source = db_session.get(
        CvmFinancialDocument, lineage.previous_source_document_id
    )
    assert current_source.statement_type == second_method
    assert previous_source.statement_type == second_method
    assert previous_source.version == 2


def test_itr_same_version_md_mi_conflict_abstains_from_quarter_derivation(
    tmp_path, db_session
):
    md_q1 = row(
        "DFC_MD", version=2, code="6.01", value="10",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    mi_q1 = row(
        "DFC_MI", version=2, code="6.01", value="11",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    mi_q2 = row(
        "DFC_MI", version=1, code="6.01", value="25",
        start="2025-01-01", reference="2025-06-30", end="2025-06-30",
    )
    service = CvmFinancialService(
        CvmFinancialRepository(db_session),
        AssetRepository(db_session),
        provider(tmp_path),
    )

    # Imports separados simulam a chegada dos arquivos em sincronizações
    # distintas. Assim ambos os métodos ficam persistidos para o teste da
    # seleção conservadora no cálculo, sem o desempate do importador mascarar
    # o conflito antes de chegar ao _calculate_quarters().
    md_archive = write_archive(
        tmp_path, {"itr_cia_aberta_DFC_MD_con_2025.csv": HEADER_FLOW + md_q1}
    )
    service.import_archive(md_archive, "ITR", COLLECTED)
    mi_archive = write_archive(
        tmp_path,
        {"itr_cia_aberta_DFC_MI_con_2025.csv": HEADER_FLOW + mi_q1 + mi_q2},
    )
    service.import_archive(mi_archive, "ITR", COLLECTED)

    persisted_methods = {
        document.statement_type
        for document in db_session.query(CvmFinancialDocument).all()
    }
    assert {"DFC_MD", "DFC_MI"} <= persisted_methods

    calculated = (
        db_session.query(CvmFinancialAccount)
        .filter(CvmFinancialAccount.acquisition_method == "calculated")
        .all()
    )
    assert calculated == []


def test_latest_normalized_abstains_when_latest_dfc_marker_has_both_methods(
    tmp_path, db_session
):
    md_q1 = row(
        "DFC_MD", version=2, code="6.01", value="10",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    mi_q1 = row(
        "DFC_MI", version=2, code="6.01", value="11",
        start="2025-01-01", reference="2025-03-31", end="2025-03-31",
    )
    repository = CvmFinancialRepository(db_session)
    service = CvmFinancialService(
        repository,
        AssetRepository(db_session),
        provider(tmp_path),
    )

    # Arquivos importados em execuções separadas garantem que o banco contenha
    # os dois métodos na mesma referência/versão. Importá-los juntos acionaria
    # o desempate do importador e tornaria este teste de latest_normalized()
    # incapaz de exercitar o cenário ambíguo.
    md_archive = write_archive(
        tmp_path, {"itr_cia_aberta_DFC_MD_con_2025.csv": HEADER_FLOW + md_q1}
    )
    service.import_archive(md_archive, "ITR", COLLECTED)
    mi_archive = write_archive(
        tmp_path, {"itr_cia_aberta_DFC_MI_con_2025.csv": HEADER_FLOW + mi_q1}
    )
    service.import_archive(mi_archive, "ITR", COLLECTED)

    persisted_methods = {
        document.statement_type
        for document in db_session.query(CvmFinancialDocument).all()
    }
    assert {"DFC_MD", "DFC_MI"} <= persisted_methods

    issuer = repository.list_issuers()[0]
    asset = Asset(
        ticker="DFCT1", name="Teste DFC", asset_type="STOCK", currency="BRL"
    )
    db_session.add(asset)
    db_session.commit()
    service.link_asset(asset.id, issuer.id)

    rows = repository.latest_normalized(asset.id)
    assert not any(
        document.statement_type in {"DFC_MD", "DFC_MI"}
        for _, document, _ in rows
    )
