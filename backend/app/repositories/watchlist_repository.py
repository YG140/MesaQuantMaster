from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.watchlist import Watchlist


class WatchlistRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, watchlist: Watchlist) -> Watchlist:
        self.db.add(watchlist)
        self.db.commit()
        self.db.refresh(watchlist)
        return watchlist

    def get(self, user_id: UUID, asset_id: UUID):
        return (
            self.db.query(Watchlist)
            .filter(
                Watchlist.user_id == user_id,
                Watchlist.asset_id == asset_id,
            )
            .first()
        )

    def list(self, user_id: UUID):
        return self.db.query(Watchlist).filter(Watchlist.user_id == user_id).all()

    def delete(self, watchlist: Watchlist):
        self.db.delete(watchlist)
        self.db.commit()
