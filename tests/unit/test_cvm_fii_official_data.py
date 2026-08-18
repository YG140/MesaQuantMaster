from __future__ import annotations

import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest

from app.models.cvm_fii import AssetFiiIssuer, FiiIssuer, FiiPropertyVacancyDocument
from app.providers.cvm_fii_open_data_provider import (
    CvmFiiArchiveError,
    CvmFiiOpenDataProvider,
    CvmFiiSizeLimitError,
)
from app.repositories.cvm_fii_repository import CvmFiiRepository
from app.services.cvm_fii_service import CvmFiiService


@pytest.fixture
def safe_tmp_dir():
    """Diretório temporário próprio, fora da fixture `tmp_path` do pytest
    (PermissionError conhecido de limpeza compartilhada no Windows -- ver
    memória do projeto). Nome único (UUID), limpo explicitamente ao final
    de cada teste; nunca deixa nada persistente no repositório."""
    path = Path(tempfile.gettempdir()) / f"mesaqm_fii_test_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


COLLECTED = datetime(2026, 8, 18, tzinfo=timezone.utc)

IMOVEL_HEADER = (
    "CNPJ_Fundo_Classe;Data_Referencia;Versao;Classe;Nome_Imovel;Endereco;Area;"
    "Numero_Unidades;Outras_Caracteristicas_Relevantes;Percentual_Vacancia;"
    "Percentual_Inadimplencia;Percentual_Receitas_FII;Percentual_Locado;"
    "Percentual_Vendido;Percentual_Conclusao_Obras_Realizado;"
    "Percentual_Conclusao_Obras_Previsto;Custo_Construcao_Realizado;"
    "Custo_Construcao_Previsto;Percentual_Imovel_Total_Investido\n"
)
GERAL_HEADER = "CNPJ_Fundo_Classe;Data_Referencia;Versao;Nome_Fundo_Classe\n"


def imovel_row(
    cnpj="11.222.333/0001-81",
    reference="2026-06-30",
    version=1,
    classe="Imóveis para renda acabados",
    name="Imovel A",
    area="1000",
    vacancy="0.05",
):
    fields = [
        cnpj,
        reference,
        str(version),
        classe,
        name,
        "Endereco",
        area,
        "1",
        "-",
        vacancy,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]
    return ";".join(fields) + "\n"


def geral_row(cnpj="11.222.333/0001-81", reference="2026-06-30", version=1, name="FUNDO TESTE FII"):
    return f"{cnpj};{reference};{version};{name}\n"


def archive_bytes(entries: dict[str, str | bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(
                name, content.encode("cp1252") if isinstance(content, str) else content
            )
    return output.getvalue()


def write_archive(safe_tmp_dir: Path, entries: dict[str, str | bytes]) -> Path:
    path = safe_tmp_dir / "sample.zip"
    path.write_bytes(archive_bytes(entries))
    return path


def provider(safe_tmp_dir, **kwargs):
    return CvmFiiOpenDataProvider(cache_dir=safe_tmp_dir / "cache", **kwargs)


# --- Provider: parsing, segurança, cache -----------------------------------


def test_iter_properties_parses_real_fields_and_preserves_missing_vacancy(safe_tmp_dir):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05") + imovel_row(
        name="Imovel B", vacancy=""
    )
    path = write_archive(safe_tmp_dir, {"inf_trimestral_fii_imovel_2026.csv": content})
    rows = list(provider(safe_tmp_dir).iter_properties(path, COLLECTED))
    assert len(rows) == 2
    assert rows[0].cnpj == "11222333000181"
    assert rows[0].vacancy_rate == Decimal("0.05")
    assert rows[0].area == Decimal("1000")
    # Vacância ausente na fonte oficial nunca vira 0 -- permanece None.
    assert rows[1].vacancy_rate is None


def test_iter_properties_parses_brazilian_decimal_comma(safe_tmp_dir):
    content = IMOVEL_HEADER + imovel_row(vacancy="0,0512", area="1.234,5")
    path = write_archive(safe_tmp_dir, {"inf_trimestral_fii_imovel_2026.csv": content})
    row = next(provider(safe_tmp_dir).iter_properties(path, COLLECTED))
    assert row.vacancy_rate == Decimal("0.0512")


def test_iter_fund_names_matches_real_field_and_ignores_empty_name(safe_tmp_dir):
    content = GERAL_HEADER + geral_row(name="FUNDO REAL FII") + geral_row(
        cnpj="99.888.777/0001-11", name=""
    )
    path = write_archive(safe_tmp_dir, {"inf_trimestral_fii_geral_2026.csv": content})
    names = list(provider(safe_tmp_dir).iter_fund_names(path))
    assert len(names) == 1
    assert names[0].cnpj == "11222333000181"
    assert names[0].official_name == "FUNDO REAL FII"


def test_invalid_zip_and_path_traversal_are_rejected(safe_tmp_dir):
    invalid = safe_tmp_dir / "invalid.zip"
    invalid.write_bytes(b"not a zip")
    with pytest.raises(CvmFiiArchiveError):
        provider(safe_tmp_dir).validate_archive(invalid)
    traversal = write_archive(safe_tmp_dir, {"../escape.csv": "x"})
    with pytest.raises(CvmFiiArchiveError, match="inseguro"):
        provider(safe_tmp_dir).validate_archive(traversal)


def test_uncompressed_size_limit_is_enforced(safe_tmp_dir):
    path = write_archive(safe_tmp_dir, {"large.csv": b"x" * 100})
    with pytest.raises(CvmFiiSizeLimitError):
        provider(safe_tmp_dir, max_uncompressed_bytes=50).validate_archive(path)


def test_download_uses_fresh_cache_without_http_call(safe_tmp_dir):
    cache = safe_tmp_dir / "cache"
    cache.mkdir()
    archive = cache / "inf_trimestral_fii_2026.zip"
    archive.write_bytes(archive_bytes({"ok.csv": "x"}))
    (cache / "inf_trimestral_fii_2026.json").write_text(
        '{"checked_at":"2026-08-18T00:00:00+00:00","collected_at":"2026-08-18T00:00:00+00:00","size_bytes":100}',
        encoding="utf-8",
    )
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    cvm_fii = CvmFiiOpenDataProvider(
        cache_dir=cache,
        cache_ttl_hours=99999,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = cvm_fii.download_year(2026)
    assert result.cache_hit is True
    assert calls == 0


def test_stale_cache_uses_conditional_headers_and_304(safe_tmp_dir):
    cache = safe_tmp_dir / "cache"
    cache.mkdir()
    archive = cache / "inf_trimestral_fii_2026.zip"
    archive.write_bytes(archive_bytes({"ok.csv": "x"}))
    (cache / "inf_trimestral_fii_2026.json").write_text(
        '{"checked_at":"2020-01-01T00:00:00+00:00","collected_at":"2020-01-01T00:00:00+00:00","etag":"abc","last_modified":"y"}',
        encoding="utf-8",
    )

    def handler(request):
        assert request.headers["if-none-match"] == "abc"
        assert request.headers["if-modified-since"] == "y"
        return httpx.Response(304)

    cvm_fii = CvmFiiOpenDataProvider(
        cache_dir=cache,
        cache_ttl_hours=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert cvm_fii.download_year(2026).cache_hit is True


# --- Caminho operacional de sync: populamento limpo, falha não corrompe ----


def test_synchronize_populates_clean_database_and_tracks_run(safe_tmp_dir, db_session):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05")
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        safe_tmp_dir,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )

    class StubProvider(CvmFiiOpenDataProvider):
        def download_year(self, year):
            from app.providers.cvm_fii_open_data_provider import CvmFiiDownloadResult

            return CvmFiiDownloadResult(
                path=path,
                etag=None,
                last_modified=None,
                collected_at=COLLECTED,
                cache_hit=False,
                size_bytes=path.stat().st_size,
            )

    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, StubProvider(cache_dir=safe_tmp_dir / "cache"))
    result = service.synchronize(2026)
    assert result["documents_imported"] == 1

    runs = repo.list_runs()
    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert runs[0].documents_imported == 1
    assert repo.find_issuer_by_cnpj("11222333000181") is not None


def test_synchronize_marks_run_failed_and_does_not_corrupt_on_provider_error(
    safe_tmp_dir, db_session
):
    class FailingProvider(CvmFiiOpenDataProvider):
        def download_year(self, year):
            raise RuntimeError("CVM indisponível (simulado)")

    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, FailingProvider(cache_dir=safe_tmp_dir / "cache"))
    with pytest.raises(RuntimeError):
        service.synchronize(2026)

    runs = repo.list_runs()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error_message is not None
    # Nenhum dado parcial/corrompido foi persistido.
    assert db_session.query(FiiIssuer).count() == 0
    assert db_session.query(FiiPropertyVacancyDocument).count() == 0


def test_synchronize_is_idempotent_on_repeated_execution(safe_tmp_dir, db_session):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05")
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        safe_tmp_dir,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )

    class StubProvider(CvmFiiOpenDataProvider):
        def download_year(self, year):
            from app.providers.cvm_fii_open_data_provider import CvmFiiDownloadResult

            return CvmFiiDownloadResult(
                path=path,
                etag=None,
                last_modified=None,
                collected_at=COLLECTED,
                cache_hit=False,
                size_bytes=path.stat().st_size,
            )

    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, StubProvider(cache_dir=safe_tmp_dir / "cache"))
    service.synchronize(2026)
    service.synchronize(2026)
    assert db_session.query(FiiIssuer).count() == 1
    assert db_session.query(FiiPropertyVacancyDocument).count() == 1
    assert len(repo.list_runs()) == 2


# --- Service: agregação, reapresentação, idempotência -----------------------


def test_import_archive_computes_area_weighted_vacancy(safe_tmp_dir, db_session):
    content = (
        IMOVEL_HEADER
        + imovel_row(name="A", area="1000", vacancy="0.10")
        + imovel_row(name="B", area="3000", vacancy="0.02")
    )
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        safe_tmp_dir,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(safe_tmp_dir))
    result = service.import_archive(path, COLLECTED)
    assert result["documents_imported"] == 1
    issuer = repo.find_issuer_by_cnpj("11222333000181")
    assert issuer is not None
    assert issuer.official_name == "FUNDO TESTE FII"
    document = repo.latest_vacancy_document(issuer.id)
    # (1000*0.10 + 3000*0.02) / 4000 = 0.04
    assert document.area_weighted_vacancy_rate == Decimal("0.04")
    assert document.property_count == 2


def test_import_archive_never_fabricates_vacancy_when_no_property_has_data(
    safe_tmp_dir, db_session
):
    content = IMOVEL_HEADER + imovel_row(vacancy="") + imovel_row(name="B", vacancy="")
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        safe_tmp_dir,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(safe_tmp_dir))
    result = service.import_archive(path, COLLECTED)
    assert result["documents_imported"] == 0
    assert repo.find_issuer_by_cnpj("11222333000181") is None


def test_import_archive_skips_fund_without_confirmed_official_name(
    safe_tmp_dir, db_session
):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05")
    path = write_archive(
        safe_tmp_dir, {"inf_trimestral_fii_imovel_2026.csv": content}
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(safe_tmp_dir))
    result = service.import_archive(path, COLLECTED)
    assert result["documents_imported"] == 0


def test_import_archive_reapresentation_uses_latest_version_only(safe_tmp_dir, db_session):
    content = (
        IMOVEL_HEADER
        + imovel_row(version=1, area="1000", vacancy="0.50")
        + imovel_row(version=2, area="1000", vacancy="0.01")
    )
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        safe_tmp_dir,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(safe_tmp_dir))
    service.import_archive(path, COLLECTED)
    issuer = repo.find_issuer_by_cnpj("11222333000181")
    document = repo.latest_vacancy_document(issuer.id)
    assert document.version == 2
    assert document.area_weighted_vacancy_rate == Decimal("0.01")


def test_import_archive_is_idempotent_on_reimport(safe_tmp_dir, db_session):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05")
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        safe_tmp_dir,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(safe_tmp_dir))
    service.import_archive(path, COLLECTED)
    service.import_archive(path, COLLECTED)
    assert db_session.query(FiiPropertyVacancyDocument).count() == 1
    assert db_session.query(FiiIssuer).count() == 1


# --- Repository: vínculo automático (create-if-absent / verify-same) -------


def test_ensure_asset_link_never_overwrites_different_issuer(db_session):
    from app.models.asset import Asset

    asset = Asset(ticker="FII1", name="Fundo Um", asset_type="FII", currency="BRL")
    db_session.add(asset)
    db_session.commit()
    repo = CvmFiiRepository(db_session)
    issuer_a = repo.upsert_issuer("11222333000181", "FUNDO A")
    issuer_b = repo.upsert_issuer("22333444000162", "FUNDO B")
    db_session.commit()

    assert repo.ensure_asset_link(asset.id, issuer_a.id) is not None
    db_session.commit()
    # Segunda tentativa para um emissor diferente -- deve recusar, nunca
    # sobrescrever.
    assert repo.ensure_asset_link(asset.id, issuer_b.id) is None

    link = (
        db_session.query(AssetFiiIssuer)
        .filter(AssetFiiIssuer.asset_id == asset.id)
        .first()
    )
    assert link.issuer_id == issuer_a.id
