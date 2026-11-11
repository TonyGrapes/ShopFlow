"""
Схемы админ-API.

Отдельный файл, чтобы не смешивать с пользовательскими схемами.
Наружу отдаём public_id (единый контракт — клиент не зависит
от внутренних id).
"""
from datetime import date, datetime
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

    Потоки, а не P&L:
    - revenue_gross — заказы, созданные в окне, по которым получены деньги.
    - refunds_total — возвраты, ЗАВЕРШЁННЫЕ в окне (по refunded_at).
    - revenue_net = revenue_gross - refunds_total. Может быть отрицательным:
      заказ создан раньше окна, но возврат попал в окно.

    refunds_total = SUM(refunds.amount) WHERE status='completed'
                    AND refunded_at > threshold.
    pending/failed возвраты не учитываем — деньги ещё не вернулись.
    """
    period_days: int

    # ── Текущий период ──
    orders_count: int
    revenue_gross: Money
    refunds_total: Money
    revenue_net: Money
    new_users_count: int
    top_products: list[TopProductItem]

    # ── Предыдущее окно ──
    orders_count_prev: int
    orders_count_delta_pct: float | None
    revenue_gross_prev: Money
    revenue_gross_delta_pct: float | None
    refunds_total_prev: Money
    refunds_total_delta_pct: float | None
    new_users_count_prev: int
    new_users_count_delta_pct: float | None

# ============================================================
#  Dashboard series (C4: динамика по дням)
# ============================================================

class DailySeriesItem(BaseModel):
    """
    Один день в серии.

    date — ISO YYYY-MM-DD (локальная дата PostgreSQL CURRENT_DATE).
    orders_count — все заказы в этот день (pending/canceled тоже).
    revenue_gross — только paid|shipped|delivered.

    net по дням не считаем: revenue_gross считается по orders.created_at,
    а refunds — по refunds.refunded_at (разные окна). Сумма по дням не
    сошлась бы с общим revenue_net в дашборде — путает. Если понадобится —
    отдельная серия series_refunds.
    """
    date: date
    orders_count: int
    revenue_gross: Money


class AdminDashboardSeriesResponse(BaseModel):
    period_days: int
    items: list[DailySeriesItem]