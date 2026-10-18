"""Performance de recomendações: apenas preços comprovados (todos sintéticos aqui)."""
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.providers.b3.models import B3HistoricalRecord
from app.services.recommendation_performance_service import (
    B3Evidence, B3HistoricalDailyEvidence, RecommendationPerformanceService,
)

START = datetime(2026, 1, 2, 18, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 18, 15, tzinfo=timezone.utc)


def quote(ticker, day, price, *, isin=None, dist="001", market=None):
    return B3HistoricalRecord(
        trading_date=day, codbdi="02", trading_symbol=ticker,
        market_type=market or ("020" if ticker.endswith("F") else "010"),
        issuer_short_name=ticker, specification="ON", forward_term_days=None,
        currency="R$", open_price=Decimal(str(price)), high_price=Decimal(str(price)),
        low_price=Decimal(str(price)), average_price=Decimal(str(price)),
        close_price=Decimal(str(price)), best_bid_price=None, best_ask_price=None,
        trade_count=10, traded_quantity=100, traded_volume=Decimal("1000"),
        strike_price=None, correction_indicator=None, maturity_date=None,
        quote_factor=1, isin=isin or ("BR" + ticker[:4] + "202600"),
        distribution_number=dist,
    )


BASE_DAY = date(2025, 12, 31)
END_DAY = date(2026, 10, 16)


def record():
    return {
        "generated_at": START.isoformat(),
        "assets": [
            {
                "symbol": "PETR4", "trading_symbol": "PETR4F",
                "asset_class": "Ações", "reference_price": "20",
                "executable_quantity": "10", "executable_amount": "200",
                "quote_observed_at": (START - timedelta(days=1)).isoformat(),
                "execution_impediments": [],
            },
            {
                "symbol": "HGLG11", "trading_symbol": "HGLG11",
                "asset_class": "FIIs", "reference_price": "100",
                "executable_quantity": "5", "executable_amount": "500",
                "quote_observed_at": (START - timedelta(days=1)).isoformat(),
                "execution_impediments": [],
            },
        ],
    }


def evidence(day, prices, *, dist="001"):
    return B3Evidence(day, {
        sym: quote(sym, day, price, dist=dist)
        for sym, price in prices.items()
    })


class StaticEvidence:
    def __init__(self, initial=None, final=None):
        self.initial = initial
        self.final = final
        self.calls = []

    def closes(self, symbols, anchor):
        self.calls.append((set(symbols), anchor))
        return self.initial if len(self.calls) == 1 else self.final


def service(initial=None, final=None):
    src = StaticEvidence(
        initial or evidence(BASE_DAY, {"PETR4F": 20, "HGLG11": 100, "BOVA11": 100}),
        final or evidence(END_DAY, {"PETR4F": 25, "HGLG11": 90, "BOVA11": 110}),
    )
    return RecommendationPerformanceService(src), src


def test_price_only_is_not_realized_profit_or_total_return():
    evaluator, source = service()
    result = evaluator.calculate(uuid4(), record(), now=NOW)
    assert result.status == "price_only"
    assert result.entry_date == BASE_DAY
    assert result.observation_date == END_DAY
    assert result.analyzed_assets == 2
    assert result.observed_initial_notional == Decimal("700.00")
    assert result.portfolio_price_change_percent == Decimal("0.00")
    assert result.benchmark_price_change_percent == Decimal("10.00")
    assert result.price_difference_percentage_points == Decimal("-10.00")
    assert result.dividends_status == "not_verified"
    assert result.total_return_status == "not_calculated"
    assert result.realized_profit_status == "not_calculated"
    assert source.calls[0][1] < START.date()
    assert source.calls[1][1] < NOW.date()


def test_horizon_3_months_waits_until_it_is_over_without_fetching_evidence():
    evaluator, source = service()
    result = evaluator.calculate(uuid4(), record(), horizon_months=3,
                                 now=START + timedelta(days=50))
    assert result.status == "pending"
    assert result.portfolio_price_change_percent is None
    assert source.calls == []


def test_horizon_fixed_date_never_uses_quotes_after_target():
    evaluator, source = service(
        final=evidence(date(2026, 4, 1),
                       {"PETR4F": 20, "HGLG11": 100, "BOVA11": 100}),
    )
    result = evaluator.calculate(uuid4(), record(), horizon_months=3, now=NOW)
    assert result.status == "price_only"
    assert result.observation_date == date(2026, 4, 1)
    assert source.calls[1][1] == date(2026, 4, 2)
    assert result.portfolio_price_change_percent == Decimal("0.00")


def test_partial_or_missing_quote_never_invents_portfolio_result():
    # A reader must refuse missing official files. No fallback to live quote.
    src = StaticEvidence(initial=evidence(BASE_DAY, {"PETR4F": 20, "HGLG11": 100, "BOVA11": 100}))
    result = RecommendationPerformanceService(src).calculate(uuid4(), record(), now=NOW)
    assert result.status == "unavailable"
    assert result.portfolio_price_change_percent is None


def test_corporate_distribution_change_refuses_unadjusted_total():
    evaluator, _ = service(final=evidence(END_DAY,
        {"PETR4F": 25, "HGLG11": 90, "BOVA11": 110}, dist="002"))
    result = evaluator.calculate(uuid4(), record(), now=NOW)
    assert result.status == "unavailable"
    assert result.portfolio_price_change_percent is None
    assert "distribuição" in result.warnings[0]


def test_unverified_position_or_missing_quote_observation_rejects_all():
    for change in [
        {"trading_symbol": None},
        {"quote_observed_at": None},
        {"quote_observed_at": (START + timedelta(hours=5)).isoformat()},
        {"executable_amount": "100"},
        {"asset_class": "Criptomoedas"},
        {"execution_impediments": ["suspensa"]},
    ]:
        entry = record()
        entry["assets"][0].update(change)
        evaluator, source = service()
        result = evaluator.calculate(uuid4(), entry, now=NOW)
        assert result.status == "unavailable"
        assert source.calls == []


def test_missing_history_and_no_selection_do_not_call_provider():
    evaluator, source = service()
    empty = evaluator.calculate(uuid4(), {"generated_at": START.isoformat(), "assets": []}, now=NOW)
    assert empty.status == "unavailable" and not source.calls


def test_invalid_horizon_and_future_recommendation_are_rejected():
    evaluator, source = service()
    try:
        evaluator.calculate(uuid4(), record(), horizon_months=5, now=NOW)
        raise AssertionError("invalid horizon allowed")
    except ValueError:
        pass
    try:
        evaluator.calculate(uuid4(), record(), now=START - timedelta(days=1))
        raise AssertionError("future recommendation allowed")
    except ValueError:
        pass
    assert not source.calls


def test_daily_source_loads_once_per_day_for_all_tickers_and_refuses_partial_days():
    class FakeCotahist:
        daily_max_uncompressed_bytes = 20971520

        def __init__(self):
            self.days = []
            self.files = {}

        def download_daily(self, day):
            self.days.append(day)
            if day not in self.files:
                raise OSError("sem arquivo")
            return SimpleNamespace(path=day)

        def iter_records(self, day, unused_limit):
            for row in self.files[day]:
                yield row

    fake = FakeCotahist()
    # Em um dia faltou o ETF; usa pregão anterior sem misturar datas.
    fake.files[date(2026, 10, 16)] = [quote("PETR4", date(2026, 10, 16), 20)]
    fake.files[date(2026, 10, 15)] = [
        quote("PETR4", date(2026, 10, 15), 20),
        quote("BOVA11", date(2026, 10, 15), 100),
    ]
    result = B3HistoricalDailyEvidence(fake).closes(
        {"PETR4", "BOVA11"}, date(2026, 10, 16),
    )
    assert result.date == date(2026, 10, 15)
    assert len(fake.days) == 2
    assert result.prices["PETR4"].close_price == Decimal("20")


def test_missing_corporate_action_identity_never_yields_price_return():
    initial = evidence(BASE_DAY, {"PETR4F": 20, "HGLG11": 100, "BOVA11": 100})
    final = evidence(END_DAY, {"PETR4F": 25, "HGLG11": 90, "BOVA11": 110})
    original = final.prices["PETR4F"]
    from dataclasses import replace
    final.prices["PETR4F"] = replace(original, isin="BRDIFFERENT")
    evaluator, _ = service(initial, final)
    result = evaluator.calculate(uuid4(), record(), now=NOW)
    assert result.status == "unavailable"
    assert result.total_return_status == "not_calculated"
