from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.investor_profile import InvestorProfile


class InvestorProfileRepository:
    """Espelha o padrão de PortfolioPolicyRepository: commit por chamada,
    isolamento estrito por user_id, nenhum ID controlável pelo cliente."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_user(self, user_id: UUID) -> InvestorProfile | None:
        return (
            self.db.query(InvestorProfile)
            .filter(InvestorProfile.user_id == user_id)
            .first()
        )

    def save(self, profile: InvestorProfile) -> InvestorProfile:
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile
