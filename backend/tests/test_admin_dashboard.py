"""Тесты /api/v1/admin/dashboard (C1: базовые метрики)."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.security import create_access_token, hash_password
from app.db.enum import OrderStatus, UserRole, UserStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User as UserModel


class TestDashboardRBAC:
    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        response = await client.get("/api/v1/admin/dashboard")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_customer_403(self, client, auth_headers):
        response = await client.get(
            "/api/v1/admin/dashboard", headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_moderator_ok(self, client, db_session):
        mod = UserModel(
            email="dash-mod@example.com",
            password_hash=hash_password("dash-mod-1234"),
            first_name="M", last_name="U", phone_number="+79990000070",
            role=UserRole.MODERATOR, status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        db_session.add(mod)
        await db_session.flush()
        await db_session.refresh(mod)
        headers = {"Authorization": f"Bearer {create_access_token(str(mod.public_id))}"}
        response = await client.get("/api/v1/admin/dashboard", headers=headers)
        assert response.status_code == 200


class TestDashboardMetrics:
    @pytest.mark.asyncio
    async def test_empty_db(self, client, admin_headers):
        response = await client.get(
            "/api/v1/admin/dashboard", headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["orders_count"] == 0
        assert Decimal(body["revenue_gross"]) == Decimal("0.00")
        assert Decimal(body["refunds_total"]) == Decimal("0.00")
        assert Decimal(body["revenue_net"]) == Decimal("0.00")
        assert body["top_products"] == []

    @pytest.mark.asyncio
    async def test_orders_and_revenue(
        self, client, admin_headers, db_session, verified_user, address, product
    ):
        """
        orders_count = все заказы (включая pending/canceled).
        revenue_gross = только paid|shipped|delivered.
        """
        # paid → в revenue
        o1 = Order(
            user_id=verified_user.id, total=Decimal("1000.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        # pending → в count, не в revenue
        o2 = Order(
            user_id=verified_user.id, total=Decimal("500.00"),
            status=OrderStatus.PENDING, shipping_address_id=address.id,
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        # canceled → в count, не в revenue
        o3 = Order(
            user_id=verified_user.id, total=Decimal("300.00"),
            status=OrderStatus.CANCELED, shipping_address_id=address.id,
            created_at=datetime.now(UTC) - timedelta(hours=3),
        )
        db_session.add_all([o1, o2, o3])
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        assert body["orders_count"] == 3
        assert Decimal(body["revenue_gross"]) == Decimal("1000.00")

    @pytest.mark.asyncio
    async def test_period_filter(
        self, client, admin_headers, db_session, verified_user, address
    ):
        """Заказ старше period_days не учитывается."""
        old = Order(
            user_id=verified_user.id, total=Decimal("9999.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        recent = Order(
            user_id=verified_user.id, total=Decimal("100.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add_all([old, recent])
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        assert body["orders_count"] == 1
        assert Decimal(body["revenue_gross"]) == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_new_users_count(
        self, client, admin_headers, db_session, category
    ):
        """new_users_count — только созданные за период и не deleted."""
        recent = UserModel(
            email="recent-dash@example.com",
            password_hash=hash_password("recent-1234"),
            first_name="R", last_name="U", phone_number="+79990000071",
            role=UserRole.CUSTOMER, status=UserStatus.ACTIVE,
            is_email_verified=True,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        old = UserModel(
            email="old-dash@example.com",
            password_hash=hash_password("old-1234"),
            first_name="O", last_name="U", phone_number="+79990000072",
            role=UserRole.CUSTOMER, status=UserStatus.ACTIVE,
            is_email_verified=True,
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        db_session.add_all([recent, old])
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        # recent + admin_headers' user (тоже создан в фикстуре — created_at = now)
        assert body["new_users_count"] >= 1

    @pytest.mark.asyncio
    async def test_top_products_sorted_by_revenue(
        self, client, admin_headers, db_session, verified_user, address, category
    ):
        """top_products отсортирован по revenue desc, лимит 5."""
        products = []
        for i in range(6):
            p = Product(
                name=f"Top-{i}", description="Test",
                cost=Decimal(f"{(i + 1) * 100}.00"),
                category_id=category.id,
            )
            db_session.add(p)
            await db_session.flush()
            products.append(p)

        order = Order(
            user_id=verified_user.id, total=Decimal("5000.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add(order)
        await db_session.flush()

        # Каждый товар по quantity=i+1 → revenue = cost*qty
        # Top-5 (по revenue): Top-5*6=3600, Top-4*5=2500, Top-3*4=1600, Top-2*3=900, Top-1*2=400
        # Top-0*1=100 — не входит
        for i, p in enumerate(products):
            db_session.add(OrderItem(
                order_id=order.id, product_id=p.id,
                product_cost=p.cost, product_count=i + 1,
            ))
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        top = body["top_products"]
        assert len(top) == 5
        # Первый — самый дорогой по revenue
        assert top[0]["product_name"] == "Top-5"
        assert Decimal(top[0]["total_revenue"]) == Decimal("3600.00")
        # Сортировка по убыванию
        revenues = [Decimal(t["total_revenue"]) for t in top]
        assert revenues == sorted(revenues, reverse=True)

class TestDashboardComparison:
    @pytest.mark.asyncio
    async def test_prev_and_delta(
        self, client, admin_headers, db_session, verified_user, address
    ):
        """
        Текущее окно (0..7 дней): 1 заказ на 100.
        Предыдущее окно (7..14 дней): 2 заказа на 50+50=100.
        delta_pct = (1-2)/2*100 = -50.0; (100-100)/100*100 = 0.0.
        """
        now = datetime.now(UTC)
        db_session.add(Order(
            user_id=verified_user.id, total=Decimal("100.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=now - timedelta(hours=1),
        ))
        db_session.add(Order(
            user_id=verified_user.id, total=Decimal("50.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=now - timedelta(days=10),
        ))
        db_session.add(Order(
            user_id=verified_user.id, total=Decimal("50.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=now - timedelta(days=11),
        ))
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()

        assert body["orders_count"] == 1
        assert body["orders_count_prev"] == 2
        assert body["orders_count_delta_pct"] == -50.0

        assert Decimal(body["revenue_gross"]) == Decimal("100.00")
        assert Decimal(body["revenue_gross_prev"]) == Decimal("100.00")
        assert body["revenue_gross_delta_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_delta_none_when_prev_zero(
        self, client, admin_headers, db_session, verified_user, address
    ):
        """prev=0, curr>0 → delta_pct = None (не ∞)."""
        db_session.add(Order(
            user_id=verified_user.id, total=Decimal("100.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        ))
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        assert body["orders_count"] == 1
        assert body["orders_count_prev"] == 0
        assert body["orders_count_delta_pct"] is None
        assert body["revenue_gross_delta_pct"] is None