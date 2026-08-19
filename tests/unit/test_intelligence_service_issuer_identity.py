from types import SimpleNamespace

from app.models.asset import Asset
from app.services.intelligence_service import PortfolioIntelligenceService
from app.services.symbol_identity import B3_MARKET


def _asset(ticker: str, name: str, exchange: str | None = None) -> Asset:
    return Asset(
        ticker=ticker, name=name, asset_type="STOCK", currency="BRL", exchange=exchange
    )


def test_fractional_and_standard_lot_share_the_same_issuer_identity():
    """Achado central da auditoria (Prompt 1, seção I): antes desta
    correção, `issuer` era `asset.name` -- e o `shortName` que a BRAPI
    devolve para o mercado fracionário é literalmente o próprio ticker
    ("PETR4F"), nunca o nome da empresa. Isso fazia PETR4 e PETR4F
    contarem como dois emissores independentes para
    `maximum_weight_per_issuer`. A correção usa a identidade econômica
    (canonical_symbol) namespaced pelo mercado comprovado, que é a MESMA
    para os dois quando o contexto B3 é comprovado (aqui, via
    market_context -- o mesmo que MarketService/BrapiProvider provam em
    produção).
    """
    standard = _asset("PETR4", "PETR4")
    fractional = _asset("PETR4F", "PETR4F")

    standard_issuer = PortfolioIntelligenceService._issuer_identity(
        standard, snapshot=None, market_context=B3_MARKET
    )
    fractional_issuer = PortfolioIntelligenceService._issuer_identity(
        fractional, snapshot=None, market_context=B3_MARKET
    )

    assert standard_issuer == fractional_issuer == "B3:PETR4"


def test_issuer_identity_differs_between_unrelated_companies():
    petrobras = PortfolioIntelligenceService._issuer_identity(
        _asset("PETR4", "PETR4"), snapshot=None, market_context=B3_MARKET
    )
    vale = PortfolioIntelligenceService._issuer_identity(
        _asset("VALE3", "VALE3"), snapshot=None, market_context=B3_MARKET
    )

    assert petrobras != vale


def test_issuer_identity_falls_back_to_snapshot_symbol_when_asset_is_unknown():
    snapshot = SimpleNamespace(symbol="ITUB4F", name="ITUB4F")

    issuer = PortfolioIntelligenceService._issuer_identity(
        None, snapshot=snapshot, market_context=B3_MARKET
    )

    assert issuer == "B3:ITUB4"


def test_issuer_identity_is_none_when_neither_asset_nor_symbol_is_available():
    snapshot = SimpleNamespace(symbol="", name=None)

    issuer = PortfolioIntelligenceService._issuer_identity(
        None, snapshot=snapshot, market_context=B3_MARKET
    )

    assert issuer is None


# --- Namespace de mercado: nunca um canonical_symbol isolado global -------
# (Prompt 3, seção 6/10, casos F e G)


def test_asset_exchange_takes_priority_over_the_current_provider_market_context():
    """`asset.exchange`, quando já persistido, é mais estável do que o
    contexto do provider desta chamada específica -- prioridade 1 sobre
    prioridade 3 (ver docstring de _issuer_identity)."""
    asset = _asset("PETR4F", "PETR4F", exchange=B3_MARKET)

    # market_context=None (provider desta chamada não prova nada), mas o
    # Asset já tem exchange="B3" persistido -- deve canonicalizar mesmo
    # assim.
    issuer = PortfolioIntelligenceService._issuer_identity(
        asset, snapshot=None, market_context=None
    )

    assert issuer == "B3:PETR4"


def test_same_canonical_ticker_in_two_proven_different_markets_never_collides():
    """Ticker nunca é identidade global única (auditoria Prompt 1, seção
    4): o MESMO canonical_symbol ("PETR4") obtido em dois mercados
    DIFERENTES e comprovados nunca pode virar a mesma chave de emissor.
    """
    b3_asset = _asset("PETR4", "PETR4", exchange=B3_MARKET)
    other_market_asset = _asset("PETR4", "PETR4", exchange="NASDAQ")

    b3_issuer = PortfolioIntelligenceService._issuer_identity(
        b3_asset, snapshot=None, market_context=None
    )
    other_issuer = PortfolioIntelligenceService._issuer_identity(
        other_market_asset, snapshot=None, market_context=None
    )

    assert b3_issuer == "B3:PETR4"
    assert other_issuer == "NASDAQ:PETR4"
    assert b3_issuer != other_issuer


def test_no_market_context_at_all_falls_back_to_bare_canonical_symbol():
    """Sem exchange no Asset e sem contexto de provider -- fallback
    conservador idêntico ao comportamento anterior (sem namespace, sem
    canonicalização do fracionário, já que não há B3 comprovado)."""
    asset = _asset("PETR4F", "PETR4F")

    issuer = PortfolioIntelligenceService._issuer_identity(
        asset, snapshot=None, market_context=None
    )

    assert issuer == "PETR4F"
