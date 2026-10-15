"""Regressões do motor multiclasse: não transformar preço ou volume em nota."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.engines.market_intelligence_engine import ScoringEngine, RecommendationEngine
from app.engines.multimarket_scoring import score_specialized_indicator
from app.engines.smart_portfolio_engine import (
    SmartPortfolioEngine, PortfolioCandidate, PortfolioStrategy,
)
from app.engines.indicator_catalog import indicators_for_class, coverage_breakdown_for_asset
from app.schemas.intelligence import BuildPortfolioRequest
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot, ConfidenceLevel, IndicatorStatus,
    InvestmentClass, NormalizedIndicator, RecommendationAction,
    ValuationAssessment, ValuationStatus,
)

NOW = datetime.now(timezone.utc)


def item(key: str, value: str, *, unit: str = "percent", age=1,
         confidence=ConfidenceLevel.HIGH, source_type="official"):
    return NormalizedIndicator(
        key=key, label=key, value=Decimal(value), unit=unit,
        status=IndicatorStatus.AVAILABLE, confidence=confidence,
        source="Teste", source_type=source_type,
        reference_date=NOW - timedelta(days=age), collected_at=NOW,
    )


def test_crypto_quote_and_volume_are_not_scoring():
    scores = ScoringEngine.score_all(InvestmentClass.CRYPTO, [
        item("price", "120000", unit="currency"),
        item("volume", "1000000000", unit="quantity"),
    ])
    assert all(score.value is None for score in scores.values())


def test_crypto_risk_and_spread_use_real_values():
    scores = ScoringEngine.score_all(InvestmentClass.CRYPTO, [
        item("volatility", "24"), item("maximum_drawdown", "-45"),
        item("bid_ask_spread", "0.18"),
    ])
    assert scores["risk"].value is not None
    assert scores["liquidity"].value is not None
    assert scores["quality"].value is None
    assert scores["valuation"].value is None


def test_higher_crypto_volatility_and_spread_reduce_scores():
    def rates(vol, spread):
        return ScoringEngine.score_all(InvestmentClass.CRYPTO, [
            item("volatility", vol), item("bid_ask_spread", spread),
        ])
    stable, volatile = rates("28", "0.1"), rates("110", "2.5")
    assert stable["risk"].value > volatile["risk"].value
    assert stable["liquidity"].value > volatile["liquidity"].value


def test_stale_manual_or_untrusted_indicators_cannot_make_a_score():
    for bad in [
        item("volatility", "21", age=500),
        item("volatility", "21", source_type="manual"),
        item("volatility", "21", confidence=ConfidenceLevel.LOW),
    ]:
        assert score_specialized_indicator(InvestmentClass.CRYPTO, bad) is None


def test_wrong_units_or_nan_are_not_interpreted_as_percent():
    assert score_specialized_indicator(
        InvestmentClass.ETF, item("management_fee", "0.2", unit="ratio")
    ) is None
    assert score_specialized_indicator(
        InvestmentClass.ETF, item("management_fee", "NaN")
    ) is None


def test_lower_etf_fee_spread_and_tracking_error_improve_score():
    def assessment(fee, spread, tracking):
        return ScoringEngine.score_all(InvestmentClass.ETF, [
            item("management_fee", fee),
            item("bid_ask_spread", spread),
            item("tracking_error", tracking),
        ])
    lower = assessment("0.12", "0.1", "0.4")
    higher = assessment("1.95", "2.8", "7")
    for key in ("quality", "risk", "liquidity"):
        assert lower[key].value is not None
        assert lower[key].value > higher[key].value
    assert lower["valuation"].value is None


def test_etf_requires_nav_premium_as_well_as_cost_risk_spread():
    base = [
        item("management_fee", "0.15"),
        item("volatility", "12"),
        item("bid_ask_spread", "0.1"),
    ]
    no_nav = ScoringEngine.score_all(InvestmentClass.ETF, base)
    with_nav = ScoringEngine.score_all(
        InvestmentClass.ETF, [*base, item("premium_discount", "0.05")]
    )
    snap = snapshot(InvestmentClass.ETF, "BOVA11")
    assert RecommendationEngine.recommend(
        snap, no_nav, snap.valuation, ConfidenceLevel.HIGH, Decimal("80")
    ) == RecommendationAction.REVIEW_DATA
    assert RecommendationEngine.recommend(
        snap, with_nav, snap.valuation, ConfidenceLevel.HIGH, Decimal("80")
    ) == RecommendationAction.ANALYZE_TO_BUY


def test_international_stock_uses_financial_ratios_not_price_appreciation():
    good = ScoringEngine.score_all(InvestmentClass.INTERNATIONAL, [
        item("roe", "23", unit="percent"),
        item("price_earnings", "12", unit="ratio"),
        item("volume", "50000000", unit="quantity"),
    ])
    bad = ScoringEngine.score_all(InvestmentClass.INTERNATIONAL, [
        item("roe", "-3", unit="percent"),
        item("price_earnings", "35", unit="ratio"),
        item("volume", "50000000", unit="quantity"),
    ])
    assert good["quality"].value > bad["quality"].value
    assert good["valuation"].value > bad["valuation"].value
    assert good["liquidity"].value is None


def test_bdr_without_underlying_or_financial_data_has_no_score():
    result = ScoringEngine.score_all(InvestmentClass.BDR, [
        item("volume", "999999", unit="quantity"),
        item("daily_change", "45"),
    ])
    assert all(value.value is None for value in result.values())
    keys = {key.key for key in indicators_for_class(InvestmentClass.BDR)}
    assert {"roe", "price_earnings", "bid_ask_spread", "underlying_symbol"} <= keys


def test_international_catalog_has_financial_indicators_with_correct_class():
    keys = {entry.key for entry in indicators_for_class(InvestmentClass.INTERNATIONAL)}
    assert {"roe", "price_earnings", "earnings_per_share", "sector"} <= keys


def snapshot(cls=InvestmentClass.INTERNATIONAL, symbol="MSFT",
             currency="USD", price="100", overall="85"):
    return AssetIntelligenceSnapshot(
        symbol=symbol, asset_class=cls, currency=currency,
        current_price=Decimal(price),
        market_updated_at=NOW,
        indicators=[],
        quality_score=Decimal(overall),
        valuation_score=Decimal(overall),
        overall_score=Decimal(overall),
        confidence=ConfidenceLevel.HIGH,
        coverage_percentage=Decimal("100"),
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.ATTRACTIVE,
        valuation=ValuationAssessment(
            status=ValuationStatus.ATTRACTIVE, confidence=ConfidenceLevel.MEDIUM
        ),
        available_indicators_count=1, missing_indicators_count=0,
        stale_indicators_count=0, calculated_at=NOW,
    )


def _strategy():
    req = BuildPortfolioRequest(
        available_amount=Decimal("10000"), objective="crescimento patrimonial",
        horizon="longo prazo", risk_profile="moderado", needs_emergency_reserve=False,
    )
    return PortfolioStrategy.from_request(req)


def test_foreign_currency_cannot_be_allocated_as_brl():
    candidate = PortfolioCandidate(snapshot=snapshot())
    eligible, exclusions = SmartPortfolioEngine.eligibility(_strategy(), [candidate])
    assert not eligible
    assert any("conversão cambial" in reason for e in exclusions for reason in e.reasons)


def test_crypto_never_receives_auto_buy_from_risk_scores():
    candidate = PortfolioCandidate(snapshot=snapshot(
        InvestmentClass.CRYPTO, "BTC", currency="BRL",
    ))
    eligible, exclusions = SmartPortfolioEngine.eligibility(_strategy(), [candidate])
    assert not eligible
    assert any("cripto" in reason.lower() for e in exclusions for reason in e.reasons)


def test_bdr_without_validated_valuation_is_excluded():
    snap = snapshot(InvestmentClass.BDR, "AAPL34", currency="BRL")
    snap = snap.model_copy(update={
        "valuation_status": ValuationStatus.INSUFFICIENT_DATA
    })
    eligible, exclusions = SmartPortfolioEngine.eligibility(
        _strategy(), [PortfolioCandidate(snapshot=snap)]
    )
    assert not eligible
    assert any("faixa de avaliação" in r for e in exclusions for r in e.reasons)


def test_foreign_stock_and_bdr_profiles_are_separate_classes():
    keys = {entry.key for entry in indicators_for_class(InvestmentClass.INTERNATIONAL)}
    assert "country" in keys and "currency" in keys
    bdr = {entry.key for entry in indicators_for_class(InvestmentClass.BDR)}
    assert "bdr_ratio" in bdr and "underlying_symbol" in bdr
