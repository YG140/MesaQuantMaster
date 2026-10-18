"""Acompanhamento de recomendação: apenas preços oficiais B3, nunca lucro real.

É um monitor de decisão *hipotética* e NÃO uma leitura de ordens reais.
COTAHIST não ajusta proventos/desdobramentos; não permite anunciar
retorno total líquido. Endpoints são GET autenticados sem gravações.
"""
from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

from app.providers.b3.cotahist import CotahistProvider
from app.providers.b3.exceptions import B3ProviderError
from app.providers.b3.models import B3HistoricalRecord
from app.schemas.portfolio_recommendation_history import (
    RecommendationPriceObservation,
    RecommendationPerformanceResponse,
)

BENCHMARK = "BOVA11"
ELIGIBLE_CLASSES = frozenset({"Ações", "FIIs", "ETFs", "BDRs"})
B3_SYMBOL = re.compile(r"^[A-Z]{4}[0-9]{1,2}F?$")
MAX_QUOTE_AGE = timedelta(days=7)
MONEY = Decimal("0.01")
HORIZONS = {0, 3, 6, 12}


@dataclass(frozen=True)
class B3Evidence:
    date: date
    prices: dict[str, B3HistoricalRecord]


class B3HistoricalDailyEvidence:
    """Downloads por DIA, jamais por ticker; arquivos validados integralmente.

    Janela curta e tempo-limite pequeno para não sobrecarregar Render Free.
    Não presume que todo pregão existe ou que haverá um documento B3.
    """

    def __init__(self, source: CotahistProvider | None = None):
        self.source = source or CotahistProvider(timeout_seconds=4)

    def closes(self, symbols: set[str], on_or_before: date) -> B3Evidence | None:
        for offset in range(7):  # no máximo 5 pregões / 7 datas e 7 downloads
            day = on_or_before - timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            try:
                download = self.source.download_daily(day)
                # Consumir integralmente valida trailer/contagem/ZIP.
                all_records = list(self.source.iter_records(
                    download.path, self.source.daily_max_uncompressed_bytes
                ))
            except (B3ProviderError, OSError, ValueError):
                continue
            matches: dict[str, B3HistoricalRecord] = {}
            ambiguous: set[str] = set()
            for row in all_records:
                ticker = row.trading_symbol
                if ticker not in symbols:
                    continue
                if (row.trading_date != day or row.close_price is None
                        or not row.close_price.is_finite() or row.close_price <= 0
                        or row.quote_factor != 1 or row.currency not in {"R$", "BRL"}
                        or row.market_type != ("020" if ticker.endswith("F") else "010")):
                    continue
                if ticker in matches:
                    ambiguous.add(ticker)
                matches[ticker] = row
            if not ambiguous and symbols.issubset(matches):
                return B3Evidence(date=day, prices={name: matches[name] for name in symbols})
        return None


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _amount(value: object) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return amount if amount.is_finite() and amount > 0 else None


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator / denominator * Decimal("100")).quantize(MONEY, rounding=ROUND_HALF_UP)


def _return(run_id: UUID, date_of_run: datetime, horizon_months: int, status: str,
            *, reasons: list[str] | None = None, **kwargs) -> RecommendationPerformanceResponse:
    warnings = [*(reasons or []), *kwargs.pop("warnings", [])]
    return RecommendationPerformanceResponse(
        run_id=run_id, generated_at=date_of_run, horizon_months=horizon_months,
        status=status, warnings=warnings, **kwargs,
    )


class RecommendationPerformanceService:
    def __init__(self, source: B3HistoricalDailyEvidence | None = None):
        self.source = source or B3HistoricalDailyEvidence()

    def calculate(self, run_id: UUID, record: dict, *, horizon_months: int = 0,
                  now: datetime | None = None) -> RecommendationPerformanceResponse:
        if horizon_months not in HORIZONS:
            raise ValueError("Horizonte aceito: atual (0), 3, 6 ou 12 meses.")
        checked_at = _aware(now or datetime.now(timezone.utc))
        generated = _parse_time(record.get("generated_at"))
        if generated is None or generated > checked_at:
            raise ValueError("Data da recomendação inválida ou futura.")
        target = (
            _add_months(generated.date(), horizon_months)
            if horizon_months else (checked_at.date() - timedelta(days=1))
        )
        if target >= checked_at.date():
            return _return(run_id, generated, horizon_months, "pending", reasons=[
                "Prazo ainda não concluído; nenhuma cotação futura foi presumida."
            ])
        assets = record.get("assets")
        if not isinstance(assets, list) or not assets:
            return _return(run_id, generated, horizon_months, "unavailable", reasons=[
                "Esta recomendação não continha aportes executáveis."
            ])
        if len(assets) > 200:
            return _return(run_id, generated, horizon_months, "unavailable", reasons=[
                "Seleção excede o limite de avaliação em uma única consulta."
            ])

        positions = []
        symbols: set[str] = {BENCHMARK}
        for selected in assets:
            if not isinstance(selected, dict):
                return _return(run_id, generated, horizon_months, "unavailable",
                               reasons=["Registro histórico sem posição válida."])
            symbol = selected.get("trading_symbol")
            qty = _amount(selected.get("executable_quantity"))
            reference = _amount(selected.get("reference_price"))
            executable = _amount(selected.get("executable_amount"))
            observed = _parse_time(selected.get("quote_observed_at"))
            impediments = selected.get("execution_impediments", [])
            if (
                selected.get("asset_class") not in ELIGIBLE_CLASSES
                or not isinstance(symbol, str)
                or not B3_SYMBOL.fullmatch(symbol)
                or qty is None or reference is None or executable is None
                or observed is None or observed > generated
                or generated - observed > MAX_QUOTE_AGE
                or (isinstance(impediments, list) and bool(impediments))
                or abs(qty * reference - executable) > MONEY
            ):
                return _return(run_id, generated, horizon_months, "unavailable", reasons=[
                    "Uma ou mais posições não têm quantidade, identidade B3, preço e data "
                    "de referência verificáveis. Nada foi estimado para esses ativos."
                ])
            # Registro de recomendação é de operação SIMULADA, nunca de compra.
            positions.append((symbol, qty, reference))
            symbols.add(symbol)

        # Entrada estritamente anterior à DATA da recomendação: fechamento
        # do próprio dia só é publicado após negociação, não supor disponibilidade.
        entry = self.source.closes(symbols, generated.date() - timedelta(days=1))
        if entry is None:
            return _return(run_id, generated, horizon_months, "unavailable", reasons=[
                "Sem fechamentos oficiais B3 na mesma data para todos os ativos e BOVA11 na entrada."
            ])
        exit_date = min(target, checked_at.date() - timedelta(days=1))
        if exit_date <= entry.date:
            return _return(run_id, generated, horizon_months, "pending", reasons=[
                "Ainda não existe pregão posterior comprovado para medir a variação de preços."
            ])
        ending = self.source.closes(symbols, exit_date)
        if ending is None or ending.date <= entry.date:
            return _return(run_id, generated, horizon_months, "unavailable", reasons=[
                "Sem fechamentos oficiais B3 em data comum após a recomendação."
            ])
        start_total = Decimal("0")
        end_total = Decimal("0")
        observations = []
        for symbol, quantity, reference in positions:
            first, last = entry.prices[symbol], ending.prices[symbol]
            if (
                not first.isin or not last.isin or first.isin != last.isin
                or not first.distribution_number or not last.distribution_number
                or first.distribution_number != last.distribution_number
                or abs(first.close_price / reference - 1) > Decimal("0.10")
            ):
                return _return(run_id, generated, horizon_months, "unavailable", reasons=[
                    "Identidade, número de distribuição B3 ou preço inicial não conciliado; "
                    "pode ter ocorrido evento societário, ajuste ou divergência de cotação."
                ])
            start_total += quantity * first.close_price
            end_total += quantity * last.close_price
            observations.append(RecommendationPriceObservation(
                symbol=symbol, quantity=quantity, entry_price=first.close_price,
                exit_price=last.close_price,
                price_change_percent=_percent(last.close_price - first.close_price, first.close_price),
            ))
        b0, b1 = entry.prices[BENCHMARK], ending.prices[BENCHMARK]
        if (
            not b0.isin or not b1.isin or b0.isin != b1.isin
            or not b0.distribution_number or not b1.distribution_number
            or b0.distribution_number != b1.distribution_number
            or start_total <= 0
        ):
            return _return(run_id, generated, horizon_months, "unavailable", reasons=[
                "Referência BOVA11 com identidade ou distribuição não conciliada."
            ])
        portfolio_return = _percent(end_total - start_total, start_total)
        benchmark_return = _percent(b1.close_price - b0.close_price, b0.close_price)
        return _return(
            run_id, generated, horizon_months, "price_only",
            entry_date=entry.date, observation_date=ending.date,
            analyzed_assets=len(positions), observed_initial_notional=start_total.quantize(MONEY),
            portfolio_price_change_percent=portfolio_return,
            benchmark_price_change_percent=benchmark_return,
            price_difference_percentage_points=portfolio_return - benchmark_return,
            observations=observations,
            warnings=[
                "Variação bruta de fechamento de carteira hipotética; NÃO é lucro realizado.",
                "B3 COTAHIST não ajusta dividendos, JCP, subscrições ou desdobramentos.",
                "Proventos, impostos, taxas e custos NÃO foram verificados; retorno total e líquido indisponíveis.",
                "BOVA11 é proxy de preço de ETF; NÃO equivale ao Ibovespa de retorno total.",
                "Entrada pelo fechamento B3 ANTERIOR à recomendação; não é preço garantido de execução.",
                "Sem rebalanceamento nem novos aportes após a recomendação.",
            ],
        )
