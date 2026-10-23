"""Auditoria offline da estrutura COTAHIST: somente preços NÃO AJUSTADOS.

Todos os números e arquivos ZIP desta suíte são SINTÉTICOS.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from zipfile import ZipFile

import pytest

from app.engines.b3_historical_price_audit import B3HistoricalPriceAudit
from app.providers.b3.exceptions import B3ProviderError
from app.schemas.intelligence import BuildPortfolioRequest
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot, ConfidenceLevel, InvestmentClass,
    RecommendationAction, ValuationAssessment, ValuationStatus,
)
from app.schemas.portfolio_validation import (
    AdjustedReturnInterval, BenchmarkInterval, HistoricalCandidate,
    WalkForwardPeriod, WalkForwardRequest,
)

DECISION = datetime(2026, 1, 6, 20, tzinfo=timezone.utc)
QUOTE = datetime(2026, 1, 5, 20, tzinfo=timezone.utc)
END = datetime(2026, 2, 6, 20, tzinfo=timezone.utc)


def record(*, symbol="EXEM3", closing="10.00", fatcot=1, codbdi="02",
           market="010", date="20260105", currency="R$"):
    data = [" "] * 245

    def put(start, end, value):
        text = str(value)
        assert len(text) <= end - start
        data[start:end] = list(text.ljust(end-start))

    put(0, 2, "01")
    put(2, 10, date)
    put(10, 12, codbdi)
    put(12, 24, symbol)
    put(24, 27, market)
    put(27, 39, "COMPANHIA")
    put(39, 49, "ON")
    put(52, 56, currency)
    put(108, 121, f"{int(Decimal(closing) * 100):013d}")
    put(202, 210, "00000000")
    put(210, 217, f"{fatcot:07d}")
    return "".join(data)


def cotahist_file(tmp_path, *, details=None, archive_name="COTAHIST_A2026.ZIP",
                  member_name="COTAHIST_A2026.TXT"):
    details = details if details is not None else [record()]
    header = "00" + " " * 243
    trailer = "99" + " " * 30 + f"{len(details):010d}" + " " * 203
    archive = tmp_path / archive_name
    with ZipFile(archive, "w") as z:
        z.writestr(member_name, "\n".join([header, *details, trailer]) + "\n")
    return archive


def request(*, close="10", quote_at=QUOTE, decision=DECISION):
    snap = AssetIntelligenceSnapshot(
        symbol="EXEM3", asset_class=InvestmentClass.STOCK, currency="BRL",
        current_price=Decimal(close), market_updated_at=quote_at,
        indicators=[], overall_score=Decimal("80"),
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.ATTRACTIVE,
        valuation=ValuationAssessment(
            status=ValuationStatus.ATTRACTIVE,
            methods=["Exemplo"], confidence=ConfidenceLevel.MEDIUM,
            estimated_range_low=Decimal("15"),
            estimated_range_high=Decimal("17"),
            data_date=decision,
        ),
        confidence=ConfidenceLevel.HIGH, coverage_percentage=Decimal("100"),
        available_indicators_count=0, missing_indicators_count=0,
        stale_indicators_count=0, calculated_at=decision,
    )
    period = WalkForwardPeriod(
        decision_at=decision, evaluation_at=END, profile_recorded_at=QUOTE,
        request=BuildPortfolioRequest(
            available_amount=Decimal("1000"),
            objective="crescimento", horizon="longo prazo", risk_profile="moderado",
        ),
        candidates=[HistoricalCandidate(snapshot=snap, sector="Energia", issuer="EXEM")],
        realized_returns=[AdjustedReturnInterval(
            symbol="EXEM3", start_index=Decimal("100"), end_index=Decimal("110"),
            start_observed_at=decision, end_observed_at=END, source="Índice ajustado sintético",
        )],
        benchmark=BenchmarkInterval(
            name="IBOV sintético", start_index=Decimal("100"),
            end_index=Decimal("101"), start_observed_at=decision,
            end_observed_at=END, source="Série sintética",
        ),
    )
    return WalkForwardRequest(initial_capital=Decimal("1000"), periods=[period])


def test_exact_prior_day_quote_from_local_valid_zip_yields_hash_audit_only(tmp_path):
    archive = cotahist_file(tmp_path)
    report = B3HistoricalPriceAudit.verify(request(), [archive])
    assert report.status == "source_price_checks_only"
    assert report.checked_quotes == report.matched_quotes == 1
    assert report.quotes[0].symbol == "EXEM3"
    assert report.quotes[0].close_price == Decimal("10.00")
    assert report.quotes[0].trading_date.isoformat() == "2026-01-05"
    assert report.quotes[0].price_adjusted_for_events is False
    assert report.quotes[0].archive_sha256 == sha256(archive.read_bytes()).hexdigest()
    assert report.archives[0].sha256 == report.quotes[0].archive_sha256
    assert any("não" in item.lower() for item in report.limitations)


def test_mismatching_price_is_refused_not_rounded_or_corrected(tmp_path):
    archive = cotahist_file(tmp_path)
    with pytest.raises(ValueError, match="difere"):
        B3HistoricalPriceAudit.verify(request(close="10.01"), [archive])


def test_missing_symbol_or_trading_day_fails_closed(tmp_path):
    archive = cotahist_file(tmp_path, details=[record(symbol="OUTR3")])
    with pytest.raises(ValueError, match="não encontradas"):
        B3HistoricalPriceAudit.verify(request(), [archive])


def test_same_day_close_is_not_assumed_published_before_decision(tmp_path):
    archive = cotahist_file(tmp_path)
    with pytest.raises(ValueError, match="pregão anterior"):
        B3HistoricalPriceAudit.verify(request(quote_at=DECISION), [archive])


def test_quote_is_rejected_if_market_or_bdi_is_not_regular_stock(tmp_path):
    archive = cotahist_file(tmp_path, details=[record(market="020")])
    with pytest.raises(ValueError, match="não encontradas"):
        B3HistoricalPriceAudit.verify(request(), [archive])
    archive = cotahist_file(tmp_path, details=[record(codbdi="96")])
    with pytest.raises(ValueError, match="não encontradas"):
        B3HistoricalPriceAudit.verify(request(), [archive])


def test_non_unit_quote_factor_is_not_silently_normalized(tmp_path):
    archive = cotahist_file(tmp_path, details=[record(fatcot=1000)])
    with pytest.raises(ValueError, match="fator de cotação"):
        B3HistoricalPriceAudit.verify(request(), [archive])


def test_wrong_currency_is_rejected(tmp_path):
    archive = cotahist_file(tmp_path, details=[record(currency="USD")])
    with pytest.raises(ValueError, match="BRL"):
        B3HistoricalPriceAudit.verify(request(), [archive])


def test_truncated_trailer_is_rejected_even_if_matching_record_was_found(tmp_path):
    archive = tmp_path / "COTAHIST_A2026.ZIP"
    with ZipFile(archive, "w") as z:
        z.writestr("COTAHIST_A2026.TXT", "00" + " " * 243 + "\n" + record() + "\n")
    with pytest.raises(B3ProviderError, match="trailer"):
        B3HistoricalPriceAudit.verify(request(), [archive])


def test_wrong_internal_member_name_and_wrong_year_are_rejected(tmp_path):
    archive = cotahist_file(tmp_path, member_name="COTAHIST_A2025.TXT")
    with pytest.raises(ValueError, match="Data incompatível"):
        B3HistoricalPriceAudit.verify(request(), [archive])
    archive = cotahist_file(tmp_path, member_name="OTHER.TXT")
    with pytest.raises(B3ProviderError):
        B3HistoricalPriceAudit.verify(request(), [archive])


def test_duplicate_archive_or_conflicting_record_is_rejected(tmp_path):
    archive = cotahist_file(tmp_path)
    with pytest.raises(ValueError, match="duplicado"):
        B3HistoricalPriceAudit.verify(request(), [archive, archive])
    archive = cotahist_file(tmp_path, details=[record(), record(closing="11")])
    with pytest.raises(ValueError, match="duplicada"):
        B3HistoricalPriceAudit.verify(request(), [archive])


def test_no_archives_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Informe de 1"):
        B3HistoricalPriceAudit.verify(request(), [])


def test_future_indicator_is_rejected_before_consulting_archive(tmp_path):
    archive = cotahist_file(tmp_path)
    req = request()
    req.periods[0].candidates[0].snapshot = req.periods[0].candidates[0].snapshot.model_copy(
        update={"calculated_at": DECISION + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="look-ahead"):
        B3HistoricalPriceAudit.verify(req, [archive])
