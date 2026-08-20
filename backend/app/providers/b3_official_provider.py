from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.providers.b3.cotahist import CotahistProvider
from app.providers.b3.daily_price import B3DailyPriceSource
from app.providers.b3.exceptions import B3ProviderError
from app.providers.b3.instruments import B3InstrumentRegistrySource
from app.providers.b3.models import B3DailyPrice, B3HistoricalRecord, B3Instrument

_MAX_RECENT_EOD_LOOKBACK_DAYS = 10


@dataclass(frozen=True)
class B3EodResult:
    """Fechamento oficial B3 de um instrumento para um pregão específico,
    com a competência econômica real (`reference_date`) separada do
    momento em que o dado foi obtido (`collected_at`) -- nunca o inverso.
    `dataset` identifica de qual arquivo oficial o valor veio, para
    provenance honesta (nunca aparentar que um dado veio de outra fonte).
    """

    record: B3HistoricalRecord
    dataset: str  # "cotahist_daily" ou "cotahist_annual"
    collected_at: datetime
    cache_hit: bool


class B3OfficialDataProvider:
    """Orquestra as fontes oficiais B3 distintas (COTAHIST histórico/EOD,
    BVBG.186 EOD simplificado, BVBG.028 cadastro de instrumentos) atrás de
    uma interface única -- NUNCA substitui `ProviderFactory.get_provider()`
    (BRAPI continua o provider principal para quote live/pesquisa/
    fundamentos). Este provider é especializado, consumido pontualmente
    pelo resolver como fonte oficial complementar/fallback.

    Não implementa BaseMarketProvider: a semântica (fechamento EOD,
    histórico não ajustado, cadastro de instrumento) não corresponde a
    "quote atual" -- forçar essa interface aqui misturaria live com EOD,
    exatamente o que esta tarefa proíbe.
    """

    provider_name = "B3"
    # Mesma metadata de mercado que BrapiProvider.market declara -- ver
    # app.services.symbol_identity.market_context_of(). Todo dado deste
    # provider é comprovadamente B3 (fonte primária da própria bolsa).
    market = "B3"

    def __init__(
        self,
        cotahist: CotahistProvider | None = None,
        daily_price_source: B3DailyPriceSource | None = None,
        instrument_registry_source: B3InstrumentRegistrySource | None = None,
    ):
        self.cotahist = cotahist or CotahistProvider()
        self.daily_price_source = daily_price_source or B3DailyPriceSource()
        self.instrument_registry_source = (
            instrument_registry_source or B3InstrumentRegistrySource()
        )

    # --- EOD / histórico via COTAHIST (fonte pública confirmada) ---------

    def get_recent_eod(
        self,
        trading_symbol: str,
        *,
        anchor_date: date | None = None,
        max_lookback_days: int = _MAX_RECENT_EOD_LOOKBACK_DAYS,
    ) -> B3EodResult | None:
        """Busca o fechamento oficial mais recente para `trading_symbol`
        (símbolo de negociação EXATO -- ex. "PETR4F" continua "PETR4F",
        nunca canonicalizado aqui) andando para trás a partir de
        `anchor_date` (default: hoje), pulando fins de semana, até
        `max_lookback_days`. Um dia sem arquivo publicado (feriado, fim de
        semana, falha transitória) nunca aborta a busca inteira -- só
        aquele dia é pulado. Retorna None (nunca um valor fabricado) se
        nenhum pregão do intervalo tiver o instrumento."""
        cursor = anchor_date or datetime.now(timezone.utc).date()
        attempts = 0
        while attempts < max_lookback_days:
            if cursor.weekday() < 5:  # segunda(0)..sexta(4); fim de semana pulado sem contar tentativa
                attempts += 1
                try:
                    download = self.cotahist.download_daily(cursor)
                    # list() força a iteração COMPLETA do generator antes
                    # de procurarmos o ticker -- iter_records só valida
                    # header/trailer/contagem de registros DEPOIS do laço
                    # de leitura (ver cotahist.py), então um next() com
                    # short-circuit encerraria a leitura assim que o ticker
                    # aparecesse, sem nunca confirmar a integridade do
                    # resto do arquivo. Um pregão diário é pequeno o
                    # bastante para isso ser seguro (ver get_historical,
                    # que já faz o mesmo para o arquivo anual, bem maior).
                    records = list(
                        self.cotahist.iter_records(
                            download.path, self.cotahist.daily_max_uncompressed_bytes
                        )
                    )
                    record = next(
                        (r for r in records if r.trading_symbol == trading_symbol),
                        None,
                    )
                except B3ProviderError:
                    record = None
                if record is not None:
                    return B3EodResult(
                        record=record,
                        dataset="cotahist_daily",
                        collected_at=download.collected_at,
                        cache_hit=download.cache_hit,
                    )
            cursor -= timedelta(days=1)
        return None

    def get_historical(self, trading_symbol: str, year: int) -> list[B3HistoricalRecord]:
        """Histórico diário NÃO AJUSTADO (ver B3HistoricalRecord.adjusted)
        para `trading_symbol` no ano informado, a partir do arquivo anual
        COTAHIST_A<AAAA>.ZIP. Nunca ajustado por proventos/desdobramentos
        -- callers que esperam série ajustada (ex. backtesting existente,
        se algum dia consumir isto) precisam saber disso explicitamente."""
        download = self.cotahist.download_annual(year)
        records = [
            record
            for record in self.cotahist.iter_records(
                download.path, self.cotahist.annual_max_uncompressed_bytes
            )
            if record.trading_symbol == trading_symbol
        ]
        return sorted(records, key=lambda r: r.trading_date)

    # --- BVBG.186 (EOD simplificado) --------------------------------------

    def get_daily_price_report(self, trading_symbol: str) -> B3DailyPrice:
        """Levanta B3NotConfiguredError quando BVBG.186 não tem URL
        pública confirmada (ver B3DailyPriceSource) -- nunca retorna dado
        fabricado nem finge indisponibilidade transitória quando o
        problema real é ausência de configuração."""
        xml_bytes = self.daily_price_source.fetch()
        for record in self.daily_price_source.parse(xml_bytes):
            if record.trading_symbol == trading_symbol:
                return record
        raise B3ProviderError(
            f"Instrumento {trading_symbol!r} não encontrado no BVBG.186 do dia."
        )

    # --- BVBG.028 (cadastro de instrumentos) ------------------------------

    def get_instrument(self, trading_symbol: str) -> B3Instrument:
        """Levanta B3NotConfiguredError quando BVBG.028 não tem URL
        pública confirmada configurada (ver B3InstrumentRegistrySource)."""
        xml_bytes = self.instrument_registry_source.fetch()
        for instrument in self.instrument_registry_source.parse(xml_bytes):
            if instrument.trading_symbol == trading_symbol:
                return instrument
        raise B3ProviderError(
            f"Instrumento {trading_symbol!r} não encontrado no cadastro BVBG.028."
        )
