import pytest

from app.services.symbol_identity import (
    B3_FRACTIONAL_RESOLUTION_REASON,
    B3_MARKET,
    FRACTIONAL_MARKET_SEGMENT,
    resolve_symbol_identity,
)


# --- Ações do lote padrão nunca são afetadas -------------------------------


def test_standard_lot_stock_stays_unchanged():
    identity = resolve_symbol_identity("PETR4", market=B3_MARKET)
    assert identity.requested_symbol == "PETR4"
    assert identity.trading_symbol == "PETR4"
    assert identity.canonical_symbol == "PETR4"
    assert identity.is_fractional is False
    assert identity.market_segment is None
    assert identity.resolution_reason is None


@pytest.mark.parametrize("symbol", ["PETR4", "VALE3", "ITUB4", "MXRF11", "BOVA11"])
def test_various_standard_symbols_are_never_touched(symbol):
    identity = resolve_symbol_identity(symbol, market=B3_MARKET)
    assert identity.canonical_symbol == symbol
    assert identity.is_fractional is False


# --- Canonicalização do mercado fracionário B3 ------------------------------


@pytest.mark.parametrize(
    "trading_symbol,expected_canonical",
    [
        ("PETR4F", "PETR4"),
        ("VALE3F", "VALE3"),
        ("ITUB4F", "ITUB4"),
    ],
)
def test_b3_fractional_ticker_resolves_canonical_economic_identity(
    trading_symbol, expected_canonical
):
    identity = resolve_symbol_identity(trading_symbol, market=B3_MARKET)
    assert identity.trading_symbol == trading_symbol
    assert identity.canonical_symbol == expected_canonical
    assert identity.is_fractional is True
    assert identity.market_segment == FRACTIONAL_MARKET_SEGMENT
    assert identity.resolution_reason == B3_FRACTIONAL_RESOLUTION_REASON


def test_lowercase_and_surrounding_whitespace_are_normalized_before_resolution():
    identity = resolve_symbol_identity("petr4f", market=B3_MARKET)
    assert identity.trading_symbol == "PETR4F"
    assert identity.canonical_symbol == "PETR4"
    assert identity.is_fractional is True


def test_surrounding_whitespace_is_trimmed():
    identity = resolve_symbol_identity(" PETR4F ", market=B3_MARKET)
    assert identity.trading_symbol == "PETR4F"
    assert identity.canonical_symbol == "PETR4"


def test_requested_symbol_preserves_original_input_exactly():
    identity = resolve_symbol_identity(" petr4f ", market=B3_MARKET)
    assert identity.requested_symbol == " petr4f "
    assert identity.trading_symbol == "PETR4F"


# --- FIIs/ETFs/BDRs fracionários usam a MESMA regra estrutural -------------


def test_hypothetical_fractional_fii_canonicalizes_without_mutilating_the_11_class_code():
    identity = resolve_symbol_identity("MXRF11F", market=B3_MARKET)
    assert identity.canonical_symbol == "MXRF11"
    assert identity.is_fractional is True


def test_hypothetical_fractional_etf_canonicalizes_correctly():
    identity = resolve_symbol_identity("BOVA11F", market=B3_MARKET)
    assert identity.canonical_symbol == "BOVA11"
    assert identity.is_fractional is True


# --- Proteção contra strip global / bases inválidas -------------------------


@pytest.mark.parametrize("invalid_symbol", ["F", "PETRF", "AAAAF"])
def test_invalid_base_never_auto_converts_to_a_fabricated_ticker(invalid_symbol):
    identity = resolve_symbol_identity(invalid_symbol, market=B3_MARKET)
    assert identity.canonical_symbol == invalid_symbol.upper()
    assert identity.is_fractional is False
    assert identity.market_segment is None
    assert identity.resolution_reason is None


def test_single_character_f_never_indexes_negative():
    identity = resolve_symbol_identity("F", market=B3_MARKET)
    assert identity.trading_symbol == "F"
    assert identity.canonical_symbol == "F"
    assert identity.is_fractional is False


# --- A regra nunca é global: exige contexto B3 explícito --------------------


def test_international_ticker_ending_in_f_is_never_touched_without_b3_context():
    identity = resolve_symbol_identity("XXXXF", market=None)
    assert identity.trading_symbol == "XXXXF"
    assert identity.canonical_symbol == "XXXXF"
    assert identity.is_fractional is False


def test_a_ticker_shaped_exactly_like_a_b3_fractional_stays_untouched_outside_b3():
    # Mesmo formato estrutural de PETR4F, mas o chamador não afirma
    # contexto B3 -- a canonicalização nunca pode ser inferida só pela
    # forma da string.
    identity = resolve_symbol_identity("PETR4F", market="NASDAQ")
    assert identity.canonical_symbol == "PETR4F"
    assert identity.is_fractional is False


def test_default_market_is_none_and_never_applies_the_b3_rule_implicitly():
    identity = resolve_symbol_identity("PETR4F")
    assert identity.canonical_symbol == "PETR4F"
    assert identity.is_fractional is False
