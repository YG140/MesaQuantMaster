from __future__ import annotations

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


def write_archive(tmp_path: Path, entries: dict[str, str | bytes]) -> Path:
    path = tmp_path / "sample.zip"
    path.write_bytes(archive_bytes(entries))
    return path


def provider(tmp_path, **kwargs):
    return CvmFiiOpenDataProvider(cache_dir=tmp_path / "cache", **kwargs)


# --- Provider: parsing, segurança, cache -----------------------------------


def test_iter_properties_parses_real_fields_and_preserves_missing_vacancy(tmp_path):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05") + imovel_row(
        name="Imovel B", vacancy=""
    )
    path = write_archive(tmp_path, {"inf_trimestral_fii_imovel_2026.csv": content})
    rows = list(provider(tmp_path).iter_properties(path, COLLECTED))
    assert len(rows) == 2
    assert rows[0].cnpj == "11222333000181"
    assert rows[0].vacancy_rate == Decimal("0.05")
    assert rows[0].area == Decimal("1000")
    # Vacância ausente na fonte oficial nunca vira 0 -- permanece None.
    assert rows[1].vacancy_rate is None


def test_iter_properties_parses_brazilian_decimal_comma(tmp_path):
    content = IMOVEL_HEADER + imovel_row(vacancy="0,0512", area="1.234,5")
    path = write_archive(tmp_path, {"inf_trimestral_fii_imovel_2026.csv": content})
    row = next(provider(tmp_path).iter_properties(path, COLLECTED))
    assert row.vacancy_rate == Decimal("0.0512")


def test_iter_fund_names_matches_real_field_and_ignores_empty_name(tmp_path):
    content = GERAL_HEADER + geral_row(name="FUNDO REAL FII") + geral_row(
        cnpj="99.888.777/0001-11", name=""
    )
    path = write_archive(tmp_path, {"inf_trimestral_fii_geral_2026.csv": content})
    names = list(provider(tmp_path).iter_fund_names(path))
    assert len(names) == 1
    assert names[0].cnpj == "11222333000181"
    assert names[0].official_name == "FUNDO REAL FII"


def test_invalid_zip_and_path_traversal_are_rejected(tmp_path):
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"not a zip")
    with pytest.raises(CvmFiiArchiveError):
        provider(tmp_path).validate_archive(invalid)
    traversal = write_archive(tmp_path, {"../escape.csv": "x"})
    with pytest.raises(CvmFiiArchiveError, match="inseguro"):
        provider(tmp_path).validate_archive(traversal)


def test_uncompressed_size_limit_is_enforced(tmp_path):
    path = write_archive(tmp_path, {"large.csv": b"x" * 100})
    with pytest.raises(CvmFiiSizeLimitError):
        provider(tmp_path, max_uncompressed_bytes=50).validate_archive(path)


def test_download_uses_fresh_cache_without_http_call(tmp_path):
    cache = tmp_path / "cache"
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


def test_stale_cache_uses_conditional_headers_and_304(tmp_path):
    cache = tmp_path / "cache"
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


# --- Service: agregação, reapresentação, idempotência -----------------------


def test_import_archive_computes_area_weighted_vacancy(tmp_path, db_session):
    content = (
        IMOVEL_HEADER
        + imovel_row(name="A", area="1000", vacancy="0.10")
        + imovel_row(name="B", area="3000", vacancy="0.02")
    )
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        tmp_path,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(tmp_path))
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
    tmp_path, db_session
):
    content = IMOVEL_HEADER + imovel_row(vacancy="") + imovel_row(name="B", vacancy="")
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        tmp_path,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(tmp_path))
    result = service.import_archive(path, COLLECTED)
    assert result["documents_imported"] == 0
    assert repo.find_issuer_by_cnpj("11222333000181") is None


def test_import_archive_skips_fund_without_confirmed_official_name(
    tmp_path, db_session
):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05")
    path = write_archive(
        tmp_path, {"inf_trimestral_fii_imovel_2026.csv": content}
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(tmp_path))
    result = service.import_archive(path, COLLECTED)
    assert result["documents_imported"] == 0


def test_import_archive_reapresentation_uses_latest_version_only(tmp_path, db_session):
    content = (
        IMOVEL_HEADER
        + imovel_row(version=1, area="1000", vacancy="0.50")
        + imovel_row(version=2, area="1000", vacancy="0.01")
    )
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        tmp_path,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(tmp_path))
    service.import_archive(path, COLLECTED)
    issuer = repo.find_issuer_by_cnpj("11222333000181")
    document = repo.latest_vacancy_document(issuer.id)
    assert document.version == 2
    assert document.area_weighted_vacancy_rate == Decimal("0.01")


def test_import_archive_is_idempotent_on_reimport(tmp_path, db_session):
    content = IMOVEL_HEADER + imovel_row(vacancy="0.05")
    names = GERAL_HEADER + geral_row()
    path = write_archive(
        tmp_path,
        {
            "inf_trimestral_fii_imovel_2026.csv": content,
            "inf_trimestral_fii_geral_2026.csv": names,
        },
    )
    repo = CvmFiiRepository(db_session)
    service = CvmFiiService(repo, provider(tmp_path))
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
