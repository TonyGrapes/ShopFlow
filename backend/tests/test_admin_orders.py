# tests/test_admin_orders.py
"""
Тесты /api/v1/admin/orders.

Проверяют:
- RBAC: customer → 403;
- список всех заказов с фильтрами;
- смена статуса через state machine;
- 422 на недопустимый переход.
"""

import pytest

from app.db.enum import OrderStatus
from app.models.order import Order


class TestAdminOrdersRBAC:
    """RBAC: только admin/moderator."""

    @pytest.mark.asyncio
    async def test_list_requires_admin(self, client, auth_headers):
        """Customer → 403."""
        response = await client.get(
            "/api/v1/admin/orders", headers=auth_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_requires_admin(self, client, auth_headers, order):
        response = await client.get(
            f"/api/v1/admin/orders/{order.public_id}",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_status_requires_admin(
        self, client, auth_headers, order
    ):
        response = await client.patch(
            f"/api/v1/admin/orders/{order.public_id}/status",
            json={"status": "paid"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        response = await client.get("/api/v1/admin/orders")
        assert response.status_code == 401


class TestAdminOrdersList:
    """GET /api/v1/admin/orders."""

    @pytest.mark.asyncio
    async def test_list_all(
        self, client, admin_headers, order, db_session, verified_user, address
    ):
        from decimal import Decimal as D
        # Второй заказ (тоже verified_user, но другой)
        o2 = Order(
            user_id=verified_user.id,
            total=D("500.00"),
            status=OrderStatus.PAID,
            shipping_address_id=address.id,
        )
        db_session.add(o2)
        await db_session.flush()

        response = await client.get(
            "/api/v1/admin/orders", headers=admin_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(
        self, client, admin_headers, order, paid_order
    ):
        response = await client.get(
            "/api/v1/admin/orders?status=paid", headers=admin_headers
        )
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "paid"

    @pytest.mark.asyncio
    async def test_filter_by_user_id(
        self, client, admin_headers, order, verified_user
    ):
        response = await client.get(
            f"/api/v1/admin/orders?user_id={verified_user.id}",
            headers=admin_headers,
        )
        body = response.json()
        assert body["total"] == 1


class TestAdminOrdersGet:
    """GET /api/v1/admin/orders/{public_id}."""

    @pytest.mark.asyncio
    async def test_get_any_order(self, client, admin_headers, order):
        """Admin может смотреть любой заказ."""
        response = await client.get(
            f"/api/v1/admin/orders/{order.public_id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["public_id"] == str(order.public_id)

    @pytest.mark.asyncio
    async def test_get_missing_404(self, client, admin_headers):
        response = await client.get(
            "/api/v1/admin/orders/00000000-0000-0000-0000-000000000000",
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestAdminOrdersStatusUpdate:
    """PATCH /api/v1/admin/orders/{public_id}/status."""

    @pytest.mark.asyncio
    async def test_valid_transition_pending_to_paid(
        self, client, admin_headers, order, db_session
    ):
        response = await client.patch(
            f"/api/v1/admin/orders/{order.public_id}/status",
            json={"status": "paid"},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["status"] == "paid"

        await db_session.refresh(order)
        assert order.status == OrderStatus.PAID

    @pytest.mark.asyncio
    async def test_valid_transition_paid_to_shipped(
        self, client, admin_headers, paid_order, db_session
    ):
        response = await client.patch(
            f"/api/v1/admin/orders/{paid_order.public_id}/status",
            json={"status": "shipped"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "shipped"

    @pytest.mark.asyncio
    async def test_invalid_transition_delivered_to_paid(
        self, client, admin_headers, order, db_session
    ):
        """delivered → paid запрещён."""
        order.status = OrderStatus.DELIVERED
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/admin/orders/{order.public_id}/status",
            json={"status": "paid"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        body = response.json()["detail"]
        assert body["code"] == "invalid_transition"
        assert body["from"] == "delivered"
        assert body["to"] == "paid"

    @pytest.mark.asyncio
    async def test_invalid_transition_canceled_to_pending(
        self, client, admin_headers, order, db_session
    ):
        order.status = OrderStatus.CANCELED
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/admin/orders/{order.public_id}/status",
            json={"status": "pending"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_transition"

    @pytest.mark.asyncio
    async def test_patch_missing_order_404(self, client, admin_headers):
        response = await client.patch(
            "/api/v1/admin/orders/00000000-0000-0000-0000-000000000000/status",
            json={"status": "paid"},
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_rejects_invalid_status_value(
        self, client, admin_headers, order
    ):
        """Невалидный статус (не из enum) → 422 от Pydantic."""
        response = await client.patch(
            f"/api/v1/admin/orders/{order.public_id}/status",
            json={"status": "hacked"},
            headers=admin_headers,
        )
        assert response.status_code == 422