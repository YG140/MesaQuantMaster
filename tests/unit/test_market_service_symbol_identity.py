from decimal import Decimal

from app.schemas.market import MarketProfileResponse, QuoteResponse
from app.services.market_service import MarketService
from app.services.symbol_identity import B3_MARKET


class _BaseRecordingProvider:
    """Fake de provider que grava exatamente quais símbolos recebeu em
    cada método -- usado para provar, sem depender de rede, que
    MarketService roteia trading_symbol para cotação e canonical_symbol
    para perfil/fundamentos (ver Prompt 2, seção 26) SOMENTE quando o
    próprio provider comprovadamente declara mercado B3 (ver Prompt 3,
    seção 2/3/4) -- nunca porque MarketService assume B3 genericamente.

    `market` é definido pelas subclasses concretas abaixo, nunca aqui:
    esta base representa a FORMA de um provider, não sua identidade de
    mercado.
    """

    limited_mode = False

    def __init__(self):
        self.quote_calls: list[list[str]] = []
        self.profile_calls: list[str] = []
        self.stock_dataset_calls: list[tuple[str, list[str]]] = []

    def get_quotes(self, tickers: list[str]):
        self.quote_calls.append(list(tickers))
        return [
            QuoteResponse(
                ticker=ticker.upper(),
                symbol=ticker.upper(),
                requested_symbol=ticker.upper(),
                price=Decimal("10"),
                current_price=Decimal("10"),
                currency="BRL",
                source="BRAPI",
                provider="BRAPI",
            )
            for ticker in tickers
        ]

    def get_quote(self, ticker: str):
        return self.get_quotes([ticker])[0]

    def search_assets(self, query: str, limit: int = 10):
        return []

    def get_asset(self, ticker: str):
        return None

    def get_profile(self, ticker: str):
        self.profile_calls.append(ticker)
        return MarketProfileResponse(
            symbol=ticker,
            name="Petroleo Brasileiro SA Pfd",
            sector="Energia",
            cnpj="33000167000101",
            provider="BRAPI",
        )

    def get_stock_dataset(self, dataset: str, symbols: list[str], **params):
        self.stock_dataset_calls.append((dataset, list(symbols)))
        return {"results": [{"requestedSymbol": s, "symbol": s} for s in symbols]}


class RecordingProvider(_BaseRecordingProvider):
    """Provider que comprovadamente atende B3 (equivalente ao
    BrapiProvider real) -- só esta classe deve acionar a canonicalização
    do fracionário."""

    market = B3_MARKET


class NonB3RecordingProvider(_BaseRecordingProvider):
    """Provider de OUTRO mercado comprovado, explicitamente diferente de
    B3 -- prova que a regra do fracionário nunca vaza para fora do
    contexto que a declarou."""

    market = "NASDAQ"


class GenericRecordingProvider(_BaseRecordingProvider):
    """Provider sem NENHUM atributo `market` declarado -- equivalente ao
    default `market: str | None = None` de BaseMarketProvider para
    qualquer provider real que não declare o seu. `market_context_of`
    resolve isso para None do mesmo jeito (via getattr com default), e
    None nunca aciona a regra do fracionário B3: prova o fallback
    conservador, sem contexto comprovado, nenhum "F" é removido."""


def setup_function():
    MarketService.clear_caches()


# --- Cotação SEMPRE usa o trading_symbol (nunca canonicaliza) --------------


def test_fractional_quote_keeps_the_fractional_trading_symbol():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    service.get_quote("PETR4F")

    assert provider.quote_calls == [["PETR4F"]]


def test_standard_lot_quote_is_unaffected():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    service.get_quote("PETR4")

    assert provider.quote_calls == [["PETR4"]]


# --- Perfil/fundamentos SEMPRE usam o canonical_symbol ----------------------


def test_fractional_profile_is_resolved_through_the_canonical_symbol():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    profile = service.get_profile("PETR4F")

    assert provider.profile_calls == ["PETR4"]
    assert profile.cnpj == "33000167000101"
    assert profile.requested_symbol == "PETR4F"
    assert profile.symbol_changed is True


def test_standard_lot_profile_is_unaffected():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    profile = service.get_profile("PETR4")

    assert provider.profile_calls == ["PETR4"]
    assert profile.requested_symbol == "PETR4"
    assert profile.symbol_changed is False


def test_fractional_statistics_dataset_is_resolved_through_the_canonical_symbol():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    service.get_stock_dataset("statistics", ["PETR4F"], mode="current")

    assert provider.stock_dataset_calls == [("statistics", ["PETR4"])]


def test_fractional_financial_data_dataset_is_resolved_through_the_canonical_symbol():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    service.get_stock_dataset("financial_data", ["PETR4F"], mode="current")

    assert provider.stock_dataset_calls == [("financial_data", ["PETR4"])]


def test_standard_lot_stock_dataset_is_unaffected():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    service.get_stock_dataset("statistics", ["PETR4"], mode="current")

    assert provider.stock_dataset_calls == [("statistics", ["PETR4"])]


# --- Cache: cotação nunca compartilha chave; perfil compartilha por ser
#     a mesma identidade econômica -----------------------------------------


def test_quote_cache_keys_for_standard_and_fractional_symbols_are_independent():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    service.get_quote("PETR4")
    service.get_quote("PETR4F")
    # Repete ambos -- se as chaves de cache estivessem coalescidas, a
    # segunda rodada não geraria nenhuma chamada nova ao provider; como
    # são independentes, também não deveria (cada uma já está em cache
    # sob sua própria chave), mas a prova real é que o provider nunca viu
    # PETR4 quando pediram PETR4F nem vice-versa.
    service.get_quote("PETR4")
    service.get_quote("PETR4F")

    assert provider.quote_calls == [["PETR4"], ["PETR4F"]]


def test_profile_cache_is_shared_between_standard_and_fractional_symbols():
    provider = RecordingProvider()
    service = MarketService(provider=provider)

    first = service.get_profile("PETR4")
    second = service.get_profile("PETR4F")

    # Mesma identidade econômica -- uma única chamada real ao provider,
    # a segunda é atendida pelo cache (semanticamente correto: é o
    # mesmo perfil de empresa).
    assert provider.profile_calls == ["PETR4"]
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.cnpj == first.cnpj


# --- Sem contexto B3 comprovado, nenhum "F" é removido (Prompt 3, seção
#     10, casos A e B) -------------------------------------------------------


def test_non_b3_provider_never_has_its_fractional_looking_symbol_stripped():
    """Provider de outro mercado comprovado (NASDAQ): mesmo que o símbolo
    tenha exatamente o formato estrutural de um fracionário B3 válido
    (4 letras + 1-2 dígitos + "F"), o provider deve receber o símbolo
    original intacto -- a regra do fracionário nunca vaza para fora do
    contexto que a declarou."""
    provider = NonB3RecordingProvider()
    service = MarketService(provider=provider)

    profile = service.get_profile("ABCD4F")

    assert provider.profile_calls == ["ABCD4F"]
    assert profile.symbol_changed is False


def test_non_b3_provider_stock_dataset_never_canonicalizes():
    provider = NonB3RecordingProvider()
    service = MarketService(provider=provider)

    service.get_stock_dataset("statistics", ["ABCD4F"], mode="current")

    assert provider.stock_dataset_calls == [("statistics", ["ABCD4F"])]


def test_provider_without_any_declared_market_never_strips_f():
    """Provider genérico sem NENHUM contexto de mercado conhecido: mesmo
    resultado conservador do caso não-B3 acima -- ausência de contexto
    nunca é tratada como "provavelmente B3"."""
    provider = GenericRecordingProvider()
    service = MarketService(provider=provider)

    profile = service.get_profile("ABCD4F")

    assert provider.profile_calls == ["ABCD4F"]
    assert profile.symbol_changed is False


def test_provider_without_any_declared_market_quote_is_also_unaffected():
    provider = GenericRecordingProvider()
    service = MarketService(provider=provider)

    service.get_quote("ABCD4F")

    assert provider.quote_calls == [["ABCD4F"]]
