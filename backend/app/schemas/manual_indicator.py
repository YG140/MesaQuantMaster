from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ManualIndicatorCreate(BaseModel):
    indicator_key: str = Field(min_length=1, max_length=60)
    value: Decimal
    unit: str = Field(min_length=1, max_length=30)
    reference_date: date
    source_description: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("value")
    @classmethod
    def finite_and_reasonable(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or abs(value) > Decimal("1000000000000000"):
            raise ValueError("Informe um valor numérico válido e razoável.")
        return value

    @field_validator("reference_date")
    @classmethod
    def not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("A data de referência não pode estar no futuro.")
        return value


class ManualIndicatorUpdate(BaseModel):
    value: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    reference_date: date | None = None
    source_description: str | None = Field(default=None, min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)

    _finite_and_reasonable = field_validator("value")(
        ManualIndicatorCreate.finite_and_reasonable.__func__
    )
    _not_future = field_validator("reference_date")(
        ManualIndicatorCreate.not_future.__func__
    )


class ManualIndicatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    asset_id: UUID
    indicator_key: str
    value: Decimal
    unit: str
    reference_date: date
    source: str = "Informado manualmente"
    source_type: str
    source_description: str
    notes: str | None
    freshness_status: str
    availability_status: str = "available"
    created_at: datetime
    updated_at: datetime
