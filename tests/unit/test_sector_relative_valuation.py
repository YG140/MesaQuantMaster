"""Regressões do preço indicativo setorial: não inventar preço intrínseco."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.engines.sector_relative_valuation import PeerAsset, enrich_sector_valuations
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot, ConfidenceLevel, IndicatorStatus, InvestmentClass,
    NormalizedIndicator, RecommendationAction, ValuationAssessment, ValuationStatus,
)

NOW = datetime(2026, 10, 14, 19, 0, tzinfo=timezone.utc)
REF = NOW - timedelta(days=35)


def ind(key, value, *, expired=False, status=IndicatorStatus.AVAILABLE):
    return NormalizedIndicator(
        key=key, label=key, value=Decimal(str(value)), unit="ratio",
        status=status, source="CVM", source_type="official",
        reference_date=REF,
        valid_until=NOW - timedelta(days=1) if expired else NOW + timedelta(days=80),
        collected_at=NOW, confidence=ConfidenceLevel.HIGH,
    )


def stock(symbol, *, price="60", sector="Energia", eps="5", bvps="50",
          pe="12", pb="1.2", roe="14", currency="BRL",
          issuer=None, observed=NOW, score="80", segment=None):
    indicators = [
        ind("price_earnings", pe), ind("price_book", pb),
        ind("roe", roe), ind("earnings_per_share", eps),
        ind("book_value_per_share", bvps),
    ]
    if segment:
        indicators.append(NormalizedIndicator(
            key="segment", label="Segmento", value=segment, unit="text",
            status=IndicatorStatus.AVAILABLE, source="official",
            reference_date=REF, collected_at=NOW, confidence=ConfidenceLevel.HIGH,
        ))
    snap = AssetIntelligenceSnapshot(
        symbol=symbol, asset_class=InvestmentClass.STOCK,
        currency=currency, current_price=Decimal(price), market_updated_at=observed,
        indicators=indicators,
        quality_score=Decimal(score), valuation_score=Decimal(score),
        growth_score=Decimal("70"), overall_score=Decimal("76.67"),
        recommendation=RecommendationAction.REVIEW_DATA,
        valuation_status=ValuationStatus.INSUFFICIENT_DATA,
        valuation=ValuationAssessment(
            status=ValuationStatus.INSUFFICIENT_DATA,
            confidence=ConfidenceLevel.INSUFFICIENT,
        ),
        confidence=ConfidenceLevel.HIGH, coverage_percentage=Decimal("100"),
        available_indicators_count=len(indicators), missing_indicators_count=0,
        stale_indicators_count=0, calculated_at=NOW,
    )
    return PeerAsset(snapshot=snap, sector=sector, issuer=issuer or symbol)


def universe(*, price="60", sector="Energia"):
    target = stock("ALVO3", price=price, sector=sector)
    peers = [
        stock("PARA3", price="60", pe="10", pb="1", roe="12", sector=sector),
        stock("PARB3", price="60", pe="12", pb="1.2", roe="14", sector=sector),
        stock("PARC3", price="60", pe="14", pb="1.4", roe="16", sector=sector),
    ]
    return [target, *peers]


def test_same_sector_medians_compute_relative_price_band():
    group = universe(price="45")
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low == Decimal("60.00")
    assert result.valuation.estimated_range_high == Decimal("60.00")
    assert result.valuation.status == ValuationStatus.ATTRACTIVE
    assert result.recommendation == RecommendationAction.ANALYZE_TO_BUY
    assert "3 emissores" in result.valuation.peer_comparison
    assert "Não é preço justo intrínseco" in result.valuation.peer_comparison
    assert any(indicator.sector_comparison for indicator in result.indicators)


def test_sector_price_expensive_never_produces_buy_signal():
    result = enrich_sector_valuations(universe(price="85"))["ALVO3"]
    assert result.valuation.status == ValuationStatus.ELEVATED
    assert result.recommendation == RecommendationAction.WAIT


def test_near_sector_reference_is_not_a_buy_signal():
    result = enrich_sector_valuations(universe(price="60"))["ALVO3"]
    assert result.valuation.status == ValuationStatus.NEAR_ESTIMATED_VALUE
    assert result.recommendation != RecommendationAction.ANALYZE_TO_BUY


def test_insufficient_peers_abstains_without_inventing_values():
    group = universe()[:3]  # apenas 2 pares
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.status == ValuationStatus.INSUFFICIENT_DATA
    assert result.valuation.estimated_range_low is None
    assert result.recommendation == RecommendationAction.REVIEW_DATA


def test_financial_sector_does_not_mix_banks_with_holding_companies():
    result = enrich_sector_valuations(universe(sector="Financeiro"))["ALVO3"]
    assert result.valuation.status == ValuationStatus.INSUFFICIENT_DATA
    assert result.valuation.estimated_range_low is None


def test_nonmatching_sector_and_currency_cannot_feed_peer_median():
    group = universe()
    group[1] = stock("PARA3", sector="Consumo")
    group[2] = stock("PARB3", currency="USD")
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_stale_valuation_indicator_does_not_feed_estimate():
    group = universe()
    peer = group[1]
    old = peer.snapshot.indicators
    poisoned = [x.model_copy(update={"valid_until": NOW - timedelta(days=1)}) if x.key == "price_earnings" else x for x in old]
    group[1] = PeerAsset(peer.snapshot.model_copy(update={"indicators": poisoned}), peer.sector, peer.issuer)
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_negative_eps_or_book_value_abstains():
    group = universe()
    group[0] = stock("ALVO3", eps="-4")
    assert enrich_sector_valuations(group)["ALVO3"].valuation.estimated_range_low is None
    group[0] = stock("ALVO3", bvps="0")
    assert enrich_sector_valuations(group)["ALVO3"].valuation.estimated_range_low is None


def test_stale_quote_abstains():
    group = universe()
    group[0] = stock("ALVO3", observed=NOW - timedelta(days=15))
    assert enrich_sector_valuations(group)["ALVO3"].valuation.estimated_range_low is None


def test_incompatible_valuation_methods_abstain():
    group = universe()
    group[0] = stock("ALVO3", eps="15", bvps="10")
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None
    assert result.recommendation == RecommendationAction.REVIEW_DATA


def test_separate_equity_classes_same_issuer_are_deduplicated():
    group = universe()
    group[2] = stock("PARA4", issuer="PARA3")
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_segment_mismatch_is_not_a_peer():
    group = universe()
    group[0] = stock("ALVO3", segment="Energia solar")
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_relative_adjustment_is_idempotent_on_rerun():
    group = universe(price="45")
    first = enrich_sector_valuations(group)
    repeated = [
        PeerAsset(first[peer.snapshot.symbol], peer.sector, peer.issuer)
        for peer in group
    ]
    second = enrich_sector_valuations(repeated)
    for symbol in first:
        assert second[symbol].overall_score == first[symbol].overall_score
        assert second[symbol].valuation_score == first[symbol].valuation_score
        assert second[symbol].quality_score == first[symbol].quality_score


def test_manual_peers_are_not_an_independent_reference():
    group = universe()
    peer = group[1]
    modified = [
        x.model_copy(update={"source_type": "manual"})
        if x.key in {"price_earnings", "price_book"} else x
        for x in peer.snapshot.indicators
    ]
    group[1] = PeerAsset(
        peer.snapshot.model_copy(update={"indicators": modified}), peer.sector, peer.issuer
    )
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_holding_segment_is_not_scored_as_a_regular_operating_company():
    group = universe()
    group[0] = stock("ALVO3", segment="Holding")
    for idx in (1, 2, 3):
        group[idx] = stock(f"PAR{idx}3", segment="Holding")
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_b3_ordinary_and_preferred_shares_do_not_count_as_two_issuers():
    group = universe()
    # B3:PARA3 e B3:PARA4 parecem diferentes no cadastro, mas não
    # demonstram emissores distintos para mediana.
    group[1] = stock("PARA3", issuer="B3:PARA3")
    group[2] = stock("PARA4", issuer="B3:PARA4")
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_low_confidence_ratio_cannot_justify_reference_range():
    group = universe()
    peer = group[1]
    altered = [
        x.model_copy(update={"confidence": ConfidenceLevel.LOW})
        if x.key == "price_book" else x
        for x in peer.snapshot.indicators
    ]
    group[1] = PeerAsset(
        peer.snapshot.model_copy(update={"indicators": altered}), peer.sector, peer.issuer
    )
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None


def test_only_attractively_valued_stock_enters_new_contributions():
    """Integra a comparação setorial real com o filtro da montagem."""
    from app.engines.smart_portfolio_engine import PortfolioCandidate, SmartPortfolioEngine
    from app.schemas.intelligence import BuildPortfolioRequest

    peers = universe(price="45")
    enriched = enrich_sector_valuations(peers)
    candidates = [
        PortfolioCandidate(
            snapshot=enriched[item.snapshot.symbol],
            sector=item.sector,
            issuer=item.issuer,
            market_context="B3",
        )
        for item in peers
    ]
    req = BuildPortfolioRequest(
        available_amount=Decimal("10000"),
        objective="crescimento",
        horizon="longo prazo",
        risk_profile="moderado",
    )
    result = SmartPortfolioEngine.build(req, candidates)
    assert [asset.symbol for asset in result.assets] == ["ALVO3"]
    assert {item.symbol for item in result.exclusions} == {"PARA3", "PARB3", "PARC3"}
    assert result.total_allocated_amount + result.unallocated_amount == Decimal("10000.00")


def test_no_peer_reference_never_causes_a_stock_purchase_suggestion():
    """Sem comparação verificável, a nota alta não justifica compra."""
    from app.engines.smart_portfolio_engine import PortfolioCandidate, SmartPortfolioEngine
    from app.schemas.intelligence import BuildPortfolioRequest

    peers = universe(price="45")[:3]
    enriched = enrich_sector_valuations(peers)
    result = SmartPortfolioEngine.build(
        BuildPortfolioRequest(
            available_amount=Decimal("10000"),
            objective="crescimento",
            horizon="longo prazo",
            risk_profile="moderado",
        ),
        [
            PortfolioCandidate(
                snapshot=enriched["ALVO3"],
                sector=peers[0].sector,
                issuer=peers[0].issuer,
                market_context="B3",
            )
        ],
    )
    assert result.assets == []
    assert result.unallocated_amount == Decimal("10000.00")


def _alter_indicators(peer, *, drop=(), date_for=None):
    modified = []
    for item in peer.snapshot.indicators:
        if item.key in drop:
            continue
        if date_for and item.key in date_for:
            item = item.model_copy(update={"reference_date": date_for[item.key]})
        modified.append(item)
    return PeerAsset(
        peer.snapshot.model_copy(update={"indicators": modified}),
        peer.sector, peer.issuer,
    )


def test_separate_pe_and_pb_cohorts_do_not_create_a_false_sector_discount():
    """3 pares com apenas P/L + 3 com apenas P/VP não formam 3 comparações independentes."""
    group = [universe(price="45")[0]]
    for idx in range(3):
        group.append(_alter_indicators(
            stock(f"PEER{idx}3", price="60"), drop={"price_book"},
        ))
    for idx in range(3):
        group.append(_alter_indicators(
            stock(f"BOOK{idx}3", price="60"), drop={"price_earnings"},
        ))
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.status == ValuationStatus.INSUFFICIENT_DATA
    assert result.valuation.estimated_range_low is None
    assert result.recommendation != RecommendationAction.ANALYZE_TO_BUY
    assert "conjuntamente" in result.valuation.peer_comparison


def test_three_paired_companies_still_support_discount_even_with_incomplete_extra_peers():
    group = universe(price="45")
    group.append(_alter_indicators(
        stock("EXTRA3", price="60"), drop={"price_book"},
    ))
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.status == ValuationStatus.ATTRACTIVE
    assert result.valuation.estimated_range_low == Decimal("60.00")
    assert "3 emissores distintos com ambos os múltiplos" in result.valuation.peer_comparison


def test_peer_outdated_price_does_not_back_an_apparent_bargain():
    group = universe(price="45")
    peer = group[1]
    group[1] = PeerAsset(
        peer.snapshot.model_copy(update={"market_updated_at": NOW - timedelta(days=30)}),
        peer.sector, peer.issuer,
    )
    target = enrich_sector_valuations(group)["ALVO3"]
    assert target.valuation.status == ValuationStatus.INSUFFICIENT_DATA
    assert target.valuation.estimated_range_low is None
    assert target.recommendation != RecommendationAction.ANALYZE_TO_BUY


def test_pe_and_pb_from_far_apart_reporting_periods_are_not_combined():
    group = universe(price="45")
    peer = group[1]
    group[1] = _alter_indicators(peer, date_for={
        "price_book": REF - timedelta(days=150),
    })
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None
    assert result.valuation.status == ValuationStatus.INSUFFICIENT_DATA


def test_target_eps_and_book_per_share_require_compatible_periods():
    group = universe(price="45")
    group[0] = _alter_indicators(group[0], date_for={
        "earnings_per_share": REF - timedelta(days=150),
    })
    result = enrich_sector_valuations(group)["ALVO3"]
    assert result.valuation.estimated_range_low is None
    assert result.recommendation == RecommendationAction.REVIEW_DATA


def test_peer_loss_retracts_previously_attractive_range_without_touching_original_snapshot():
    from app.engines.smart_portfolio_engine import PortfolioCandidate, SmartPortfolioEngine
    from app.schemas.intelligence import BuildPortfolioRequest

    group = universe(price="45")
    originally = enrich_sector_valuations(group)["ALVO3"]
    assert originally.recommendation == RecommendationAction.ANALYZE_TO_BUY
    # Recalcula-se a partir do snapshot enriquecido, após o universo perder
    # pares confiáveis; jamais reaproveitar a faixa anterior.
    later = [PeerAsset(originally, group[0].sector, group[0].issuer), group[1], group[2]]
    reevaluated = enrich_sector_valuations(later)["ALVO3"]
    assert reevaluated.valuation.status == ValuationStatus.INSUFFICIENT_DATA
    assert reevaluated.valuation.estimated_range_low is None
    assert reevaluated.valuation.estimated_range_high is None
    assert reevaluated.valuation.methods == []
    assert reevaluated.recommendation == RecommendationAction.REVIEW_DATA
    assert originally.valuation.estimated_range_low == Decimal("60.00")
    portfolio = SmartPortfolioEngine.build(
        BuildPortfolioRequest(
            available_amount=Decimal("1000"), objective="crescimento",
            horizon="longo prazo", risk_profile="moderado",
        ),
        [PortfolioCandidate(
            snapshot=reevaluated, sector="Energia", issuer="ALVO3", market_context="B3",
        )],
    )
    assert not portfolio.assets
    assert portfolio.unallocated_amount == Decimal("1000.00")


def test_inconsistent_input_with_existing_manual_attractive_flag_is_not_trusted():
    group = universe(price="45")
    target = group[0]
    bogus = target.snapshot.model_copy(update={
        "valuation": ValuationAssessment(
            status=ValuationStatus.ATTRACTIVE,
            confidence=ConfidenceLevel.HIGH,
            methods=["Aparentemente barato"], estimated_range_low=Decimal("120"),
            estimated_range_high=Decimal("180"), data_date=NOW,
        ),
        "valuation_status": ValuationStatus.ATTRACTIVE,
        "recommendation": RecommendationAction.ANALYZE_TO_BUY,
    })
    insufficient = enrich_sector_valuations([
        PeerAsset(bogus, target.sector, target.issuer), group[1], group[2],
    ])["ALVO3"]
    assert insufficient.valuation.status == ValuationStatus.INSUFFICIENT_DATA
    assert insufficient.valuation.estimated_range_low is None
    assert insufficient.recommendation != RecommendationAction.ANALYZE_TO_BUY
