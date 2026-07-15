from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.asset import Asset


class AssetRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, asset: Asset) -> Asset:
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def get_by_id(self, asset_id: UUID) -> Asset | None:
        return self.db.query(Asset).filter(Asset.id == asset_id).first()

    def list_by_ids(self, asset_ids: set[UUID]) -> list[Asset]:
        if not asset_ids:
            return []

        return self.db.query(Asset).filter(Asset.id.in_(asset_ids)).all()

    def get_by_ticker(self, ticker: str) -> Asset | None:
        return self.db.query(Asset).filter(Asset.ticker == ticker.upper()).first()

    def list(self) -> list[Asset]:
        return self.db.query(Asset).order_by(Asset.ticker.asc()).all()

    def update(self, asset: Asset) -> Asset:
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def delete(self, asset: Asset) -> None:
        self.db.delete(asset)
        self.db.commit()
