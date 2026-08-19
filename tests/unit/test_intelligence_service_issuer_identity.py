from types import SimpleNamespace

from app.models.asset import Asset
from app.services.intelligence_service import PortfolioIntelligenceService


def _asset(ticker: str, name: str) -> Asset:
    return Asset(ticker=ticker, name=name, asset_type="STOCK", currency="BRL")


def test_fractional_and_standard_lot_share_the_same_issuer_identity():
    """Achado central da auditoria (Prompt 1, seção I): antes desta
    correção, `issuer` era `asset.name` -- e o `shortName` que a BRAPI
    devolve para o mercado fracionário é literalmente o próprio ticker
    ("PETR4F"), nunca o nome da empresa. Isso fazia PETR4 e PETR4F
    contarem como dois emissores independentes para
    `maximum_weight_per_issuer`. A correção usa a identidade econômica
    (canonical_symbol), que é a MESMA para os dois.
    """
    standard = _asset("PETR4", "PETR4")
    fractional = _asset("PETR4F", "PETR4F")

    standard_issuer = PortfolioIntelligenceService._issuer_identity(
        standard, snapshot=None
    )
    fractional_issuer = PortfolioIntelligenceService._issuer_identity(
        fractional, snapshot=None
    )

    assert standard_issuer == fractional_issuer == "PETR4"


def test_issuer_identity_differs_between_unrelated_companies():
    petrobras = PortfolioIntelligenceService._issuer_identity(
        _asset("PETR4", "PETR4"), snapshot=None
    )
    vale = PortfolioIntelligenceService._issuer_identity(
        _asset("VALE3", "VALE3"), snapshot=None
    )

    assert petrobras != vale


def test_issuer_identity_falls_back_to_snapshot_symbol_when_asset_is_unknown():
    snapshot = SimpleNamespace(symbol="ITUB4F", name="ITUB4F")

    issuer = PortfolioIntelligenceService._issuer_identity(None, snapshot=snapshot)

    assert issuer == "ITUB4"


def test_issuer_identity_is_none_when_neither_asset_nor_symbol_is_available():
    snapshot = SimpleNamespace(symbol="", name=None)

    issuer = PortfolioIntelligenceService._issuer_identity(None, snapshot=snapshot)

    assert issuer is None
