"""
Схемы админ-API.

Отдельный файл, чтобы не смешивать с пользовательскими схемами.
Наружу отдаём public_id (единый контракт — клиент не зависит
от внутренних id).
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.enum import UserRole, UserStatus


class AdminUserListItem(BaseModel):
    """Пользователь в админ-списке. Без password_hash."""
    public_id: UUID
    email: str
    first_name: str
    last_name: str
    phone_number: str
    role: UserRole
    status: UserStatus
    is_email_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdateRequest(BaseModel):
    role: UserRole

    model_config = ConfigDict(extra="forbid")


class UserStatusUpdateRequest(BaseModel):
    status: UserStatus

    model_config = ConfigDict(extra="forbid")