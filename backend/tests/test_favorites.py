# tests/test_favorites.py
"""
Тесты избранного: только для авторизованных.

Контракт:
- GET /favorites — список (soft-deleted товары отфильтрованы);
- POST /favorites — добавить (идемпотентно);
- DELETE /favorites/{product_id} — удалить (404 если нет);
- Без токена — 401.
"""
from datetime import UTC, datetime

import pytest


class TestAddFavorite:
    """POST /favorites."""

    @pytest.mark.asyncio
    async def test_add_and_list(self, cart_client, product, auth_headers):
        response = await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": product.id},
            headers=auth_headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["product_id"] == product.id
        assert body["product_name"] == product.name

        r2 = await cart_client.get("/api/v1/favorites", headers=auth_headers)
        assert r2.status_code == 200
        assert len(r2.json()) == 1
        assert r2.json()[0]["product_id"] == product.id

    @pytest.mark.asyncio
    async def test_add_is_idempotent(
        self, cart_client, product, auth_headers
    ):
        """Добавление дважды → одна запись в БД."""
        first = await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": product.id},
            headers=auth_headers,
        )
        assert first.status_code == 201

        second = await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": product.id},
            headers=auth_headers,
        )
        assert second.status_code == 201
        # id одинаковый — вернули существующую запись
        assert first.json()["id"] == second.json()["id"]

        r = await cart_client.get("/api/v1/favorites", headers=auth_headers)
        assert len(r.json()) == 1

    @pytest.mark.asyncio
    async def test_add_nonexistent_product_404(
        self, cart_client, auth_headers
    ):
        response = await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": 999999},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_soft_deleted_product_404(
        self, cart_client, db_session, product, auth_headers
    ):
        product.deleted_at = datetime.now(UTC)
        await db_session.flush()

        response = await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": product.id},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_requires_auth(self, cart_client, product):
        """Без токена → 401."""
        response = await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": product.id},
        )
        assert response.status_code == 401


class TestListFavorites:
    """GET /favorites."""

    @pytest.mark.asyncio
    async def test_empty_list(self, cart_client, auth_headers):
        response = await cart_client.get(
            "/api/v1/favorites", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_soft_deleted_hidden(
        self, cart_client, db_session, product, auth_headers
    ):
        """Soft-deleted товар не показывается в списке."""
        await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": product.id},
            headers=auth_headers,
        )

        product.deleted_at = datetime.now(UTC)
        await db_session.flush()

        response = await cart_client.get(
            "/api/v1/favorites", headers=auth_headers
        )
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, cart_client):
        response = await cart_client.get("/api/v1/favorites")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_order_by_created_desc(
        self, cart_client, db_session, category, auth_headers
    ):
        """Список отсортирован по created_at DESC (сначала новые)."""
        from datetime import datetime, timedelta
        from decimal import Decimal

        from sqlalchemy import select

        from app.models.favorite import Favorite
        from app.models.product import Product as ProductModel

        p1 = ProductModel(
            name="OrderP1", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        db_session.add(p1)
        await db_session.flush()

        p2 = ProductModel(
            name="OrderP2", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        db_session.add(p2)
        await db_session.flush()

        r1 = await cart_client.post(
            "/api/v1/favorites", json={"product_id": p1.id},
            headers=auth_headers,
        )
        assert r1.status_code == 201, r1.json()

        r2 = await cart_client.post(
            "/api/v1/favorites", json={"product_id": p2.id},
            headers=auth_headers,
        )
        assert r2.status_code == 201, r2.json()

        # ✅ Явно задаём created_at: p1 — раньше, p2 — позже.
        #    func.now() в одной транзакции даёт одно значение,
        #    поэтому сортировка "DESC" недетерминирована.
        now = datetime.now(UTC)
        f1 = (await db_session.execute(
            select(Favorite).where(Favorite.product_id == p1.id)
        )).scalar_one()
        f2 = (await db_session.execute(
            select(Favorite).where(Favorite.product_id == p2.id)
        )).scalar_one()

        f1.created_at = now - timedelta(seconds=10)
        f2.created_at = now
        await db_session.flush()

        r = await cart_client.get("/api/v1/favorites", headers=auth_headers)
        body = r.json()
        assert len(body) == 2, f"Expected 2, got {len(body)}: {body}"
        # ✅ Сначала новые: p2 (свежее) → p1 (старее)
        assert body[0]["product_id"] == p2.id
        assert body[1]["product_id"] == p1.id

class TestRemoveFavorite:
    """DELETE /favorites/{product_id}."""

    @pytest.mark.asyncio
    async def test_remove(self, cart_client, product, auth_headers):
        await cart_client.post(
            "/api/v1/favorites",
            json={"product_id": product.id},
            headers=auth_headers,
        )
        response = await cart_client.delete(
            f"/api/v1/favorites/{product.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        r = await cart_client.get("/api/v1/favorites", headers=auth_headers)
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_remove_nonexistent_404(
        self, cart_client, product, auth_headers
    ):
        response = await cart_client.delete(
            f"/api/v1/favorites/{product.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_requires_auth(self, cart_client, product):
        response = await cart_client.delete(
            f"/api/v1/favorites/{product.id}"
        )
        assert response.status_code == 401


class TestFavoritesIsolation:
    """Избранное разных пользователей изолировано."""

    @pytest.mark.asyncio
    async def test_customer_and_admin_isolated(
        self, cart_client, product, auth_headers, admin_headers
    ):
        await cart_client.post(
            "/api/v1/favorites", json={"product_id": product.id},
            headers=auth_headers,
        )

        r = await cart_client.get("/api/v1/favorites", headers=admin_headers)
        assert r.json() == []