from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WatchlistCreate(BaseModel):
    asset_id: UUID


class WatchlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    asset_id: UUID

    created_at: datetime
