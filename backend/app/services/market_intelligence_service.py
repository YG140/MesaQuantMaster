from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.engines.market_intelligence_engine import (
    AssetAnalysisEngine,
    EtfAnalysisEngine,
    FiiAnalysisEngine,
    StockAnalysisEngine,
    TreasuryAnalysisEngine,
)
from app.models.asset import Asset
from app.repositories.asset_repository import AssetRepository
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.schemas.market import QuoteResponse
from app.schemas.market_intelligence import (
    AnalyzeAssetsRequest,
    AssetAnalysisError,
    AssetIntelligenceHistoryResponse,
    AssetIntelligenceSnapshot,
    BatchAssetAnalysisResponse,
    ConfidenceLevel,
    IndicatorStatus,
    InvestmentClass,
    RecommendationAction,
    ValuationAssessment,
    ValuationStatus,
)
from app.schemas.portfolio import PortfolioPosition
from app.services.indicator_normalization_service import (
    IndicatorNormalizationService,
    classify_market_asset,
)
from app.services.indicator_validation_service import IndicatorValidationService
from app.services.market_service import MarketService
from app.services.indicator_resolver_service import (
    IndicatorResolverService,
    build_resolution_summary,
)
from app.engines.sector_relative_valuation import PeerAsset, enrich_sector_valuations
from app.services.portfolio_service import PortfolioService
from app.services.symbol_identity import market_context_of, resolve_symbol_identity


class MarketIntelligenceService:
    def __init__(
        self,
        *,
        market_service: MarketService,
        asset_repository: AssetRepository,
        portfolio_service: PortfolioService,
        policy_repository: PortfolioPolicyRepository,
        normalizer: IndicatorNormalizationService | None = None,
        validator: IndicatorValidationService | None = None,
        snapshot_repository=None,
        manual_repository=None,
        cvm_repository=None,
        cvm_fii_repository=None,
        resolver: IndicatorResolverService | None = None,
    ):
        self.market_service = market_service
        self.asset_repository = asset_repository
        self.portfolio_service = portfolio_service
        self.policy_repository = policy_repository
        self.normalizer = normalizer or IndicatorNormalizationService()
        self.validator = validator or IndicatorValidationService()
        self.resolver = resolver or IndicatorResolverService(
            market_service=market_service,
            normalizer=self.normalizer,
            snapshot_repository=snapshot_repository,
            manual_repository=manual_repository,
            cvm_repository=cvm_repository,
            cvm_fii_repository=cvm_fii_repository,
        )

    def analyze_asset(self, symbol: str, user_id) -> AssetIntelligenceSnapshot:
        response = self.analyze_assets(
            AnalyzeAssetsRequest(symbols=[symbol]),
            user_id=user_id,
        )
        if response.snapshots:
            return response.snapshots[0]
        return self._missing_snapshot(
            symbol, response.errors[0].message if response.errors else None
        )

    def analyze_assets(
        self,
        data: AnalyzeAssetsRequest,
        user_id,
    ) -> BatchAssetAnalysisResponse:
        now = datetime.now(timezone.utc)
        symbols = normalize_symbols(data.symbols)
        provider_error: str | None = None
        try:
            quotes_response = self.market_service.get_quotes(symbols)
            quotes_by_symbol = {
                (quote.requested_symbol or quote.ticker).upper(): quote
                for quote in quotes_response.quotes
            }
        except Exception as exc:
            provider_error = str(exc) or "Provider de mercado indisponível."
            quotes_by_symbol = {}
        local_assets = {
            symbol: self.asset_repository.get_by_ticker(symbol) for symbol in symbols
        }
        portfolio = self.portfolio_service.calculate(user_id)
        positions = {
            position.ticker.upper(): position for position in portfolio.positions
        }
        policy = self.policy_repository.get_by_user(user_id)

        snapshots = []
        errors = []
        for symbol in symbols:
            quote = quotes_by_symbol.get(symbol)
            if quote is None:
                errors.append(
                    AssetAnalysisError(
                        symbol=symbol,
                        message=provider_error
                        or "Cotação indisponível no provedor atual.",
                    )
                )
            snapshots.append(
                self._snapshot_for_symbol(
                    symbol=symbol,
                    quote=quote,
                    local_asset=local_assets.get(symbol),
                    position=positions.get(symbol),
                    policy=policy,
                    collected_at=now,
                    user_id=user_id,
                )
            )

        # Só compara com papéis realmente analisados neste lote. A análise
        # isolada não recebe benchmarks setoriais presumidos.
        peers = []
        for snap in snapshots:
            local = local_assets.get(snap.symbol)
            quote = quotes_by_symbol.get(snap.symbol)
            sector_indicator = next(
                (item for item in snap.indicators
                 if item.key == "sector" and item.status == IndicatorStatus.AVAILABLE),
                None,
            )
            peers.append(PeerAsset(
                snapshot=snap,
                sector=(
                    getattr(local, "sector", None)
                    or getattr(quote, "sector", None)
                    or (str(sector_indicator.value) if sector_indicator else None)
                ),
            ))
        enriched = enrich_sector_valuations(peers)
        return BatchAssetAnalysisResponse(
            snapshots=[enriched.get(snap.symbol, snap) for snap in snapshots],
            errors=errors,
            provider_calls=1 if symbols else 0,
            calculated_at=now,
        )

    def _market_context(self) -> str | None:
        return market_context_of(getattr(self.market_service, "provider", None))

    def indicators_for_asset(self, symbol: str, user_id) -> list:
        return self.analyze_asset(symbol, user_id).indicators

    def history_for_asset(self, symbol: str) -> AssetIntelligenceHistoryResponse:
        return AssetIntelligenceHistoryResponse(
            symbol=symbol.upper().strip(),
            snapshots=[],
            message="Histórico de inteligência ainda não é persistido nesta etapa.",
        )

    def portfolio_recommendations(self, user_id) -> BatchAssetAnalysisResponse:
        portfolio = self.portfolio_service.calculate(user_id)
        symbols = [position.ticker for position in portfolio.positions]
        if not symbols:
            return BatchAssetAnalysisResponse(
                snapshots=[],
                errors=[],
                provider_calls=0,
                calculated_at=datetime.now(timezone.utc),
            )
        return self.analyze_assets(AnalyzeAssetsRequest(symbols=symbols), user_id)

    def _snapshot_for_symbol(
        self,
        *,
        symbol: str,
        quote: QuoteResponse | None,
        local_asset: Asset | None,
        position: PortfolioPosition | None,
        policy,
        collected_at: datetime,
        user_id=None,
    ) -> AssetIntelligenceSnapshot:
        asset_type = (
            local_asset.asset_type
            if local_asset is not None
            else getattr(quote, "asset_type", None)
        )
        asset_class, indicators = self.normalizer.normalize_quote(
            quote,
            requested_symbol=symbol,
            asset_type=asset_type,
            collected_at=collected_at,
        )
        inferred_asset_class = infer_class_from_symbol(
            symbol, asset_type, market=self._market_context()
        )
        if (
            asset_class == InvestmentClass.UNKNOWN
            or inferred_asset_class != asset_class
        ):
            asset_class = inferred_asset_class
            asset_class, indicators = self.normalizer.normalize_quote(
                quote,
                requested_symbol=symbol,
                asset_type=asset_class.value,
                collected_at=collected_at,
            )
        indicators = self.resolver.resolve_asset(
            symbol=symbol,
            asset_class=asset_class,
            asset_id=local_asset.id if local_asset is not None else None,
            user_id=user_id,
            baseline=indicators,
            collected_at=collected_at,
        )
        segment_indicator = next(
            (item for item in indicators if item.key == "segment"), None
        )
        indicators, data_quality = self.validator.validate(
            indicators,
            sector=(
                local_asset.sector
                if local_asset is not None
                else getattr(quote, "sector", None)
            ),
            segment=(
                segment_indicator.value
                if segment_indicator is not None
                and segment_indicator.status == IndicatorStatus.AVAILABLE
                else None
            ),
            collected_at=collected_at,
        )
        strategy_fit_score = strategy_fit(
            asset_class=asset_class,
            current_weight=position.allocation if position else None,
            policy=policy,
        )
        resolution_summary = build_resolution_summary(indicators)
        base = AssetIntelligenceSnapshot(
            asset_id=local_asset.id if local_asset is not None else None,
            symbol=(quote.ticker if quote else symbol).upper(),
            name=(
                local_asset.name
                if local_asset is not None
                else getattr(quote, "name", None)
            ),
            asset_class=asset_class,
            current_price=(
                (quote.current_price or quote.price) if quote is not None else None
            ),
            currency=getattr(quote, "currency", None) if quote is not None else None,
            market_updated_at=(
                quote.market_time or quote.updated_at or quote.last_updated
                if quote is not None
                else None
            ),
            indicators=indicators,
            data_quality_score=data_quality.data_quality_score,
            data_quality=data_quality,
            non_applicable_indicators_count=len(data_quality.non_applicable_indicators),
            anomaly_flags=data_quality.anomaly_flags,
            strategy_fit_score=strategy_fit_score,
            recommendation=RecommendationAction.INSUFFICIENT_DATA,
            valuation_status=ValuationStatus.INSUFFICIENT_DATA,
            valuation=ValuationAssessment(
                status=ValuationStatus.INSUFFICIENT_DATA,
                confidence=ConfidenceLevel.INSUFFICIENT,
            ),
            confidence=ConfidenceLevel.INSUFFICIENT,
            coverage_percentage=Decimal("0"),
            available_indicators_count=0,
            missing_indicators_count=0,
            stale_indicators_count=0,
            resolution_summary=resolution_summary,
            calculated_at=collected_at,
        )
        snapshot = engine_for_class(asset_class).build_snapshot(base)
        return snapshot

    def _missing_snapshot(
        self,
        symbol: str,
        message: str | None,
    ) -> AssetIntelligenceSnapshot:
        now = datetime.now(timezone.utc)
        return AssetIntelligenceSnapshot(
            symbol=symbol.upper().strip(),
            asset_class=InvestmentClass.UNKNOWN,
            indicators=[],
            recommendation=RecommendationAction.INSUFFICIENT_DATA,
            valuation_status=ValuationStatus.INSUFFICIENT_DATA,
            valuation=ValuationAssessment(
                status=ValuationStatus.INSUFFICIENT_DATA,
                missing_indicators=[],
                confidence=ConfidenceLevel.INSUFFICIENT,
            ),
            confidence=ConfidenceLevel.INSUFFICIENT,
            coverage_percentage=Decimal("0"),
            available_indicators_count=0,
            missing_indicators_count=0,
            stale_indicators_count=0,
            warning_reasons=[
                message
                or "Não existem dados suficientes para uma análise confiável deste investimento."
            ],
            calculated_at=now,
        )


def engine_for_class(asset_class: InvestmentClass) -> type[AssetAnalysisEngine]:
    return {
        InvestmentClass.STOCK: StockAnalysisEngine,
        InvestmentClass.FII: FiiAnalysisEngine,
        InvestmentClass.ETF: EtfAnalysisEngine,
        InvestmentClass.TREASURY: TreasuryAnalysisEngine,
    }.get(asset_class, AssetAnalysisEngine)


def normalize_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for symbol in symbols:
        item = symbol.upper().strip()
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def infer_class_from_symbol(
    symbol: str, asset_type: str | None, *, market: str | None = None
) -> InvestmentClass:
    # Classifica pela identidade ECONÔMICA (canonical_symbol), nunca pelo
    # símbolo de negociação bruto: um FII/ETF fracionário B3 (ex.:
    # hipotético "MXRF11F") preserva a classe FII do seu lote padrão
    # "MXRF11" -- o sufixo "F" do mercado fracionário nunca deve mascarar
    # o "11" que identifica a classe.
    #
    # `market` NUNCA tem default implícito para B3 -- é responsabilidade
    # exclusiva do chamador (ver MarketIntelligenceService._market_context,
    # que deriva do provider realmente em uso) provar que o contexto é B3
    # antes que qualquer canonicalização do fracionário seja tentada. Sem
    # esse contexto (`market=None` ou qualquer outro mercado), a regra do
    # fracionário nunca se aplica e canonical_symbol == símbolo
    # normalizado -- comportamento idêntico ao de antes desta correção
    # existir, sem regressão para nenhum ticker de produção hoje.
    canonical_symbol = resolve_symbol_identity(symbol, market=market).canonical_symbol
    if canonical_symbol in KNOWN_B3_ETFS:
        return InvestmentClass.ETF
    classified = classify_market_asset(asset_type)
    if canonical_symbol.endswith("11") and classified in {
        InvestmentClass.UNKNOWN,
        InvestmentClass.INVESTMENT_FUND,
    }:
        return InvestmentClass.FII
    if classified != InvestmentClass.UNKNOWN:
        return classified
    return InvestmentClass.STOCK


KNOWN_B3_ETFS = {
    "BOVA11",
    "IVVB11",
    "SMAL11",
    "DIVO11",
    "HASH11",
    "XINA11",
    "GOLD11",
    "NASD11",
    "SPXI11",
    "BOVV11",
    "MATB11",
    "PIBB11",
    "ECOO11",
}


def strategy_fit(
    *,
    asset_class: InvestmentClass,
    current_weight: Decimal | None,
    policy,
) -> Decimal | None:
    if policy is None:
        return None
    policy_class = {
        InvestmentClass.STOCK: "Ações",
        InvestmentClass.FII: "FIIs",
        InvestmentClass.ETF: "ETFs",
        InvestmentClass.BDR: "BDRs",
        InvestmentClass.INTERNATIONAL: "Ativos internacionais",
        InvestmentClass.CRYPTO: "Criptomoedas",
        InvestmentClass.TREASURY: "Tesouro Direto",
    }.get(asset_class)
    if policy_class is None:
        return None
    allocation = next(
        (
            item
            for item in policy.allocations
            if item.enabled and item.asset_class == policy_class
        ),
        None,
    )
    if allocation is None:
        return Decimal("20")
    if current_weight is None:
        return Decimal("70")
    if current_weight > allocation.maximum_percentage:
        return Decimal("25")
    if current_weight < allocation.minimum_percentage:
        return Decimal("75")
    return Decimal("90")
