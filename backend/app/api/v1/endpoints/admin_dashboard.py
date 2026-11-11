"""
Админ-дашборд: метрики за period_days.

C1 (этот коммит): orders_count, revenue_gross, new_users_count, top-5.
C2 добавит сравнение с предыдущим периодом (*_prev, *_delta_pct).
C3 заполнит refunds_total реальным SUM(refunds.amount).
C4 добавит /series (динамика по дням).
C5 добавит кэш (TTL 60 сек).
C6 добавит /export.csv.

3 SQL-запроса — приемлемо (см. ревью): один SQL на orders-метрики через
FILTER, один на users count, один на top-5. «Один SQL с UNION ALL» —
читался бы хуже без выигрыша по нагрузке.
"""
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.db.enum import OrderStatus, RefundStatus, UserRole
from app.db.session import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.refund import Refund
from app.models.user import User as UserModel
from app.schemas.admin import (
    AdminDashboardResponse,
    AdminDashboardSeriesResponse,
    DailySeriesItem,
    TopProductItem,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/dashboard", tags=["admin:dashboard"])


# ✅ «Выручка» = заказы, за которые получены деньги:
#    paid / shipped / delivered. pending — деньги ещё не пришли.
#    canceled — отменён. Учёт возвратов — отдельно (C3).
_REVENUE_STATUSES = (
    OrderStatus.PAID,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
)


@router.get(
    "",
    response_model=AdminDashboardResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)
async def get_admin_dashboard(
    period_days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """
    Метрики дашборда за period_days (1..90).

    4 SQL:
    1. orders_count + revenue_gross (current + prev, FILTER).
    2. new_users_count (current + prev, FILTER).
    3. top-5 товаров по выручке (JOIN order_items).
    4. refunds_total (current + prev, FILTER by refunded_at).
    """
    
    threshold = datetime.now(UTC) - timedelta(days=period_days)

        # ── SQL 1: orders_count + revenue_gross — текущий + prev одним проходом ──
    prev_threshold = threshold - timedelta(days=period_days)

    orders_result = await db.execute(
        select(
            func.count()
            .filter(Order.created_at > threshold)
            .label("orders_count"),
            func.count()
            .filter(
                and_(
                    Order.created_at > prev_threshold,
                    Order.created_at <= threshold,
                )
            )
            .label("orders_count_prev"),
            func.coalesce(
                func.sum(Order.total).filter(
                    and_(
                        Order.status.in_(_REVENUE_STATUSES),
                        Order.created_at > threshold,
                    )
                ),
                Decimal("0.00"),
            ).label("revenue_gross"),
            func.coalesce(
                func.sum(Order.total).filter(
                    and_(
                        Order.status.in_(_REVENUE_STATUSES),
                        Order.created_at > prev_threshold,
                        Order.created_at <= threshold,
                    )
                ),
                Decimal("0.00"),
            ).label("revenue_gross_prev"),
        )
    )
    row = orders_result.one()
    orders_count = row.orders_count
    orders_count_prev = row.orders_count_prev
    revenue_gross = row.revenue_gross
    revenue_gross_prev = row.revenue_gross_prev

        # ── SQL 2: users count (current + prev) ──
    users_result = await db.execute(
        select(
            func.count()
            .filter(UserModel.created_at > threshold)
            .label("new_users_count"),
            func.count()
            .filter(
                and_(
                    UserModel.created_at > prev_threshold,
                    UserModel.created_at <= threshold,
                )
            )
            .label("new_users_count_prev"),
        )
        .where(UserModel.deleted_at.is_(None))
    )
    urow = users_result.one()
    new_users_count = urow.new_users_count
    new_users_count_prev = urow.new_users_count_prev

    # ── SQL 3: top-5 по выручке ──
    revenue_expr = func.sum(OrderItem.product_cost * OrderItem.product_count)
    top_result = await db.execute(
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            func.sum(OrderItem.product_count).label("total_quantity"),
            revenue_expr.label("total_revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.status.in_(_REVENUE_STATUSES),
            Order.created_at > threshold,
        )
        .group_by(Product.id, Product.name)
        .order_by(revenue_expr.desc())
        .limit(5)
    )
    top_products = [
        TopProductItem(
            product_id=row.product_id,
            product_name=row.product_name,
            total_quantity=int(row.total_quantity),
            total_revenue=row.total_revenue,
        )
        for row in top_result
    ]

    # ── SQL 4: refunds_total + refunds_total_prev ──
    #    Только completed. Окно по refunded_at (когда деньги вернулись),
    #    не по created_at (когда возврат инициирован).
    refunds_result = await db.execute(
        select(
            func.coalesce(
                func.sum(Refund.amount).filter(
                    and_(
                        Refund.status == RefundStatus.COMPLETED,
                        Refund.refunded_at > threshold,
                    )
                ),
                Decimal("0.00"),
            ).label("refunds_total"),
            func.coalesce(
                func.sum(Refund.amount).filter(
                    and_(
                        Refund.status == RefundStatus.COMPLETED,
                        Refund.refunded_at > prev_threshold,
                        Refund.refunded_at <= threshold,
                    )
                ),
                Decimal("0.00"),
            ).label("refunds_total_prev"),
        )
    )
    rrow = refunds_result.one()
    refunds_total = rrow.refunds_total
    refunds_total_prev = rrow.refunds_total_prev

    return AdminDashboardResponse(
        period_days=period_days,
        orders_count=orders_count,
        revenue_gross=revenue_gross,
        refunds_total=refunds_total,
        revenue_net=revenue_gross - refunds_total,
        new_users_count=new_users_count,
        top_products=top_products,
        orders_count_prev=orders_count_prev,
        orders_count_delta_pct=_delta_pct(orders_count, orders_count_prev),
        revenue_gross_prev=revenue_gross_prev,
        revenue_gross_delta_pct=_delta_pct(revenue_gross, revenue_gross_prev),
        refunds_total_prev=refunds_total_prev,
        refunds_total_delta_pct=_delta_pct(refunds_total, refunds_total_prev),
        new_users_count_prev=new_users_count_prev,
        new_users_count_delta_pct=_delta_pct(new_users_count, new_users_count_prev),
    )

def _delta_pct(curr, prev) -> float | None:
    """
    Процент изменения curr относительно prev (округление до 1 знака).

    - prev > 0 → (curr - prev) / prev * 100
    - prev == 0 и curr == 0 → 0.0 (нет изменений)
    - prev == 0 и curr > 0 → None (не определено; фронт покажет «—»)
    """
    prev_f = float(prev)
    curr_f = float(curr)
    if prev_f == 0:
        return 0.0 if curr_f == 0 else None
    return round((curr_f - prev_f) / prev_f * 100, 1)

@router.get(
    "/series",
    response_model=AdminDashboardSeriesResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)
async def get_admin_dashboard_series(
    period_days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """
    Динамика по дням за period_days.

    Один SQL с generate_series: заполняет пустые дни нулями (иначе
    график «прыгает» — визуально неверно).

    Значения в SQL — из OrderStatus (enum): 'paid','shipped','delivered'.
    Захардкожены строкой, потому что bind-параметры для IN-list в text()
    менее читаемы, а значения стабильны (см. app/db/enum.py).
    """
    sql = text("""
        WITH days AS (
            SELECT generate_series(
                (CURRENT_DATE - (:period - 1) * INTERVAL '1 day')::date,
                CURRENT_DATE,
                INTERVAL '1 day'
            )::date AS date
        )
        SELECT d.date AS date,
               COUNT(o.id) AS orders_count,
               COALESCE(
                   SUM(o.total) FILTER (
                       WHERE o.status IN ('paid', 'shipped', 'delivered')
                   ),
                   0
               ) AS revenue_gross
        FROM days d
        LEFT JOIN orders o ON o.created_at::date = d.date
        GROUP BY d.date
        ORDER BY d.date
    """)

    result = await db.execute(sql, {"period": period_days})
    items = [
        DailySeriesItem(
            date=row.date,
            orders_count=row.orders_count,
            revenue_gross=row.revenue_gross,
        )
        for row in result.all()
    ]
    return AdminDashboardSeriesResponse(period_days=period_days, items=items)