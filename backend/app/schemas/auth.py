from pydantic import BaseModel, EmailStr
from pydantic import Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    email: EmailStr


class EmailRequest(BaseModel):
    email: EmailStr


class OneTimeTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class ResetPasswordRequest(OneTimeTokenRequest):
    password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str


class AuthErrorResponse(BaseModel):
    detail: str
    code: str
