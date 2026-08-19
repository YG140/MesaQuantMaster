from __future__ import annotations

import re
from dataclasses import dataclass

# Mercado que legitima a canonicalização do mercado fracionário abaixo.
# É um parâmetro explícito de `resolve_symbol_identity`, nunca um default
# silencioso: o chamador precisa declarar que está operando num fluxo
# B3 (hoje, exclusivamente o pipeline BRAPI/CVM, os únicos providers de
# ações/FIIs deste sistema) antes que qualquer sufixo seja interpretado.
# Isso é o que torna a regra "market-aware" em vez de uma normalização
# global de string — um ticker internacional legitimamente terminado em
# "F" nunca passa por aqui com market=B3_MARKET.
B3_MARKET = "B3"

# Código-base B3 válido: 4 letras (código da empresa/fundo) + 1 ou 2
# dígitos (classe/tipo — ON=3, PN=4, units/FIIs/ETFs/BDRs=11..99).
# Cobre deliberadamente ações (PETR4), FIIs/ETFs/units (MXRF11, BOVA11)
# e BDRs (AAPL34) com a MESMA regra — não é uma lista de tickers
# hardcoded, é o formato estrutural do código de negociação B3.
_B3_BASE_TICKER_PATTERN = re.compile(r"^[A-Z]{4}[0-9]{1,2}$")

B3_FRACTIONAL_RESOLUTION_REASON = "b3_fractional_canonicalization"

# Segmento de mercado fracionário B3 (distinto do lote padrão/mercado à
# vista). Usado apenas como rótulo descritivo em SymbolIdentity — nunca
# como chave de cache ou de banco.
FRACTIONAL_MARKET_SEGMENT = "fractional"


@dataclass(frozen=True)
class SymbolIdentity:
    """Identidade de um símbolo, com os papéis que a auditoria (Prompt 1)
    encontrou colapsados numa única string em todo o sistema, agora
    explicitamente separados:

    - requested_symbol: exatamente o que foi digitado/selecionado, sem
      nenhuma normalização (preservado para exibição/telemetria).
    - trading_symbol: símbolo normalizado (maiúsculas, sem espaços nas
      pontas) que deve ser usado para COTAÇÃO/negociação — nunca
      substituído por canonicalização econômica, porque o mercado
      fracionário B3 tem preço e volume próprios (ver auditoria, seção C).
    - canonical_symbol: identidade econômica compartilhada — o símbolo a
      usar para perfil da empresa, CNPJ, fundamentos, estatísticas e
      vínculo de emissor CVM. Igual a trading_symbol quando não há
      canonicalização aplicável.
    - is_fractional / market_segment / resolution_reason: descrevem SE e
      POR QUE uma transformação ocorreu, para uso em provenance — nunca
      omitidos silenciosamente quando trading_symbol != canonical_symbol.
    """

    requested_symbol: str
    trading_symbol: str
    canonical_symbol: str
    is_fractional: bool
    market_segment: str | None
    resolution_reason: str | None


def resolve_symbol_identity(symbol: str, *, market: str | None = None) -> SymbolIdentity:
    """Resolve a identidade de `symbol`, de forma pura e determinística
    (sem I/O, sem banco, sem rede).

    A canonicalização do mercado fracionário B3 (remover o sufixo `F`
    para obter a identidade econômica) só é considerada quando:

    1. `market == B3_MARKET` — o chamador afirma explicitamente que este
       fluxo já opera sobre instrumentos B3 (nunca inferido por forma de
       string sozinha; ver auditoria seção 5). Passar qualquer outro
       valor (ou None) preserva o símbolo tal como normalizado, mesmo que
       termine em "F" — protege tickers internacionais legítimos.
    2. o restante do símbolo após remover o "F" final corresponde ao
       formato estrutural de um código-base B3 (`_B3_BASE_TICKER_PATTERN`)
       — isto rejeita "F", "PETRF" e "AAAAF" (bases inválidas: sem dígito
       de classe), evitando conversões automáticas para tickers que nunca
       existiram.

    Símbolos que já são o próprio lote padrão (ex. "PETR4") nunca terminam
    processados por esta regra, pois não terminam em "F".
    """
    requested_symbol = symbol
    trading_symbol = symbol.upper().strip()

    if market == B3_MARKET and len(trading_symbol) > 1 and trading_symbol.endswith("F"):
        base = trading_symbol[:-1]
        if _B3_BASE_TICKER_PATTERN.match(base):
            return SymbolIdentity(
                requested_symbol=requested_symbol,
                trading_symbol=trading_symbol,
                canonical_symbol=base,
                is_fractional=True,
                market_segment=FRACTIONAL_MARKET_SEGMENT,
                resolution_reason=B3_FRACTIONAL_RESOLUTION_REASON,
            )

    return SymbolIdentity(
        requested_symbol=requested_symbol,
        trading_symbol=trading_symbol,
        canonical_symbol=trading_symbol,
        is_fractional=False,
        market_segment=None,
        resolution_reason=None,
    )
