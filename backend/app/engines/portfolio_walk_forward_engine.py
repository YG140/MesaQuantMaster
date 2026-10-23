"""Simulação walk-forward de CARTEIRA, isolada dos bancos e de ordens reais.

Por decisão: rejeita informações coletadas/publicadas no futuro, executa
SmartPortfolioEngine somente nos candidatos da época, mede retorno total
posterior e compara com benchmark na mesma janela. Status sempre SIMULAÇÃO.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.engines.smart_portfolio_engine import PortfolioCandidate, SmartPortfolioEngine
from app.schemas.market_intelligence import IndicatorStatus, InvestmentClass
from app.schemas.portfolio_validation import (
    WalkForwardPeriod, WalkForwardPeriodResult, WalkForwardRequest, WalkForwardResult,
)

HUNDRED = Decimal("100")
BPS = Decimal("10000")
CENT = Decimal("0.01")
MAX_SIGNAL_AGE = timedelta(days=7)


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label}: é obrigatório informar o fuso horário.")
    return value.astimezone(timezone.utc)


def _past(value: datetime, cutoff: datetime, label: str) -> None:
    if _utc(value, label) > cutoff:
        raise ValueError(f"{label}: informação posterior à decisão (look-ahead).")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _pct(value: Decimal) -> Decimal:
    return (value * HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)


def _validate_period(period: WalkForwardPeriod, prev: WalkForwardPeriod | None) -> None:
    decision = _utc(period.decision_at, "decision_at")
    ending = _utc(period.evaluation_at, "evaluation_at")
    if ending <= decision:
        raise ValueError("A data da avaliação deve ser posterior à decisão.")
    if ending > datetime.now(timezone.utc):
        raise ValueError("O período de avaliação deve estar integralmente no passado.")
    if prev is not None and decision != _utc(prev.evaluation_at, "evaluation_at"):
        raise ValueError("Períodos históricos devem ser contíguos, ordenados e sem sobreposição.")
    _past(period.profile_recorded_at, decision, "profile_recorded_at")
    symbols = set()
    for item in period.candidates:
        snap = item.snapshot
        symbol = snap.symbol.upper()
        if symbol in symbols:
            raise ValueError(f"Ativo duplicado no universo histórico: {symbol}.")
        symbols.add(symbol)
        if snap.asset_class != InvestmentClass.STOCK or snap.currency != "BRL":
            raise ValueError("Primeira versão walk-forward aceita apenas ações brasileiras em BRL.")
        if item.market_context != "B3":
            raise ValueError("Candidatos históricos devem pertencer ao mercado B3.")
        _past(snap.calculated_at, decision, f"{symbol}.calculated_at")
        if snap.market_updated_at is None:
            raise ValueError(f"{symbol}: cotação histórica sem data verificável.")
        quote_date = _utc(snap.market_updated_at, f"{symbol}.market_updated_at")
        if quote_date > decision or decision - quote_date > MAX_SIGNAL_AGE:
            raise ValueError(f"{symbol}: cotação posterior à decisão ou desatualizada.")
        for indicator in snap.indicators:
            label = f"{symbol}.{indicator.key}"
            _past(indicator.collected_at, decision, f"{label}.collected_at")
            if indicator.reference_date is not None:
                _past(indicator.reference_date, decision, f"{label}.reference_date")
            elif indicator.status == IndicatorStatus.AVAILABLE:
                raise ValueError(f"{label}: indicador disponível sem data de referência.")
            if indicator.valid_until is not None:
                _utc(indicator.valid_until, f"{label}.valid_until")
                if indicator.status == IndicatorStatus.AVAILABLE and _utc(indicator.valid_until, f"{label}.valid_until") < decision:
                    raise ValueError(f"{label}: indicador marcado como disponível após vencimento.")
            for attempt in indicator.resolution_attempts:
                _past(attempt.attempted_at, decision, f"{label}.attempted_at")
        if snap.valuation.data_date is not None:
            _past(snap.valuation.data_date, decision, f"{symbol}.valuation.data_date")

    returns = {}
    for observed in period.realized_returns:
        symbol = observed.symbol.upper()
        if symbol in returns:
            raise ValueError(f"Retorno duplicado para {symbol}.")
        returns[symbol] = observed
        if not observed.start_index.is_finite() or not observed.end_index.is_finite():
            raise ValueError(f"{symbol}: índices de retorno devem ser finitos.")
        if _utc(observed.start_observed_at, "return.start_observed_at") > decision:
            raise ValueError(f"{symbol}: índice inicial ainda não era conhecido na decisão.")
        if _utc(observed.end_observed_at, "return.end_observed_at") < ending:
            raise ValueError(f"{symbol}: índice final não representa a data de avaliação.")
        if _utc(observed.end_observed_at, "return.end_observed_at") > datetime.now(timezone.utc):
            raise ValueError(f"{symbol}: não aceitar divulgação futura de resultado.")

    benchmark = period.benchmark
    if not benchmark.start_index.is_finite() or not benchmark.end_index.is_finite():
        raise ValueError("Benchmark possui índice não finito.")
    if _utc(benchmark.start_observed_at, "benchmark.start_observed_at") > decision:
        raise ValueError("Índice inicial do benchmark ainda não conhecido na decisão.")
    if _utc(benchmark.end_observed_at, "benchmark.end_observed_at") < ending:
        raise ValueError("Índice final do benchmark anterior ao fim da janela.")
    if _utc(benchmark.end_observed_at, "benchmark.end_observed_at") > datetime.now(timezone.utc):
        raise ValueError("Índice final do benchmark declarado no futuro.")
    if prev is not None and (
        benchmark.name != prev.benchmark.name
        or benchmark.start_index != prev.benchmark.end_index
    ):
        raise ValueError("Benchmark deve manter nome e índice contínuos entre janelas.")


class PortfolioWalkForwardEngine:
    @classmethod
    def run(cls, data: WalkForwardRequest) -> WalkForwardResult:
        if not data.initial_capital.is_finite() or not data.fee_bps.is_finite():
            raise ValueError("Capital inicial e taxa devem ser finitos.")
        for index, period in enumerate(data.periods):
            _validate_period(period, data.periods[index - 1] if index else None)

        capital = _money(data.initial_capital)
        benchmark_capital = capital
        peak_equity = capital
        max_drawdown = Decimal("0")
        previous_drifted_weights: dict[str, Decimal] = {}
        fee_total = Decimal("0")
        turnover_total = Decimal("0")
        positive_periods = 0
        rows: list[WalkForwardPeriodResult] = []

        for period in data.periods:
            # O montador recebe somente snapshots datados da decisão,
            # nunca retornos subsequentes nem números do benchmark.
            historical_request = period.request.model_copy(
                update={"available_amount": capital}
            )
            candidates = [
                PortfolioCandidate(
                    snapshot=item.snapshot,
                    sector=item.sector,
                    issuer=item.issuer,
                    market_context=item.market_context,
                )
                for item in period.candidates
            ]
            recommendation = SmartPortfolioEngine.build(historical_request, candidates)
            weights = {
                asset.symbol.upper(): asset.executable_amount / capital
                for asset in recommendation.assets if asset.executable_amount > 0
            }
            invested = sum(weights.values(), Decimal("0"))
            if invested > 1 or invested < 0:
                raise ValueError("Alocação da carteira excede o capital histórico.")
            returns = {item.symbol.upper(): item for item in period.realized_returns}
            for symbol in weights:
                if symbol not in returns:
                    raise ValueError(
                        f"{symbol}: retorno total ajustado ausente; simulação bloqueada."
                    )
            # Diferença de pesos após valorização/depreciação anterior.
            turnover = sum(
                (
                    abs(weights.get(symbol, Decimal("0")) -
                        previous_drifted_weights.get(symbol, Decimal("0")))
                    for symbol in set(weights) | set(previous_drifted_weights)
                ),
                Decimal("0"),
            )
            fee = _money(capital * turnover * data.fee_bps / BPS)
            if fee >= capital:
                raise ValueError("Custos de transação consumiram o capital.")
            start_capital = capital
            fee_total += fee
            turnover_total += turnover
            factor = Decimal("1") - invested
            asset_factors: dict[str, Decimal] = {}
            for symbol, weight in weights.items():
                item = returns[symbol]
                asset_factor = item.end_index / item.start_index
                asset_factors[symbol] = asset_factor
                factor += weight * asset_factor
            if factor <= 0:
                raise ValueError("Fator de retorno inválido.")
            capital = _money((capital - fee) * factor)
            benchmark_factor = period.benchmark.end_index / period.benchmark.start_index
            benchmark_capital = _money(benchmark_capital * benchmark_factor)
            previous_drifted_weights = {
                symbol: weight * asset_factors[symbol] / factor
                for symbol, weight in weights.items()
            }
            peak_equity = max(peak_equity, capital)
            drawdown = (peak_equity - capital) / peak_equity
            max_drawdown = max(max_drawdown, drawdown)
            net_return = (capital / start_capital) - 1
            if net_return > 0:
                positive_periods += 1
            rows.append(WalkForwardPeriodResult(
                decision_at=period.decision_at,
                evaluation_at=period.evaluation_at,
                selected_symbols=sorted(weights),
                excluded_symbols=sorted(item.symbol for item in recommendation.exclusions),
                starting_equity=start_capital,
                ending_equity=capital,
                benchmark_ending_equity=benchmark_capital,
                net_return_percent=_pct(net_return),
                benchmark_return_percent=_pct(benchmark_factor - 1),
                invested_percentage=_pct(invested),
                cash_percentage=_pct(Decimal("1") - invested),
                turnover_percentage=_pct(turnover),
                fee_paid=fee,
                sampled_drawdown_percent=_pct(drawdown),
            ))

        base = _money(data.initial_capital)
        portfolio_return = (capital / base) - 1
        benchmark_return = (benchmark_capital / base) - 1
        return WalkForwardResult(
            initial_capital=base,
            ending_equity=capital,
            benchmark_ending_equity=benchmark_capital,
            net_return_percent=_pct(portfolio_return),
            benchmark_return_percent=_pct(benchmark_return),
            excess_return_percentage_points=_pct(portfolio_return - benchmark_return),
            maximum_sampled_drawdown_percent=_pct(max_drawdown),
            positive_periods=positive_periods,
            periods_count=len(rows),
            total_fees=fee_total,
            total_turnover_percentage=_pct(turnover_total),
            periods=rows,
        )
