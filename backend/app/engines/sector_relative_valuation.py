"""Comparações setoriais e faixa de preço implícita por múltiplos de pares.

Não é preço justo intrínseco: calcula somente referência *relativa* aos
múltiplos de emissores comparáveis presentes no universo analisado, sem
consultar fontes externas nem presumir que a média do setor seja justa.

Regra de abstenção: dados atuais + setor definido + >= 3 emissores
distintos + LPA/VPA positivos + múltiplos comparáveis + métodos
concordantes. Sem isso não há faixa estimada nem sinal de compra.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from statistics import median
from unicodedata import normalize
import re

from app.schemas.market_intelligence import (
    AssetIntelligenceSnapshot, ConfidenceLevel, IndicatorStatus,
    InvestmentClass, RecommendationAction, ValuationAssessment,
    ValuationStatus,
)

CENT = Decimal("0.01")
MIN_PEERS = 3
MAX_RATIO_AGE = timedelta(days=450)
MAX_PRICE_AGE = timedelta(days=7)
# Bancos, holdings e seguradoras precisam de pares e modelos financeiros
# específicos. "Financeiro" como setor agregado não distingue tais emissoras.
INCOMPATIBLE_SECTORS = (
    "banco", "financeir", "holding", "segur", "intermedi", "investimento"
)
COMPARABLE_KEYS = {
    "roe": ("quality_score", True),
    "roa": ("quality_score", True),
    "roic": ("quality_score", True),
    "price_earnings": ("valuation_score", False),
    "price_book": ("valuation_score", False),
    "net_debt_equity": ("debt_score", False),
    "revenue_cagr_3y": ("growth_score", True),
}


@dataclass(frozen=True)
class PeerAsset:
    snapshot: AssetIntelligenceSnapshot
    sector: str | None
    issuer: str | None = None


def _canonical(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(
        normalize("NFKD", value).encode("ascii", "ignore")
        .decode("ascii").casefold().split()
    )


def _valid_sector(value: str | None) -> str:
    key = _canonical(value)
    if not key or key in {"outros", "diversos", "sem setor", "nao informado"}:
        return ""
    if any(part in key for part in INCOMPATIBLE_SECTORS):
        return ""
    return key


def _text_indicator(snapshot: AssetIntelligenceSnapshot, key: str) -> str:
    item = next(
        (x for x in snapshot.indicators if x.key == key and x.status == IndicatorStatus.AVAILABLE), None
    )
    return _canonical(str(item.value)) if item and item.value is not None else ""


def _issuer_key(peer: PeerAsset) -> str:
    identity = _canonical(peer.issuer or "")
    # A identidade do portfólio pode ser B3:PETR4 / B3:PETR3. Sem CNPJ
    # oficial, nenhum desses tickers prova emissor distinto; agrupe pelo
    # prefixo da companhia para não aumentar artificialmente o tamanho
    # da amostra (e preserve o namespace do mercado).
    if identity:
        prefix, sep, ticker = identity.rpartition(":")
        candidate = ticker if sep else identity
        if re.fullmatch(r"[a-z]{4}\d{1,2}f?", candidate):
            prefix_key = re.sub(r"\d{1,2}f?$", "", candidate)
            return f"{prefix}:{prefix_key}" if sep else prefix_key
        return identity
    # Falta de identificador verificável: não considerar diferentes
    # classes do mesmo prefixo como pares independentes.
    return re.sub(r"\d{1,2}f?$", "", peer.snapshot.symbol.casefold())


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _numeric(snapshot: AssetIntelligenceSnapshot, key: str, at: datetime) -> Decimal | None:
    for item in snapshot.indicators:
        if item.key != key or item.status != IndicatorStatus.AVAILABLE:
            continue
        # Declarações manuais (confiança baixa) não formam benchmarks
        # independentes. Não inferir preço a partir de números do usuário.
        if item.source_type in {"manual", "user"} or item.confidence in {
            ConfidenceLevel.LOW, ConfidenceLevel.INSUFFICIENT
        }:
            return None
        if item.value is None or isinstance(item.value, str):
            # Pydantic pode normalizar decimais como Decimal; rejeite texto
            # livres e unidades não mensuráveis.
            return None
        try:
            value = Decimal(str(item.value))
        except (TypeError, ValueError, InvalidOperation):
            return None
        if not value.is_finite():
            return None
        if item.reference_date is None:
            return None
        ref = _aware(item.reference_date)
        if ref > at + timedelta(days=1) or at - ref > MAX_RATIO_AGE:
            return None
        if item.valid_until is not None and _aware(item.valid_until) < at:
            return None
        return value
    return None


def _price(snapshot: AssetIntelligenceSnapshot, at: datetime) -> Decimal | None:
    value = snapshot.current_price
    observed = snapshot.market_updated_at
    if value is None or not value.is_finite() or value <= 0 or observed is None:
        return None
    age = at - _aware(observed)
    if age < -timedelta(days=1) or age > MAX_PRICE_AGE:
        return None
    return value


def _metric_median(peers: list[PeerAsset], key: str, at: datetime) -> Decimal | None:
    amounts = []
    for peer in peers:
        value = _numeric(peer.snapshot, key, at)
        if value is not None and value.is_finite():
            if key in {"price_earnings", "price_book"} and not (Decimal("1") <= value <= Decimal("60")):
                continue
            amounts.append(value)
    if len(amounts) < MIN_PEERS:
        return None
    return median(amounts)


def _peer_reference(target: PeerAsset, universe: list[PeerAsset]) -> list[PeerAsset]:
    key = _valid_sector(target.sector)
    if not key or target.snapshot.asset_class not in {
        InvestmentClass.STOCK, InvestmentClass.INTERNATIONAL
    }:
        return []
    segment = _text_indicator(target.snapshot, "segment")
    if any(block in segment for block in INCOMPATIBLE_SECTORS):
        return []
    result = []
    issuers = {_issuer_key(target)}
    for peer in sorted(universe, key=lambda p: p.snapshot.symbol):
        # Global equities use only global-equity peers, never BDRs or
        # Brazilian listings. No currency conversion across peers.
        if peer.snapshot.asset_class != target.snapshot.asset_class or _valid_sector(peer.sector) != key:
            continue
        if peer.snapshot.currency != target.snapshot.currency or not peer.snapshot.currency:
            continue
        peer_segment = _text_indicator(peer.snapshot, "segment")
        if any(block in peer_segment for block in INCOMPATIBLE_SECTORS):
            continue
        if segment != peer_segment:
            # Sem uma segmentação homogênea, setor genérico pode misturar
            # modelos de negócio (e.g., holding com operador).
            continue
        identifier = _issuer_key(peer)
        if not identifier or identifier in issuers:
            continue
        if peer.snapshot.confidence == ConfidenceLevel.INSUFFICIENT or peer.snapshot.anomaly_flags:
            continue
        issuers.add(identifier)
        result.append(peer)
    return result


def _valuation(snapshot: AssetIntelligenceSnapshot, peers: list[PeerAsset], at: datetime) -> ValuationAssessment:
    previous = snapshot.valuation
    if len(peers) < MIN_PEERS:
        return previous.model_copy(update={
            "peer_comparison": (
                "Comparação setorial indisponível: mínimo de 3 emissores "
                "independentes, no mesmo setor, com dados válidos."
            ),
        })
    price = _price(snapshot, at)
    eps = _numeric(snapshot, "earnings_per_share", at)
    bvps = _numeric(snapshot, "book_value_per_share", at)
    pe = _metric_median(peers, "price_earnings", at)
    pb = _metric_median(peers, "price_book", at)
    if price is None or eps is None or bvps is None or eps <= 0 or bvps <= 0 or pe is None or pb is None:
        return previous.model_copy(update={
            "peer_comparison": (
                "Múltiplos setoriais insuficientes, preço desatualizado "
                "ou LPA/VPA positivos não disponíveis para estimar faixa."
            ),
        })
    by_earnings, by_book = eps * pe, bvps * pb
    low, high = min(by_earnings, by_book), max(by_earnings, by_book)
    # Métodos incompatíveis = incerteza estrutural, não promediar.
    if low <= 0 or high / low > Decimal("1.5"):
        return previous.model_copy(update={
            "peer_comparison": "LPA×P/L setorial e VPA×P/VP setorial discordam acima do limite de 50%.",
        })
    low, high = low.quantize(CENT), high.quantize(CENT)
    if price <= low * Decimal("0.80"):
        status = ValuationStatus.ATTRACTIVE
    elif price >= high * Decimal("1.20"):
        status = ValuationStatus.ELEVATED
    else:
        status = ValuationStatus.NEAR_ESTIMATED_VALUE
    return ValuationAssessment(
        status=status, confidence=ConfidenceLevel.MEDIUM,
        methods=["Faixa relativa setorial: LPA × mediana P/L e VPA × mediana P/VP"],
        used_indicators=["LPA", "VPA", "P/L de pares", "P/VP de pares", "Preço atual"],
        missing_indicators=[],
        estimated_range_low=low,
        estimated_range_high=high,
        peer_comparison=(
            f"Referência relativa ao setor ({len(peers)} emissores distintos): "
            f"P/L mediano {pe:.2f}; P/VP mediano {pb:.2f}. "
            "Não é preço justo intrínseco nem garantia de valorização."
        ),
        data_date=at,
    )


def _comparisons(snapshot: AssetIntelligenceSnapshot, peers: list[PeerAsset], at: datetime):
    annotated = []
    deltas = {}
    for item in snapshot.indicators:
        key = item.key
        own = _numeric(snapshot, key, at) if key in COMPARABLE_KEYS else None
        med = _metric_median(peers, key, at) if own is not None else None
        if med is None or own is None:
            annotated.append(item)
            continue
        annotated.append(item.model_copy(update={
            "sector_comparison": (
                f"Mediana de {len(peers)} empresas comparáveis: {med:.2f}; "
                f"ativo: {own:.2f}. Somente pares disponíveis no universo analisado."
            )
        }))
        # Métricas 0 ou negativas não admitem comparação relativa estável.
        if med > 0 and own >= 0:
            desired_high = COMPARABLE_KEYS[key][1]
            relative = (own / med - 1) * Decimal("30")
            delta = max(Decimal("-15"), min(Decimal("15"), relative))
            deltas.setdefault(COMPARABLE_KEYS[key][0], []).append(
                delta if desired_high else -delta
            )
    return annotated, deltas


def enrich_sector_valuations(assets: list[PeerAsset]) -> dict[str, AssetIntelligenceSnapshot]:
    """Compara apenas o universo explicitamente fornecido pelo chamador.

    Não busca concorrentes adivinhados nem modifica snapshots originais.
    A análise de um ativo isolado permanece com valuation insuficiente.
    """
    result = {}
    for target in assets:
        snap = target.snapshot
        if snap.asset_class not in {InvestmentClass.STOCK, InvestmentClass.INTERNATIONAL}:
            result[snap.symbol] = snap
            continue
        peers = _peer_reference(target, assets)
        at = _aware(snap.calculated_at)
        valuation = _valuation(snap, peers, at)
        if len(peers) < MIN_PEERS:
            result[snap.symbol] = snap.model_copy(update={
                "valuation": valuation,
                "valuation_status": valuation.status,
                "warning_reasons": [
                    *snap.warning_reasons,
                    valuation.peer_comparison or "Sem pares setoriais confiáveis.",
                ],
            })
            continue
        indicators, deltas = _comparisons(snap, peers, at)
        updates = {"indicators": indicators, "valuation": valuation, "valuation_status": valuation.status}
        # analyze_assets() pode ser chamado por lotes antes da montagem
        # final. Guarde a nota fundamentada original e reaplique sempre a
        # partir dela; nunca duplique o bônus relativo em uma segunda passagem.
        score_fields = ("quality_score", "valuation_score", "income_score", "growth_score", "debt_score", "risk_score", "liquidity_score")
        baseline = snap.sector_baseline_scores or {
            field: getattr(snap, field) for field in score_fields
        }
        updates["sector_baseline_scores"] = baseline
        updates.update(baseline)
        # Ajuste limitado sobre scores fundamentados; nunca pontua uma
        # categoria originalmente ausente.
        changed = {}
        for category, values in deltas.items():
            original = baseline.get(category, getattr(snap, category))
            if original is None:
                continue
            extra = sum(values, Decimal("0")) / len(values)
            changed[category] = max(Decimal("0"), min(Decimal("100"), original + extra)).quantize(CENT)
        updates.update(changed)
        computed = [updates.get(field, getattr(snap, field)) for field in score_fields]
        available_scores = [value for value in computed if value is not None]
        if len(available_scores) >= 2:
            updates["overall_score"] = (
                sum(available_scores, Decimal("0")) / len(available_scores)
            ).quantize(CENT)
        overall = updates.get("overall_score", snap.overall_score)
        # Somente a avaliação relativa com margem >= 20% pode liberar uma
        # análise de compra; preço elevado nunca recebe recomendação de compra.
        if snap.confidence == ConfidenceLevel.INSUFFICIENT:
            action = RecommendationAction.INSUFFICIENT_DATA
        elif snap.data_quality and snap.data_quality.recommendation_blocked:
            action = RecommendationAction.REVIEW_DATA
        elif snap.strategy_fit_score is not None and snap.strategy_fit_score < 40:
            action = RecommendationAction.WAIT
        elif valuation.status == ValuationStatus.ELEVATED:
            action = RecommendationAction.WAIT
        elif valuation.status == ValuationStatus.ATTRACTIVE and overall is not None and overall >= 75:
            action = RecommendationAction.ANALYZE_TO_BUY
        elif valuation.status != ValuationStatus.INSUFFICIENT_DATA and overall is not None and overall >= 60:
            action = RecommendationAction.HOLD
        else:
            action = RecommendationAction.REVIEW_DATA
        updates["recommendation"] = action
        if valuation.status == ValuationStatus.INSUFFICIENT_DATA:
            updates["warning_reasons"] = [
                *snap.warning_reasons,
                valuation.peer_comparison or "Sem pares setoriais confiáveis.",
            ]
        result[snap.symbol] = snap.model_copy(update=updates)
    return result
