from app.models.user import User

from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository

from app.schemas.order import (
    OrderCreate,
    OrderResponse,
)

from app.schemas.operation import OperationCreate

from app.services.operation_service import OperationService


class OrderService:

    def __init__(
        self,
        asset_repository: AssetRepository,
        operation_repository: OperationRepository,
    ):
        self.asset_repository = asset_repository
        self.operation_repository = operation_repository

    def execute(
        self,
        user: User,
        data: OrderCreate,
    ) -> OrderResponse:

        asset = self.asset_repository.get_by_id(data.asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        service = OperationService(
            self.operation_repository,
            self.asset_repository,
        )

        operation = service.create(
            user,
            OperationCreate(
                asset_id=data.asset_id,
                operation_type=data.operation,
                operation_date=None,
                quantity=data.quantity,
                unit_price=data.unit_price,
                fees=data.fees,
                taxes=data.taxes,
                notes="Criado pela Boleta Inteligente",
            ),
        )

        return OrderResponse(
            success=True,
            message="Ordem executada com sucesso.",
            operation_id=operation.id,
        )
