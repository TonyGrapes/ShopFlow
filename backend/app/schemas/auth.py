# app/schemas/auth.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.enum import UserRole, UserStatus


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str = Field(..., min_length=5, max_length=20)

    model_config = ConfigDict(extra="forbid")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid")


class TokenResponse(BaseModel):
    """Ответ login/refresh. Refresh-токен НЕ здесь — он в httpOnly-cookie."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int          # секунды до exp access-токена


class UserResponse(BaseModel):
    """Публичный профиль. Без password_hash, без внутренних id."""
    public_id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    phone_number: str
    role: UserRole
    status: UserStatus
    is_email_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Нейтральные ответы: resend-verification, verify-email."""
    message: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr
    model_config = ConfigDict(extra="forbid")