# tests/test_review_service.py
"""
Сервисные тесты review_service.

Проверяют:
- get_reviewable_order: поиск последнего delivered-заказа;
- create_review: все проверки (товар, delivered, дубликат);
- list_product_reviews: сортировка, фильтрация soft-deleted;
- get_product_summary: avg, total, distribution, пустой случай;
- soft_delete_review: deleted_at, повторное создание возможно.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from app.core.exceptions import ConflictError
from app.db.enum import OrderStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.review import Review
from app.schemas.review import ReviewCreate
from app.services import review_service
from fastapi import HTTPException
from sqlalchemy import select

# ============================================================
#  get_reviewable_order
# ============================================================

class TestGetReviewableOrder:
    """Поиск delivered-заказа с товаром."""

    @pytest.mark.asyncio
    async def test_finds_delivered(
        self, db_session, verified_user, product, delivered_order
    ):
        order = await review_service.get_reviewable_order(
            db_session, verified_user.id, product.id
        )
        assert order is not None
        assert order.id == delivered_order.id

    @pytest.mark.asyncio
    async def test_returns_none_for_pending(
        self, db_session, verified_user, product, address
    ):
        """Order в статусе pending — не reviewable."""
        o = Order(
            user_id=verified_user.id,
            total=Decimal("1000.00"),
            status=OrderStatus.PENDING,
            shipping_address_id=address.id,
        )
        db_session.add(o)
        await db_session.flush()
        db_session.add(OrderItem(
            order_id=o.id, product_id=product.id,
            product_cost=Decimal("1000.00"), product_count=1,
        ))
        await db_session.flush()

        order = await review_service.get_reviewable_order(
            db_session, verified_user.id, product.id
        )
        assert order is None

    @pytest.mark.asyncio
    async def test_returns_none_for_other_product(
        self, db_session, verified_user, category, delivered_order
    ):
        """Delivered-заказ без этого товара."""
        from app.models.product import Product
        other = Product(
            name="Other", description="Test",
            cost=Decimal("100.00"), category_id=category.id,
        )
        db_session.add(other)
        await db_session.flush()

        order = await review_service.get_reviewable_order(
            db_session, verified_user.id, other.id
        )
        assert order is None

    @pytest.mark.asyncio
    async def test_returns_latest_when_multiple(
        self, db_session, verified_user, product, address
    ):
        """Несколько delivered — вернуть последний (по created_at DESC)."""
        import asyncio
        orders = []
        for _ in range(3):
            o = Order(
                user_id=verified_user.id,
                total=Decimal("1000.00"),
                status=OrderStatus.DELIVERED,
                shipping_address_id=address.id,
            )
            db_session.add(o)
            await db_session.flush()
            db_session.add(OrderItem(
                order_id=o.id, product_id=product.id,
                product_cost=Decimal("1000.00"), product_count=1,
            ))
            await db_session.flush()
            orders.append(o)
            await asyncio.sleep(0.01)

        order = await review_service.get_reviewable_order(
            db_session, verified_user.id, product.id
        )
        assert order is not None
        assert order.id == orders[-1].id


# ============================================================
#  create_review
# ============================================================

class TestCreateReview:
    """Создание отзыва."""

    @pytest.mark.asyncio
    async def test_happy_path(
        self, db_session, verified_user, delivered_order, product
    ):
        data = ReviewCreate(product_id=product.id, rating=5,
                            title="Great", comment="Very good")
        review = await review_service.create_review(
            db_session, verified_user, data
        )
        assert review.id is not None
        assert review.public_id is not None
        assert review.rating == 5
        assert review.is_verified is True   # ✅ Всегда True
        assert review.order_id == delivered_order.id

    @pytest.mark.asyncio
    async def test_product_not_found_404(
        self, db_session, verified_user
    ):
        data = ReviewCreate(product_id=999999, rating=5)
        with pytest.raises(HTTPException) as exc:
            await review_service.create_review(db_session, verified_user, data)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "product_not_found"

    @pytest.mark.asyncio
    async def test_no_delivered_order_403(
        self, db_session, verified_user, product
    ):
        """Без delivered-заказа — 403."""
        data = ReviewCreate(product_id=product.id, rating=5)
        with pytest.raises(HTTPException) as exc:
            await review_service.create_review(db_session, verified_user, data)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "no_delivered_order"

    @pytest.mark.asyncio
    async def test_soft_deleted_product_404(
        self, db_session, verified_user, product, delivered_order
    ):
        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        data = ReviewCreate(product_id=product.id, rating=5)
        with pytest.raises(HTTPException) as exc:
            await review_service.create_review(db_session, verified_user, data)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_already_reviewed_409(
        self, db_session, verified_user, product, delivered_order, review
    ):
        """Активный отзыв уже есть → 409."""
        data = ReviewCreate(product_id=product.id, rating=3)
        with pytest.raises(ConflictError) as exc:
            await review_service.create_review(db_session, verified_user, data)
        assert exc.value.status_code == 409
        assert exc.value.code == "already_reviewed"

    @pytest.mark.asyncio
    async def test_review_after_soft_delete_allowed(
        self, db_session, verified_user, product, delivered_order, review
    ):
        """Soft-deleted отзыв → можно создать новый."""
        review.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        data = ReviewCreate(product_id=product.id, rating=3)
        new_review = await review_service.create_review(
            db_session, verified_user, data
        )
        assert new_review.id != review.id
        assert new_review.rating == 3


# ============================================================
#  list_product_reviews
# ============================================================

class TestListProductReviews:
    """Список отзывов."""

    @pytest.mark.asyncio
    async def test_empty(self, db_session, product):
        items, total = await review_service.list_product_reviews(
            db_session, product.id
        )
        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_excludes_soft_deleted(
        self, db_session, product, review
    ):
        review.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        items, total = await review_service.list_product_reviews(
            db_session, product.id
        )
        assert total == 0

    @pytest.mark.asyncio
    async def test_sort_by_rating_desc(
        self, db_session, verified_user, product, delivered_order, admin_user, address
    ):
        """Сортировка по rating desc."""
        # admin_user тоже должен иметь delivered-заказ на product
        o = Order(
            user_id=admin_user.id,
            total=Decimal("1000.00"),
            status=OrderStatus.DELIVERED,
            shipping_address_id=address.id,
        )
        db_session.add(o)
        await db_session.flush()
        db_session.add(OrderItem(
            order_id=o.id, product_id=product.id,
            product_cost=Decimal("1000.00"), product_count=1,
        ))
        await db_session.flush()

        db_session.add(Review(
            user_id=verified_user.id, product_id=product.id,
            order_id=delivered_order.id, rating=3, is_verified=True,
        ))
        db_session.add(Review(
            user_id=admin_user.id, product_id=product.id,
            order_id=o.id, rating=5, is_verified=True,
        ))
        await db_session.flush()

        items, total = await review_service.list_product_reviews(
            db_session, product.id, sort_by="rating", sort_order="desc"
        )
        assert total == 2
        assert items[0].rating == 5
        assert items[1].rating == 3


# ============================================================
#  get_product_summary
# ============================================================

class TestGetProductSummary:
    """Агрегат."""

    @pytest.mark.asyncio
    async def test_empty_summary(self, db_session, product):
        summary = await review_service.get_product_summary(
            db_session, product.id
        )
        assert summary.avg_rating == 0.0
        assert summary.total_count == 0
        assert summary.distribution == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    @pytest.mark.asyncio
    async def test_summary_with_reviews(
        self, db_session, verified_user, admin_user, product,
        delivered_order, address
    ):
        """avg=4.0, total=2, distribution — все ключи."""
        o = Order(
            user_id=admin_user.id,
            total=Decimal("1000.00"),
            status=OrderStatus.DELIVERED,
            shipping_address_id=address.id,
        )
        db_session.add(o)
        await db_session.flush()
        db_session.add(OrderItem(
            order_id=o.id, product_id=product.id,
            product_cost=Decimal("1000.00"), product_count=1,
        ))
        await db_session.flush()

        db_session.add(Review(
            user_id=verified_user.id, product_id=product.id,
            order_id=delivered_order.id, rating=3, is_verified=True,
        ))
        db_session.add(Review(
            user_id=admin_user.id, product_id=product.id,
            order_id=o.id, rating=5, is_verified=True,
        ))
        await db_session.flush()

        summary = await review_service.get_product_summary(
            db_session, product.id
        )
        assert summary.avg_rating == 4.0
        assert summary.total_count == 2
        assert summary.distribution[3] == 1
        assert summary.distribution[5] == 1
        assert summary.distribution[1] == 0


# ============================================================
#  soft_delete_review
# ============================================================

class TestSoftDeleteReview:
    """Soft-delete."""

    @pytest.mark.asyncio
    async def test_sets_deleted_at(self, db_session, review):
        assert review.deleted_at is None
        await review_service.soft_delete_review(db_session, review)
        await db_session.refresh(review)
        assert review.deleted_at is not None

    @pytest.mark.asyncio
    async def test_other_reviews_unaffected(
        self, db_session, verified_user, admin_user, product,
        delivered_order, address, review
    ):
        """Soft-delete review не трогает другие отзывы."""
        o = Order(
            user_id=admin_user.id,
            total=Decimal("1000.00"),
            status=OrderStatus.DELIVERED,
            shipping_address_id=address.id,
        )
        db_session.add(o)
        await db_session.flush()
        db_session.add(OrderItem(
            order_id=o.id, product_id=product.id,
            product_cost=Decimal("1000.00"), product_count=1,
        ))
        await db_session.flush()

        other = Review(
            user_id=admin_user.id, product_id=product.id,
            order_id=o.id, rating=4, is_verified=True,
        )
        db_session.add(other)
        await db_session.flush()

        await review_service.soft_delete_review(db_session, review)
        await db_session.refresh(other)
        assert other.deleted_at is None