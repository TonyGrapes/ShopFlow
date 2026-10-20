# tests/test_concurrency.py
"""
Тесты на race-условия.

ВАЖНО: используют РЕАЛЬНЫЕ независимые сессии (не savepoint-фикстуры).
Savepoint-изоляция видит одну транзакцию — race-тесты в ней вакуумные.

Маркер @pytest.mark.integration — отдельный прогон (см. test_auth_integration.py).
"""
import asyncio
from decimal import Decimal

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.enum import OrderStatus, ProductStatus, UserRole, UserStatus
from app.models.address import Address
from app.models.cart_item import CartItem
from app.models.category import Category
from app.models.order import Order
from app.models.product import Product
from app.models.user import User as UserModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = get_settings().database_url


@pytest_asyncio.fixture(scope="function")
async def race_engine():
    """
    Отдельный движок для race-тестов.

    НЕ использует conftest.engine — там savepoint-изоляция.
    Каждый тест — чистая схема (create_all / drop_all).
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS ltree'))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def race_factory(race_engine):
    """Фабрика независимых сессий."""
    return async_sessionmaker(
        race_engine, class_=AsyncSession, expire_on_commit=False,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_order_creation_one_wins(race_factory):
    """
    ✅ RACE-01: два параллельных create_order_from_cart из одной корзины.

    Ожидание:
    - Один создаёт Order.
    - Второй получает ValidationError(empty_cart).
    - В БД ровно 1 Order.
    - cart_items пуст.
    """
    from app.core.exceptions import ValidationError
    from app.services.order_service import create_order_from_cart

    # ── Подготовка ────────────────────────────────────
    async with race_factory() as setup:
        category = Category(path="electronics", category_name="Electronics")
        setup.add(category)
        await setup.flush()

        product = Product(
            name="Laptop",
            description="Test",
            cost=Decimal("1000.00"),
            category_id=category.id,
            status=ProductStatus.AVAILABLE,
        )
        setup.add(product)
        await setup.flush()

        user = UserModel(
            email="race-order@example.com",
            password_hash=hash_password("race-pass-1234"),
            first_name="Race",
            last_name="User",
            phone_number="+79990000001",
            role=UserRole.CUSTOMER,
            status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        setup.add(user)
        await setup.flush()

        address = Address(
            user_id=user.id,
            address_line1="Race st, 1",
            city="Moscow",
            postal_code="101000",
            country="RU",
            is_default=True,
        )
        setup.add(address)
        await setup.flush()

        cart = CartItem(
            user_id=user.id,
            product_id=product.id,
            quantity=1,
            product_cost=product.cost,
        )
        setup.add(cart)
        await setup.flush()

        await setup.commit()

        user_id = user.id
        address_id = address.id

    # ── Два параллельных вызова ──────────────────────
    async def _create():
        async with race_factory() as session:
            user_obj = await session.get(UserModel, user_id)
            try:
                order = await create_order_from_cart(session, user_obj, address_id)
                await session.commit()
                return ("success", order.id)
            except ValidationError as e:
                await session.rollback()
                return ("conflict", e.code)

    r1, r2 = await asyncio.gather(_create(), _create())

    statuses = sorted([r1[0], r2[0]])
    assert statuses == ["conflict", "success"], f"Expected one success one conflict, got {r1}, {r2}"

    conflict = r1 if r1[0] == "conflict" else r2
    assert conflict[1] == "empty_cart", f"Expected empty_cart, got {conflict}"

    # ── Проверка БД ────────────────────────────────────
    async with race_factory() as check:
        orders = (await check.execute(
            select(Order).where(Order.user_id == user_id)
        )).scalars().all()
        assert len(orders) == 1, f"Expected 1 order, got {len(orders)}"

        cart_items = (await check.execute(
            select(CartItem).where(CartItem.user_id == user_id)
        )).scalars().all()
        assert cart_items == [], f"Expected empty cart, got {len(cart_items)}"