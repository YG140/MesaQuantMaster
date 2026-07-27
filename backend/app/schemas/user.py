from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Nome do usuário",
    )

    email: EmailStr

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Senha do usuário",
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    is_active: bool
    is_superuser: bool
    is_email_verified: bool
    created_at: datetime
