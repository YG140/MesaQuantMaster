from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from app.models.portfolio_policy import PortfolioPolicy, PortfolioPolicyAllocation


class PortfolioPolicyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user(self, user_id: UUID) -> PortfolioPolicy | None:
        return (
            self.db.query(PortfolioPolicy)
            .options(selectinload(PortfolioPolicy.allocations))
            .filter(PortfolioPolicy.user_id == user_id)
            .first()
        )

    def save(self, policy: PortfolioPolicy) -> PortfolioPolicy:
        self.db.add(policy)
        self.db.commit()
        self.db.refresh(policy)
        return self.get_by_user(policy.user_id) or policy

    def replace_allocations(
        self,
        policy: PortfolioPolicy,
        allocations: list[PortfolioPolicyAllocation],
    ) -> PortfolioPolicy:
        policy.allocations.clear()
        self.db.flush()
        policy.allocations.extend(allocations)
        self.db.commit()
        self.db.refresh(policy)
        return self.get_by_user(policy.user_id) or policy
