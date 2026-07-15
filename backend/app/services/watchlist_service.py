from __future__ import annotations

from app.models.user import User
from app.models.watchlist import Watchlist

from app.repositories.asset_repository import AssetRepository
from app.repositories.watchlist_repository import WatchlistRepository

from app.schemas.watchlist import WatchlistCreate


class WatchlistService:
    def __init__(
        self,
        repository: WatchlistRepository,
        asset_repository: AssetRepository,
    ):
        self.repository = repository
        self.asset_repository = asset_repository

    def create(
        self,
        user: User,
        data: WatchlistCreate,
    ) -> Watchlist:

        asset = self.asset_repository.get_by_id(data.asset_id)

        if asset is None:
            raise ValueError("Ativo não encontrado.")

        existing = self.repository.get(user.id, data.asset_id)

        if existing:
            raise ValueError("O ativo já está na Watchlist.")

        watchlist = Watchlist(
            user_id=user.id,
            asset_id=data.asset_id,
        )

        return self.repository.create(watchlist)

    def list(self, user: User):
        return self.repository.list(user.id)

    def delete(
        self,
        user: User,
        asset_id,
    ):

        watchlist = self.repository.get(user.id, asset_id)

        if watchlist is None:
            raise ValueError("Ativo não encontrado na Watchlist.")

        self.repository.delete(watchlist)
