from datetime import date
from decimal import Decimal

from app.engines.portfolio_engine import PortfolioEngine
from app.models.asset import Asset
from app.models.operation import Operation
from app.repositories.asset_repository import AssetRepository
from app.repositories.brokerage_repository import BrokerageRepository
from app.repositories.operation_repository import OperationRepository
from app.schemas.portfolio import (
    InitialPortfolioImport,
    InitialPortfolioImportResponse,
    InvestmentCreate,
    InvestmentCreateResponse,
    PortfolioSummary,
)
from app.services.market_service import MarketService


class PortfolioService:
    def __init__(
        self,
        operation_repository: OperationRepository,
        asset_repository: AssetRepository,
        brokerage_repository: BrokerageRepository | None = None,
        market_service: MarketService | None = None,
    ):
        self.operation_repository = operation_repository
        self.asset_repository = asset_repository
        self.brokerage_repository = brokerage_repository
        self.market_service = market_service

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
        if positions:
            quotes_by_symbol = self._get_quotes_by_symbol(
                [position.ticker for position in positions]
            )
            positions = PortfolioEngine.apply_quotes(
                positions=positions,
                quotes_by_symbol=quotes_by_symbol,
            )

        return PortfolioEngine.summarize(positions)

    def _get_quotes_by_symbol(self, symbols: list[str]) -> dict:
        try:
            market_service = self.market_service or MarketService()
            quotes = market_service.get_quotes(symbols)
        except Exception:
            return {}
        return {quote.ticker.upper(): quote for quote in quotes.quotes}

    def add_investment(
        self, user_id, data: InvestmentCreate
    ) -> InvestmentCreateResponse:
        self._validate_positive(data.quantity, "Quantidade")
        self._validate_positive(data.unit_price, "Preco unitario")
        self._ensure_owned_brokerage(user_id, data.brokerage_id)

        try:
            asset, asset_created = self._get_or_add_asset(
                ticker=data.ticker,
                name=data.name,
                asset_type=data.asset_type,
            )
            operation = self.operation_repository.add(
                Operation(
                    user_id=user_id,
                    asset_id=asset.id,
                    brokerage_id=data.brokerage_id,
                    operation_type="BUY",
                    operation_date=data.operation_date,
                    quantity=data.quantity,
                    unit_price=data.unit_price,
                    fees=data.fees,
                    taxes=data.taxes,
                    notes=data.notes,
                    source="manual_investment",
                )
            )
            self.operation_repository.db.commit()
            self.operation_repository.db.refresh(operation)
        except Exception:
            self.operation_repository.db.rollback()
            raise

        return InvestmentCreateResponse(
            asset_id=asset.id,
            operation_id=operation.id,
            brokerage_id=data.brokerage_id,
            asset_created=asset_created,
        )

    def import_initial_portfolio(
        self,
        user_id,
        data: InitialPortfolioImport,
    ) -> InitialPortfolioImportResponse:
        self._ensure_owned_brokerage(user_id, data.brokerage_id)
        if not data.positions:
            raise ValueError("Informe pelo menos uma posicao para importar.")

        for item in data.positions:
            self._validate_positive(item.quantity, f"Quantidade de {item.ticker}")
            self._validate_positive(item.average_price, f"Preco medio de {item.ticker}")

        assets_created = 0
        assets_reused = 0
        operations_created = 0

        try:
            for item in data.positions:
                asset, asset_created = self._get_or_add_asset(
                    ticker=item.ticker,
                    name=item.name or item.ticker.upper().strip(),
                    asset_type=item.asset_type,
                )
                if asset_created:
                    assets_created += 1
                else:
                    assets_reused += 1

                self.operation_repository.add(
                    Operation(
                        user_id=user_id,
                        asset_id=asset.id,
                        brokerage_id=data.brokerage_id,
                        operation_type="BUY",
                        operation_date=item.reference_date or date.today(),
                        quantity=item.quantity,
                        unit_price=item.average_price,
                        fees=Decimal("0"),
                        taxes=Decimal("0"),
                        notes=item.notes,
                        source="initial_import",
                    )
                )
                operations_created += 1

            self.operation_repository.db.commit()
        except Exception:
            self.operation_repository.db.rollback()
            raise

        return InitialPortfolioImportResponse(
            assets_created=assets_created,
            assets_reused=assets_reused,
            operations_created=operations_created,
            brokerage_id=data.brokerage_id,
        )

    def _ensure_owned_brokerage(self, user_id, brokerage_id) -> None:
        if self.brokerage_repository is None:
            return
        brokerage = self.brokerage_repository.get_by_id(brokerage_id)
        if brokerage is None or brokerage.user_id != user_id:
            raise ValueError("Corretora nao encontrada.")

    def _get_or_add_asset(
        self,
        ticker: str,
        name: str,
        asset_type: str,
    ) -> tuple[Asset, bool]:
        normalized_ticker = ticker.upper().strip()
        asset = self.asset_repository.get_by_ticker(normalized_ticker)
        if asset is not None:
            return asset, False

        asset = self.asset_repository.add(
            Asset(
                ticker=normalized_ticker,
                name=name.strip(),
                asset_type=asset_type.strip(),
                currency="BRL",
            )
        )
        return asset, True

    @staticmethod
    def _validate_positive(value: Decimal, label: str) -> None:
        if value <= 0:
            raise ValueError(f"{label} deve ser maior que zero.")
