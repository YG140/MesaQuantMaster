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
from app.services.portfolio_service import PortfolioService


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
    ):
        self.market_service = market_service
        self.asset_repository = asset_repository
        self.portfolio_service = portfolio_service
        self.policy_repository = policy_repository
        self.normalizer = normalizer or IndicatorNormalizationService()
        self.validator = validator or IndicatorValidationService()
        self.snapshot_repository = snapshot_repository

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
                )
            )

        return BatchAssetAnalysisResponse(
            snapshots=snapshots,
            errors=errors,
            provider_calls=1 if symbols else 0,
            calculated_at=now,
        )

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
        inferred_asset_class = infer_class_from_symbol(symbol, asset_type)
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
        provider_payloads = self._load_detailed_payloads(symbol, asset_class)
        if provider_payloads:
            indicators = self.normalizer.merge_provider_payloads(
                indicators, provider_payloads, collected_at=collected_at
            )
        indicators, data_quality = self.validator.validate(
            indicators,
            sector=(
                local_asset.sector
                if local_asset is not None
                else getattr(quote, "sector", None)
            ),
            collected_at=collected_at,
        )
        strategy_fit_score = strategy_fit(
            asset_class=asset_class,
            current_weight=position.allocation if position else None,
            policy=policy,
        )
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
            calculated_at=collected_at,
        )
        snapshot = engine_for_class(asset_class).build_snapshot(base)
        if self.snapshot_repository is not None:
            self.snapshot_repository.save(
                snapshot.symbol, snapshot.asset_class.value, snapshot.indicators
            )
        return snapshot

    def _load_detailed_payloads(
        self, symbol: str, asset_class: InvestmentClass
    ) -> list[dict]:
        payloads = []
        datasets = (
            ["indicators", "properties", "portfolio", "reports", "dividends"]
            if asset_class == InvestmentClass.FII
            else [
                "statistics",
                "financial_data",
                "balance_sheet",
                "income_statement",
                "cash_flow",
                "dividends",
            ]
        )
        for dataset in datasets:
            try:
                if asset_class == InvestmentClass.FII:
                    payloads.append(
                        self.market_service.get_fii_dataset(dataset, [symbol])
                    )
                else:
                    period = (
                        "annual"
                        if dataset in {"balance_sheet", "income_statement", "cash_flow"}
                        else None
                    )
                    payloads.append(
                        self.market_service.get_stock_dataset(
                            dataset, [symbol], mode="current", period=period
                        )
                    )
            except Exception:
                continue
        return payloads

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


def infer_class_from_symbol(symbol: str, asset_type: str | None) -> InvestmentClass:
    normalized_symbol = symbol.upper().strip()
    if normalized_symbol in KNOWN_B3_ETFS:
        return InvestmentClass.ETF
    classified = classify_market_asset(asset_type)
    if normalized_symbol.endswith("11") and classified in {
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
