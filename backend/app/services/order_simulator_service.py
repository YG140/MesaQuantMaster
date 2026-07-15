from decimal import Decimal

from app.repositories.asset_repository import AssetRepository
from app.repositories.operation_repository import OperationRepository
from app.schemas.order_simulator import (
    OrderSimulationRequest,
    OrderSimulationResponse,
)


class OrderSimulatorService:
    def __init__(
        self,
        asset_repository: AssetRepository,
        operation_repository: OperationRepository,
    ):
        self.asset_repository = asset_repository
        self.operation_repository = operation_repository

    def simulate(self, user, data: OrderSimulationRequest):

        asset = self.asset_repository.get_by_id(data.asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        operations = self.operation_repository.list_by_user(user.id)

        quantity = Decimal("0")
        invested = Decimal("0")

        for op in operations:

            if op.asset_id != data.asset_id:
                continue

            if op.operation_type == "BUY":
                quantity += op.quantity
                invested += op.quantity * op.unit_price + op.fees + op.taxes

            elif op.operation_type == "SELL":

                if quantity > 0:
                    average = invested / quantity

                    quantity -= op.quantity
                    invested -= average * op.quantity

        current_average = invested / quantity if quantity > 0 else Decimal("0")

        gross = data.quantity * data.unit_price

        total = gross + data.fees + data.taxes

        warning = None

        if data.operation.upper() == "BUY":

            new_quantity = quantity + data.quantity

            new_average = (invested + total) / new_quantity

        else:

            if data.quantity > quantity:

                raise ValueError("Quantidade insuficiente para venda.")

            new_quantity = quantity - data.quantity

            new_average = current_average

            if new_quantity == 0:
                new_average = Decimal("0")

        return OrderSimulationResponse(
            ticker=asset.ticker,
            operation=data.operation.upper(),
            gross_value=gross,
            fees=data.fees,
            taxes=data.taxes,
            total_value=total,
            current_quantity=quantity,
            new_quantity=new_quantity,
            current_average_price=current_average,
            new_average_price=new_average,
            warning=warning,
        )
