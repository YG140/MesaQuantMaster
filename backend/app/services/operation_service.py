from __future__ import annotations

from uuid import UUID

from app.models.operation import Operation
from app.models.user import User
from app.repositories.asset_repository import AssetRepository
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.operation_repository import OperationRepository
from app.schemas.operation import OperationCreate, OperationUpdate


class OperationService:
    def __init__(
        self,
        operation_repository: OperationRepository,
        asset_repository: AssetRepository,
        brokerage_repository: BrokerageRepository | None = None,
    ):
        self.operation_repository = operation_repository
        self.asset_repository = asset_repository
        self.brokerage_repository = brokerage_repository

    def create(
        self,
        user: User,
        data: OperationCreate,
    ) -> Operation:

        asset = self.asset_repository.get_by_id(data.asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        if data.brokerage_id is not None and self.brokerage_repository is not None:
            brokerage = self.brokerage_repository.get_by_id(data.brokerage_id)
            if brokerage is None or brokerage.user_id != user.id:
                raise ValueError("Corretora nao encontrada.")

        operation = Operation(
            user_id=user.id,
            asset_id=data.asset_id,
            brokerage_id=data.brokerage_id,
            operation_type=data.operation_type.upper().strip(),
            operation_date=data.operation_date,
            quantity=data.quantity,
            unit_price=data.unit_price,
            fees=data.fees,
            taxes=data.taxes,
            notes=data.notes,
            source=data.source,
        )

        return self.operation_repository.create(operation)

    def get_by_id(
        self,
        operation_id: UUID,
    ) -> Operation:

        operation = self.operation_repository.get_by_id(operation_id)

        if operation is None:
            raise ValueError("Operação não encontrada.")

        return operation

    def list(self) -> list[Operation]:
        return self.operation_repository.list()

    def list_by_user(
        self,
        user_id: UUID,
    ) -> list[Operation]:
        return self.operation_repository.list_by_user(user_id)

    def update(
        self,
        operation_id: UUID,
        data: OperationUpdate,
    ) -> Operation:

        operation = self.operation_repository.get_by_id(operation_id)

        if operation is None:
            raise ValueError("Operação não encontrada.")

        if data.operation_type is not None:
            operation.operation_type = data.operation_type.upper().strip()

        if data.operation_date is not None:
            operation.operation_date = data.operation_date

        if data.quantity is not None:
            operation.quantity = data.quantity

        if data.unit_price is not None:
            operation.unit_price = data.unit_price

        if data.fees is not None:
            operation.fees = data.fees

        if data.taxes is not None:
            operation.taxes = data.taxes

        if data.notes is not None:
            operation.notes = data.notes

        if data.source is not None:
            operation.source = data.source

        return self.operation_repository.update(operation)

    def delete(
        self,
        operation_id: UUID,
    ) -> None:

        operation = self.operation_repository.get_by_id(operation_id)

        if operation is None:
            raise ValueError("Operação não encontrada.")

        self.operation_repository.delete(operation)
