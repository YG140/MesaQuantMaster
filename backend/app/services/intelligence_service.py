from __future__ import annotations

from datetime import datetime, timezone

from app.engines.intelligence_engine import (
    PortfolioBuilderEngine,
    PortfolioIntelligenceEngine,
)
from app.models.portfolio_policy import PortfolioPolicy, PortfolioPolicyAllocation
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    PortfolioIntelligenceResponse,
    PortfolioPolicyAllocationRead,
    PortfolioPolicyRead,
    PortfolioPolicyUpsert,
)
from app.services.portfolio_service import PortfolioService


class PortfolioIntelligenceService:
    def __init__(
        self,
        portfolio_service: PortfolioService,
        policy_repository: PortfolioPolicyRepository,
    ):
        self.portfolio_service = portfolio_service
        self.policy_repository = policy_repository

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
        policy = self.get_policy(user_id)
        return PortfolioBuilderEngine.build(data, policy)

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
