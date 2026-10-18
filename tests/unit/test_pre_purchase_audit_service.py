"""Validação da auditoria que não trava carteira existente nem usa rede."""
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot, NormalizedIndicator, IndicatorStatus,
    InvestmentClass, RecommendationAction, ValuationAssessment, ValuationStatus,
    ConfidenceLevel,
)
from app.services.official_source_verification_service import OfficialFact, OfficialVerification
from app.services.pre_purchase_audit_service import PrePurchaseAuditService

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def stock_asset(**updates):
    data = dict(id=uuid4(), ticker="CVMX3", asset_type="stock", currency="BRL",
                exchange="B3", is_active=True)
    data.update(updates)
    return SimpleNamespace(**data)


def stock_snapshot(*, metric="assets", value=Decimal("1000"),
                   reference_date=NOW, source_type="provider", provenance=None,
                   market_updated_at=NOW, anomaly_flags=None):
    indicator = NormalizedIndicator(
        key=metric, label=metric, value=value, unit="currency",
        source="BRAPI" if source_type == "provider" else "CVM Dados Abertos",
        source_type=source_type, status=IndicatorStatus.AVAILABLE,
        reference_date=reference_date, collected_at=NOW,
        confidence=ConfidenceLevel.MEDIUM, provenance=provenance if provenance is not None else {"scope": "consolidated"},
    )
    return AssetIntelligenceSnapshot(
        symbol="CVMX3", name="Exemplo", asset_class=InvestmentClass.STOCK,
        currency="BRL", current_price=Decimal("20"), market_updated_at=market_updated_at,
        indicators=[indicator], quality_score=Decimal("60"), valuation_score=Decimal("60"),
        overall_score=Decimal("60"),
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.NEAR_ESTIMATED_VALUE,
        valuation=ValuationAssessment(status=ValuationStatus.NEAR_ESTIMATED_VALUE,
                                      confidence=ConfidenceLevel.MEDIUM),
        confidence=ConfidenceLevel.MEDIUM, coverage_percentage=Decimal("65"),
        available_indicators_count=1, missing_indicators_count=0,
        stale_indicators_count=0, calculated_at=NOW,
        anomaly_flags=anomaly_flags or [],
    )


def filing(value=Decimal("1000"), *, metric="assets", period_end=date(2026, 10, 17),
           status="verified_filing", cnpj="11222333000144"):
    fact = OfficialFact(
        metric=metric, value=value, unit="BRL", period_end=period_end,
        document_type="ITR", source="CVM Dados Abertos",
        source_url="https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr", acquired_at=NOW
    )
    return OfficialVerification(
        symbol="CVMX3", asset_class="stock", market="B3", checked_at=NOW,
        status=status, issuer_id="CNPJ:" + cnpj, facts=[fact] if status == "verified_filing" else [],
    )


class LocalOfficial:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def verify_brazil(self, asset):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_equal_metric_and_same_period_allows_buy():
    official = LocalOfficial(filing())
    result = PrePurchaseAuditService(official).check(stock_snapshot(), stock_asset(), now=NOW)
    assert result.blocking_reasons == ()
    assert result.official_comparisons == 1
    assert official.calls == 1


def test_official_mismatch_on_exact_account_period_blocks_only_buy():
    official = LocalOfficial(filing(Decimal("700")))
    result = PrePurchaseAuditService(official).check(stock_snapshot(), stock_asset(), now=NOW)
    assert "diverge da CVM" in result.blocking_reasons[0]
    assert result.official_comparisons == 1


def test_different_periods_do_not_cause_false_conflict():
    official = LocalOfficial(filing(Decimal("50"), period_end=date(2025, 12, 31)))
    result = PrePurchaseAuditService(official).check(stock_snapshot(), stock_asset(), now=NOW)
    assert not result.blocking_reasons and result.official_comparisons == 0


def test_no_link_not_synced_or_offline_never_blocks_everything():
    for source in (filing(status="not_linked"), filing(status="no_data"), TimeoutError("CVM offline")):
        result = PrePurchaseAuditService(LocalOfficial(source)).check(
            stock_snapshot(), stock_asset(), now=NOW
        )
        assert result.blocking_reasons == ()
        assert result.official_comparisons == 0


def test_unreported_values_and_missing_dates_do_not_trigger_sql():
    official = LocalOfficial(filing(Decimal("100")))
    raw = stock_snapshot(reference_date=None)
    assert not PrePurchaseAuditService(official).check(raw, stock_asset(), now=NOW).blocking_reasons
    assert official.calls == 0
    unsupported = stock_snapshot(metric="price_earnings")
    assert not PrePurchaseAuditService(official).check(unsupported, stock_asset(), now=NOW).blocking_reasons
    assert official.calls == 0


def test_cvm_identity_mismatch_blocks_even_if_amount_matches():
    official = LocalOfficial(filing())
    snapshot = stock_snapshot(source_type="official", provenance={
        "provider": "cvm", "cnpj": "99999999000111",
    })
    result = PrePurchaseAuditService(official).check(snapshot, stock_asset(), now=NOW)
    assert any("Identidade CVM divergente" in reason for reason in result.blocking_reasons)


def test_cvm_identity_with_same_cnpj_does_not_block():
    official = LocalOfficial(filing())
    snapshot = stock_snapshot(source_type="official", provenance={
        "provider": "cvm", "cnpj": "11222333000144",
    })
    assert not PrePurchaseAuditService(official).check(snapshot, stock_asset(), now=NOW).blocking_reasons


def test_does_not_query_cvm_for_usd_international_or_unknown_exchange():
    official = LocalOfficial(filing())
    for asset in (stock_asset(currency="USD"), stock_asset(exchange="NASDAQ"),
                  stock_asset(asset_type="international"), None):
        assert not PrePurchaseAuditService(official).check(
            stock_snapshot(), asset, now=NOW
        ).blocking_reasons
    assert official.calls == 0


def test_explicit_old_quote_future_quote_and_time_missing():
    official = LocalOfficial(filing(status="not_linked"))
    audit = PrePurchaseAuditService(official)
    old = stock_snapshot(market_updated_at=NOW - timedelta(days=9))
    assert any("sete dias" in reason for reason in audit.check(old, stock_asset(), now=NOW).blocking_reasons)
    future = stock_snapshot(market_updated_at=NOW + timedelta(hours=4))
    assert any("futuro" in reason for reason in audit.check(future, stock_asset(), now=NOW).blocking_reasons)
    missing = stock_snapshot(market_updated_at=None)
    assert not audit.check(missing, stock_asset(), now=NOW).blocking_reasons
    # Feriados/fechamentos de até sete dias não bloqueiam por idade apenas.
    previous = stock_snapshot(market_updated_at=NOW - timedelta(days=6))
    assert not audit.check(previous, stock_asset(), now=NOW).blocking_reasons


def test_critical_anomalies_always_block_even_if_confidence_medium():
    audit = PrePurchaseAuditService()
    result = audit.check(stock_snapshot(anomaly_flags=["conflicting_sources"]), stock_asset(), now=NOW)
    assert any("Fontes de mercado em conflito" in reason for reason in result.blocking_reasons)
    assert not audit.check(
        stock_snapshot(anomaly_flags=["RSI extremo"]), stock_asset(), now=NOW
    ).blocking_reasons


def test_unverified_source_does_not_block_and_never_claims_comparison():
    audit = PrePurchaseAuditService()
    result = audit.check(stock_snapshot(), stock_asset(), now=NOW)
    assert result.blocking_reasons == ()
    assert result.official_comparisons == 0


def test_unverified_statement_scope_never_blocks_based_on_incompatible_financial_statements():
    official = LocalOfficial(filing(Decimal("300")))
    for scope in ({}, {"scope": "individual"}, {"scope": "unknown"}):
        result = PrePurchaseAuditService(official).check(
            stock_snapshot(provenance=scope), stock_asset(), now=NOW
        )
        assert not result.blocking_reasons
        assert result.official_comparisons == 0
