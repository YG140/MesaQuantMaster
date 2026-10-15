"""Contexto de compras reais na recomendação de novos aportes.

As posições chegam exclusivamente do serviço autenticado. Este módulo não
interpreta rentabilidade passada como indicador de qualidade nem inventa
pontuações quando faltam fundamentos.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_DOWN

from app.schemas.intelligence import ExistingHoldingAssessment
from app.schemas.market_intelligence import ConfidenceLevel

HUNDRED = Decimal("100")
CENT = Decimal("0.01")


def limit_new_contributions(request, ranked, strategy, percentages, holdings, class_label):
    """Limit NEW allocations against post-contribution portfolio exposure."""
    total_after = sum((h.value for h in holdings), Decimal("0")) + request.available_amount
    by_symbol = defaultdict(lambda: Decimal("0"))
    by_sector = defaultdict(lambda: Decimal("0"))
    by_issuer = defaultdict(lambda: Decimal("0"))
    by_class = defaultdict(lambda: Decimal("0"))
    for holding in holdings:
        by_symbol[holding.symbol.upper()] += holding.value
        by_sector[(holding.sector or f"unknown:{holding.symbol}").casefold()] += holding.value
        by_issuer[holding.issuer or f"unknown:{holding.symbol}"] += holding.value
        if holding.asset_class:
            by_class[holding.asset_class] += holding.value

    notes = {}
    result = {}
    for candidate, _ in ranked:
        symbol = candidate.snapshot.symbol
        share = percentages.get(symbol, Decimal("0"))
        if share <= 0:
            continue
        asset_class = class_label(candidate.snapshot.asset_class)
        sector = (candidate.sector or f"unknown:{symbol}").casefold()
        issuer = candidate.issuer or f"unknown:{symbol}"
        limits = [
            total_after * strategy.max_percentage_per_asset / HUNDRED - by_symbol[symbol.upper()],
            total_after * strategy.max_percentage_per_sector / HUNDRED - by_sector[sector],
        ]
        if strategy.max_percentage_per_issuer is not None:
            limits.append(
                total_after * strategy.max_percentage_per_issuer / HUNDRED - by_issuer[issuer]
            )
        if strategy.class_targets:
            target = strategy.class_targets.get(asset_class)
            if target:
                limits.append(
                    total_after * target.maximum_percentage / HUNDRED - by_class[asset_class]
                )
        else:
            limits.append(
                total_after * request.max_percentage_per_class / HUNDRED - by_class[asset_class]
            )
        proposed = request.available_amount * share / HUNDRED
        allowed = max(Decimal("0"), min(proposed, *limits))
        adjusted = (allowed / request.available_amount * HUNDRED).quantize(
            CENT, rounding=ROUND_DOWN
        )
        result[symbol] = adjusted
        actual = request.available_amount * adjusted / HUNDRED
        by_symbol[symbol.upper()] += actual
        by_sector[sector] += actual
        by_issuer[issuer] += actual
        by_class[asset_class] += actual
        if adjusted < share:
            notes[symbol] = (
                "Aporte reduzido para respeitar os limites de concentração "
                "considerando as posições já registradas na corretora."
            )
    return result, notes


def assess_holdings(holdings, candidates, strategy, effective_score):
    """Assess every held asset, including uncovered ones without fake verdicts."""
    snapshots = {c.snapshot.symbol.upper(): c.snapshot for c in candidates}
    total = sum((h.value for h in holdings), Decimal("0"))
    assessed = []
    for h in sorted(holdings, key=lambda p: p.symbol):
        snapshot = snapshots.get(h.symbol.upper())
        confidence = (
            snapshot.confidence.value if snapshot
            else ConfidenceLevel.INSUFFICIENT.value
        )
        score = effective_score(snapshot) if snapshot else None
        alerts = []
        weight = (
            (h.value / total * HUNDRED).quantize(CENT)
            if total > 0 else Decimal("0")
        )
        if weight > strategy.max_percentage_per_asset:
            alerts.append("Posição supera o limite definido pelo perfil por ativo.")
        if h.valuation_basis != "market":
            alerts.append("Cotação indisponível; exposição estimada pelo custo registrado.")
        if snapshot:
            alerts.extend(snapshot.warning_reasons[:3])
            recommendation = (
                snapshot.recommendation.value
                if hasattr(snapshot.recommendation, "value")
                else str(snapshot.recommendation)
            )
            rationale = (
                snapshot.positive_reasons[0] if snapshot.positive_reasons
                else "Reveja indicadores e riscos antes de um novo aporte."
            )
            if confidence == ConfidenceLevel.INSUFFICIENT.value:
                recommendation = "insufficient_data"
                rationale = "Dados insuficientes para avaliar o ativo com segurança."
            if weight > strategy.max_percentage_per_asset:
                recommendation = "review_concentration"
                rationale = "Exposição acima do limite: evite ampliar sem revisar a política."
        else:
            recommendation = "not_analyzed"
            rationale = "Ativo fora do universo analisado; sem parecer fundamentado."
        assessed.append(ExistingHoldingAssessment(
            symbol=h.symbol, quantity=h.quantity, estimated_value=h.value,
            estimated_weight=weight, valuation_basis=h.valuation_basis,
            recommendation=recommendation, confidence=confidence,
            overall_score=score, rationale=rationale, alerts=alerts,
        ))
    return assessed
