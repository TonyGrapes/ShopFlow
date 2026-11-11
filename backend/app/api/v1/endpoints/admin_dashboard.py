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
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_roles
from app.db.enum import OrderStatus, UserRole
from app.db.session import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User as UserModel
from app.schemas.admin import (
    AdminDashboardResponse,
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

    - orders_count:   все заказы за период (включая pending/canceled).
    - revenue_gross:  SUM(orders.total) WHERE status IN (paid,shipped,delivered).
    - refunds_total:  0.00 (C1); реальное значение — в C3.
    - revenue_net:    revenue_gross - refunds_total.
    - new_users_count: пользователи, созданные за период (deleted_at IS NULL).
    - top_products:   top-5 по выручке (SUM(product_cost * product_count)).
    """
    threshold = datetime.now(UTC) - timedelta(days=period_days)

    # ── SQL 1: orders_count + revenue_gross одним проходом ──
    orders_result = await db.execute(
        select(
            func.count().filter(Order.created_at > threshold).label("orders_count"),
            func.coalesce(
                func.sum(Order.total).filter(
                    and_(
                        Order.status.in_(_REVENUE_STATUSES),
                        Order.created_at > threshold,
                    )
                ),
                Decimal("0.00"),
            ).label("revenue_gross"),
        )
    )
    orders_count, revenue_gross = orders_result.one()

    # ── SQL 2: users count за период ──
    users_result = await db.execute(
        select(func.count())
        .select_from(UserModel)
        .where(
            UserModel.created_at > threshold,
            UserModel.deleted_at.is_(None),
        )
    )
    new_users_count = users_result.scalar_one()

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

    # C3: refunds_total = SUM(refunds.amount WHERE refunds.status='completed'
    #     AND refunds.refunded_at > threshold). Сейчас — 0.
    refunds_total = Decimal("0.00")

    return AdminDashboardResponse(
        period_days=period_days,
        orders_count=orders_count,
        revenue_gross=revenue_gross,
        refunds_total=refunds_total,
        revenue_net=revenue_gross - refunds_total,
        new_users_count=new_users_count,
        top_products=top_products,
    )