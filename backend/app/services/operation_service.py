from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.engines.portfolio_engine import PortfolioEngine
from app.models.operation import Operation
from app.models.portfolio_action_audit import PortfolioActionAudit
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
            raise LookupError("Operação não encontrada.")
        return operation

    def get_owned(self, operation_id: UUID, user_id: UUID) -> Operation:
        operation = self.operation_repository.get_by_id(operation_id)
        if operation is None or operation.user_id != user_id:
            raise LookupError("Operação não encontrada.")
        return operation

    def list(self) -> list[Operation]:
        return self.operation_repository.list()

    def list_by_user(self, user_id: UUID) -> list[Operation]:
        return self.operation_repository.list_by_user(user_id)

    def list_position_operations(
        self, user_id: UUID, asset_id: UUID
    ) -> list[Operation]:
        if self.asset_repository.get_by_id(asset_id) is None:
            raise LookupError("Posição não encontrada.")
        return self.operation_repository.list_by_user_and_asset(user_id, asset_id)

    def update(
        self, operation_id: UUID, data: OperationUpdate, user_id: UUID | None = None
    ) -> Operation:
        operation = (
            self.get_owned(operation_id, user_id)
            if user_id is not None
            else self.get_by_id(operation_id)
        )
        before = self._operation_snapshot(operation)
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
            self.operation_repository.db.add(
                PortfolioActionAudit(
                    user_id=operation.user_id,
                    asset_id=operation.asset_id,
                    action="UPDATE_OPERATION",
                    operation_count=1,
                    before_json=json.dumps(before, ensure_ascii=False),
                    after_json=json.dumps(
                        self._operation_snapshot(operation), ensure_ascii=False
                    ),
                )
            )
            self.operation_repository.db.commit()
            self.operation_repository.db.refresh(operation)
            return operation
        except Exception:
            self.operation_repository.db.rollback()
            raise

    def delete(self, operation_id: UUID, user_id: UUID | None = None) -> None:
        operation = (
            self.get_owned(operation_id, user_id)
            if user_id is not None
            else self.get_by_id(operation_id)
        )
        owner_id, asset_id = operation.user_id, operation.asset_id
        try:
            self.operation_repository.db.delete(operation)
            self.operation_repository.db.flush()
            self._validate_asset_history(owner_id, asset_id)
            self.operation_repository.db.commit()
        except Exception:
            self.operation_repository.db.rollback()
            raise

    def delete_position(
        self,
        user_id: UUID,
        asset_id: UUID,
        expected_operations: int,
        ticker: str,
    ) -> int:
        asset = self.asset_repository.get_by_id(asset_id)
        operations = self.operation_repository.list_by_user_and_asset(
            user_id, asset_id
        )
        if asset is None or not operations:
            raise LookupError("Posição não encontrada.")
        if asset.ticker.upper() != ticker.strip().upper():
            raise RuntimeError("O ticker de confirmação não corresponde à posição.")
        if len(operations) != expected_operations:
            raise RuntimeError(
                "A posição foi alterada. Atualize a carteira antes de excluir."
            )
        before = [self._operation_snapshot(item) for item in operations]
        try:
            for operation in operations:
                self.operation_repository.db.delete(operation)
            self.operation_repository.db.flush()
            if self.operation_repository.list_by_user_and_asset(user_id, asset_id):
                raise RuntimeError("Não foi possível excluir toda a posição.")
            self.operation_repository.db.add(
                PortfolioActionAudit(
                    user_id=user_id,
                    asset_id=asset_id,
                    action="DELETE_POSITION",
                    operation_count=len(operations),
                    before_json=json.dumps(before, ensure_ascii=False),
                    after_json="[]",
                )
            )
            self.operation_repository.db.commit()
            return len(operations)
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
        if operation.unit_price <= 0:
            raise ValueError("Preço unitário deve ser maior que zero.")
        if (operation.fees or 0) < 0 or (operation.taxes or 0) < 0:
            raise ValueError("Taxas e impostos não podem ser negativos.")

    def _validate_asset_history(self, user_id: UUID, asset_id: UUID) -> None:
        operations = self.operation_repository.list_by_user_and_asset(user_id, asset_id)
        asset = self.asset_repository.get_by_id(asset_id)
        PortfolioEngine.calculate_positions(operations, {asset_id: asset})

    @staticmethod
    def _operation_snapshot(operation: Operation) -> dict[str, object]:
        def serialize(value):
            if value is None:
                return None
            if isinstance(value, (Decimal, UUID, date, datetime)):
                return str(value)
            return value

        fields = (
            "id",
            "asset_id",
            "brokerage_id",
            "operation_type",
            "operation_date",
            "quantity",
            "unit_price",
            "fees",
            "taxes",
            "notes",
            "source",
        )
        return {field: serialize(getattr(operation, field)) for field in fields}
