from __future__ import annotations

from uuid import UUID

from app.models.alert import Alert
from app.models.user import User

from app.repositories.alert_repository import AlertRepository
from app.repositories.asset_repository import AssetRepository

from app.schemas.alert import (
    AlertCreate,
    AlertUpdate,
)


class AlertService:

    def __init__(
        self,
        repository: AlertRepository,
        asset_repository: AssetRepository,
    ):
        self.repository = repository
        self.asset_repository = asset_repository

    def create(
        self,
        user: User,
        data: AlertCreate,
    ) -> Alert:

        asset = self.asset_repository.get_by_id(data.asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        alert = Alert(
            user_id=user.id,
            asset_id=data.asset_id,
            alert_type=data.alert_type.upper().strip(),
            target_value=data.target_value,
        )

        return self.repository.create(alert)

    def list(
        self,
        user: User,
    ) -> list[Alert]:

        return self.repository.list_by_user(user.id)

    def get_by_id(
        self,
        alert_id: UUID,
    ) -> Alert:

        alert = self.repository.get_by_id(alert_id)

        if alert is None:
            raise ValueError("Alerta não encontrado.")

        return alert

    def update(
        self,
        alert_id: UUID,
        data: AlertUpdate,
    ) -> Alert:

        alert = self.get_by_id(alert_id)

        if data.alert_type is not None:
            alert.alert_type = data.alert_type.upper().strip()

        if data.target_value is not None:
            alert.target_value = data.target_value

        if data.is_active is not None:
            alert.is_active = data.is_active

        return self.repository.update(alert)

    def delete(
        self,
        alert_id: UUID,
    ) -> None:

        alert = self.get_by_id(alert_id)

        self.repository.delete(alert)
