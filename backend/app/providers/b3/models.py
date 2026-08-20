from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Código TPMERC (COTAHIST) / Mkt (BVBG.028) para o mercado fracionário B3 --
# confirmado por dado real (amostra COTAHIST_D18082026, ver auditoria):
# PETR4F/VALE3F/ITUB4F aparecem com TPMERC="020" e CODBDI="96", e o catálogo
# oficial BVBG.028 (Cadastro de Instrumento v2.6) lista "20 - Odd Lot" /
# "20 - Fracionário" como valor do campo Mkt. Mesma convenção numérica nas
# duas fontes.
B3_FRACTIONARY_MARKET_TYPE = "020"
B3_FRACTIONARY_BDI_CODE = "96"
B3_FRACTIONARY_MARKET_CODE = "20"

# TPMERC="010" é o mercado à vista (lote padrão) -- ver layout oficial
# "FILE LAYOUT - HISTORICAL QUOTATIONS", tabela TPMERC.
B3_CASH_MARKET_TYPE = "010"


@dataclass(frozen=True)
class B3HistoricalRecord:
    """Um registro tipo 01 (cotação histórica por papel) do arquivo oficial
    COTAHIST.AAAA.TXT / COTAHIST_D<DDMMAAAA>.TXT da B3.

    Campos e escala derivados EXCLUSIVAMENTE do layout oficial "FILE LAYOUT
    - HISTORICAL QUOTATIONS" (b3.com.br, "PUBLIC INFORMATION"). Nomes dos
    atributos aqui são descritivos; os nomes oficiais do layout (CODNEG,
    TPMERC, PREULT, etc.) ficam documentados em cada campo.
    """

    trading_date: date  # DATA DO PREGÃO (competência econômica real)
    codbdi: str  # CODBDI -- código de classificação no boletim diário
    trading_symbol: str  # CODNEG -- símbolo de negociação EXATO (ex.: PETR4F)
    market_type: str  # TPMERC -- "010"=à vista, "020"=fracionário, etc.
    issuer_short_name: str  # NOMRES
    specification: str  # ESPECI -- ON/PN/UNT/CI/etc.
    forward_term_days: str | None  # PRAZOT
    currency: str  # MODREF -- moeda de referência na data do pregão
    open_price: Decimal | None  # PREABE
    high_price: Decimal | None  # PREMAX
    low_price: Decimal | None  # PREMIN
    average_price: Decimal | None  # PREMED
    close_price: Decimal | None  # PREULT -- fechamento oficial do pregão
    best_bid_price: Decimal | None  # PREOFC
    best_ask_price: Decimal | None  # PREOFV
    trade_count: int | None  # TOTNEG -- número de negócios
    traded_quantity: int | None  # QUATOT -- quantidade total negociada
    traded_volume: Decimal | None  # VOLTOT -- volume financeiro negociado
    strike_price: Decimal | None  # PREEXE
    correction_indicator: str | None  # INDOPC
    maturity_date: date | None  # DATVEN
    quote_factor: int  # FATCOT -- 1=cotação unitária, 1000=lote de 1000
    isin: str | None  # CODISI -- idêntico entre lote padrão e fracionário
    distribution_number: str | None  # DISMES

    @property
    def is_fractional_market(self) -> bool:
        return self.market_type == B3_FRACTIONARY_MARKET_TYPE

    @property
    def adjusted(self) -> bool:
        """COTAHIST é sempre não ajustado por proventos/desdobramentos --
        nunca deve ser interpretado como série ajustada (ver auditoria,
        seção 25 do Prompt 2)."""
        return False


@dataclass(frozen=True)
class B3Instrument:
    """Metadados de um instrumento conforme o catálogo oficial BVBG.028.02
    (InstrumentReport / "Cadastro de Instrumento", v2.6, b3.com.br).

    Nomes de campo do schema oficial documentados em cada atributo.
    """

    trading_symbol: str  # TckrSymb
    isin: str | None  # ISIN
    market_identifier_code: str | None  # MktIdrCd (MIC, ISO 10383; default "BVMF")
    currency: str | None  # TradgCcy
    cfi_code: str | None  # CFICd -- classifica o tipo do instrumento
    segment: str | None  # Sgmt -- primeiro nível de classificação de mercado
    market_code: str | None  # Mkt -- segundo nível; "20" = fracionário
    maturity_date: date | None  # MtrtyDt

    @property
    def is_fractional_market(self) -> bool:
        return self.market_code == B3_FRACTIONARY_MARKET_CODE


@dataclass(frozen=True)
class B3DailyPrice:
    """Um registro de preço EOD conforme o schema oficial BVBG.186.01
    (EquitiesSimplifiedPriceReport, mensagem bvmf.217.01 "PriceReport",
    v1.1, b3.com.br). Nomes das tags XML oficiais documentados em cada
    campo -- NUNCA deve ser interpretado como cotação intraday/live: é o
    fechamento oficial do pregão de `reference_date` (ver
    TradeAveragePrice/LastPrice/etc. no schema, todos EOD por definição).
    """

    trading_symbol: str  # TckrSymb
    reference_date: date  # TradDt / Dt
    open_price: Decimal | None  # FrstPric
    high_price: Decimal | None  # MaxPric
    low_price: Decimal | None  # MinPric
    average_price: Decimal | None  # TradAvrgPric
    close_price: Decimal | None  # LastPric
    trade_count: int | None  # RglrTxsQty
    traded_quantity: Decimal | None  # FinInstrmQty
    national_financial_volume: Decimal | None  # NtlFinVol

    @property
    def adjusted(self) -> bool:
        return False
