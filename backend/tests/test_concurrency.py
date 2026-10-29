# tests/test_concurrency.py
"""
Тесты на race-условия.

ВАЖНО: используют РЕАЛЬНЫЕ независимые сессии (не savepoint-фикстуры).
Savepoint-изоляция видит одну транзакцию — race-тесты в ней вакуумные.

Маркер @pytest.mark.integration — отдельный прогон (см. test_auth_integration.py).
"""
import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.core.security import hash_password
from app.db.base import Base
from app.db.enum import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductStatus,
    RefundStatus,
    UserRole,
    UserStatus,
)
from app.models.address import Address
from app.models.cart_item import CartItem
from app.models.category import Category
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.refund import Refund
from app.models.user import User as UserModel
from app.schemas.refund import RefundCreate
from app.services.refund_service import create_refund

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

@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_payment_one_wins(race_factory):
    """
    ✅ RACE-02: два параллельных process_payment на один order
    с разными external_id.

    Ожидание:
    - Один создаёт Payment, order → PAID.
    - Второй получает ConflictError(order_not_payable).
    - В БД ровно 1 Payment.
    """
    from app.core.exceptions import ConflictError
    from app.db.enum import PaymentMethod
    from app.models.payment import Payment
    from app.services.payment_service import process_payment

    # setup
    async with race_factory() as setup:
        cat = Category(path="electronics", category_name="Electronics")
        setup.add(cat)
        await setup.flush()

        product = Product(
            name="Laptop", description="Test",
            cost=Decimal("1000.00"), category_id=cat.id,
            status=ProductStatus.AVAILABLE,
        )
        setup.add(product)
        await setup.flush()

        user = UserModel(
            email="race-pay@example.com",
            password_hash=hash_password("race-pass-1234"),
            first_name="Race", last_name="Pay", phone_number="+79990000002",
            role=UserRole.CUSTOMER, status=UserStatus.ACTIVE, is_email_verified=True,
        )
        setup.add(user)
        await setup.flush()

        addr = Address(
            user_id=user.id, address_line1="X", city="Y",
            postal_code="Z", country="RU", is_default=True,
        )
        setup.add(addr)
        await setup.flush()

        order = Order(
            user_id=user.id, total=Decimal("1000.00"),
            status=OrderStatus.PENDING, shipping_address_id=addr.id,
        )
        setup.add(order)
        await setup.flush()

        setup.add(OrderItem(
            order_id=order.id, product_id=product.id,
            product_cost=Decimal("1000.00"), product_count=1,
        ))
        await setup.flush()
        await setup.commit()
        order_id = order.id

    async def _pay(ext_id):
        async with race_factory() as session:
            order_obj = await session.get(Order, order_id)
            try:
                payment = await process_payment(
                    session, order_obj, ext_id, PaymentMethod.CARD,
                )
                await session.commit()
                return ("success", payment.id)
            except ConflictError as e:
                await session.rollback()
                return ("conflict", e.code)

    r1, r2 = await asyncio.gather(_pay("ext-A"), _pay("ext-B"))

    statuses = sorted([r1[0], r2[0]])
    assert statuses == ["conflict", "success"], f"Expected one each, got {r1}, {r2}"

    async with race_factory() as check:
        payments = (await check.execute(
            select(Payment).where(Payment.order_id == order_id)
        )).scalars().all()
        assert len(payments) == 1, f"Expected 1 payment, got {len(payments)}"

        order_obj = await check.get(Order, order_id)
        await check.refresh(order_obj)
        assert order_obj.status == OrderStatus.PAID


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_refunds_do_not_exceed_payment(race_factory):
    """
    ✅ RACE-03: два параллельных create_refund на 800 + 800 при payment.amount=1000.
    Один success (800 <= 1000), второй ValidationError(amount_exceeds_remaining).
    Сумма completed refunds <= payment.amount.
    """
    
    # setup: user, address, product, order(PAID), payment(COMPLETED, 1000)
    async with race_factory() as setup:
        cat = Category(path="electronics", category_name="Electronics")
        setup.add(cat)
        await setup.flush()

        product = Product(
            name="Laptop", description="Test",
            cost=Decimal("1000.00"), category_id=cat.id,
            status=ProductStatus.AVAILABLE,
        )
        setup.add(product)
        await setup.flush()

        user = UserModel(
            email="race-refund@example.com",
            password_hash=hash_password("race-pass-1234"),
            first_name="Race", last_name="Refund", phone_number="+79990000003",
            role=UserRole.CUSTOMER, status=UserStatus.ACTIVE, is_email_verified=True,
        )
        setup.add(user)
        await setup.flush()

        addr = Address(
            user_id=user.id, address_line1="X", city="Y",
            postal_code="Z", country="RU", is_default=True,
        )
        setup.add(addr)
        await setup.flush()

        order = Order(
            user_id=user.id, total=Decimal("1000.00"),
            status=OrderStatus.PAID, shipping_address_id=addr.id,
        )
        setup.add(order)
        await setup.flush()

        setup.add(OrderItem(
            order_id=order.id, product_id=product.id,
            product_cost=Decimal("1000.00"), product_count=1,
        ))
        await setup.flush()

        payment = Payment(
            order_id=order.id, amount=Decimal("1000.00"),
            currency="RUB", payment_method=PaymentMethod.CARD,
            status=PaymentStatus.COMPLETED,
            external_id="race-refund-pay",
            paid_at=datetime.now(UTC),
        )
        setup.add(payment)
        await setup.flush()
        await setup.commit()
        payment_id = payment.id

    async def _refund(ext_id):
        async with race_factory() as session:
            payment_obj = await session.get(Payment, payment_id)
            try:
                refund = await create_refund(
                    session, payment_obj,
                    RefundCreate(amount=Decimal("800.00"), external_id=ext_id),
                )
                await session.commit()
                return ("success", refund.id)
            except ValidationError as e:
                await session.rollback()
                return ("conflict", e.code)

    r1, r2 = await asyncio.gather(_refund("refund-A"), _refund("refund-B"))

    statuses = sorted([r1[0], r2[0]])
    assert statuses == ["conflict", "success"], f"Expected one each, got {r1}, {r2}"

    conflict = r1 if r1[0] == "conflict" else r2
    assert conflict[1] == "amount_exceeds_remaining", f"Got {conflict}"

    # ✅ Сумма completed refunds <= payment.amount
    async with race_factory() as check:
        total = (await check.execute(
            select(func.coalesce(func.sum(Refund.amount), Decimal("0.00")))
            .where(
                Refund.payment_id == payment_id,
                Refund.status == RefundStatus.COMPLETED,
            )
        )).scalar_one()
        assert total <= Decimal("1000.00"), f"Refunds sum {total} exceeds payment"