from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BrokerageBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class BrokerageCreate(BrokerageBase):
    pass


class BrokerageResponse(BrokerageBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
