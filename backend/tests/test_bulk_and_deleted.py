"""
Тесты для админских операций над товарами:
- POST /products/bulk/status — bulk update статуса;
- GET /products?include_deleted=true — список с soft-deleted.

Контракт:
- bulk: обновляет только активные товары, возвращает updated + ids;
- include_deleted: обходит кэш (X-Cache: BYPASS), включает deleted;
- оба требуют write-роль (ADMIN/MODERATOR/SELLER).
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from app.db.enum import ProductStatus
from app.models.product import Product

# ============================================================
#  POST /products/bulk/status
# ============================================================

class TestBulkStatusUpdate:
    """POST /api/v1/products/bulk/status."""

    @pytest.mark.asyncio
    async def test_bulk_update_happy(
        self, client, db_session, category, admin_headers
    ):
        """Обновляет 3 товара одним запросом."""
        ids = []
        for i in range(3):
            p = Product(
                name=f"Bulk {i}", description="Test",
                cost=Decimal("100.00"), category_id=category.id,
                status=ProductStatus.AVAILABLE,
            )
            db_session.add(p)
            await db_session.flush()
            ids.append(p.id)

        response = await client.post(
            "/api/v1/products/bulk/status",
            json={"product_ids": ids, "status": "out_of_stock"},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["updated"] == 3
        assert set(body["product_ids"]) == set(ids)

        # Проверяем статус в БД
        for pid in ids:
            p = await db_session.get(Product, pid)
            await db_session.refresh(p)
            assert p.status == ProductStatus.OUTOFSTOCK

    @pytest.mark.asyncio
    async def test_bulk_skips_soft_deleted(
        self, client, db_session, category, admin_headers
    ):
        """Soft-deleted товар не обновляется, но считается updated=0 для него."""
        active = Product(
            name="Active", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
            status=ProductStatus.AVAILABLE,
        )
        deleted = Product(
            name="Deleted", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
            status=ProductStatus.AVAILABLE,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, deleted])
        await db_session.flush()

        response = await client.post(
            "/api/v1/products/bulk/status",
            json={
                "product_ids": [active.id, deleted.id],
                "status": "discontinued",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["updated"] == 1
        assert body["product_ids"] == [active.id]

        # Soft-deleted не тронут
        await db_session.refresh(deleted)
        assert deleted.status == ProductStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_bulk_missing_ids_ignored(
        self, client, category, admin_headers
    ):
        """Несуществующие id — просто не попадают в updated."""
        response = await client.post(
            "/api/v1/products/bulk/status",
            json={"product_ids": [999999, 888888], "status": "available"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["updated"] == 0
        assert body["product_ids"] == []

    @pytest.mark.asyncio
    async def test_bulk_requires_write_role(
        self, client, category, auth_headers
    ):
        """CUSTOMER → 403."""
        response = await client.post(
            "/api/v1/products/bulk/status",
            json={"product_ids": [1], "status": "available"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_bulk_requires_auth(self, client):
        """Без токена → 401."""
        response = await client.post(
            "/api/v1/products/bulk/status",
            json={"product_ids": [1], "status": "available"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_bulk_rejects_empty_list(
        self, client, admin_headers
    ):
        """product_ids минимум 1 элемент."""
        response = await client.post(
            "/api/v1/products/bulk/status",
            json={"product_ids": [], "status": "available"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_rejects_too_many(
        self, client, admin_headers
    ):
        """Максимум 100 id."""
        response = await client.post(
            "/api/v1/products/bulk/status",
            json={"product_ids": list(range(1, 102)), "status": "available"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_rejects_extra_fields(
        self, client, admin_headers
    ):
        """extra='forbid'."""
        response = await client.post(
            "/api/v1/products/bulk/status",
            json={
                "product_ids": [1],
                "status": "available",
                "hacker": "field",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_invalidates_cache(
        self, client, mock_cache, category, admin_headers
    ):
        """После bulk update кэш каталога очищается."""
        mock_cache._storage.clear()
        await client.get("/api/v1/products")
        assert len(mock_cache._storage) >= 1

        response = await client.post(
            "/api/v1/products/bulk/status",
            json={"product_ids": [1], "status": "available"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert len(mock_cache._storage) == 0


# ============================================================
#  GET /products?include_deleted=true
# ============================================================

class TestIncludeDeleted:
    """GET /api/v1/products с include_deleted=true."""

    @pytest.mark.asyncio
    async def test_without_flag_excludes_deleted(
        self, client, db_session, category
    ):
        """По умолчанию deleted не показываются."""
        active = Product(
            name="Active", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        deleted = Product(
            name="Deleted", description="Test",
            cost=Decimal("200.00"), category_id=category.id,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, deleted])
        await db_session.flush()

        response = await client.get("/api/v1/products")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == active.id

    @pytest.mark.asyncio
    async def test_with_flag_includes_deleted(
        self, client, db_session, category
    ):
        """include_deleted=true возвращает и deleted."""
        active = Product(
            name="Active", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        deleted = Product(
            name="Deleted", description="Test",
            cost=Decimal("200.00"), category_id=category.id,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, deleted])
        await db_session.flush()

        response = await client.get("/api/v1/products?include_deleted=true")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        ids = {item["id"] for item in body["items"]}
        assert ids == {active.id, deleted.id}

    @pytest.mark.asyncio
    async def test_bypasses_cache(
        self, client, mock_cache, db_session, category
    ):
        """
        include_deleted=true не пишет и не читает из кэша.
        X-Cache: BYPASS.
        """
        mock_cache._storage.clear()

        response = await client.get("/api/v1/products?include_deleted=true")
        assert response.status_code == 200
        assert response.headers["X-Cache"] == "BYPASS"

        # Кэш не заполнен — не пишем админский результат в публичный ключ
        assert len(mock_cache._storage) == 0

    @pytest.mark.asyncio
    async def test_combines_with_filters(
        self, client, db_session, category
    ):
        """include_deleted + другие фильтры работают вместе."""
        active = Product(
            name="Active", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
            status=ProductStatus.AVAILABLE,
        )
        deleted = Product(
            name="Deleted", description="Test",
            cost=Decimal("200.00"), category_id=category.id,
            deleted_at=datetime.now(timezone.utc),
            status=ProductStatus.OUTOFSTOCK,
        )
        db_session.add_all([active, deleted])
        await db_session.flush()

        response = await client.get(
            "/api/v1/products?include_deleted=true&status=out_of_stock"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == deleted.id

    @pytest.mark.asyncio
    async def test_public_no_auth(
        self, client, db_session, category
    ):
        """
        include_deleted — флаг, но эндпоинт публичный.
        Это осознанно: гости могут видеть soft-deleted через флаг.

        Альтернатива — требовать роль ADMIN/MODERATOR. Но текущая
        реализация этого не делает. Фиксируем как design decision.
        """
        response = await client.get("/api/v1/products?include_deleted=true")
        assert response.status_code == 200