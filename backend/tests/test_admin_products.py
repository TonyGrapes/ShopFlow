"""Тесты /api/v1/admin/products."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.order_item import OrderItem
from app.models.product import Product


class TestAdminProductsList:
    @pytest.mark.asyncio
    async def test_list_includes_soft_deleted(
        self, client, admin_headers, db_session, category
    ):
        from datetime import UTC, datetime
        active = Product(
            name="Active", description="Test", cost=Decimal("100.00"),
            category_id=category.id,
        )
        deleted = Product(
            name="Deleted", description="Test", cost=Decimal("200.00"),
            category_id=category.id, deleted_at=datetime.now(UTC),
        )
        db_session.add_all([active, deleted])
        await db_session.flush()

        response = await client.get("/api/v1/admin/products", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        response = await client.get("/api/v1/admin/products")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_customer_403(self, client, auth_headers):
        response = await client.get("/api/v1/admin/products", headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_moderator_ok(self, client, db_session):
        from app.core.security import create_access_token, hash_password
        from app.db.enum import UserRole, UserStatus
        from app.models.user import User as UserModel

        mod = UserModel(
            email="mod@example.com",
            password_hash=hash_password("mod-password-1"),
            first_name="M", last_name="U", phone_number="+79990000050",
            role=UserRole.MODERATOR, status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        db_session.add(mod)
        await db_session.flush()
        await db_session.refresh(mod)

        headers = {"Authorization": f"Bearer {create_access_token(str(mod.public_id))}"}
        response = await client.get("/api/v1/admin/products", headers=headers)
        assert response.status_code == 200


class TestAdminProductsDelete:
    @pytest.mark.asyncio
    async def test_hard_delete_no_orders(
        self, client, admin_headers, db_session, product
    ):
        response = await client.delete(
            f"/api/v1/admin/products/{product.id}", headers=admin_headers,
        )
        assert response.status_code == 204

        found = (await db_session.execute(
            select(Product).where(Product.id == product.id)
        )).scalar_one_or_none()
        assert found is None   # hard, не soft

    @pytest.mark.asyncio
    async def test_hard_delete_blocked_by_order_items(
        self, client, admin_headers, db_session, product, order, address,
        verified_user,
    ):
        """Товар в заказе → 409 product_has_orders."""
        # product уже в order.items? Проверим — фикстура order создаёт OrderItem.
        # На всякий случай явно создадим ещё один, если фикстура не гарантирует.
        oi = (await db_session.execute(
            select(OrderItem).where(OrderItem.product_id == product.id)
        )).scalar_one_or_none()
        if oi is None:
            db_session.add(OrderItem(
                order_id=order.id, product_id=product.id,
                product_cost=Decimal("100.00"), product_count=1,
            ))
            await db_session.flush()

        response = await client.delete(
            f"/api/v1/admin/products/{product.id}", headers=admin_headers,
        )
        assert response.status_code == 409
        assert response.json()["code"] == "product_has_orders"

    @pytest.mark.asyncio
    async def test_hard_delete_customer_403(
        self, client, auth_headers, product
    ):
        response = await client.delete(
            f"/api/v1/admin/products/{product.id}", headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_hard_delete_moderator_403(
        self, client, db_session, product
    ):
        """MODERATOR не может hard-delete (только ADMIN)."""
        from app.core.security import create_access_token, hash_password
        from app.db.enum import UserRole, UserStatus
        from app.models.user import User as UserModel

        mod = UserModel(
            email="mod2@example.com",
            password_hash=hash_password("mod-password-2"),
            first_name="M", last_name="U", phone_number="+79990000051",
            role=UserRole.MODERATOR, status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        db_session.add(mod)
        await db_session.flush()
        await db_session.refresh(mod)

        headers = {"Authorization": f"Bearer {create_access_token(str(mod.public_id))}"}
        response = await client.delete(
            f"/api/v1/admin/products/{product.id}", headers=headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_hard_delete_missing_404(
        self, client, admin_headers
    ):
        response = await client.delete(
            "/api/v1/admin/products/999999", headers=admin_headers,
        )
        assert response.status_code == 404


class TestAdminProductsCreateUpdate:
    @pytest.mark.asyncio
    async def test_create_ok(
        self, client, admin_headers, category
    ):
        response = await client.post(
            "/api/v1/admin/products",
            json={
                "name": "Admin Created",
                "description": "Test",
                "cost": "100.00",
                "category_id": category.id,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_patch_ok(
        self, client, admin_headers, product
    ):
        response = await client.patch(
            f"/api/v1/admin/products/{product.id}",
            json={"name": "Renamed Admin"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed Admin"