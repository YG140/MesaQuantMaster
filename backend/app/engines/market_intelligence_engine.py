from __future__ import annotations

from decimal import Decimal

from app.engines.indicator_catalog import SCORING_CATEGORIES, coverage_breakdown_for_asset
from app.engines.equity_indicator_scoring import score_stock_indicator
from app.engines.multimarket_scoring import specialized_categories, score_specialized_indicator
from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot,
    ConfidenceLevel,
    CoverageBreakdown,
    DataQualityReport,
    IndicatorStatus,
    InvestmentClass,
    NormalizedIndicator,
    RecommendationAction,
    ScoreBreakdown,
    ValuationAssessment,
    ValuationStatus,
)


MINIMUM_SCORE_COVERAGE = Decimal("40")

# Thresholds canônicos de confidence (P1) — centralizados aqui, não espalhar
# números mágicos por outros arquivos.
MINIMUM_SCORING_CATEGORIES = 2
CONFIDENCE_HIGH_SCORING_COVERAGE = Decimal("80")
CONFIDENCE_MEDIUM_SCORING_COVERAGE = Decimal("60")

# Anomalias que, se presentes, tornam a análise INSUFFICIENT independente de
# cobertura (identidade do ativo/emissor não confiável, conflito crítico entre
# fontes). Nunca inferido automaticamente por este engine — precisa vir
# marcado explicitamente em anomaly_flags por quem detectou a condição.
CRITICAL_ANOMALY_FLAGS = {"identifier_unresolved", "issuer_identity_unresolved", "conflicting_sources"}


class ScoringEngine:
    @classmethod
    def score_all(
        cls,
        asset_class: InvestmentClass,
        indicators: list[NormalizedIndicator],
    ) -> dict[str, ScoreBreakdown]:
        # ETF, BDR, exterior e cripto usam métricas específicas da
        # classe; volume/preço disponíveis não devem virar nota de qualidade.
        categories = specialized_categories(asset_class) or SCORING_CATEGORIES
        return {
            category: cls.score_category(asset_class, indicators, keys)
            for category, keys in categories.items()
        }

    @staticmethod
    def score_category(
        asset_class: InvestmentClass,
        indicators: list[NormalizedIndicator],
        keys: list[str],
    ) -> ScoreBreakdown:
        applicable = [item for item in indicators if item.key in keys]
        if not applicable:
            return ScoreBreakdown(
                available_indicators=0,
                missing_indicators=0,
                stale_indicators=0,
                coverage_percentage=Decimal("0"),
                confidence=ConfidenceLevel.INSUFFICIENT,
                reasons=[
                    f"Categoria sem indicadores aplicáveis para {asset_class.value}."
                ],
            )

        available = [
            item for item in applicable if item.status == IndicatorStatus.AVAILABLE
        ]
        stale = [item for item in applicable if item.status == IndicatorStatus.STALE]
        missing = [
            item
            for item in applicable
            if item.status
            in {
                IndicatorStatus.UNAVAILABLE,
                IndicatorStatus.INVALID,
                IndicatorStatus.PARTIAL,
                IndicatorStatus.INSUFFICIENT_DATA,
                IndicatorStatus.POTENTIALLY_INCONSISTENT,
            }
        ]
        coverage = (
            Decimal(len(available)) / Decimal(len(applicable)) * Decimal("100")
        ).quantize(Decimal("0.01"))
        if coverage < MINIMUM_SCORE_COVERAGE and asset_class not in {
            InvestmentClass.ETF, InvestmentClass.BDR,
            InvestmentClass.INTERNATIONAL, InvestmentClass.CRYPTO,
        }:
            return ScoreBreakdown(
                available_indicators=len(available),
                missing_indicators=len(missing),
                stale_indicators=len(stale),
                coverage_percentage=coverage,
                confidence=confidence_for_coverage(coverage),
                reasons=[
                    "Cobertura insuficiente para pontuar sem distorcer a análise."
                ],
            )

        if asset_class in {
            InvestmentClass.ETF, InvestmentClass.BDR,
            InvestmentClass.INTERNATIONAL, InvestmentClass.CRYPTO,
        }:
            observed = [
                rating for item in available
                if (rating := score_specialized_indicator(asset_class, item)) is not None
            ]
            return ScoreBreakdown(
                value=(
                    (sum(observed, Decimal("0")) / len(observed)).quantize(Decimal("0.01"))
                    if observed else None
                ),
                available_indicators=len(available),
                missing_indicators=len(missing),
                stale_indicators=len(stale),
                coverage_percentage=coverage,
                confidence=confidence_for_coverage(coverage),
                reasons=[
                    "Pontuação baseada apenas em índices numéricos comparáveis, "
                    "com procedência e atualização verificadas."
                    if observed else
                    "Sem índices apropriados para pontuar esta categoria; "
                    "disponibilidade não equivale a qualidade."
                ],
            )
        if asset_class == InvestmentClass.STOCK:
            # Disponibilidade é um critério de confiança, NÃO de qualidade.
            # Os números de ROE, alavancagem, P/L etc. devem influenciar
            # a nota. Nenhum indicador não comparável recebe nota artificial.
            # Dividend Yield é retorno/distribuição, não uma medida
            # independente de valuation: não o contamos duas vezes.
            scored_indicators = [
                item for item in available
                if not (item.key == "dividend_yield" and "price_earnings" in keys)
            ]
            observed = [
                rating for item in scored_indicators
                if (rating := score_stock_indicator(item)) is not None
            ]
            if not observed:
                return ScoreBreakdown(
                    available_indicators=len(available),
                    missing_indicators=len(missing),
                    stale_indicators=len(stale),
                    coverage_percentage=coverage,
                    confidence=confidence_for_coverage(coverage),
                    reasons=[
                        "Dados presentes, mas sem proporções financeiras "
                        "comparáveis para uma pontuação fundamentada."
                    ],
                )
            value = (sum(observed, Decimal("0")) / len(observed)).quantize(Decimal("0.01"))
            return ScoreBreakdown(
                value=value,
                available_indicators=len(available),
                missing_indicators=len(missing),
                stale_indicators=len(stale),
                coverage_percentage=coverage,
                confidence=confidence_for_coverage(coverage),
                reasons=[
                    "Heurística inicial baseada nos valores reais dos índices "
                    "financeiros, independente da cobertura; não substitui "
                    "comparação setorial e análise de balanços."
                ],
            )
        return ScoreBreakdown(
            value=coverage,
            available_indicators=len(available),
            missing_indicators=len(missing),
            stale_indicators=len(stale),
            coverage_percentage=coverage,
            confidence=confidence_for_coverage(coverage),
            reasons=[
                "Pontuação provisória de disponibilidade: avaliação por "
                "fundamentos específicos da classe ainda pendente."
            ],
        )


class AssetAnalysisEngine:
    @classmethod
    def build_snapshot(
        cls,
        base: AssetIntelligenceSnapshot,
    ) -> AssetIntelligenceSnapshot:
        scores = ScoringEngine.score_all(base.asset_class, base.indicators)
        valuation = ValuationEngine.assess(base.indicators)
        category_values = [
            score.value for score in scores.values() if score.value is not None
        ]
        coverage = cls.coverage(base.indicators)
        coverage_breakdown = coverage_breakdown_for_asset(base.asset_class, base.indicators)
        # Confidence estrutural (P1) é calculado ANTES da recomendação (P4) para
        # que RecommendationEngine deixe de depender só do coverage legado —
        # overall_score não é usado pelo cálculo de confidence (ver docstring
        # de confidence_for_asset), então passar None aqui não afeta o resultado.
        confidence = confidence_for_asset(
            coverage_breakdown=coverage_breakdown,
            scores=scores,
            overall_score=None,
            data_quality=base.data_quality,
            anomaly_flags=base.anomaly_flags,
        )
        # overall_score exige base financeira estrutural real: pelo menos
        # MINIMUM_SCORING_CATEGORIES categorias com valor realmente calculado
        # (mesmo limiar usado pelo confidence). Nunca mais gated pelo
        # coverage_percentage legado, que mistura indicadores não essenciais
        # e podia zerar overall_score mesmo com categorias reais suficientes.
        overall = (
            (
                sum(category_values, Decimal("0")) / Decimal(len(category_values))
            ).quantize(Decimal("0.01"))
            if len(category_values) >= MINIMUM_SCORING_CATEGORIES
            else None
        )
        recommendation = RecommendationEngine.recommend(
            base,
            scores=scores,
            valuation=valuation,
            confidence=confidence,
            overall_score=overall,
        )
        return base.model_copy(
            update={
                "quality_score": scores["quality"].value,
                "valuation_score": scores["valuation"].value,
                "income_score": scores["income"].value,
                "growth_score": scores["growth"].value,
                "debt_score": scores["debt"].value,
                "risk_score": scores["risk"].value,
                "liquidity_score": scores["liquidity"].value,
                "data_quality_score": (
                    base.data_quality.data_quality_score
                    if base.data_quality is not None
                    else None
                ),
                "overall_score": overall,
                "valuation_status": valuation.status,
                "valuation": valuation,
                "recommendation": recommendation,
                "confidence": confidence,
                "coverage_percentage": coverage,
                "coverage_breakdown": coverage_breakdown,
                "available_indicators_count": sum(
                    1
                    for item in base.indicators
                    if item.status == IndicatorStatus.AVAILABLE
                ),
                "missing_indicators_count": sum(
                    1
                    for item in base.indicators
                    if item.status
                    in {
                        IndicatorStatus.UNAVAILABLE,
                        IndicatorStatus.INVALID,
                        IndicatorStatus.PARTIAL,
                        IndicatorStatus.INSUFFICIENT_DATA,
                        IndicatorStatus.POTENTIALLY_INCONSISTENT,
                    }
                ),
                "stale_indicators_count": sum(
                    1
                    for item in base.indicators
                    if item.status == IndicatorStatus.STALE
                ),
                "missing_data": [
                    item.label
                    for item in base.indicators
                    if item.status
                    in {
                        IndicatorStatus.UNAVAILABLE,
                        IndicatorStatus.INVALID,
                        IndicatorStatus.PARTIAL,
                        IndicatorStatus.INSUFFICIENT_DATA,
                        IndicatorStatus.POTENTIALLY_INCONSISTENT,
                    }
                ],
                "positive_reasons": positive_reasons(base),
                "warning_reasons": warning_reasons(
                    base, coverage_breakdown=coverage_breakdown, confidence=confidence
                ),
            }
        )

    @staticmethod
    def coverage(indicators: list[NormalizedIndicator]) -> Decimal:
        scored = [
            item for item in indicators if item.status != IndicatorStatus.NOT_APPLICABLE
        ]
        if not scored:
            return Decimal("0")
        available = sum(
            1 for item in scored if item.status == IndicatorStatus.AVAILABLE
        )
        return (Decimal(available) / Decimal(len(scored)) * Decimal("100")).quantize(
            Decimal("0.01")
        )


class StockAnalysisEngine(AssetAnalysisEngine):
    pass


class FiiAnalysisEngine(AssetAnalysisEngine):
    pass


class EtfAnalysisEngine(AssetAnalysisEngine):
    pass


class TreasuryAnalysisEngine(AssetAnalysisEngine):
    pass


class ValuationEngine:
    @staticmethod
    def assess(indicators: list[NormalizedIndicator]) -> ValuationAssessment:
        valuation_keys = {"price_earnings", "price_book", "dividend_yield"}
        used = [
            item
            for item in indicators
            if item.key in valuation_keys and item.status == IndicatorStatus.AVAILABLE
        ]
        missing = [
            item.label
            for item in indicators
            if item.key in valuation_keys and item.status != IndicatorStatus.AVAILABLE
        ]
        if len(used) < 2:
            return ValuationAssessment(
                status=ValuationStatus.INSUFFICIENT_DATA,
                methods=[],
                used_indicators=[item.label for item in used],
                missing_indicators=missing,
                confidence=ConfidenceLevel.INSUFFICIENT,
                data_date=next((item.reference_date for item in used), None),
            )
        # Ter dois indicadores NÃO produz uma estimativa independente de
        # preço justo. P/L e P/VP precisam de histórico/pares comparáveis,
        # e não existe ainda um modelo validado de valor intrínseco.
        # Até sua implementação, evite classificar automaticamente
        # uma ação como "próxima do valor estimado".
        return ValuationAssessment(
            status=ValuationStatus.INSUFFICIENT_DATA,
            methods=[],
            used_indicators=[item.label for item in used],
            missing_indicators=[
                *missing, "Referência setorial/histórica validada para preço justo."
            ],
            confidence=ConfidenceLevel.INSUFFICIENT,
            data_date=next((item.reference_date for item in used), None),
        )


class RecommendationEngine:
    @staticmethod
    def recommend(
        snapshot: AssetIntelligenceSnapshot,
        scores: dict[str, ScoreBreakdown],
        valuation: ValuationAssessment,
        confidence: ConfidenceLevel,
        overall_score: Decimal | None,
    ) -> RecommendationAction:
        # P4: o gate universal deixou de ser coverage_percentage legado (que
        # mistura indicadores não essenciais e podia bloquear um ativo com
        # required completo e scoring real suficiente). Passa a usar o
        # confidence estrutural (P1): só bloqueia quando genuinamente
        # INSUFFICIENT (pilar obrigatório não satisfeito, poucas categorias
        # reais de scoring, ou anomalia crítica de identidade/conflito).
        if confidence == ConfidenceLevel.INSUFFICIENT:
            return RecommendationAction.INSUFFICIENT_DATA
        if (
            snapshot.data_quality is not None
            and snapshot.data_quality.recommendation_blocked
        ):
            return RecommendationAction.REVIEW_DATA
        if snapshot.strategy_fit_score is not None and snapshot.strategy_fit_score < 40:
            return RecommendationAction.WAIT
        if snapshot.asset_class == InvestmentClass.ETF:
            # ETF não é empresa com LPA/VPA; em vez de inventar
            # preço justo, exige spread, risco, custo de gestão e
            # prêmio/desconto ao NAV verificáveis antes de cogitar aporte.
            required = ("quality", "valuation", "risk", "liquidity")
            if overall_score is None or any(
                scores[key].value is None for key in required
            ):
                return RecommendationAction.REVIEW_DATA
            if overall_score < Decimal("60"):
                return RecommendationAction.WAIT
            if overall_score >= Decimal("75") and confidence in {
                ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM,
            }:
                return RecommendationAction.ANALYZE_TO_BUY
            return RecommendationAction.HOLD
        if valuation.status == ValuationStatus.INSUFFICIENT_DATA:
            return RecommendationAction.REVIEW_DATA
        if overall_score is None:
            return RecommendationAction.REVIEW_DATA
        if overall_score >= 75:
            return RecommendationAction.ANALYZE_TO_BUY
        if overall_score >= 60:
            return RecommendationAction.HOLD
        return RecommendationAction.WAIT


def confidence_for_coverage(coverage: Decimal) -> ConfidenceLevel:
    if coverage >= Decimal("80"):
        return ConfidenceLevel.HIGH
    if coverage >= Decimal("60"):
        return ConfidenceLevel.MEDIUM
    if coverage >= Decimal("40"):
        return ConfidenceLevel.LOW
    return ConfidenceLevel.INSUFFICIENT


def confidence_for_asset(
    *,
    coverage_breakdown: CoverageBreakdown,
    scores: dict[str, ScoreBreakdown],
    overall_score: Decimal | None,
    data_quality: DataQualityReport | None,
    anomaly_flags: list[str] | None = None,
) -> ConfidenceLevel:
    """Confidence estruturado do ativo (P1): HIGH/MEDIUM/LOW/INSUFFICIENT.

    Avalia a SUFICIÊNCIA DOS DADOS de forma independente do gate legado
    coverage_percentage < MINIMUM_SCORE_COVERAGE. Desde P4, RecommendationEngine
    também usa este confidence como gate único de INSUFFICIENT_DATA (deixou
    de gatear em coverage_percentage legado); SmartPortfolio já usava
    confidence desde P2. `overall_score` e `data_quality` continuam
    recebidos para compatibilidade de assinatura e futura evolução, mas não
    são usados como gate sozinhos aqui: overall_score pode ser None mesmo
    com dados estruturalmente suficientes (categorias reais < 2), e
    data_quality.recommendation_blocked pode disparar por completeness/
    freshness não crítica — nenhum dos dois, isoladamente, deve forçar
    INSUFFICIENT neste confidence.

    LOW nunca bloqueia sozinho — é apenas um sinal de menor cobertura/certeza.
    INSUFFICIENT é reservado para condições estruturalmente críticas: pilar
    REQUIRED essencial não satisfeito (o que já cobre preço indispensável,
    pois "price" é sempre um pilar REQUIRED ALL_OF), poucas categorias reais
    de score, ou anomalia crítica de identidade/conflito de fontes.
    """
    if anomaly_flags and any(flag in CRITICAL_ANOMALY_FLAGS for flag in anomaly_flags):
        return ConfidenceLevel.INSUFFICIENT

    required_total = coverage_breakdown.required_total
    required_satisfied = coverage_breakdown.required_satisfied
    required_complete = required_total == 0 or required_satisfied == required_total
    if not required_complete:
        return ConfidenceLevel.INSUFFICIENT

    scored_categories = sum(1 for score in scores.values() if score.value is not None)
    if scored_categories < MINIMUM_SCORING_CATEGORIES:
        return ConfidenceLevel.INSUFFICIENT

    scoring_coverage = coverage_breakdown.scoring_coverage or Decimal("0")
    if scoring_coverage >= CONFIDENCE_HIGH_SCORING_COVERAGE:
        return ConfidenceLevel.HIGH
    if scoring_coverage >= CONFIDENCE_MEDIUM_SCORING_COVERAGE:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def positive_reasons(snapshot: AssetIntelligenceSnapshot) -> list[str]:
    reasons = []
    if snapshot.current_price is not None:
        reasons.append("Cotação real disponível no provedor de mercado.")
    if snapshot.strategy_fit_score is not None and snapshot.strategy_fit_score >= 60:
        reasons.append("Classe alinhada à política de investimentos configurada.")
    return reasons


def warning_reasons(
    snapshot: AssetIntelligenceSnapshot,
    *,
    coverage_breakdown: CoverageBreakdown,
    confidence: ConfidenceLevel,
) -> list[str]:
    reasons = []
    if confidence == ConfidenceLevel.INSUFFICIENT:
        reasons.append(
            _insufficient_confidence_reason(coverage_breakdown, snapshot.anomaly_flags)
        )
    if snapshot.strategy_fit_score is not None and snapshot.strategy_fit_score < 40:
        reasons.append("Classe acima dos limites definidos na política do usuário.")
    if snapshot.market_updated_at is None:
        reasons.append("Data da cotação indisponível.")
    if snapshot.data_quality is not None and snapshot.data_quality.blocking_reason:
        reasons.append(snapshot.data_quality.blocking_reason)
    return reasons


def _insufficient_confidence_reason(
    coverage_breakdown: CoverageBreakdown, anomaly_flags: list[str] | None
) -> str:
    """Traduz confidence == INSUFFICIENT numa causa específica e real (P4),
    nunca a mensagem genérica "Dados insuficientes"."""
    flags = set(anomaly_flags or [])
    if flags & CRITICAL_ANOMALY_FLAGS:
        return "Identidade do ativo ou conflito crítico entre fontes de dados não resolvido."
    if (
        coverage_breakdown.required_total
        and coverage_breakdown.required_satisfied < coverage_breakdown.required_total
    ):
        missing = coverage_breakdown.required_total - coverage_breakdown.required_satisfied
        plural = "pilares obrigatórios" if missing > 1 else "pilar obrigatório"
        return f"{missing} {plural} não atendido(s) para esta classe de ativo."
    return "Categorias reais de pontuação insuficientes para uma análise confiável."
