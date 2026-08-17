from decimal import Decimal

from app.engines.derived_indicator_engine import DerivedIndicatorEngine


def test_roe_computes_percentage_from_net_income_and_equity():
    result = DerivedIndicatorEngine.roe(
        net_income=Decimal("1000"), equity=Decimal("10000")
    )
    assert result.value == Decimal("10.00")
    assert result.unit == "percent"
    assert result.key == "roe"
    assert result.components == {"net_income": Decimal("1000"), "equity": Decimal("10000")}


def test_roe_returns_none_when_equity_is_zero():
    assert DerivedIndicatorEngine.roe(net_income=Decimal("1000"), equity=Decimal("0")) is None


def test_roe_returns_none_when_a_component_is_missing():
    assert DerivedIndicatorEngine.roe(net_income=None, equity=Decimal("10000")) is None
    assert DerivedIndicatorEngine.roe(net_income=Decimal("1000"), equity=None) is None


def test_roa_computes_percentage_from_net_income_and_assets():
    result = DerivedIndicatorEngine.roa(
        net_income=Decimal("2000"), assets=Decimal("40000")
    )
    assert result.value == Decimal("5.00")
    assert result.unit == "percent"


def test_roa_returns_none_when_assets_is_zero():
    assert DerivedIndicatorEngine.roa(net_income=Decimal("2000"), assets=Decimal("0")) is None


def test_net_debt_subtracts_cash_from_gross_debt():
    result = DerivedIndicatorEngine.net_debt(
        gross_debt=Decimal("5000"), cash_and_equivalents=Decimal("1200")
    )
    assert result.value == Decimal("3800")
    assert result.unit == "currency"


def test_net_debt_can_be_negative_when_cash_exceeds_debt():
    result = DerivedIndicatorEngine.net_debt(
        gross_debt=Decimal("500"), cash_and_equivalents=Decimal("1200")
    )
    assert result.value == Decimal("-700")


def test_net_debt_equity_ratio():
    result = DerivedIndicatorEngine.net_debt_equity(
        net_debt=Decimal("3800"), equity=Decimal("19000")
    )
    assert result.value == Decimal("0.2000")
    assert result.unit == "ratio"


def test_net_debt_equity_returns_none_when_equity_is_zero():
    assert (
        DerivedIndicatorEngine.net_debt_equity(net_debt=Decimal("3800"), equity=Decimal("0"))
        is None
    )


def test_liabilities_assets_percentage():
    result = DerivedIndicatorEngine.liabilities_assets(
        total_liabilities=Decimal("30000"), assets=Decimal("100000")
    )
    assert result.value == Decimal("30.00")
    assert result.unit == "percent"


def test_liabilities_assets_returns_none_when_assets_is_zero():
    assert (
        DerivedIndicatorEngine.liabilities_assets(
            total_liabilities=Decimal("30000"), assets=Decimal("0")
        )
        is None
    )


def test_current_liquidity_ratio():
    result = DerivedIndicatorEngine.current_liquidity(
        current_assets=Decimal("15000"), current_liabilities=Decimal("10000")
    )
    assert result.value == Decimal("1.5000")
    assert result.unit == "ratio"


def test_current_liquidity_returns_none_when_current_liabilities_is_zero():
    assert (
        DerivedIndicatorEngine.current_liquidity(
            current_assets=Decimal("15000"), current_liabilities=Decimal("0")
        )
        is None
    )


def test_every_result_discloses_formula_and_components():
    result = DerivedIndicatorEngine.roe(net_income=Decimal("1000"), equity=Decimal("10000"))
    assert "lucro líquido" in result.formula
    assert "patrimônio líquido" in result.formula
    assert set(result.components) == {"net_income", "equity"}
