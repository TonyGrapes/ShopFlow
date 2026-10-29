"""
HTTP-тесты отзывов.

Проверяют:
- публичный доступ к GET .../reviews и .../summary;
- POST /reviews: auth, 404, 403, 409, 201;
- DELETE /reviews/{public_id}: soft-delete, ownership (404 чужой);
- DELETE /admin/reviews/{public_id}: RBAC, soft-delete любого.
"""
from datetime import UTC, datetime

import pytest

from app.models.review import Review

# ============================================================
#  GET /products/{id}/reviews
# ============================================================

class TestListReviewsEndpoint:
    """Публичный список отзывов."""

    @pytest.mark.asyncio
    async def test_empty_list(self, client, product):
        response = await client.get(f"/api/v1/products/{product.id}/reviews")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_review(self, client, product, review):
        response = await client.get(f"/api/v1/products/{product.id}/reviews")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["public_id"] == str(review.public_id)
        assert item["rating"] == 5
        assert item["is_verified"] is True
        # Публичный профиль автора без email/phone
        assert item["user"]["public_id"] is not None
        assert "email" not in item["user"]
        assert "phone_number" not in item["user"]

    @pytest.mark.asyncio
    async def test_soft_deleted_excluded(
        self, client, db_session, product, review
    ):
        review.deleted_at = datetime.now(UTC)
        await db_session.flush()

        response = await client.get(f"/api/v1/products/{product.id}/reviews")
        assert response.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_public_no_auth(self, client, product, review):
        """Доступно без токена."""
        response = await client.get(f"/api/v1/products/{product.id}/reviews")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_sort_returns_422(self, client, product):
        response = await client.get(
            f"/api/v1/products/{product.id}/reviews?sort_by=hacked"
        )
        assert response.status_code == 422


# ============================================================
#  GET /products/{id}/reviews/summary
# ============================================================

class TestSummaryEndpoint:
    """Агрегат отзывов."""

    @pytest.mark.asyncio
    async def test_empty_summary(self, client, product):
        response = await client.get(
            f"/api/v1/products/{product.id}/reviews/summary"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["avg_rating"] == 0.0
        assert body["total_count"] == 0
        # Все 5 ключей в distribution (Pydantic сериализует int-ключи как строки)
        assert set(body["distribution"].keys()) == {"1", "2", "3", "4", "5"}

    @pytest.mark.asyncio
    async def test_summary_with_one_review(
        self, client, product, review
    ):
        response = await client.get(
            f"/api/v1/products/{product.id}/reviews/summary"
        )
        body = response.json()
        assert body["avg_rating"] == 5.0
        assert body["total_count"] == 1
        assert body["distribution"]["5"] == 1


# ============================================================
#  POST /reviews
# ============================================================

class TestCreateReviewEndpoint:
    """Создание отзыва."""

    @pytest.mark.asyncio
    async def test_create_happy(
        self, client, auth_headers, product, delivered_order
    ):
        response = await client.post(
            "/api/v1/reviews",
            json={
                "product_id": product.id,
                "rating": 5,
                "title": "Great",
                "comment": "Very good",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["rating"] == 5
        assert body["is_verified"] is True
        assert body["title"] == "Great"
        assert body["user"]["public_id"] is not None

    @pytest.mark.asyncio
    async def test_create_without_auth_401(self, client, product, delivered_order):
        response = await client.post(
            "/api/v1/reviews",
            json={"product_id": product.id, "rating": 5},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_without_delivered_403(
        self, client, auth_headers, product
    ):
        response = await client.post(
            "/api/v1/reviews",
            json={"product_id": product.id, "rating": 5},
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "no_delivered_order"

    @pytest.mark.asyncio
    async def test_create_product_not_found_404(
        self, client, auth_headers
    ):
        response = await client.post(
            "/api/v1/reviews",
            json={"product_id": 999999, "rating": 5},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_409(
        self, client, auth_headers, product, delivered_order, review
    ):
        """Активный отзыв уже есть."""
        response = await client.post(
            "/api/v1/reviews",
            json={"product_id": product.id, "rating": 3},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["code"] == "already_reviewed"

    @pytest.mark.asyncio
    async def test_create_invalid_rating_422(
        self, client, auth_headers, product, delivered_order
    ):
        """rating=6 → 422 от Pydantic."""
        response = await client.post(
            "/api/v1/reviews",
            json={"product_id": product.id, "rating": 6},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_rejects_extra_fields(
        self, client, auth_headers, product, delivered_order
    ):
        response = await client.post(
            "/api/v1/reviews",
            json={"product_id": product.id, "rating": 5, "hacker": "field"},
            headers=auth_headers,
        )
        assert response.status_code == 422


# ============================================================
#  DELETE /reviews/{public_id}
# ============================================================

class TestDeleteOwnReviewEndpoint:
    """Soft-delete свой."""

    @pytest.mark.asyncio
    async def test_delete_own(
        self, client, db_session, auth_headers, review
    ):
        response = await client.delete(
            f"/api/v1/reviews/{review.public_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        await db_session.refresh(review)
        assert review.deleted_at is not None   # soft, не hard

    @pytest.mark.asyncio
    async def test_delete_foreign_404(
        self, client, auth_headers, db_session, admin_user, product,
        address, category
    ):
        """
        Чужой отзыв → 404.

        Создаём отзыв через admin_user, пробуем удалить через verified_user
        (auth_headers).
        """
        from decimal import Decimal as D

        from app.db.enum import OrderStatus
        from app.models.order import Order
        from app.models.order_item import OrderItem

        o = Order(
            user_id=admin_user.id, total=D("1000.00"),
            status=OrderStatus.DELIVERED,
            shipping_address_id=address.id,
        )
        db_session.add(o)
        await db_session.flush()
        db_session.add(OrderItem(
            order_id=o.id, product_id=product.id,
            product_cost=D("1000.00"), product_count=1,
        ))
        await db_session.flush()

        foreign = Review(
            user_id=admin_user.id, product_id=product.id,
            order_id=o.id, rating=4, is_verified=True,
        )
        db_session.add(foreign)
        await db_session.flush()

        response = await client.delete(
            f"/api/v1/reviews/{foreign.public_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_requires_auth(self, client, review):
        response = await client.delete(f"/api/v1/reviews/{review.public_id}")
        assert response.status_code == 401


# ============================================================
#  DELETE /admin/reviews/{public_id}
# ============================================================

class TestAdminDeleteReview:
    """Админское удаление."""

    @pytest.mark.asyncio
    async def test_admin_can_delete_any(
        self, client, admin_headers, db_session, review
    ):
        response = await client.delete(
            f"/api/v1/admin/reviews/{review.public_id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

        await db_session.refresh(review)
        assert review.deleted_at is not None   # soft

    @pytest.mark.asyncio
    async def test_customer_cannot_delete(
        self, client, auth_headers, review
    ):
        response = await client.delete(
            f"/api/v1/admin/reviews/{review.public_id}",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_requires_auth(self, client, review):
        response = await client.delete(
            f"/api/v1/admin/reviews/{review.public_id}"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_review_404(self, client, admin_headers):
        response = await client.delete(
            "/api/v1/admin/reviews/00000000-0000-0000-0000-000000000000",
            headers=admin_headers,
        )
        assert response.status_code == 404