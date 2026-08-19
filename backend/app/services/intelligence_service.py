from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import settings
from app.engines.intelligence_engine import (
    PortfolioBuilderEngine,
    PortfolioIntelligenceEngine,
)
from app.engines.smart_portfolio_engine import PortfolioCandidate, SmartPortfolioEngine
from app.models.portfolio_policy import PortfolioPolicy, PortfolioPolicyAllocation
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.repositories.asset_repository import AssetRepository
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    PortfolioIntelligenceResponse,
    PortfolioPolicyAllocationRead,
    PortfolioPolicyRead,
    PortfolioPolicyUpsert,
)
from app.services.portfolio_service import PortfolioService
from app.services.market_intelligence_service import MarketIntelligenceService
from app.schemas.market_intelligence import AnalyzeAssetsRequest


# Espelha AnalyzeAssetsRequest.symbols (max_length=50 em
# app/schemas/market_intelligence.py) — o limite real de símbolos aceitos
# por chamada ao analisador/resolver. Não é um número mágico independente:
# se o schema mudar, os lotes passam a violar essa constante nos testes.
MAX_SYMBOLS_PER_ANALYSIS_BATCH = 50


class PortfolioIntelligenceService:
    def __init__(
        self,
        portfolio_service: PortfolioService,
        policy_repository: PortfolioPolicyRepository,
        asset_repository: AssetRepository | None = None,
        market_intelligence_service: MarketIntelligenceService | None = None,
    ):
        self.portfolio_service = portfolio_service
        self.policy_repository = policy_repository
        self.asset_repository = asset_repository
        self.market_intelligence_service = market_intelligence_service

    def get_policy(self, user_id) -> PortfolioPolicyRead | None:
        policy = self.policy_repository.get_by_user(user_id)
        return self._policy_to_schema(policy) if policy is not None else None

    def save_policy(self, user_id, data: PortfolioPolicyUpsert) -> PortfolioPolicyRead:
        now = datetime.now(timezone.utc)
        policy = self.policy_repository.get_by_user(user_id)
        if policy is None:
            policy = PortfolioPolicy(
                user_id=user_id,
                created_at=now,
                updated_at=now,
                name=data.name,
                objective=data.objective,
                risk_profile=data.risk_profile,
                investment_horizon=data.investment_horizon,
                monthly_contribution=data.monthly_contribution,
                liquidity_need=data.liquidity_need,
                income_need=data.income_need,
                emergency_reserve_months=data.emergency_reserve_months,
                maximum_weight_per_asset=data.maximum_weight_per_asset,
                maximum_weight_per_sector=data.maximum_weight_per_sector,
                maximum_weight_per_issuer=data.maximum_weight_per_issuer,
                rebalance_tolerance=data.rebalance_tolerance,
            )
            policy = self.policy_repository.save(policy)
        else:
            policy.name = data.name
            policy.objective = data.objective
            policy.risk_profile = data.risk_profile
            policy.investment_horizon = data.investment_horizon
            policy.monthly_contribution = data.monthly_contribution
            policy.liquidity_need = data.liquidity_need
            policy.income_need = data.income_need
            policy.emergency_reserve_months = data.emergency_reserve_months
            policy.maximum_weight_per_asset = data.maximum_weight_per_asset
            policy.maximum_weight_per_sector = data.maximum_weight_per_sector
            policy.maximum_weight_per_issuer = data.maximum_weight_per_issuer
            policy.rebalance_tolerance = data.rebalance_tolerance
            policy.updated_at = now

        allocations = [
            PortfolioPolicyAllocation(
                asset_class=item.asset_class,
                target_percentage=item.target_percentage,
                minimum_percentage=item.minimum_percentage,
                maximum_percentage=item.maximum_percentage,
                enabled=item.enabled,
            )
            for item in data.allocations
        ]
        saved = self.policy_repository.replace_allocations(policy, allocations)
        return self._policy_to_schema(saved)

    def get_portfolio_intelligence(self, user_id) -> PortfolioIntelligenceResponse:
        portfolio = self.portfolio_service.calculate(user_id)
        policy = self.get_policy(user_id)
        return PortfolioIntelligenceEngine.build(portfolio, policy)

    def build_portfolio(
        self, user_id, data: BuildPortfolioRequest
    ) -> BuildPortfolioResponse:
        # user_id vem exclusivamente do usuário autenticado (ver
        # app/api/intelligence.py, current_user.id) -- nunca do corpo da
        # requisição. Uma PortfolioPolicy persistida (via onboarding do
        # Perfil do Investidor OU via PUT/POST /policy diretos -- ambos
        # igualmente autoritativos; o modelo não persiste campo de
        # provenance, então não há como distinguir a origem) passa a ser
        # a fonte estratégica de verdade
        # de build_portfolio() (ver SmartPortfolioEngine.build/
        # PortfolioStrategy). Ausência de política preserva o
        # comportamento legado integralmente (policy=None) -- inclusive
        # quando policy_repository não foi injetado (mesmo padrão
        # defensivo já usado para asset_repository/
        # market_intelligence_service abaixo).
        policy = self.get_policy(user_id) if self.policy_repository is not None else None
        if self.asset_repository is None or self.market_intelligence_service is None:
            return SmartPortfolioEngine.build(data, [], policy=policy)

        # Ordenamos explicitamente por ticker (chave estável) em vez de
        # confiar na ordem implícita do repositório, para que o universo e o
        # resultado sejam sempre reproduzíveis. Deduplicamos por ticker e
        # filtramos inativos na mesma passagem.
        seen_tickers: set[str] = set()
        active_assets = []
        for item in sorted(self.asset_repository.list(), key=lambda asset: asset.ticker):
            if not item.is_active:
                continue
            ticker = item.ticker.upper()
            if ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)
            active_assets.append(item)

        universe_total = len(active_assets)
        universe_max = settings.PORTFOLIO_UNIVERSE_MAX_ASSETS
        universe_truncated = universe_total > universe_max
        considered_assets = (
            active_assets[:universe_max] if universe_truncated else active_assets
        )
        universe_considered = len(considered_assets)

        if not considered_assets:
            legacy = PortfolioBuilderEngine.build(data, policy)
            return legacy.model_copy(
                update={
                    "unallocated_amount": data.available_amount.quantize(
                        Decimal("0.01")
                    ),
                    "missing_data": [
                        "Nenhum ativo cadastrado está disponível para análise."
                    ],
                    "strategy_summary": (
                        "Metas por classe exibidas; seleção indisponível por ausência de ativos."
                    ),
                }
            )

        # Universo processado em lotes determinísticos (mesma ordem por
        # ticker), nunca truncado silenciosamente acima de universe_max.
        batches = [
            considered_assets[index : index + MAX_SYMBOLS_PER_ANALYSIS_BATCH]
            for index in range(0, universe_considered, MAX_SYMBOLS_PER_ANALYSIS_BATCH)
        ]

        snapshots = []
        errors = []
        for batch in batches:
            result = self.market_intelligence_service.analyze_assets(
                AnalyzeAssetsRequest(symbols=[item.ticker for item in batch]),
                user_id=user_id,
            )
            snapshots.extend(result.snapshots)
            errors.extend(result.errors)

        assets_by_symbol = {item.ticker.upper(): item for item in considered_assets}
        candidates = []
        for snapshot in snapshots:
            asset = assets_by_symbol.get(snapshot.symbol.upper())
            candidates.append(
                PortfolioCandidate(
                    snapshot=snapshot,
                    sector=asset.sector if asset else None,
                    issuer=asset.name if asset else snapshot.name,
                )
            )
        return SmartPortfolioEngine.build(
            data,
            candidates,
            policy=policy,
            provider_errors=[item.message for item in errors],
            universe_total=universe_total,
            universe_considered=universe_considered,
            universe_truncated=universe_truncated,
            batch_size=MAX_SYMBOLS_PER_ANALYSIS_BATCH,
            batch_count=len(batches),
        )

    @staticmethod
    def _policy_to_schema(policy: PortfolioPolicy) -> PortfolioPolicyRead:
        return PortfolioPolicyRead(
            id=policy.id,
            user_id=policy.user_id,
            name=policy.name,
            objective=policy.objective,
            risk_profile=policy.risk_profile,
            investment_horizon=policy.investment_horizon,
            monthly_contribution=policy.monthly_contribution,
            liquidity_need=policy.liquidity_need,
            income_need=policy.income_need,
            emergency_reserve_months=policy.emergency_reserve_months,
            maximum_weight_per_asset=policy.maximum_weight_per_asset,
            maximum_weight_per_sector=policy.maximum_weight_per_sector,
            maximum_weight_per_issuer=policy.maximum_weight_per_issuer,
            rebalance_tolerance=policy.rebalance_tolerance,
            allocations=[
                PortfolioPolicyAllocationRead(
                    id=allocation.id,
                    asset_class=allocation.asset_class,
                    target_percentage=allocation.target_percentage,
                    minimum_percentage=allocation.minimum_percentage,
                    maximum_percentage=allocation.maximum_percentage,
                    enabled=allocation.enabled,
                )
                for allocation in policy.allocations
            ],
            created_at=policy.created_at,
            updated_at=policy.updated_at,
        )
