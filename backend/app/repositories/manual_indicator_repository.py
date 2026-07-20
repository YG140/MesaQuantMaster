from uuid import UUID

from sqlalchemy.orm import Session

from app.models.manual_indicator import ManualIndicator


class ManualIndicatorRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_asset(self, user_id: UUID, asset_id: UUID) -> list[ManualIndicator]:
        return (
            self.db.query(ManualIndicator)
            .filter(
                ManualIndicator.user_id == user_id, ManualIndicator.asset_id == asset_id
            )
            .order_by(ManualIndicator.indicator_key)
            .all()
        )

    def get_owned(self, indicator_id: UUID, user_id: UUID) -> ManualIndicator | None:
        return (
            self.db.query(ManualIndicator)
            .filter(
                ManualIndicator.id == indicator_id, ManualIndicator.user_id == user_id
            )
            .first()
        )

    def get_by_key(
        self, user_id: UUID, asset_id: UUID, key: str
    ) -> ManualIndicator | None:
        return (
            self.db.query(ManualIndicator)
            .filter(
                ManualIndicator.user_id == user_id,
                ManualIndicator.asset_id == asset_id,
                ManualIndicator.indicator_key == key,
            )
            .first()
        )

    def save(self, indicator: ManualIndicator) -> ManualIndicator:
        self.db.add(indicator)
        self.db.commit()
        self.db.refresh(indicator)
        return indicator

    def delete(self, indicator: ManualIndicator) -> None:
        self.db.delete(indicator)
        self.db.commit()
