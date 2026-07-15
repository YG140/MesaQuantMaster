from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertCreate(BaseModel):
    asset_id: UUID
    alert_type: str
    target_value: Decimal


class AlertUpdate(BaseModel):
    alert_type: str | None = None
    target_value: Decimal | None = None
    is_active: bool | None = None


class AlertResponse(BaseModel):
    id: UUID

    user_id: UUID

    asset_id: UUID

    alert_type: str

    target_value: Decimal

    is_active: bool

    triggered: bool

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )
