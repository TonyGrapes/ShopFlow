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
from app.schemas.common import Money


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

# ============================================================
#  Dashboard (C1: базовые метрики; C2 добавит *_prev/*_delta_pct,
#  C3 заполнит refunds_total реальным значением, C4 — series)
# ============================================================

class TopProductItem(BaseModel):
    """Товар в топ-5 по выручке за период."""
    product_id: int
    product_name: str
    total_quantity: int
    total_revenue: Money


class AdminDashboardResponse(BaseModel):
    """
    Метрики дашборда за period_days.

    revenue_gross — сумма orders.total для статусов paid|shipped|delivered.
    refunds_total — в C1 всегда 0.00; C3 заполнит реальным SUM(refunds.amount).
    revenue_net   — revenue_gross - refunds_total (в C1 совпадает с gross).
    """
    period_days: int
    orders_count: int
    revenue_gross: Money
    refunds_total: Money
    revenue_net: Money
    new_users_count: int
    top_products: list[TopProductItem]