from __future__ import annotations

from uuid import UUID

from app.engines.portfolio_engine import PortfolioEngine
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

    def create(self, user: User, data: OperationCreate) -> Operation:
        if self.asset_repository.get_by_id(data.asset_id) is None:
            raise ValueError("Ativo não encontrado.")
        self._ensure_brokerage(user.id, data.brokerage_id)
        operation = Operation(user_id=user.id, **data.model_dump())
        operation.operation_type = operation.operation_type.upper().strip()
        self._validate_operation(operation)
        try:
            self.operation_repository.db.add(operation)
            self.operation_repository.db.flush()
            self._validate_asset_history(user.id, data.asset_id)
            self.operation_repository.db.commit()
            self.operation_repository.db.refresh(operation)
            return operation
        except Exception:
            self.operation_repository.db.rollback()
            raise

    def get_by_id(self, operation_id: UUID) -> Operation:
        operation = self.operation_repository.get_by_id(operation_id)
        if operation is None:
            raise ValueError("Operação não encontrada.")
        return operation

    def list(self) -> list[Operation]:
        return self.operation_repository.list()

    def list_by_user(self, user_id: UUID) -> list[Operation]:
        return self.operation_repository.list_by_user(user_id)

    def list_position_operations(
        self, user_id: UUID, asset_id: UUID
    ) -> list[Operation]:
        if self.asset_repository.get_by_id(asset_id) is None:
            raise ValueError("Ativo não encontrado.")
        return self.operation_repository.list_by_user_and_asset(user_id, asset_id)

    def update(
        self, operation_id: UUID, data: OperationUpdate, user_id: UUID | None = None
    ) -> Operation:
        operation = self.get_by_id(operation_id)
        if user_id is not None and operation.user_id != user_id:
            raise ValueError("Operação não encontrada.")
        if data.brokerage_id is not None:
            self._ensure_brokerage(operation.user_id, data.brokerage_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "operation_type" and value is not None:
                value = value.upper().strip()
            setattr(operation, field, value)
        self._validate_operation(operation)
        try:
            self.operation_repository.db.flush()
            self._validate_asset_history(operation.user_id, operation.asset_id)
            self.operation_repository.db.commit()
            self.operation_repository.db.refresh(operation)
            return operation
        except Exception:
            self.operation_repository.db.rollback()
            raise

    def delete(self, operation_id: UUID, user_id: UUID | None = None) -> None:
        operation = self.get_by_id(operation_id)
        if user_id is not None and operation.user_id != user_id:
            raise ValueError("Operação não encontrada.")
        owner_id, asset_id = operation.user_id, operation.asset_id
        try:
            self.operation_repository.db.delete(operation)
            self.operation_repository.db.flush()
            self._validate_asset_history(owner_id, asset_id)
            self.operation_repository.db.commit()
        except Exception:
            self.operation_repository.db.rollback()
            raise

    def _ensure_brokerage(self, user_id: UUID, brokerage_id: UUID | None) -> None:
        if brokerage_id is None or self.brokerage_repository is None:
            return
        brokerage = self.brokerage_repository.get_by_id(brokerage_id)
        if brokerage is None or brokerage.user_id != user_id:
            raise ValueError("Corretora não encontrada para este usuário.")

    @staticmethod
    def _validate_operation(operation: Operation) -> None:
        if operation.operation_type not in {"BUY", "SELL"}:
            raise ValueError("Tipo de operação deve ser compra ou venda.")
        if operation.quantity <= 0:
            raise ValueError("Quantidade deve ser maior que zero.")
        if operation.unit_price < 0:
            raise ValueError("Preço unitário deve ser maior ou igual a zero.")
        if (operation.fees or 0) < 0 or (operation.taxes or 0) < 0:
            raise ValueError("Taxas e impostos não podem ser negativos.")

    def _validate_asset_history(self, user_id: UUID, asset_id: UUID) -> None:
        operations = self.operation_repository.list_by_user_and_asset(user_id, asset_id)
        asset = self.asset_repository.get_by_id(asset_id)
        PortfolioEngine.calculate_positions(operations, {asset_id: asset})
