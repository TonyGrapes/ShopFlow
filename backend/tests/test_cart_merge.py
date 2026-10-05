# tests/test_cart_merge.py
"""
Тесты объединения корзин при логине: merge_guest_cart_into_user.

Проверяют:
- max(quantity) — берём большее количество;
- из БД больше → оставляем из БД;
- из гостя больше → обновляем БД;
- позиция только у гостя → добавляется в БД;
- позиция только в БД → не трогается;
- soft-deleted товар у гостя → warning, не добавляется;
- товар out_of_stock у гостя → warning, но добавляется (пользователь решает);
- конфликт цен → warning, снимок остаётся из БД (более старый);
- пустая гостевая корзина → no-op без ошибок;
- guest-cart НЕ удаляется из Redis самим merge (это BackgroundTask после commit).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.cart_item import CartItem
from app.models.product import Product
from app.services.cart_service import merge_guest_cart_into_user


async def _prepare_guest_cart(store, session_id, product, quantity):
    """Хелпер: наполнить guest-cart через реальный GuestCartStore."""
    await store.upsert_item(
        session_id=session_id,
        product_id=product.id,
        quantity_delta=quantity,
        product_cost=product.cost,
        max_items=100,
    )


class TestMergeMaxQuantity:
    """max(quantity) — ядро решения."""

    @pytest.mark.asyncio
    async def test_guest_empty_no_op(
        self, db_session, real_guest_store, verified_user
    ):
        """Пустая guest-cart → merge no-op, никаких ошибок."""
        sid = str(uuid.uuid4())
        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 0
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_guest_only_item_added_to_user(
        self, db_session, real_guest_store, product, verified_user
    ):
        """Товара у юзера нет, у гостя 3 → добавляется 3 в user-cart."""
        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, product, quantity=3)

        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 1
        assert result.warnings == []

        # Проверяем БД
        item = (await db_session.execute(
            select(CartItem).where(
                CartItem.user_id == verified_user.id,
                CartItem.product_id == product.id,
            )
        )).scalar_one()
        assert item.quantity == 3
        assert item.product_cost == product.cost

    @pytest.mark.asyncio
    async def test_guest_bigger_than_user(
        self, db_session, real_guest_store, product, verified_user
    ):
        """Гость 5, юзер 3 → оставляем 5 (max)."""
        # User уже имеет 3
        db_session.add(CartItem(
            user_id=verified_user.id,
            product_id=product.id,
            quantity=3,
            product_cost=product.cost,
        ))
        await db_session.flush()

        # Guest добавил 5
        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, product, quantity=5)

        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 1   # quantity изменилось

        item = (await db_session.execute(
            select(CartItem).where(
                CartItem.user_id == verified_user.id,
                CartItem.product_id == product.id,
            )
        )).scalar_one()
        assert item.quantity == 5

    @pytest.mark.asyncio
    async def test_user_bigger_than_guest(
        self, db_session, real_guest_store, product, verified_user
    ):
        """Гость 3, юзер 5 → оставляем 5 (max)."""
        db_session.add(CartItem(
            user_id=verified_user.id,
            product_id=product.id,
            quantity=5,
            product_cost=product.cost,
        ))
        await db_session.flush()

        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, product, quantity=3)

        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 0   # quantity НЕ изменилось

        item = (await db_session.execute(
            select(CartItem).where(
                CartItem.user_id == verified_user.id,
                CartItem.product_id == product.id,
            )
        )).scalar_one()
        assert item.quantity == 5

    @pytest.mark.asyncio
    async def test_merge_multiple_items(
        self, db_session, real_guest_store, category, verified_user
    ):
        """Несколько товаров в guest-cart: каждый обрабатывается независимо."""
        p1 = Product(name="P1", description="Test",
                     cost=Decimal("100.00"), category_id=category.id)
        p2 = Product(name="P2", description="Test",
                     cost=Decimal("200.00"), category_id=category.id)
        db_session.add_all([p1, p2])
        await db_session.flush()

        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, p1, quantity=2)
        await _prepare_guest_cart(real_guest_store, sid, p2, quantity=3)

        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 2

        items = (await db_session.execute(
            select(CartItem).where(CartItem.user_id == verified_user.id)
        )).scalars().all()
        quantities = {it.product_id: it.quantity for it in items}
        assert quantities == {p1.id: 2, p2.id: 3}


class TestMergeWarnings:
    """Warnings при проблемных позициях."""

    @pytest.mark.asyncio
    async def test_soft_deleted_product_warning(
        self, db_session, real_guest_store, product, verified_user
    ):
        """Soft-deleted товар: warning, позиция НЕ добавляется."""
        from datetime import datetime, timezone

        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, product, quantity=1)

        # Удаляем товар после добавления в guest-cart
        product.deleted_at = datetime.now(timezone.utc)
        await db_session.flush()

        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 0
        assert len(result.warnings) == 1
        assert "no longer available" in result.warnings[0].lower()

        # Позиции нет в БД
        item = (await db_session.execute(
            select(CartItem).where(
                CartItem.user_id == verified_user.id,
                CartItem.product_id == product.id,
            )
        )).scalar_one_or_none()
        assert item is None

    @pytest.mark.asyncio
    async def test_price_conflict_warning(
        self, db_session, real_guest_store, product, verified_user
    ):
        """
        Конфликт цен: guest_cost отличается от product_cost в БД.

        Позиция обновляется по max(quantity), но снимок цены
        остаётся из БД (более старый).
        """
        # User имеет позицию с ценой 999
        db_session.add(CartItem(
            user_id=verified_user.id,
            product_id=product.id,
            quantity=2,
            product_cost=Decimal("999.00"),
        ))
        await db_session.flush()

        # Guest добавил по текущей цене product.cost (1000.00)
        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, product, quantity=3)

        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 1   # quantity обновилось до 3
        # Warning о конфликте цен
        assert any("differs" in w.lower() for w in result.warnings)

        item = (await db_session.execute(
            select(CartItem).where(
                CartItem.user_id == verified_user.id,
                CartItem.product_id == product.id,
            )
        )).scalar_one()
        assert item.quantity == 3
        # Снимок цены остался старый (из БД)
        assert item.product_cost == Decimal("999.00")

    @pytest.mark.asyncio
    async def test_out_of_stock_product_warning(
        self, db_session, real_guest_store, product, verified_user
    ):
        """
        Товар out_of_stock у гостя: warning, но позиция ДОБАВЛЯЕТСЯ.

        Обоснование: статус может измениться, пользователь сам решит
        удалять или ждать. Каталог отдаёт is_available=false — UI покажет.
        """
        from app.db.enum import ProductStatus

        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, product, quantity=1)

        # Товар стал out_of_stock
        product.status = ProductStatus.OUTOFSTOCK
        await db_session.flush()

        result = await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )
        assert result.merged == 1
        assert any("out_of_stock" in w.lower() for w in result.warnings)


class TestMergeGuestCartNotCleared:
    """Merge НЕ удаляет guest-cart из Redis — это BackgroundTask в login."""

    @pytest.mark.asyncio
    async def test_guest_cart_still_exists_after_merge(
        self, db_session, real_guest_store, product, verified_user
    ):
        """
        После merge guest-cart в Redis остаётся.

        Удаление — задача BackgroundTask после commit в login.
        Это осознанный дизайн: если транзакция упадёт, гостевая
        корзина не потеряется.
        """
        sid = str(uuid.uuid4())
        await _prepare_guest_cart(real_guest_store, sid, product, quantity=2)

        await merge_guest_cart_into_user(
            db=db_session,
            guest_store=real_guest_store,
            session_id=sid,
            user_id=verified_user.id,
        )

        # Guest-cart всё ещё в Redis
        guest_cart = await real_guest_store.get(sid)
        assert len(guest_cart.items) == 1
        assert guest_cart.items[0].product_id == product.id