# tests/test_order_service.py
"""
Тесты order_service: создание заказа из корзины, state machine,
ownership-фильтрация.

Сервисный уровень — быстрые тесты без HTTP overhead.
"""
from decimal import Decimal

import pytest
from app.core.exceptions import ValidationError
from app.db.enum import OrderStatus, ProductStatus
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.services import order_service
from app.services.order_service import validate_transition
from fastapi import HTTPException
from sqlalchemy import select


class TestCreateOrderFromCartHappyPath:
    """Успешное создание."""

    @pytest.mark.asyncio
    async def test_create_from_single_item(
        self, db_session, verified_user, address, product, cart_with_one_item
    ):
        order = await order_service.create_order_from_cart(
            db_session, verified_user, address.id
        )

        assert order.id is not None
        assert order.public_id is not None
        assert order.status == OrderStatus.PENDING
        assert order.user_id == verified_user.id
        assert order.shipping_address_id == address.id
        # total = product_cost(1000.00) * quantity(2) = 2000.00
        assert order.total == Decimal("2000.00")

        # Один order_item
        items = (await db_session.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )).scalars().all()
        assert len(items) == 1
        assert items[0].product_id == product.id
        assert items[0].product_count == 2
        assert items[0].product_cost == product.cost

        # Корзина очищена
        cart_count = (await db_session.execute(
            select(CartItem).where(CartItem.user_id == verified_user.id)
        )).scalars().all()
        assert cart_count == []

    @pytest.mark.asyncio
    async def test_create_from_two_items_total_correct(
        self, db_session, verified_user, address, cart_with_two_items
    ):
        order = await order_service.create_order_from_cart(
            db_session, verified_user, address.id
        )
        # Laptop 1000.00 * 2 = 2000.00, Mouse 50.00 * 3 = 150.00
        assert order.total == Decimal("2150.00")

        items = (await db_session.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )).scalars().all()
        assert len(items) == 2


class TestCreateOrderFromCartValidation:
    """Валидации при создании."""

    @pytest.mark.asyncio
    async def test_empty_cart_returns_422(
        self, db_session, verified_user, address
    ):
        with pytest.raises(ValidationError) as exc:
            await order_service.create_order_from_cart(
            db_session, verified_user, address.id
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "empty_cart"

    @pytest.mark.asyncio
    async def test_invalid_address_returns_422(
        self, db_session, verified_user, product, cart_with_one_item
    ):
        """Несуществующий address_id."""
        with pytest.raises(ValidationError) as exc:
            await order_service.create_order_from_cart(
            db_session, verified_user, 999999
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "invalid_address"

    @pytest.mark.asyncio
    async def test_foreign_address_returns_422(
        self, db_session, verified_user, address_for_admin, product, cart_with_one_item
    ):
        """Чужой адрес (принадлежит другому юзеру)."""
        with pytest.raises(ValidationError) as exc:
            await order_service.create_order_from_cart(
                db_session, verified_user, address_for_admin.id
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "invalid_address"

    @pytest.mark.asyncio
    async def test_soft_deleted_product_silently_skipped(
        self, db_session, verified_user, address, product, cart_with_one_item
    ):
        """
        Soft-deleted товар НЕ попадает в order, не блокирует заказ.

        Это согласовано с логикой корзины: read-фильтр отсеивает
        soft-deleted, поэтому позиция «невидима» для юзера.
        При создании заказа — тихо пропускается.
        """
        from datetime import datetime, timezone
        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        # Корзина теперь эффективно пуста → 422 empty_cart
        with pytest.raises(ValidationError) as exc:
            await order_service.create_order_from_cart(
                db_session, verified_user, address.id
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "empty_cart"

    @pytest.mark.asyncio
    async def test_out_of_stock_returns_422_with_errors(
        self, db_session, verified_user, address, product, cart_with_one_item
    ):
        """out_of_stock → 422 со списком проблемных позиций."""
        product.status = ProductStatus.OUTOFSTOCK
        await db_session.flush()

        with pytest.raises(ValidationError) as exc:
            await order_service.create_order_from_cart(
                db_session, verified_user, address.id
            )
        assert exc.value.status_code == 422
        assert exc.value.code == "cart_has_unavailable_items"
        errors = exc.value.extra["errors"]
        assert len(errors) == 1
        assert errors[0]["product_id"] == product.id
        assert errors[0]["reason"] == "out_of_stock"

    @pytest.mark.asyncio
    async def test_discontinued_returns_422(
        self, db_session, verified_user, address, product, cart_with_one_item
    ):
        product.status = ProductStatus.DISCONTINUED
        await db_session.flush()

        with pytest.raises(ValidationError) as exc:
            await order_service.create_order_from_cart(
                db_session, verified_user, address.id
            )
        assert exc.value.status_code == 422


class TestGetUserOrders:
    """Список и детали."""

    @pytest.mark.asyncio
    async def test_get_own_order(self, db_session, verified_user, order):
        fetched = await order_service.get_order_detail(
            db_session, verified_user.id, order.public_id
        )
        assert fetched is not None
        assert fetched.id == order.id

    @pytest.mark.asyncio
    async def test_get_foreign_order_returns_none(
        self, db_session, verified_user, admin_user, order
    ):
        """Чужой заказ — None (роутер вернёт 404)."""
        # order принадлежит verified_user, пробуем от admin_user
        fetched = await order_service.get_order_detail(
            db_session, admin_user.id, order.public_id
        )
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_orders_pagination(
        self, db_session, verified_user, address, product
    ):
        from decimal import Decimal

        for i in range(3):
            o = Order(
                user_id=verified_user.id,
                total=Decimal("100.00"),
                status=OrderStatus.PENDING,
                shipping_address_id=address.id,
            )
            db_session.add(o)
        await db_session.flush()

        orders, total = await order_service.get_user_orders(
            db_session, verified_user.id, page=1, page_size=2
        )
        assert total == 3
        assert len(orders) == 2


class TestStateMachine:
    """validate_transition — параметризованные тесты."""

    @pytest.mark.parametrize("current,new,should_pass", [
        (OrderStatus.PENDING, OrderStatus.PAID, True),
        (OrderStatus.PENDING, OrderStatus.CANCELED, True),
        (OrderStatus.PAID, OrderStatus.SHIPPED, True),
        (OrderStatus.PAID, OrderStatus.CANCELED, True),
        (OrderStatus.SHIPPED, OrderStatus.DELIVERED, True),
        (OrderStatus.SHIPPED, OrderStatus.CANCELED, True),
        (OrderStatus.DELIVERED, OrderStatus.PAID, False),
        (OrderStatus.DELIVERED, OrderStatus.CANCELED, False),
        (OrderStatus.CANCELED, OrderStatus.PENDING, False),
        (OrderStatus.CANCELED, OrderStatus.PAID, False),
        (OrderStatus.PAID, OrderStatus.PENDING, False),
        (OrderStatus.SHIPPED, OrderStatus.PAID, False),
    ])
    def test_transitions(self, current, new, should_pass):
        if should_pass:
            validate_transition(current, new)   # не должно упасть
        else:
            with pytest.raises(HTTPException) as exc:
                validate_transition(current, new)
            assert exc.value.status_code == 422
            assert exc.value.detail["code"] == "invalid_transition"


class TestUpdateOrderStatus:
    """Применение state machine."""

    @pytest.mark.asyncio
    async def test_valid_transition(self, db_session, order):
        updated = await order_service.update_order_status(
            db_session, order, OrderStatus.PAID
        )
        assert updated.status == OrderStatus.PAID

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, db_session, paid_order):
        with pytest.raises(HTTPException) as exc:
            await order_service.update_order_status(
                db_session, paid_order, OrderStatus.PENDING
            )
        assert exc.value.status_code == 422