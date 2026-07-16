from utils.formatters import format_decimal, format_money, format_percent


def test_format_money_uses_brazilian_display() -> None:
    assert format_money("1234.5") == "R$ 1.234,50"


def test_format_money_handles_missing_value() -> None:
    assert format_money(None) == "-"


def test_format_percent_uses_comma_decimal_separator() -> None:
    assert format_percent("12.345") == "12,34%"


def test_format_decimal_normalizes_value() -> None:
    assert format_decimal("10.500") == "10.5"
