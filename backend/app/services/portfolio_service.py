from app.engines.portfolio_engine import PortfolioEngine
from app.repositories.operation_repository import OperationRepository
from app.repositories.asset_repository import AssetRepository
from app.schemas.portfolio import PortfolioSummary


class PortfolioService:
    def __init__(
        self,
        operation_repository: OperationRepository,
        asset_repository: AssetRepository,
    ):
        self.operation_repository = operation_repository
        self.asset_repository = asset_repository

    def calculate(self, user_id) -> PortfolioSummary:
        operations = self.operation_repository.list_by_user(user_id)

        asset_ids = {operation.asset_id for operation in operations}
        assets_by_id = {
            asset.id: asset for asset in self.asset_repository.list_by_ids(asset_ids)
        }

        positions = PortfolioEngine.calculate_positions(
            operations=operations,
            assets_by_id=assets_by_id,
        )

        return PortfolioEngine.summarize(positions)
