from app.services.market_normalizer import (
    normalize_asset_subtype,
    normalize_asset_type,
    normalize_country,
)


def test_stock_variants_become_acao():
    assert normalize_asset_type("stock") == "Ação"
    assert normalize_asset_type("STOCK") == "Ação"
    assert normalize_asset_type("Stock") == "Ação"


def test_subtype_does_not_duplicate_type():
    assert normalize_asset_subtype("STOCK", "stock") is None


def test_missing_subtype_stays_missing():
    assert normalize_asset_subtype(None, "stock") is None


def test_b3_exchange_sets_brazil_country():
    assert normalize_country(None, "B3") == "Brasil"
    assert normalize_country(None, "BVMF") == "Brasil"
    assert normalize_country(None, "SAO") == "Brasil"


def test_provider_country_is_preserved():
    assert normalize_country("Estados Unidos", "NYSE") == "Estados Unidos"
