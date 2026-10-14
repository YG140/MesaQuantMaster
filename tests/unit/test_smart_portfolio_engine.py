from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.engines.smart_portfolio_engine import (
    LEGACY_SOURCE,
    POLICY_SOURCE,
    PortfolioCandidate,
    SmartPortfolioEngine,
)
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    PortfolioPolicyAllocationRead,
    PortfolioPolicyRead,
)
from app.schemas.market_intelligence import (
    AssetAnalysisError,
    AssetIntelligenceSnapshot,
    BatchAssetAnalysisResponse,
    ConfidenceLevel,
    CoverageBreakdown,
    DataQualityReport,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
    RecommendationAction,
    ResolutionSummary,
    ValuationAssessment,
    ValuationStatus,
)
from app.services.intelligence_service import PortfolioIntelligenceService
from app.services.symbol_identity import B3_MARKET

NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def request(**updates):
    values = dict(
        available_amount=Decimal("10000"),
        objective="crescimento",
        horizon="longo prazo",
        risk_profile="moderado",
        max_percentage_per_asset=Decimal("20"),
        max_percentage_per_class=Decimal("40"),
        max_percentage_per_sector=Decimal("30"),
        max_assets=10,
    )
    values.update(updates)
    return BuildPortfolioRequest(**values)


def policy_allocation(asset_class, target, *, minimum=None, maximum=None, enabled=True):
    target = Decimal(str(target))
    return PortfolioPolicyAllocationRead(
        id=None,
        asset_class=asset_class,
        target_percentage=target,
        minimum_percentage=(
            Decimal(str(minimum)) if minimum is not None else (target * Decimal("0.7"))
        ),
        maximum_percentage=(
            Decimal(str(maximum)) if maximum is not None else (target * Decimal("1.3"))
        ),
        enabled=enabled,
    )


def policy(allocations, **updates):
    values = dict(
        id=uuid4(),
        user_id=uuid4(),
        name="Política de teste",
        objective="crescimento_patrimonial",
        risk_profile="Moderado",
        investment_horizon="mais_10_anos",
        monthly_contribution=Decimal("500"),
        liquidity_need="moderada",
        income_need=False,
        emergency_reserve_months=6,
        maximum_weight_per_asset=Decimal("20"),
        maximum_weight_per_sector=Decimal("30"),
        maximum_weight_per_issuer=Decimal("30"),
        rebalance_tolerance=Decimal("5"),
        allocations=allocations,
        created_at=NOW,
        updated_at=NOW,
    )
    values.update(updates)
    return PortfolioPolicyRead(**values)


def candidate(
    symbol,
    asset_class=InvestmentClass.STOCK,
    coverage="80",
    score="75",
    sector="Energia",
    confidence=ConfidenceLevel.MEDIUM,
    current_price=Decimal("10"),
    quality_score=None,
    valuation_score=None,
    income_score=None,
    growth_score=None,
    debt_score=None,
    risk_score=None,
    liquidity_score=None,
    strategy_fit_score=None,
    anomaly_flags=None,
    coverage_breakdown=None,
    data_quality=None,
    issuer=None,
    market_context=None,
):
    indicator = NormalizedIndicator(
        key="price_earnings",
        label="P/L",
        value=Decimal("8"),
        display_value="8",
        unit="ratio",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        source_type="snapshot",
        reference_date=NOW,
        collected_at=NOW,
        valid_until=NOW,
        confidence=ConfidenceLevel.HIGH,
    )
    snapshot = AssetIntelligenceSnapshot(
        symbol=symbol,
        name=symbol,
        asset_class=asset_class,
        current_price=current_price,
        indicators=[indicator],
        overall_score=Decimal(score) if score is not None else None,
        quality_score=quality_score,
        valuation_score=valuation_score,
        income_score=income_score,
        growth_score=growth_score,
        debt_score=debt_score,
        risk_score=risk_score,
        liquidity_score=liquidity_score,
        strategy_fit_score=strategy_fit_score,
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.NEAR_ESTIMATED_VALUE,
        valuation=ValuationAssessment(
            status=ValuationStatus.NEAR_ESTIMATED_VALUE,
            confidence=ConfidenceLevel.MEDIUM,
        ),
        confidence=confidence,
        coverage_percentage=Decimal(coverage),
        coverage_breakdown=coverage_breakdown if coverage_breakdown is not None else CoverageBreakdown(),
        anomaly_flags=anomaly_flags or [],
        data_quality=data_quality,
        available_indicators_count=1,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=NOW,
    )
    return PortfolioCandidate(
        snapshot=snapshot,
        sector=sector,
        issuer=issuer or symbol,
        market_context=market_context,
    )


class FakeAsset:
    def __init__(self, ticker, *, sector=None, is_active=True):
        self.ticker = ticker
        self.sector = sector
        self.is_active = is_active
        self.name = ticker
        self.id = None


class FakeAssetRepository:
    def __init__(self, assets):
        self._assets = assets

    def list(self):
        return list(self._assets)


def _stub_snapshot(
    symbol,
    *,
    current_price=Decimal("10"),
    confidence=ConfidenceLevel.MEDIUM,
    overall_score=Decimal("70"),
):
    indicator = NormalizedIndicator(
        key="price_earnings",
        label="P/L",
        value=Decimal("8"),
        display_value="8",
        unit="ratio",
        status=IndicatorStatus.AVAILABLE,
        source="snapshot",
        source_type="snapshot",
        reference_date=NOW,
        collected_at=NOW,
        valid_until=NOW,
        confidence=ConfidenceLevel.HIGH,
    )
    return AssetIntelligenceSnapshot(
        symbol=symbol,
        name=symbol,
        asset_class=InvestmentClass.STOCK,
        current_price=current_price,
        indicators=[indicator],
        overall_score=overall_score,
        recommendation=RecommendationAction.ANALYZE_TO_BUY,
        valuation_status=ValuationStatus.NEAR_ESTIMATED_VALUE,
        valuation=ValuationAssessment(
            status=ValuationStatus.NEAR_ESTIMATED_VALUE,
            confidence=ConfidenceLevel.MEDIUM,
        ),
        confidence=confidence,
        coverage_percentage=Decimal("30"),
        available_indicators_count=1,
        missing_indicators_count=0,
        stale_indicators_count=0,
        calculated_at=NOW,
    )


class FakeMarketIntelligenceService:
    """Fake determinístico: nunca faz chamada real de rede."""

    def __init__(self):
        self.batch_sizes: list[int] = []

    def analyze_assets(self, data, user_id):
        self.batch_sizes.append(len(data.symbols))
        snapshots = [_stub_snapshot(symbol) for symbol in data.symbols]
        return BatchAssetAnalysisResponse(
            snapshots=snapshots, errors=[], provider_calls=1, calculated_at=NOW
        )


class PartiallyFailingMarketIntelligenceService(FakeMarketIntelligenceService):
    def __init__(self, fail_batch_numbers):
        super().__init__()
        self.fail_batch_numbers = set(fail_batch_numbers)
        self.call_index = 0

    def analyze_assets(self, data, user_id):
        self.call_index += 1
        self.batch_sizes.append(len(data.symbols))
        if self.call_index in self.fail_batch_numbers:
            errors = [
                AssetAnalysisError(symbol=symbol, message="Provedor indisponível.")
                for symbol in data.symbols
            ]
            return BatchAssetAnalysisResponse(
                snapshots=[], errors=errors, provider_calls=1, calculated_at=NOW
            )
        snapshots = [_stub_snapshot(symbol) for symbol in data.symbols]
        return BatchAssetAnalysisResponse(
            snapshots=snapshots, errors=[], provider_calls=1, calculated_at=NOW
        )


def test_allocation_obeys_limits_and_preserves_provenance():
    result = SmartPortfolioEngine.build(
        request(),
        [
            candidate("AAAA3"),
            candidate("BBBB3"),
            candidate("CCCC11", InvestmentClass.FII, sector="Imobiliário"),
        ],
    )
    assert result.assets
    assert result.total_allocated_percentage <= Decimal("100")
    assert all(item.recommended_percentage <= Decimal("20") for item in result.assets)
    assert all(item.percentage <= Decimal("40") for item in result.class_allocations)
    assert result.total_allocated_amount + result.unallocated_amount == Decimal(
        "10000.00"
    )
    assert all(item.indicators_used[0].source == "snapshot" for item in result.assets)


def test_confidence_insufficient_is_excluded_and_missing_is_not_zero():
    """P2: a exclusão agora decorre de confidence == INSUFFICIENT (estrutural),
    não mais de coverage_percentage legado isoladamente — ver também o
    cenário 1 mais abaixo, que prova o oposto (coverage baixo sozinho não
    exclui)."""
    result = SmartPortfolioEngine.build(
        request(), [candidate("LOW3", confidence=ConfidenceLevel.INSUFFICIENT)]
    )
    assert result.assets == []
    assert result.unallocated_amount == Decimal("10000.00")
    assert result.exclusions[0].symbol == "LOW3"


def test_same_inputs_are_deterministic_except_timestamp():
    candidates = [candidate("BBBB3"), candidate("AAAA3")]
    first = SmartPortfolioEngine.build(request(), candidates)
    second = SmartPortfolioEngine.build(request(), list(reversed(candidates)))
    assert [(item.symbol, item.recommended_percentage) for item in first.assets] == [
        (item.symbol, item.recommended_percentage) for item in second.assets
    ]


def test_prohibited_class_and_conservative_crypto_are_excluded():
    result = SmartPortfolioEngine.build(
        request(risk_profile="conservador", prohibited_classes=["FIIs"]),
        [
            candidate("FII11", InvestmentClass.FII),
            candidate("BTC", InvestmentClass.CRYPTO),
        ],
    )
    assert not result.assets
    assert {item.symbol for item in result.exclusions} == {"FII11", "BTC"}


# =====================================================================
# P2 — elegibilidade estrutural, preflight e universo expansível.
# Cada teste está rotulado com o(s) número(s) do cenário canônico do
# prompt operacional (seção 36) que cobre.
# =====================================================================


# Cenário 1: legacy coverage <40 + confidence suficiente -> não exclui
# somente pela coverage antiga.
def test_legacy_low_coverage_alone_does_not_exclude_when_confidence_sufficient():
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("LOW3", coverage="39", confidence=ConfidenceLevel.MEDIUM)],
    )
    assert [item.symbol for item in result.assets] == ["LOW3"]
    assert result.exclusions == []


# Cenário 2: confidence LOW -> elegível se demais requisitos críticos presentes.
def test_confidence_low_is_eligible_when_critical_requirements_present():
    result = SmartPortfolioEngine.build(
        request(), [candidate("LOWC3", confidence=ConfidenceLevel.LOW)]
    )
    assert [item.symbol for item in result.assets] == ["LOWC3"]


# Cenário 3: confidence MEDIUM -> elegível.
def test_confidence_medium_is_eligible():
    result = SmartPortfolioEngine.build(
        request(), [candidate("MED3", confidence=ConfidenceLevel.MEDIUM)]
    )
    assert [item.symbol for item in result.assets] == ["MED3"]


# Cenário 4: confidence HIGH -> elegível.
def test_confidence_high_is_eligible():
    result = SmartPortfolioEngine.build(
        request(), [candidate("HIGH3", confidence=ConfidenceLevel.HIGH)]
    )
    assert [item.symbol for item in result.assets] == ["HIGH3"]


# Cenários 5 e 60: provider_coverage baixo não bloqueia sozinho e nunca é
# usado como gate de elegibilidade.
def test_low_provider_coverage_never_gates_eligibility():
    low_provider = CoverageBreakdown(
        required_coverage=Decimal("100"),
        required_satisfied=3,
        required_total=3,
        provider_coverage=Decimal("5"),
        provider_resolved=1,
        provider_requested=20,
    )
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("PROV3", confidence=ConfidenceLevel.MEDIUM, coverage_breakdown=low_provider)],
    )
    assert [item.symbol for item in result.assets] == ["PROV3"]


# Cenários 6-9: RECOMMENDED/OPTIONAL/EXPERIMENTAL ausentes e NOT_APPLICABLE
# nunca bloqueiam sozinhos (nenhum desses campos de coverage_breakdown é
# lido pela elegibilidade — o gate estrutural é sempre snapshot.confidence).
def test_recommended_optional_experimental_and_not_applicable_gaps_never_block():
    shapes = [
        CoverageBreakdown(recommended_coverage=Decimal("0"), recommended_satisfied=0, recommended_total=3),
        CoverageBreakdown(total_coverage=Decimal("10"), total_available=1, total_applicable=10),
        CoverageBreakdown(),
        CoverageBreakdown(required_total=0),
    ]
    for index, breakdown in enumerate(shapes):
        result = SmartPortfolioEngine.build(
            request(),
            [candidate(f"GAP{index}3", confidence=ConfidenceLevel.MEDIUM, coverage_breakdown=breakdown)],
        )
        assert result.exclusions == [], f"shape {index} should not exclude: {result.exclusions}"


# Cenário 10: REQUIRED ausente -> exclui, com causa específica.
def test_required_pillar_gap_excludes_with_specific_reason():
    breakdown = CoverageBreakdown(required_coverage=Decimal("66.67"), required_satisfied=2, required_total=3)
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("REQ3", confidence=ConfidenceLevel.INSUFFICIENT, coverage_breakdown=breakdown)],
    )
    assert result.assets == []
    assert result.exclusions[0].reasons == ["Pilar obrigatório aplicável não satisfeito."]


# Cenário 11: current_price ausente -> exclui.
def test_missing_current_price_excludes():
    result = SmartPortfolioEngine.build(request(), [candidate("NOPRICE3", current_price=None)])
    assert result.assets == []
    assert "Cotação atual indispensável não disponível." in result.exclusions[0].reasons


# Cenário 12: current_price zero -> exclui.
def test_zero_current_price_excludes():
    result = SmartPortfolioEngine.build(request(), [candidate("ZEROPRICE3", current_price=Decimal("0"))])
    assert result.assets == []
    assert "Cotação atual inválida (menor ou igual a zero)." in result.exclusions[0].reasons


# Cenário 13: current_price negativo -> exclui.
def test_negative_current_price_excludes():
    result = SmartPortfolioEngine.build(request(), [candidate("NEGPRICE3", current_price=Decimal("-5"))])
    assert result.assets == []
    assert "Cotação atual inválida (menor ou igual a zero)." in result.exclusions[0].reasons


# Cenário 14: confidence INSUFFICIENT -> exclui (caso geral).
def test_confidence_insufficient_excludes():
    result = SmartPortfolioEngine.build(
        request(), [candidate("INSUFF3", confidence=ConfidenceLevel.INSUFFICIENT)]
    )
    assert result.assets == []


# Cenário 15: identifier_unresolved crítico -> exclui com causa específica.
def test_identifier_unresolved_excludes_with_specific_reason():
    result = SmartPortfolioEngine.build(
        request(),
        [
            candidate(
                "ID3",
                confidence=ConfidenceLevel.INSUFFICIENT,
                anomaly_flags=["identifier_unresolved"],
            )
        ],
    )
    assert result.assets == []
    assert result.exclusions[0].reasons == ["Identidade do ativo não resolvida."]


# Cenário 16: conflicting_sources crítico -> exclui com causa específica.
def test_conflicting_sources_excludes_with_specific_reason():
    result = SmartPortfolioEngine.build(
        request(),
        [
            candidate(
                "CONF3",
                confidence=ConfidenceLevel.INSUFFICIENT,
                anomaly_flags=["conflicting_sources"],
            )
        ],
    )
    assert result.assets == []
    assert result.exclusions[0].reasons == ["Conflito crítico entre fontes de dados."]


# Cenário 17: categorias reais de scoring abaixo do mínimo -> exclui com
# causa específica (não genérica).
def test_insufficient_scoring_categories_excludes_with_generic_reason():
    result = SmartPortfolioEngine.build(
        request(), [candidate("SCORE3", confidence=ConfidenceLevel.INSUFFICIENT)]
    )
    assert result.assets == []
    assert result.exclusions[0].reasons == [
        "Categorias reais de scoring insuficientes para uma análise confiável."
    ]


# Cenário 18: recommendation_blocked legado não-crítico sozinho não exclui.
def test_legacy_recommendation_blocked_alone_does_not_exclude():
    blocked = DataQualityReport(
        data_completeness=Decimal("30"),
        data_freshness=Decimal("30"),
        recommendation_blocked=True,
        blocking_reason="Baixa completude não crítica.",
    )
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("BLOCKED3", confidence=ConfidenceLevel.MEDIUM, data_quality=blocked)],
    )
    assert [item.symbol for item in result.assets] == ["BLOCKED3"]


# Cenário 19 + TESTE DO BUG PRINCIPAL (seção 37 do prompt): required
# completo, confidence LOW/MEDIUM, scoring real suficiente, preço válido,
# coverage_percentage legado < 40 e overall_score legado None -> o ativo
# NÃO deve ser excluído apenas pelo gate legado, e deve ser rankeado com
# os scores reais disponíveis.
def test_p2_bug_scenario_asset_not_excluded_by_legacy_gate_alone():
    breakdown = CoverageBreakdown(required_coverage=Decimal("100"), required_satisfied=4, required_total=4)
    result = SmartPortfolioEngine.build(
        request(),
        [
            candidate(
                "BUG3",
                confidence=ConfidenceLevel.LOW,
                coverage="35",
                score=None,
                quality_score=Decimal("60"),
                valuation_score=Decimal("55"),
                current_price=Decimal("10"),
                coverage_breakdown=breakdown,
            )
        ],
    )
    assert [item.symbol for item in result.assets] == ["BUG3"]
    assert result.exclusions == []
    assert result.assets[0].score == Decimal("57.50")


# Cenário 20: overall_score existente -> ranking continua usando-o.
def test_ranking_uses_existing_overall_score():
    snapshot = candidate("AAAA3", score="82").snapshot
    assert SmartPortfolioEngine._effective_score(snapshot) == Decimal("82")


# Cenário 21: overall_score None não vira zero automaticamente quando há
# components reais.
def test_overall_score_none_does_not_become_zero_when_components_exist():
    snapshot = candidate("BBBB3", score=None, quality_score=Decimal("90")).snapshot
    effective = SmartPortfolioEngine._effective_score(snapshot)
    assert effective != Decimal("0")
    assert effective == Decimal("90.00")


# Cenário 22 + TESTE DE NÃO ZERO-FILL (seção 39): score component ausente
# nunca vira zero — só os components realmente calculados entram na média.
def test_missing_score_component_is_excluded_not_zero_filled():
    snapshot = candidate(
        "CCCC3", score=None, quality_score=Decimal("80"), valuation_score=Decimal("60")
    ).snapshot
    # Média real de 80 e 60 = 70. Se os 5 components ausentes virassem 0,
    # a média cairia para 20 (140/7) — bem menor e incorreta.
    assert SmartPortfolioEngine._effective_score(snapshot) == Decimal("70.00")


def test_no_zero_fill_when_overall_score_and_components_all_missing():
    """P4: overall_score=None + nenhum component real nunca mais vira score 0.

    Um candidato assim teria confidence INSUFFICIENT e seria excluído antes
    de chegar ao ranking pela eligibility() normal — se ainda assim chegar
    aqui, é tratado como violação de invariante: _effective_score retorna
    None (nunca um valor fabricado), e o candidato não recebe ranking
    numérico nenhum."""
    snapshot = candidate("ZZZZ3", score=None).snapshot
    assert SmartPortfolioEngine._effective_score(snapshot) is None
    assert SmartPortfolioEngine._effective_score(snapshot) != Decimal("0")


def test_candidate_without_any_real_score_is_excluded_from_ranking_not_scored_zero():
    """P4: score() nunca inclui no ranking um candidato sem overall_score e
    sem nenhum score component real — é excluído, não recebe score 0."""
    req = request()
    portfolio_candidate = candidate("ZZZZ3", score=None)
    ranked = SmartPortfolioEngine.score(req, [portfolio_candidate])
    assert ranked == []


# Cenário 23: ranking alternativo usa somente components reais (fim a fim).
def test_score_ranking_end_to_end_uses_only_real_components():
    result = SmartPortfolioEngine.build(
        request(),
        [
            candidate(
                "DDDD3",
                score=None,
                quality_score=Decimal("88"),
                confidence=ConfidenceLevel.MEDIUM,
            )
        ],
    )
    assert result.assets[0].score == Decimal("88.00")


# Cenário 24: ranking determinístico em empate (desempate por symbol).
def test_ranking_is_deterministic_on_score_tie():
    result = SmartPortfolioEngine.build(
        request(max_assets=1),
        [candidate("ZZZZ3", score="70"), candidate("AAAA3", score="70")],
    )
    assert result.assets[0].symbol == "AAAA3"


# Cenário 25: allowed_classes preservado.
def test_allowed_classes_preserved():
    result = SmartPortfolioEngine.build(
        request(allowed_classes=["FIIs"]),
        [candidate("STOCK3", InvestmentClass.STOCK), candidate("FII11", InvestmentClass.FII)],
    )
    assert [item.symbol for item in result.assets] == ["FII11"]
    assert {item.symbol for item in result.exclusions} == {"STOCK3"}


# Cenários 26 e 27 (prohibited_classes / conservador+cripto) já cobertos por
# test_prohibited_class_and_conservative_crypto_are_excluded acima.


# Cenário 28: max_percentage_per_asset preservado.
def test_max_percentage_per_asset_preserved():
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_asset=Decimal("5"), max_assets=1),
        [candidate("AAAA3")],
    )
    assert result.assets[0].recommended_percentage <= Decimal("5")


# Cenário 29: max_percentage_per_class preservado.
def test_max_percentage_per_class_preserved():
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_class=Decimal("10")),
        [candidate("AAAA3"), candidate("BBBB3")],
    )
    assert all(item.percentage <= Decimal("10") for item in result.class_allocations)


# Cenário 30: max_percentage_per_sector preservado.
def test_max_percentage_per_sector_preserved():
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_sector=Decimal("8"), max_percentage_per_class=Decimal("40")),
        [candidate("AAAA3", sector="Energia"), candidate("BBBB3", sector="Energia")],
    )
    total_energia = sum(
        (item.recommended_percentage for item in result.assets if item.sector == "Energia"),
        Decimal("0"),
    )
    assert total_energia <= Decimal("8")


# Cenário 31: capital impossível de alocar permanece unallocated.
def test_impossible_full_allocation_leaves_capital_unallocated():
    result = SmartPortfolioEngine.build(
        request(available_amount=Decimal("100"), max_percentage_per_asset=Decimal("5")),
        [candidate("AAAA3", current_price=Decimal("1"))],
    )
    assert result.unallocated_amount > 0


# Cenário 32: ausência de candidatos gera unavailable.
def test_no_candidates_yields_unavailable_status():
    result = SmartPortfolioEngine.build(request(), [])
    assert result.status == "unavailable"
    assert result.assets == []


# Cenário 33 + 59: candidatos parciais geram partial, e isso não vira
# unavailable só por uma restrição não crítica (aqui, limite de %/ativo).
def test_partial_candidates_yield_partial_status_not_unavailable():
    result = SmartPortfolioEngine.build(
        request(available_amount=Decimal("100"), max_percentage_per_asset=Decimal("5")),
        [candidate("AAAA3", current_price=Decimal("1"))],
    )
    assert result.status == "partial"
    assert result.status != "unavailable"


# Cenário 34: universo <= limite de batch gera um único batch.
def test_universe_within_batch_limit_uses_single_batch():
    assets = [FakeAsset(f"TCK{index:03d}3") for index in range(30)]
    market = FakeMarketIntelligenceService()
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(assets),
        market_intelligence_service=market,
    )
    result = service.build_portfolio(uuid4(), request())
    assert market.batch_sizes == [30]
    assert result.preflight.universe_total == 30
    assert result.preflight.universe_considered == 30
    assert result.preflight.batch_count == 1
    assert result.preflight.batch_size == 50
    assert result.preflight.universe_truncated is False


# Cenários 35, 36, 38 (TESTE DO UNIVERSO >50): universo > 50 gera múltiplos
# batches, nenhum excede o limite real (50), nada é truncado silenciosamente,
# snapshots são agregados, preflight é correto e a seleção final continua
# limitada por max_assets.
def test_universe_above_batch_limit_uses_multiple_batches():
    assets = [FakeAsset(f"TCK{index:03d}3") for index in range(120)]
    market = FakeMarketIntelligenceService()
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(assets),
        market_intelligence_service=market,
    )
    result = service.build_portfolio(uuid4(), request(max_assets=50))

    assert market.batch_sizes == [50, 50, 20]
    assert all(size <= 50 for size in market.batch_sizes)
    assert result.preflight.universe_total == 120
    assert result.preflight.universe_considered == 120
    assert result.preflight.universe_truncated is False
    assert result.preflight.batch_count == 3
    assert result.preflight.snapshots_received == 120
    assert len(result.assets) <= 50


# Cenário 37: universo é ordenado deterministicamente (por ticker), mesmo
# que o repositório devolva em outra ordem.
def test_universe_is_ordered_deterministically_regardless_of_repository_order():
    scrambled = [FakeAsset("CCCC3"), FakeAsset("AAAA3"), FakeAsset("BBBB3")]
    market = FakeMarketIntelligenceService()
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(scrambled),
        market_intelligence_service=market,
    )
    service.build_portfolio(uuid4(), request())

    first = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(list(reversed(scrambled))),
        market_intelligence_service=FakeMarketIntelligenceService(),
    )
    result_reversed = first.build_portfolio(uuid4(), request())
    assert [item.symbol for item in result_reversed.assets] == sorted(
        item.symbol for item in result_reversed.assets
    )


# Cenário 38: símbolos duplicados não geram análise duplicada.
def test_duplicate_symbols_do_not_get_analyzed_twice():
    assets = [FakeAsset("AAAA3"), FakeAsset("AAAA3"), FakeAsset("BBBB3")]
    market = FakeMarketIntelligenceService()
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(assets),
        market_intelligence_service=market,
    )
    result = service.build_portfolio(uuid4(), request())
    assert sum(market.batch_sizes) == 2
    assert result.preflight.universe_total == 2


# Cenário 39: ativos inativos não entram no universo.
def test_inactive_assets_are_excluded_from_universe():
    assets = [FakeAsset("AAAA3", is_active=True), FakeAsset("BBBB3", is_active=False)]
    market = FakeMarketIntelligenceService()
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(assets),
        market_intelligence_service=market,
    )
    result = service.build_portfolio(uuid4(), request())
    assert result.preflight.universe_total == 1
    assert sum(market.batch_sizes) == 1


# Cenário 40: universo maior que o limite global configurado -> truncado
# com universe_truncated=True.
def test_universe_larger_than_global_limit_is_truncated_with_flag(monkeypatch):
    from app.services import intelligence_service as intelligence_service_module

    monkeypatch.setattr(
        intelligence_service_module.settings, "PORTFOLIO_UNIVERSE_MAX_ASSETS", 10
    )
    assets = [FakeAsset(f"TCK{index:03d}3") for index in range(25)]
    market = FakeMarketIntelligenceService()
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(assets),
        market_intelligence_service=market,
    )
    result = service.build_portfolio(uuid4(), request())

    assert result.preflight.universe_total == 25
    assert result.preflight.universe_considered == 10
    assert result.preflight.universe_truncated is True
    assert sum(market.batch_sizes) == 10


# Cenários 41-43: preflight universe_total/universe_considered/batch_count
# corretos já validados nos testes de batching acima. Aqui, os contadores
# de elegibilidade/confidence/exclusão a partir de SmartPortfolioEngine.build
# diretamente (cenários 44-47).
def test_preflight_counts_reflect_candidates_and_exclusions():
    result = SmartPortfolioEngine.build(
        request(max_assets=10),
        [
            candidate("AAAA3", confidence=ConfidenceLevel.HIGH),
            candidate("BBBB3", confidence=ConfidenceLevel.MEDIUM),
            candidate("CCCC3", confidence=ConfidenceLevel.LOW),
            candidate("DDDD3", confidence=ConfidenceLevel.INSUFFICIENT),
        ],
    )
    preflight = result.preflight
    assert preflight.snapshots_received == 4
    assert preflight.confidence_high_count == 1
    assert preflight.confidence_medium_count == 1
    assert preflight.confidence_low_count == 1
    assert preflight.confidence_insufficient_count == 1
    assert preflight.eligible_count == 3
    assert preflight.excluded_count == 1
    assert preflight.universe_total == 4
    assert preflight.universe_considered == 4
    assert "DDDD3" in {item.symbol for item in result.exclusions}


# Cenário 48: falha parcial de batch não apaga snapshots válidos de outros
# batches. Cenário 49: provider_error_count correto.
def test_partial_batch_failure_preserves_valid_snapshots_and_counts_errors():
    assets = [FakeAsset(f"TCK{index:03d}3") for index in range(70)]
    market = PartiallyFailingMarketIntelligenceService(fail_batch_numbers={2})
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(assets),
        market_intelligence_service=market,
    )
    result = service.build_portfolio(uuid4(), request(max_assets=50))

    assert result.preflight.batch_count == 2
    assert result.preflight.snapshots_received == 50
    assert result.preflight.provider_error_count == 20
    assert len(result.assets) > 0
    assert any("não respondeu" in item for item in result.missing_data)


# Cenário 50: exclusion_reason_counts correto.
def test_preflight_exclusion_reason_counts():
    result = SmartPortfolioEngine.build(
        request(),
        [
            candidate("AAAA3", confidence=ConfidenceLevel.INSUFFICIENT),
            candidate("BBBB3", confidence=ConfidenceLevel.INSUFFICIENT),
            candidate("CCCC3", current_price=None),
        ],
    )
    reasons = result.preflight.exclusion_reason_counts
    assert reasons["Categorias reais de scoring insuficientes para uma análise confiável."] == 2
    assert reasons["Cotação atual indispensável não disponível."] == 1


# Cenários 51 e 52: BuildPortfolioResponse legado continua construível e os
# campos públicos existentes continuam presentes (preflight é aditivo).
def test_build_portfolio_response_legacy_fields_still_present():
    result = SmartPortfolioEngine.build(request(), [candidate("AAAA3")])
    for field in (
        "class_allocations",
        "selections",
        "assets",
        "exclusions",
        "total_allocated_percentage",
        "total_allocated_amount",
        "unallocated_amount",
        "confidence",
        "status",
        "missing_data",
        "strategy_summary",
        "diagnosis",
        "contribution_plan",
        "projections",
        "freedom_goal",
        "disclaimer",
        "generated_at",
    ):
        assert field in BuildPortfolioResponse.model_fields
    assert "preflight" in BuildPortfolioResponse.model_fields
    assert isinstance(result, BuildPortfolioResponse)


# Cenários 53 e 54: nenhum missing é convertido para zero, nenhum preço é
# fabricado.
def test_no_price_is_fabricated_for_missing_price():
    result = SmartPortfolioEngine.build(request(), [candidate("AAAA3", current_price=None)])
    assert result.assets == []
    assert result.exclusions[0].reasons == ["Cotação atual indispensável não disponível."]


# Cenário 55: mesmos inputs produzem mesma seleção/ranking, inclusive com o
# novo caminho de _effective_score.
def test_same_inputs_produce_same_ranking_with_effective_score():
    candidates = [
        candidate("BBBB3", score=None, quality_score=Decimal("70")),
        candidate("AAAA3", score=None, quality_score=Decimal("70")),
    ]
    first = SmartPortfolioEngine.build(request(), candidates)
    second = SmartPortfolioEngine.build(request(), list(reversed(candidates)))
    assert [(item.symbol, item.score) for item in first.assets] == [
        (item.symbol, item.score) for item in second.assets
    ]


# Cenário 56: assets[:50] deixa de causar truncamento silencioso — coberto
# pelos testes de batching acima (universe_considered reflete o universo
# real, sem truncar sem sinalizar).


# Cenário 57: max_assets limita a seleção FINAL, não o universo analisado.
def test_max_assets_limits_final_selection_not_universe_considered():
    assets = [FakeAsset(f"TCK{index:03d}3") for index in range(80)]
    market = FakeMarketIntelligenceService()
    service = PortfolioIntelligenceService(
        portfolio_service=None,
        policy_repository=None,
        asset_repository=FakeAssetRepository(assets),
        market_intelligence_service=market,
    )
    result = service.build_portfolio(uuid4(), request(max_assets=5))
    assert result.preflight.universe_considered == 80
    assert result.preflight.snapshots_received == 80
    assert len(result.assets) <= 5


# Cenário 58: provider errors permanecem diagnósticos (não substituem dados
# válidos nem derrubam o resultado) — já provado em
# test_partial_batch_failure_preserves_valid_snapshots_and_counts_errors.


# =====================================================================
# P4 — preflight agregado a partir de resolution_summary (P4)/
# resolution_attempts (P3). Puro diagnóstico, nunca gate de elegibilidade.
# =====================================================================


def test_preflight_aggregates_provider_failure_reasons_and_fallback_from_candidates():
    with_fallback = candidate("AAAA3", confidence=ConfidenceLevel.MEDIUM)
    with_fallback = PortfolioCandidate(
        snapshot=with_fallback.snapshot.model_copy(
            update={
                "resolution_summary": ResolutionSummary(
                    attempt_count=2,
                    success_count=1,
                    failure_count=1,
                    fallback_success_count=1,
                    unresolved_count=0,
                    stale_count=0,
                    sources_used=["CVM Dados Abertos"],
                    failure_reason_counts={"rate_limited": 1},
                )
            }
        ),
        sector=with_fallback.sector,
        issuer=with_fallback.issuer,
    )
    with_unresolved = candidate("BBBB3", confidence=ConfidenceLevel.MEDIUM)
    with_unresolved = PortfolioCandidate(
        snapshot=with_unresolved.snapshot.model_copy(
            update={
                "resolution_summary": ResolutionSummary(
                    attempt_count=1,
                    success_count=0,
                    failure_count=1,
                    fallback_success_count=0,
                    unresolved_count=1,
                    stale_count=1,
                    sources_used=[],
                    failure_reason_counts={"not_synced": 1},
                )
            }
        ),
        sector=with_unresolved.sector,
        issuer=with_unresolved.issuer,
    )
    no_summary = candidate("CCCC3", confidence=ConfidenceLevel.MEDIUM)

    response = SmartPortfolioEngine.build(
        request(), [with_fallback, with_unresolved, no_summary]
    )

    assert response.preflight.provider_failure_reason_counts == {
        "rate_limited": 1,
        "not_synced": 1,
    }
    assert response.preflight.fallback_success_count == 1
    assert response.preflight.unresolved_after_fallback_count == 1
    assert response.preflight.stale_assets_count == 1


def test_preflight_defaults_are_safe_when_no_candidate_has_resolution_summary():
    plain = candidate("AAAA3", confidence=ConfidenceLevel.MEDIUM)
    response = SmartPortfolioEngine.build(request(), [plain])

    assert response.preflight.provider_failure_reason_counts == {}
    assert response.preflight.fallback_success_count == 0
    assert response.preflight.unresolved_after_fallback_count == 0
    assert response.preflight.stale_assets_count == 0


def test_preflight_never_uses_resolution_summary_as_eligibility_gate():
    # Mesmo com falha/stale/unresolved agregados, o candidato continua
    # elegível se confidence não for INSUFFICIENT — resolution_summary é
    # só diagnóstico, nunca gate.
    stale_but_medium = candidate("AAAA3", confidence=ConfidenceLevel.MEDIUM)
    stale_but_medium = PortfolioCandidate(
        snapshot=stale_but_medium.snapshot.model_copy(
            update={
                "resolution_summary": ResolutionSummary(
                    attempt_count=1,
                    failure_count=1,
                    unresolved_count=1,
                    stale_count=1,
                    failure_reason_counts={"provider_unavailable": 1},
                )
            }
        ),
        sector=stale_but_medium.sector,
        issuer=stale_but_medium.issuer,
    )
    response = SmartPortfolioEngine.build(request(), [stale_but_medium])
    assert response.preflight.stale_assets_count == 1
    assert any(asset.symbol == "AAAA3" for asset in response.assets)


# =====================================================================
# Integração com PortfolioPolicy (Perfil do Investidor como fonte de
# verdade estratégica) -- ver SmartPortfolioEngine.build/PortfolioStrategy.
# =====================================================================


def test_no_policy_preserves_legacy_behavior():
    result = SmartPortfolioEngine.build(request(), [candidate("AAAA3")])
    assert result.policy_source == LEGACY_SOURCE
    assert result.policy_id is None
    assert result.class_allocations[0].target_percentage is None
    assert result.class_allocations[0].gap_percentage is None


def test_request_risk_profile_never_overrides_confirmed_policy():
    """Exemplo proibido da seção 4: perfil confirmado Conservador, request
    manda risk_profile="Arrojado" -- o gate de crypto deve continuar usando
    o perfil EFETIVO (Conservador), nunca o do request."""
    p = policy(
        [policy_allocation("Ações", 50), policy_allocation("Criptomoedas", 10)],
        risk_profile="Conservador",
    )
    result = SmartPortfolioEngine.build(
        request(risk_profile="Arrojado"),
        [candidate("BTC", InvestmentClass.CRYPTO, sector=None)],
        policy=p,
    )
    assert not result.assets
    assert result.exclusions[0].symbol == "BTC"
    assert "conservador" in result.exclusions[0].reasons[0].lower()


def test_policy_class_targets_replace_equal_class_target():
    """Metas desiguais por classe (Ações 60%, FIIs 10%) devem ser
    respeitadas -- nunca a meta igualitária legada (que daria 50/50)."""
    p = policy(
        [policy_allocation("Ações", 60), policy_allocation("FIIs", 10)],
        maximum_weight_per_asset=Decimal("100"),
        maximum_weight_per_sector=Decimal("100"),
        maximum_weight_per_issuer=Decimal("100"),
    )
    result = SmartPortfolioEngine.build(
        request(
            max_percentage_per_asset=Decimal("100"),
            max_percentage_per_sector=Decimal("100"),
        ),
        [
            candidate("AAAA3", InvestmentClass.STOCK, sector="Energia"),
            candidate("FII11", InvestmentClass.FII, sector="Papel"),
        ],
        policy=p,
    )
    totals = {item.asset_class: item.percentage for item in result.class_allocations}
    assert totals["Ações"] == Decimal("60.00")
    assert totals["FIIs"] == Decimal("10.00")
    assert result.policy_source == POLICY_SOURCE
    assert result.policy_id == p.id


def test_request_cannot_widen_max_percentage_per_asset_above_policy():
    """Seção 11: override operacional só pode ser MAIS restritivo, nunca
    mais permissivo -- request pedindo 50% não amplia o teto de 10% da
    política."""
    p = policy(
        [policy_allocation("Ações", 100, maximum=100)],
        maximum_weight_per_asset=Decimal("10"),
    )
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_asset=Decimal("50")),
        [candidate("AAAA3")],
        policy=p,
    )
    assert result.assets[0].recommended_percentage <= Decimal("10")


def test_request_cannot_widen_max_percentage_per_sector_above_policy():
    p = policy(
        [policy_allocation("Ações", 100, maximum=100)],
        maximum_weight_per_sector=Decimal("8"),
    )
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_sector=Decimal("90"), max_percentage_per_asset=Decimal("100")),
        [candidate("AAAA3", sector="Energia")],
        policy=p,
    )
    assert result.assets[0].recommended_percentage <= Decimal("8")


def test_maximum_weight_per_issuer_caps_combined_allocation():
    p = policy(
        [policy_allocation("Ações", 100, maximum=100)],
        maximum_weight_per_asset=Decimal("40"),
        maximum_weight_per_sector=Decimal("100"),
        maximum_weight_per_issuer=Decimal("15"),
    )
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_asset=Decimal("40"), max_percentage_per_sector=Decimal("100")),
        [
            candidate("AAAA3", sector="Energia", issuer="Emissor Único", score="90"),
            candidate("AAAA4", sector="Financeiro", issuer="Emissor Único", score="80"),
        ],
        policy=p,
    )
    total_for_issuer = sum(
        item.recommended_percentage
        for item in result.assets
        if item.issuer == "Emissor Único"
    )
    assert total_for_issuer <= Decimal("15")


def test_b3_fractional_ticker_shares_issuer_cap_with_standard_lot():
    """Prompt 2, seção 28: PETR4 (lote padrão) e PETR4F (mercado
    fracionário B3) precisam ser tratados como o MESMO emissor para
    `maximum_weight_per_issuer` -- nunca como duas empresas
    independentes (ver auditoria Prompt 1, seção I). O `issuer` de cada
    candidato aqui é calculado exatamente como
    PortfolioIntelligenceService monta em produção (ver
    intelligence_service._issuer_identity), não uma string arbitrária."""
    issuer_petr4 = PortfolioIntelligenceService._issuer_identity(
        asset=None,
        snapshot=type("S", (), {"symbol": "PETR4"})(),
        market_context=B3_MARKET,
    )
    issuer_petr4f = PortfolioIntelligenceService._issuer_identity(
        asset=None,
        snapshot=type("S", (), {"symbol": "PETR4F"})(),
        market_context=B3_MARKET,
    )
    assert issuer_petr4 == issuer_petr4f == "B3:PETR4"

    p = policy(
        [policy_allocation("Ações", 100, maximum=100)],
        maximum_weight_per_asset=Decimal("40"),
        maximum_weight_per_sector=Decimal("100"),
        maximum_weight_per_issuer=Decimal("15"),
    )
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_asset=Decimal("40"), max_percentage_per_sector=Decimal("100")),
        [
            candidate("PETR4", sector="Energia", issuer=issuer_petr4, score="90"),
            candidate("PETR4F", sector="Energia", issuer=issuer_petr4f, score="80"),
        ],
        policy=p,
    )
    total_for_petrobras = sum(
        item.recommended_percentage
        for item in result.assets
        if item.symbol in {"PETR4", "PETR4F"}
    )
    assert total_for_petrobras <= Decimal("15")


def test_issuer_absent_uses_isolated_identity_never_grouped_with_other_absent():
    """issuer=None nunca é agrupado com outro issuer=None como se fossem o
    mesmo emissor real -- cada símbolo sem emissor conhecido usa
    identidade isolada (ver _allocate_with_policy_targets)."""
    a = candidate("AAAA3", sector="Energia", score="90")
    b = candidate("AAAA4", sector="Financeiro", score="80")
    a = PortfolioCandidate(snapshot=a.snapshot, sector=a.sector, issuer=None)
    b = PortfolioCandidate(snapshot=b.snapshot, sector=b.sector, issuer=None)
    p = policy(
        [policy_allocation("Ações", 100, maximum=100)],
        maximum_weight_per_asset=Decimal("40"),
        maximum_weight_per_sector=Decimal("100"),
        maximum_weight_per_issuer=Decimal("15"),
    )
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_asset=Decimal("40"), max_percentage_per_sector=Decimal("100")),
        [a, b],
        policy=p,
    )
    # Cada um bate no próprio teto de emissor (15%) de forma INDEPENDENTE
    # -- se estivessem incorretamente agrupados como um único "emissor
    # ausente" compartilhado, o total combinado seria travado em 15% (ex.:
    # um recebe 15% e o outro 0%, ou split 7.5/7.5), nunca os dois
    # atingindo 15% cada, que soma 30% > o teto de um emissor só.
    by_symbol = {item.symbol: item.recommended_percentage for item in result.assets}
    assert by_symbol["AAAA3"] == Decimal("15")
    assert by_symbol["AAAA4"] == Decimal("15")


def test_class_without_eligible_candidate_produces_explicit_gap_never_bad_asset():
    p = policy(
        [policy_allocation("Ações", 50), policy_allocation("FIIs", 15)],
    )
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("AAAA3")],  # nenhum FII entre os candidatos
        policy=p,
    )
    fii_row = next(item for item in result.class_allocations if item.asset_class == "FIIs")
    assert fii_row.percentage == Decimal("0.00")
    assert fii_row.target_percentage == Decimal("15")
    assert fii_row.gap_percentage == Decimal("15")
    assert fii_row.gap_reason is not None
    assert not any(item.asset_class == "FIIs" for item in result.assets)


def test_target_not_reachable_by_asset_limit_leaves_honest_gap():
    p = policy(
        [policy_allocation("Ações", 30, maximum=100)],
        maximum_weight_per_asset=Decimal("5"),
    )
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_asset=Decimal("100")),
        [candidate("AAAA3")],
        policy=p,
    )
    acoes_row = next(item for item in result.class_allocations if item.asset_class == "Ações")
    assert acoes_row.percentage == Decimal("5.00")
    assert acoes_row.gap_percentage == Decimal("25.00")


def test_max_assets_truncation_never_breaks_per_asset_or_issuer_caps():
    p = policy(
        [policy_allocation("Ações", 90, maximum=100)],
        maximum_weight_per_asset=Decimal("10"),
        maximum_weight_per_issuer=Decimal("10"),
    )
    candidates = [
        candidate(f"T{i:03d}3", sector=f"Setor{i}", issuer=f"Emissor{i}", score=str(90 - i))
        for i in range(20)
    ]
    result = SmartPortfolioEngine.build(
        request(max_assets=3, max_percentage_per_asset=Decimal("100")),
        candidates,
        policy=p,
    )
    assert len(result.assets) <= 3
    assert all(item.recommended_percentage <= Decimal("10") for item in result.assets)
    acoes_row = next(item for item in result.class_allocations if item.asset_class == "Ações")
    assert acoes_row.gap_percentage is not None and acoes_row.gap_percentage > 0


def test_policy_disabled_class_never_selected_even_if_request_allows_it():
    p = policy(
        [
            policy_allocation("Ações", 50),
            policy_allocation("FIIs", 20, enabled=False),
        ],
    )
    result = SmartPortfolioEngine.build(
        request(allowed_classes=["FIIs"]),
        [candidate("FII11", InvestmentClass.FII, sector="Papel")],
        policy=p,
    )
    assert not result.assets
    assert result.exclusions[0].symbol == "FII11"


def test_income_need_from_policy_influences_scoring_even_if_request_disagrees():
    p = policy([policy_allocation("FIIs", 100, maximum=100)], income_need=True)
    high_income = candidate(
        "FII11", InvestmentClass.FII, sector="Papel", score="60", income_score=Decimal("95")
    )
    low_income = candidate(
        "FII22", InvestmentClass.FII, sector="Papel", score="60", income_score=Decimal("10")
    )
    result = SmartPortfolioEngine.build(
        request(needs_income=False, max_assets=2),
        [high_income, low_income],
        policy=p,
    )
    ranked_symbols = [item.symbol for item in result.assets]
    assert ranked_symbols[0] == "FII11"


def test_liquidity_need_from_policy_influences_scoring_even_if_request_disagrees():
    p = policy([policy_allocation("Tesouro Direto", 100, maximum=100)], liquidity_need="alta")
    liquid = candidate(
        "TESOURO1",
        InvestmentClass.TREASURY,
        sector=None,
        score="60",
        liquidity_score=Decimal("95"),
    )
    illiquid = candidate(
        "TESOURO2",
        InvestmentClass.TREASURY,
        sector=None,
        score="60",
        liquidity_score=Decimal("10"),
    )
    result = SmartPortfolioEngine.build(
        request(needs_liquidity=False, max_assets=2),
        [liquid, illiquid],
        policy=p,
    )
    ranked_symbols = [item.symbol for item in result.assets]
    assert ranked_symbols[0] == "TESOURO1"


def test_strategy_summary_reflects_effective_policy_not_conflicting_request():
    p = policy(
        [policy_allocation("Ações", 100, maximum=100)],
        risk_profile="Moderado",
        objective="renda_passiva",
        investment_horizon="mais_10_anos",
    )
    result = SmartPortfolioEngine.build(
        request(risk_profile="Arrojado", objective="crescimento", horizon="curto prazo"),
        [candidate("AAAA3")],
        policy=p,
    )
    assert "Moderado" in result.strategy_summary
    assert "renda_passiva" in result.strategy_summary
    assert "mais_10_anos" in result.strategy_summary
    assert "Arrojado" not in result.strategy_summary
    assert "PortfolioPolicy" in result.strategy_summary


def test_policy_provenance_is_never_attributed_to_investor_profile_onboarding():
    """PortfolioPolicy não tem campo de provenance -- ela pode ter sido
    criada pelo onboarding do Perfil do Investidor OU diretamente via
    POST/PUT /intelligence/policy, e o sistema não sabe distinguir qual.
    policy_source e strategy_summary NUNCA podem afirmar uma origem que
    não é conhecida. As asserções abaixo são literais (não seguem a
    constante POLICY_SOURCE cegamente) para travar regressão futura caso
    alguém reintroduza uma provenance inventada."""
    p = policy([policy_allocation("Ações", 100, maximum=100)])
    result = SmartPortfolioEngine.build(
        request(), [candidate("AAAA3")], policy=p
    )
    # Literal: nunca "investor_profile_policy" nem qualquer variação que
    # afirme onboarding como a origem.
    assert result.policy_source == "portfolio_policy"
    assert "investor_profile" not in result.policy_source
    assert "onboarding" not in result.policy_source
    # strategy_summary nunca pode afirmar que a origem é o onboarding do
    # Perfil do Investidor confirmado -- só que UMA policy persistida
    # existe e foi usada.
    assert "Perfil do Investidor confirmado" not in result.strategy_summary
    assert "onboarding" not in result.strategy_summary.lower()
    assert "PortfolioPolicy" in result.strategy_summary
    assert "persistida" in result.strategy_summary.lower()


def test_protection_phase_still_suspends_execution_regardless_of_aggressive_policy():
    p = policy([policy_allocation("Ações", 100, maximum=100)], risk_profile="Arrojado")
    result = SmartPortfolioEngine.build(
        request(
            net_monthly_income=Decimal("3000"),
            essential_monthly_expenses=Decimal("2800"),
            total_monthly_expenses=Decimal("2900"),
            emergency_reserve=Decimal("0"),
            high_cost_debt=Decimal("5000"),
        ),
        [candidate("AAAA3")],
        policy=p,
    )
    assert result.diagnosis.phase == "protection"
    assert result.assets
    assert any("suspensa" in item.lower() for item in result.assets[0].execution_impediments)


def test_execution_rounds_down_and_marks_b3_fractional_market():
    asset = SmartPortfolioEngine.explain(
        request(available_amount=Decimal("833.99")),
        candidate(
            "PETR4",
            current_price=Decimal("37.42"),
            market_context="B3",
        ),
        Decimal("80"),
        Decimal("100"),
        "accumulation",
    )

    assert asset.executable_quantity == Decimal("22")
    assert asset.executable_amount == Decimal("823.24")
    assert asset.target_gap == Decimal("10.75")
    assert asset.trading_symbol == "PETR4F"
    assert asset.economic_identity == "PETR4"
    assert asset.market_segment == "fractional"
    assert asset.quantity_step == Decimal("1")


@pytest.mark.parametrize("symbol", ["PETR4", "PETR4F"])
@pytest.mark.parametrize("quantity, segment, ticker", [
    (22, "fractional", "PETR4F"),
    (100, "standard_lot", "PETR4"),
    (200, "standard_lot", "PETR4"),
    (133, "mixed", None),
])
def test_b3_execution_identity_matches_quantity(symbol, quantity, segment, ticker):
    asset = SmartPortfolioEngine.explain(
        request(available_amount=Decimal(quantity) * Decimal("37.42")),
        candidate(symbol, current_price=Decimal("37.42"), market_context=B3_MARKET),
        Decimal("80"), Decimal("100"), "accumulation",
    )
    assert asset.executable_quantity == Decimal(quantity)
    assert asset.economic_identity == "PETR4"
    assert asset.market_segment == segment
    assert asset.trading_symbol == ticker
    assert asset.target_gap == Decimal("0")


def test_execution_preserves_fractional_granularity_for_treasury():
    asset = SmartPortfolioEngine.explain(
        request(available_amount=Decimal("1000")),
        candidate(
            "tesouro-selic-01032031",
            asset_class=InvestmentClass.TREASURY,
            current_price=Decimal("900"),
        ),
        Decimal("80"),
        Decimal("100"),
        "accumulation",
    )

    assert asset.executable_quantity == Decimal("1.11")
    assert asset.executable_amount == Decimal("999.00")
    assert asset.quantity_step == Decimal("0.01")
    assert asset.market_segment is None


def test_execution_returns_no_quantity_when_price_is_missing_or_amount_is_too_small():
    missing_price = SmartPortfolioEngine.explain(
        request(), candidate("SEM3", current_price=None), Decimal("80"), Decimal("20"), "accumulation"
    )
    below_unit = SmartPortfolioEngine.explain(
        request(available_amount=Decimal("9")),
        candidate("CARO3", current_price=Decimal("10"), market_context="B3"),
        Decimal("80"),
        Decimal("100"),
        "accumulation",
    )

    assert missing_price.executable_quantity is None
    assert "Preço de referência indisponível" in missing_price.execution_impediments[0]
    assert below_unit.executable_quantity is None
    assert below_unit.executable_amount == Decimal("0")
    assert "menor que uma unidade" in below_unit.execution_impediments[0]


def test_no_policy_response_schema_stays_backward_compatible():
    """Chamada com a assinatura antiga (sem `policy=`) continua funcionando
    e devolvendo defaults aditivos seguros."""
    result = SmartPortfolioEngine.build(request(), [candidate("AAAA3")])
    assert isinstance(result, BuildPortfolioResponse)
    assert result.policy_source == "request_legacy"
    assert result.policy_id is None


# --- Invariantes (seção 34) ------------------------------------------------


def test_invariant_no_class_exceeds_policy_maximum_percentage():
    p = policy([policy_allocation("Ações", 30, maximum=35)])
    candidates = [candidate(f"T{i:03d}3", sector=f"S{i}", issuer=f"E{i}") for i in range(10)]
    result = SmartPortfolioEngine.build(
        request(max_percentage_per_asset=Decimal("100"), max_assets=10), candidates, policy=p
    )
    acoes_row = next(item for item in result.class_allocations if item.asset_class == "Ações")
    assert acoes_row.percentage <= Decimal("35")


def test_invariant_deterministic_with_policy():
    p = policy([policy_allocation("Ações", 60), policy_allocation("FIIs", 20)])
    candidates = [
        candidate("BBBB3", sector="Financeiro"),
        candidate("AAAA3", sector="Energia"),
        candidate("FII11", InvestmentClass.FII, sector="Papel"),
    ]
    first = SmartPortfolioEngine.build(request(), candidates, policy=p)
    second = SmartPortfolioEngine.build(request(), list(reversed(candidates)), policy=p)
    assert [(item.symbol, item.recommended_percentage) for item in first.assets] == [
        (item.symbol, item.recommended_percentage) for item in second.assets
    ]


def test_invariant_unallocated_plus_allocated_equals_available_with_policy():
    p = policy([policy_allocation("Ações", 40), policy_allocation("FIIs", 20)])
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("AAAA3"), candidate("FII11", InvestmentClass.FII, sector="Papel")],
        policy=p,
    )
    assert result.total_allocated_amount + result.unallocated_amount == Decimal("10000.00")


def test_reserve_class_from_policy_is_never_redistributed_to_other_classes():
    """Reserva de emergência é tratada pelo FinancialDiagnosisEngine/fase
    protection, NUNCA como classe investível pelo SmartPortfolio -- sua
    meta na política nunca é silenciosamente transferida para outra
    classe (ex.: Ações não vira 100% só porque Reserva não tem
    candidato) nem aparece como uma "classe" a preencher na resposta."""
    p = policy(
        [
            policy_allocation("Ações", 80, maximum=100),
            policy_allocation("Reserva de emergência", 20, maximum=100),
        ],
        maximum_weight_per_asset=Decimal("100"),
        maximum_weight_per_sector=Decimal("100"),
        maximum_weight_per_issuer=Decimal("100"),
    )
    result = SmartPortfolioEngine.build(
        request(
            max_percentage_per_asset=Decimal("100"),
            max_percentage_per_sector=Decimal("100"),
        ),
        [candidate("AAAA3", sector="Energia")],
        policy=p,
    )
    totals = {item.asset_class: item.percentage for item in result.class_allocations}
    # Nunca "sobe" para 100% absorvendo a meta da reserva -- fica
    # exatamente nos 80% reais da política.
    assert totals["Ações"] == Decimal("80.00")
    # Reserva nunca vira uma linha/classe que o SmartPortfolio tenta
    # preencher com ativos.
    assert "Reserva de emergência" not in totals
    assert not any(item.asset_class == "Reserva de emergência" for item in result.assets)
    # Os 20% da meta de reserva ficam honestamente livres, nunca
    # redistribuídos/forçados em Ações.
    assert result.unallocated_amount == Decimal("2000.00")
    assert result.status == "partial"


# Carteira contextual: compras e vendas reais influenciam o próximo aporte.
def test_existing_concentrated_stock_cannot_receive_new_money():
    from app.engines.smart_portfolio_engine import PortfolioHolding
    holdings = [
        PortfolioHolding(
            symbol="AAAA3", quantity=Decimal("900"),
            value=Decimal("9000"), valuation_basis="market",
            asset_class="Ações", sector="Energia", issuer="AAAA3",
        )
    ]
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("AAAA3", sector="Energia"), candidate("BBBB3", sector="Tecnologia")],
        holdings=holdings,
    )
    assert all(item.symbol != "AAAA3" for item in result.assets)
    assert result.existing_positions_count == 1
    assert result.existing_portfolio_value == Decimal("9000")
    assessment = result.existing_holdings_assessments[0]
    assert assessment.recommendation == "review_concentration"
    assert assessment.estimated_weight == Decimal("100.00")
    assert any(item.symbol == "BBBB3" for item in result.assets)
    assert result.total_allocated_amount + result.unallocated_amount == Decimal("10000.00")


def test_new_money_is_restricted_by_existing_sector_exposure():
    from app.engines.smart_portfolio_engine import PortfolioHolding
    holdings = [
        PortfolioHolding(
            symbol="EXIST3", quantity=Decimal("200"),
            value=Decimal("6000"), valuation_basis="market",
            asset_class="Ações", sector="Energia", issuer="EXIST3",
        )
    ]
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("NEW3", sector="Energia"), candidate("TECH3", sector="Tecnologia")],
        holdings=holdings,
    )
    # Sector limit 30% of (R$ 6000 + R$ 10000), already has R$ 6000.
    assert all(item.symbol != "NEW3" for item in result.assets)
    assert any(item.symbol == "TECH3" for item in result.assets)


def test_holdings_price_fallback_and_uncovered_asset_are_not_passed_off_as_verified():
    from app.engines.smart_portfolio_engine import PortfolioHolding
    result = SmartPortfolioEngine.build(
        request(),
        [candidate("NEW3", sector="Tecnologia")],
        holdings=[
            PortfolioHolding(
                symbol="OLD3", quantity=Decimal("10"), value=Decimal("100"),
                valuation_basis="invested", asset_class="Ações",
            )
        ],
    )
    assert result.holdings_warnings
    assessment = result.existing_holdings_assessments[0]
    assert assessment.recommendation == "not_analyzed"
    assert assessment.confidence == "insufficient"
    assert assessment.valuation_basis == "invested"
