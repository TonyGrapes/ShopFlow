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

class TestDashboardRefunds:
    @pytest.mark.asyncio
    async def test_refunds_total_only_completed(
        self, client, admin_headers, db_session, verified_user,
        payment_for_refund, completed_refund,
    ):
        """
        completed_refund = 300.00, refunded_at = now.
        Ещё один pending refund = 999.00 не учитывается.
        """
        from datetime import UTC, datetime

        from app.db.enum import RefundStatus
        from app.models.refund import Refund

        # pending — не считается
        db_session.add(Refund(
            payment_id=payment_for_refund.id,
            amount=Decimal("999.00"),
            status=RefundStatus.PENDING,
            refunded_at=None,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        ))
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        assert Decimal(body["refunds_total"]) == Decimal("300.00")

    @pytest.mark.asyncio
    async def test_revenue_net_with_refunds(
        self, client, admin_headers, db_session, verified_user,
        address, payment_for_refund, completed_refund,
    ):
        """
        gross 1000 (от paid order), refunds 300 → net 700.
        Payment_for_refund привязан к order PAID total=1000.
        """
        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        gross = Decimal(body["revenue_gross"])
        refunds = Decimal(body["refunds_total"])
        net = Decimal(body["revenue_net"])
        assert refunds == Decimal("300.00")
        assert net == gross - refunds

    @pytest.mark.asyncio
    async def test_refunds_prev_and_delta(
        self, client, admin_headers, db_session, verified_user,
        payment_for_refund,
    ):
        """
        Текущее окно: 300.00 refunded (now).
        Предыдущее окно: 100.00 refunded (10 дней назад) — в prev.
        delta_pct = (300 - 100) / 100 * 100 = +200.0.
        """
        from app.db.enum import RefundStatus
        from app.models.refund import Refund

        db_session.add(Refund(
            payment_id=payment_for_refund.id,
            amount=Decimal("300.00"),
            status=RefundStatus.COMPLETED,
            refunded_at=datetime.now(UTC) - timedelta(hours=1),
        ))
        db_session.add(Refund(
            payment_id=payment_for_refund.id,
            amount=Decimal("100.00"),
            status=RefundStatus.COMPLETED,
            refunded_at=datetime.now(UTC) - timedelta(days=10),
        ))
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        body = response.json()
        assert Decimal(body["refunds_total"]) == Decimal("300.00")
        assert Decimal(body["refunds_total_prev"]) == Decimal("100.00")
        assert body["refunds_total_delta_pct"] == 200.0

class TestDashboardSeries:
    @pytest.mark.asyncio
    async def test_series_requires_admin(self, client, auth_headers):
        response = await client.get(
            "/api/v1/admin/dashboard/series", headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_series_fills_empty_days(
        self, client, admin_headers
    ):
        """
        7 дней → 7 items, даже если заказов нет.
        Все revenue_gross = 0.00.
        """
        response = await client.get(
            "/api/v1/admin/dashboard/series?period_days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["period_days"] == 7
        assert len(body["items"]) == 7
        for item in body["items"]:
            assert item["orders_count"] == 0
            assert Decimal(item["revenue_gross"]) == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_series_groups_by_day(
        self, client, admin_headers, db_session, verified_user, address
    ):
        """
        Заказ сегодня (paid, 500) + заказ вчера (pending, 100).
        Сегодня: orders_count=1, revenue_gross=500.
        Вчера: orders_count=1, revenue_gross=0 (pending не в revenue).
        Остальные дни — нули.
        """
        now = datetime.now(UTC)
        db_session.add(Order(
            user_id=verified_user.id, total=Decimal("500.00"),
            status=OrderStatus.PAID, shipping_address_id=address.id,
            created_at=now - timedelta(hours=1),
        ))
        db_session.add(Order(
            user_id=verified_user.id, total=Decimal("100.00"),
            status=OrderStatus.PENDING, shipping_address_id=address.id,
            created_at=now - timedelta(days=1),
        ))
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/dashboard/series?period_days=7",
            headers=admin_headers,
        )
        body = response.json()
        assert len(body["items"]) == 7

        # Сегодня — последний элемент
        today = body["items"][-1]
        assert today["orders_count"] == 1
        assert Decimal(today["revenue_gross"]) == Decimal("500.00")

        # Вчера — предпоследний
        yesterday = body["items"][-2]
        assert yesterday["orders_count"] == 1
        assert Decimal(yesterday["revenue_gross"]) == Decimal("0.00")

        # Первые 5 дней — нули
        for item in body["items"][:-2]:
            assert item["orders_count"] == 0

class TestDashboardCache:
    @pytest.mark.asyncio
    async def test_dashboard_miss_then_hit(
        self, client, admin_headers, mock_cache
    ):
        mock_cache._storage.clear()

        r1 = await client.get(
            "/api/v1/admin/dashboard", headers=admin_headers,
        )
        assert r1.status_code == 200
        assert r1.headers["X-Cache"] == "MISS"

        r2 = await client.get(
            "/api/v1/admin/dashboard", headers=admin_headers,
        )
        assert r2.status_code == 200
        assert r2.headers["X-Cache"] == "HIT"
        # JSON идентичен (Decimal сохраняется как str в обоих случаях)
        assert r1.json() == r2.json()

    @pytest.mark.asyncio
    async def test_dashboard_cache_per_period(
        self, client, admin_headers, mock_cache
    ):
        """Разные period_days → разные ключи → оба MISS."""
        mock_cache._storage.clear()

        r7 = await client.get(
            "/api/v1/admin/dashboard?period_days=7", headers=admin_headers,
        )
        r30 = await client.get(
            "/api/v1/admin/dashboard?period_days=30", headers=admin_headers,
        )
        assert r7.headers["X-Cache"] == "MISS"
        assert r30.headers["X-Cache"] == "MISS"
        assert len(mock_cache._storage) == 2

    @pytest.mark.asyncio
    async def test_series_miss_then_hit(
        self, client, admin_headers, mock_cache
    ):
        mock_cache._storage.clear()

        r1 = await client.get(
            "/api/v1/admin/dashboard/series", headers=admin_headers,
        )
        assert r1.headers["X-Cache"] == "MISS"

        r2 = await client.get(
            "/api/v1/admin/dashboard/series", headers=admin_headers,
        )
        assert r2.headers["X-Cache"] == "HIT"
        assert r1.json() == r2.json()

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_query_db(
        self, client, admin_headers, mock_cache, db_session
    ):
        """
        Второй запрос (HIT) не должен ходить в БД.

        Эмулируем: очищаем таблицу orders между запросами — HIT должен
        вернуть старые данные (из кэша), а не упасть / не отдать пусто.
        """
        mock_cache._storage.clear()

        r1 = await client.get(
            "/api/v1/admin/dashboard", headers=admin_headers,
        )
        assert r1.headers["X-Cache"] == "MISS"

        # «Портим» данные в БД — если бы HIT ходил в БД, ответ изменился бы
        from sqlalchemy import delete

        from app.models.order import Order
        await db_session.execute(delete(Order))
        await db_session.flush()

        r2 = await client.get(
            "/api/v1/admin/dashboard", headers=admin_headers,
        )
        assert r2.headers["X-Cache"] == "HIT"
        assert r1.json() == r2.json()   # те же данные, что в кэше


class TestDashboardCsvExport:
    @pytest.mark.asyncio
    async def test_export_requires_admin(self, client, auth_headers):
        response = await client.get(
            "/api/v1/admin/dashboard/export.csv", headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_export_content_type_and_disposition(
        self, client, admin_headers
    ):
        response = await client.get(
            "/api/v1/admin/dashboard/export.csv?period_days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert "shopflow-dashboard-7d.csv" in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_export_csv_structure(
        self, client, admin_headers
    ):
        response = await client.get(
            "/api/v1/admin/dashboard/export.csv?period_days=7",
            headers=admin_headers,
        )
        text = response.text
        lines = text.strip().splitlines()

        # Header
        assert lines[0] == "Section,Metric,Value"

        # Summary block
        assert any("Summary,Period (days),7" in line for line in lines)
        assert any("Summary,Orders count," in line for line in lines)
        assert any("Summary,Revenue gross," in line for line in lines)

        # Top products header
        assert any("Top products,Rank,Name,Quantity,Revenue" in line for line in lines)