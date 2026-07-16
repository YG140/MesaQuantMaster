from __future__ import annotations

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.brokerage import Brokerage


class BrokerageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, brokerage: Brokerage) -> Brokerage:
        self.db.add(brokerage)
        self.db.commit()
        self.db.refresh(brokerage)
        return brokerage

    def get_by_id(self, brokerage_id: UUID) -> Brokerage | None:
        return self.db.query(Brokerage).filter(Brokerage.id == brokerage_id).first()

    def get_by_user_and_name(self, user_id: UUID, name: str) -> Brokerage | None:
        normalized = name.strip().lower()
        return (
            self.db.query(Brokerage)
            .filter(Brokerage.user_id == user_id)
            .filter(func.lower(Brokerage.name) == normalized)
            .first()
        )

    def list_by_user(self, user_id: UUID) -> list[Brokerage]:
        return (
            self.db.query(Brokerage)
            .filter(Brokerage.user_id == user_id)
            .order_by(Brokerage.name.asc())
            .all()
        )
