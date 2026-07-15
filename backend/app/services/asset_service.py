from __future__ import annotations

from uuid import UUID

from app.models.asset import Asset
from app.repositories.asset_repository import AssetRepository
from app.schemas.asset import AssetUpdate


class AssetService:
    def __init__(self, repository: AssetRepository):
        self.repository = repository

    def create(
        self,
        ticker: str,
        name: str,
        asset_type: str,
        sector: str | None = None,
        country: str | None = None,
        currency: str = "BRL",
        exchange: str | None = None,
    ) -> Asset:

        ticker = ticker.upper().strip()

        existing_asset = self.repository.get_by_ticker(ticker)

        if existing_asset:
            raise ValueError(f"O ativo '{ticker}' já está cadastrado.")

        asset = Asset(
            ticker=ticker,
            name=name.strip(),
            asset_type=asset_type.strip(),
            sector=sector,
            country=country,
            currency=currency,
            exchange=exchange,
        )

        return self.repository.create(asset)

    def get_by_id(self, asset_id: UUID) -> Asset:
        asset = self.repository.get_by_id(asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        return asset

    def list(self) -> list[Asset]:
        return self.repository.list()

    def update(
        self,
        asset_id: UUID,
        data: AssetUpdate,
    ) -> Asset:

        asset = self.repository.get_by_id(asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        if data.ticker is not None:
            ticker = data.ticker.upper().strip()

            existing = self.repository.get_by_ticker(ticker)

            if existing and existing.id != asset.id:
                raise ValueError("Já existe um ativo com esse ticker.")

            asset.ticker = ticker

        if data.name is not None:
            asset.name = data.name.strip()

        if data.asset_type is not None:
            asset.asset_type = data.asset_type.strip()

        if data.sector is not None:
            asset.sector = data.sector

        if data.country is not None:
            asset.country = data.country

        if data.currency is not None:
            asset.currency = data.currency

        if data.exchange is not None:
            asset.exchange = data.exchange

        if data.is_active is not None:
            asset.is_active = data.is_active

        return self.repository.update(asset)

    def delete(self, asset_id: UUID) -> None:
        asset = self.repository.get_by_id(asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        self.repository.delete(asset)
