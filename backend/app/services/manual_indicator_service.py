from datetime import date
from uuid import UUID

from app.models.manual_indicator import ManualIndicator
from app.repositories.asset_repository import AssetRepository
from app.repositories.manual_indicator_repository import ManualIndicatorRepository
from app.schemas.manual_indicator import ManualIndicatorCreate, ManualIndicatorUpdate


STOCK_KEYS = {
    "pe",
    "price_to_book",
    "ev_ebitda",
    "ev_ebit",
    "roe",
    "roa",
    "roic",
    "gross_margin",
    "ebitda_margin",
    "ebit_margin",
    "net_margin",
    "net_debt",
    "net_debt_ebitda",
    "net_debt_equity",
    "current_ratio",
    "dividend_yield",
    "revenue_cagr",
    "earnings_cagr",
    "equity",
    "shares_outstanding",
    "free_float",
}
FII_KEYS = {
    "price_to_book",
    "book_value_per_share",
    "dividend_yield",
    "last_distribution",
    "physical_vacancy",
    "financial_vacancy",
    "equity",
    "shareholders",
    "shares_outstanding",
    "cash_percentage",
    "debt",
    "distribution_cagr",
    "price_cagr",
}


class ManualIndicatorService:
    def __init__(self, repository: ManualIndicatorRepository, assets: AssetRepository):
        self.repository = repository
        self.assets = assets

    def asset_for_symbol(self, symbol: str):
        asset = self.assets.get_by_ticker(symbol.upper().strip())
        if asset is None:
            raise ValueError("Ativo não encontrado.")
        return asset

    def list(self, user_id: UUID, symbol: str) -> list[ManualIndicator]:
        return self.repository.list_for_asset(user_id, self.asset_for_symbol(symbol).id)

    def create(
        self, user_id: UUID, symbol: str, data: ManualIndicatorCreate
    ) -> ManualIndicator:
        asset = self.asset_for_symbol(symbol)
        key = data.indicator_key.lower().strip()
        self._validate_key(asset.asset_type, key)
        if self.repository.get_by_key(user_id, asset.id, key):
            raise ValueError(
                "Este indicador já foi informado. Edite o registro existente."
            )
        return self.repository.save(
            ManualIndicator(
                user_id=user_id,
                asset_id=asset.id,
                indicator_key=key,
                value=data.value,
                unit=data.unit.strip(),
                reference_date=data.reference_date,
                source_type="manual",
                source_description=data.source_description.strip(),
                notes=data.notes,
            )
        )

    def update(
        self, user_id: UUID, indicator_id: UUID, data: ManualIndicatorUpdate
    ) -> ManualIndicator:
        item = self.repository.get_owned(indicator_id, user_id)
        if item is None:
            raise ValueError("Indicador complementar não encontrado.")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value.strip() if isinstance(value, str) else value)
        return self.repository.save(item)

    def delete(self, user_id: UUID, indicator_id: UUID) -> None:
        item = self.repository.get_owned(indicator_id, user_id)
        if item is None:
            raise ValueError("Indicador complementar não encontrado.")
        self.repository.delete(item)

    @staticmethod
    def freshness(item: ManualIndicator) -> str:
        return "stale" if (date.today() - item.reference_date).days > 395 else "current"

    @staticmethod
    def _validate_key(asset_type: str, key: str) -> None:
        normalized = asset_type.upper()
        allowed = FII_KEYS if normalized in {"FII", "REAL_ESTATE_FUND"} else STOCK_KEYS
        if key not in allowed:
            raise ValueError("Indicador incompatível com a classe do ativo.")
