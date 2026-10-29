# tests/test_orders_integration.py
"""
Интеграционные тесты заказов на ПРОД-семантике get_db (rollback всей сессии).

Отличие от test_orders_api.py: НЕ override'им get_db. Реальная get_db
делает rollback всей транзакции при исключении — именно это надо проверить.
"""
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.enum import ProductStatus, UserRole, UserStatus
from app.main import app
from app.models.address import Address
from app.models.cart_item import CartItem
from app.models.category import Category
from app.models.product import Product
from app.models.user import User as UserModel


@pytest_asyncio.fixture(scope="function")
async def prod_engine():
    engine = create_async_engine(
        get_settings().database_url, echo=False, poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS ltree'))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def prod_client(prod_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as tc:
        yield tc


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cart_not_cleared_on_error(prod_engine, prod_client):
    """
    ✅ Прод-семантика: при 422 get_db делает rollback → корзина восстановлена.

    Проверяет, что DELETE ... RETURNING в create_order_from_cart
    действительно откатывается через get_db.rollback().
    """
    factory = async_sessionmaker(prod_engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as setup:
        cat = Category(path="electronics", category_name="Electronics")
        setup.add(cat)
        await setup.flush()

        product = Product(
            name="Laptop", description="Test",
            cost=Decimal("1000.00"), category_id=cat.id,
            status=ProductStatus.OUTOFSTOCK,
        )
        setup.add(product)
        await setup.flush()

        user = UserModel(
            email="cart-race@example.com",
            password_hash=hash_password("race-pass-1234"),
            first_name="Cart", last_name="Race", phone_number="+79990000999",
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

        cart = CartItem(
            user_id=user.id, product_id=product.id,
            quantity=2, product_cost=product.cost,
        )
        setup.add(cart)
        await setup.commit()
        user_id = user.id
        address_id = addr.id

    access = create_access_token(str(user.public_id))
    response = await prod_client.post(
        "/api/v1/orders",
        json={"address_id": address_id},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "cart_has_unavailable_items"

    # ✅ В БД корзина восстановлена rollback'ом в get_db
    async with factory() as check:
        cart_items = (await check.execute(
            select(CartItem).where(CartItem.user_id == user_id)
        )).scalars().all()
        assert len(cart_items) == 1, f"Cart should be restored, got {len(cart_items)}"