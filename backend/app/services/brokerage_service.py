from __future__ import annotations

from uuid import UUID

from app.models.brokerage import Brokerage
from app.repositories.brokerage_repository import BrokerageRepository


class BrokerageService:
    def __init__(self, repository: BrokerageRepository):
        self.repository = repository

    def create(self, user_id: UUID, name: str) -> Brokerage:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Informe o nome da corretora.")

        existing = self.repository.get_by_user_and_name(user_id, normalized_name)
        if existing is not None:
            raise ValueError("Corretora ja cadastrada.")

        return self.repository.create(
            Brokerage(
                user_id=user_id,
                name=normalized_name,
            )
        )

    def list_by_user(self, user_id: UUID) -> list[Brokerage]:
        return self.repository.list_by_user(user_id)

    def get_owned(self, user_id: UUID, brokerage_id: UUID) -> Brokerage:
        brokerage = self.repository.get_by_id(brokerage_id)
        if brokerage is None or brokerage.user_id != user_id:
            raise ValueError("Corretora nao encontrada.")
        return brokerage
