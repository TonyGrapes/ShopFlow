# tests/conftest.py
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env.test"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

from types import SimpleNamespace

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1.deps import get_cache_service, get_guest_cart_store
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.enum import ProductStatus, UserRole, UserStatus
from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.product import Product
from app.models.user import User as UserModel
from app.services.cache_service import CacheService
from app.services.cart_service import GuestCartStore
from app.services.storage_service import MinioStorage, get_storage

TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)


# ============ DB / engine ============

@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(
        TEST_DATABASE_URL, echo=False, poolclass=NullPool,
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
async def db_session(engine):
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()


# ============ Пользователи ============

@pytest_asyncio.fixture
async def verified_user(db_session: AsyncSession) -> UserModel:
    """Активный верифицированный CUSTOMER. Пароль известен тестам."""
    user = UserModel(
        email="user@example.com",
        password_hash=hash_password("test-password-1234"),
        first_name="Test",
        last_name="User",
        phone_number="+79990000001",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> UserModel:
    """Активный верифицированный ADMIN — для write-тестов товаров."""
    user = UserModel(
        email="admin@example.com",
        password_hash=hash_password("admin-password-1234"),
        first_name="Admin",
        last_name="User",
        phone_number="+79990000002",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def seller_user(db_session: AsyncSession) -> UserModel:
    """SELLER — для проверки границ require_roles."""
    user = UserModel(
        email="seller@example.com",
        password_hash=hash_password("seller-password-1234"),
        first_name="Seller",
        last_name="User",
        phone_number="+79990000003",
        role=UserRole.SELLER,
        status=UserStatus.ACTIVE,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def banned_user(db_session: AsyncSession) -> UserModel:
    """BANNED — для проверки ban-политики."""
    user = UserModel(
        email="banned@example.com",
        password_hash=hash_password("banned-password-1234"),
        first_name="Banned",
        last_name="User",
        phone_number="+79990000004",
        role=UserRole.CUSTOMER,
        status=UserStatus.BANNED,
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# ============ Настоящие токены (замена мока) ============

@pytest.fixture
def auth_headers(verified_user: UserModel) -> dict[str, str]:
    """Настоящий access-токен для CUSTOMER."""
    token = create_access_token(str(verified_user.public_id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user: UserModel) -> dict[str, str]:
    """Настоящий access-токен для ADMIN."""
    token = create_access_token(str(admin_user.public_id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seller_headers(seller_user: UserModel) -> dict[str, str]:
    """Настоящий access-токен для SELLER."""
    token = create_access_token(str(seller_user.public_id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def banned_headers(banned_user: UserModel) -> dict[str, str]:
    """Access-токен для BANNED — нужен, чтобы проверить 403 в deps."""
    token = create_access_token(str(banned_user.public_id))
    return {"Authorization": f"Bearer {token}"}

# ============ Fixtures данных ============

@pytest_asyncio.fixture
async def category(db_session: AsyncSession) -> Category:
    from sqlalchemy_utils import Ltree
    cat = Category(
        path=Ltree("electronics"),
        category_name="Electronics",
    )
    db_session.add(cat)
    await db_session.flush()
    await db_session.refresh(cat)
    return cat


@pytest_asyncio.fixture
async def product(db_session: AsyncSession, category: Category) -> Product:
    p = Product(
        name="Laptop",
        description="Test laptop",
        cost=Decimal("1000.00"),
        category_id=category.id,
        status=ProductStatus.AVAILABLE,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)
    return p


# ============ MinIO mock ============

@pytest.fixture
def mock_storage():
    storage = Mock(spec=MinioStorage)
    storage.upload = AsyncMock(return_value=None)
    storage.delete = AsyncMock(return_value=None)
    storage.get_url = Mock(
        return_value="http://localhost:9000/test-media/products/1/key.jpg"
    )
    storage.ensure_bucket = Mock()
    storage.get_object_info = AsyncMock(return_value=None)
    return storage


# ============ HTTP client ============

@pytest_asyncio.fixture
async def client(db_session, mock_storage, mock_cache, fake_redis):
    """
    HTTP-клиент с override get_db, get_storage, get_cache_service.

    override_get_db эмулирует прод-семантику app.db.session.get_db:
    - SAVEPOINT на каждый вызов (запрос);
    - успех → commit savepoint (изменения видны в родительской транзакции);
    - исключение или GeneratorExit (FastAPI aclose) → rollback.

    ВАЖНО: except BaseException — потому что FastAPI завершает async
    generator через aclose(), что бросает GeneratorExit (не подкласс
    Exception). Без этого savepoint зависает → RuntimeError: Task pending.
    """

    async def override_get_db():
        nested = await db_session.begin_nested()
        try:
            yield db_session
        except BaseException:
            if nested.is_active:
                await nested.rollback()
            raise
        else:
            if nested.is_active:
                await nested.commit()

    def override_get_storage():
        return mock_storage

    def override_get_cache_service():
        return mock_cache

    def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = override_get_storage
    app.dependency_overrides[get_cache_service] = override_get_cache_service
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as tc:
        yield tc

    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def sql_counter(engine):
    """
    Считает SQL-запросы, выполненные через движок.

    Использование:
        assert len(sql_counter.statements) == 4
    """
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _on_execute(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    # ✅ SimpleNamespace — простая обёртка, работает с замыканием
    counter = SimpleNamespace(statements=statements)

    yield counter

    event.remove(engine.sync_engine, "before_cursor_execute", _on_execute)

@pytest.fixture
def mock_cache():
    """
    Мок CacheService с in-memory словарём.

    Позволяет тестировать cache hit/miss без реального Redis.
    """
    storage: dict[str, str] = {}

    cache = Mock(spec=CacheService)

    async def get_json(key):
        return storage.get(key)

    async def set_json(key, value, ttl_seconds):
        storage[key] = value

    async def delete(key):
        storage.pop(key, None)

    async def delete_by_pattern(pattern):
        # Простая реализация: pattern вида "prefix:*"
        prefix = pattern.rstrip("*")
        keys_to_delete = [k for k in storage if k.startswith(prefix)]
        for k in keys_to_delete:
            del storage[k]
        return len(keys_to_delete)

    cache.get_json = AsyncMock(side_effect=get_json)
    cache.set_json = AsyncMock(side_effect=set_json)
    cache.delete = AsyncMock(side_effect=delete)
    cache.delete_by_pattern = AsyncMock(side_effect=delete_by_pattern)
    cache._storage = storage    # для интроспекции в тестах

    return cache

@pytest_asyncio.fixture(autouse=True)
async def _dispose_cached_engine_after_test():
    """
    ✅ Между тестами сбрасываем lru_cache на engine/factory
    в app.db.session. Без этого savepoint-тесты оставляют
    открытые соединения, которые мешают real-DB тестам
    (test_auth_integration) при их teardown.
    """
    yield
    from app.db import session as session_module
    try:
        # Проверяем, есть ли кэш, не создавая новый engine
        if session_module.get_engine.cache_info().currsize > 0:
            await session_module.get_engine().dispose()
    except Exception:
        pass
    session_module.get_engine.cache_clear()
    session_module.get_async_session_factory.cache_clear()


@pytest_asyncio.fixture
async def fake_redis():
    """FakeRedis для гостевой корзины. Изолирован per-test."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()


@pytest_asyncio.fixture
async def real_guest_store(fake_redis):
    """Реальный GuestCartStore поверх fakeredis — НЕ мок."""
    return GuestCartStore(fake_redis)


@pytest_asyncio.fixture
async def guest_client(db_session, mock_storage, mock_cache, real_guest_store, fake_redis):
    """
    HTTP-клиент гостя: без Bearer, с override get_guest_cart_store.

    При первом запросе get_cart_owner сгенерирует cookie и выставит её.
    """
    async def override_get_db():
        nested = await db_session.begin_nested()
        try:
            yield db_session
        except BaseException:
            if nested.is_active:
                await nested.rollback()
            raise
        else:
            if nested.is_active:
                await nested.commit()

    def override_get_storage():
        return mock_storage

    def override_get_cache_service():
        return mock_cache

    def override_get_guest_cart_store():
        return real_guest_store

    def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = override_get_storage
    app.dependency_overrides[get_cache_service] = override_get_cache_service
    app.dependency_overrides[get_guest_cart_store] = override_get_guest_cart_store
    app.dependency_overrides[get_redis] = override_get_redis
    

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as tc:
        yield tc

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def cart_client(db_session, mock_storage, mock_cache, real_guest_store, fake_redis):
    """Клиент для тестов корзины/избранного. Переиспользует db_session."""
    async def override_get_db():
        nested = await db_session.begin_nested()
        try:
            yield db_session
        except BaseException:
            if nested.is_active:
                await nested.rollback()
            raise
        else:
            if nested.is_active:
                await nested.commit()

    def override_get_storage():
        return mock_storage

    def override_get_cache_service():
        return mock_cache

    def override_get_guest_cart_store():
        return real_guest_store

    def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = override_get_storage
    app.dependency_overrides[get_cache_service] = override_get_cache_service
    app.dependency_overrides[get_guest_cart_store] = override_get_guest_cart_store
    app.dependency_overrides[get_redis] = override_get_redis
    

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as tc:
        yield tc

    app.dependency_overrides.clear()


# tests/conftest.py — добавить в конец

from datetime import UTC

from app.db.enum import OrderStatus, PaymentMethod, PaymentStatus
from app.models.address import Address
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment

# ============ Address fixtures ============

@pytest_asyncio.fixture
async def address(db_session: AsyncSession, verified_user: UserModel) -> Address:
    """Дефолтный адрес для verified_user."""
    a = Address(
        user_id=verified_user.id,
        address_line1="ул. Ленина, 1",
        address_line2="кв. 42",
        city="Москва",
        postal_code="101000",
        country="RU",
        is_default=True,
    )
    db_session.add(a)
    await db_session.flush()
    await db_session.refresh(a)
    return a


@pytest_asyncio.fixture
async def address_for_admin(db_session: AsyncSession, admin_user: UserModel) -> Address:
    """Дефолтный адрес для admin_user — для тестов ownership."""
    a = Address(
        user_id=admin_user.id,
        address_line1="ул. Пушкина, 10",
        city="Санкт-Петербург",
        postal_code="190000",
        country="RU",
        is_default=True,
    )
    db_session.add(a)
    await db_session.flush()
    await db_session.refresh(a)
    return a


# ============ Cart fixtures (для order-тестов) ============

@pytest_asyncio.fixture
async def cart_with_one_item(
    db_session: AsyncSession, verified_user: UserModel, product
) -> CartItem:
    """Одна позиция в корзине verified_user (quantity=2)."""
    ci = CartItem(
        user_id=verified_user.id,
        product_id=product.id,
        quantity=2,
        product_cost=product.cost,
    )
    db_session.add(ci)
    await db_session.flush()
    await db_session.refresh(ci)
    return ci


@pytest_asyncio.fixture
async def cart_with_two_items(
    db_session: AsyncSession, verified_user: UserModel, category, product
) -> tuple[CartItem, CartItem]:
    """Две позиции в корзине verified_user."""
    from decimal import Decimal

    from app.models.product import Product as ProductModel

    p2 = ProductModel(
        name="Mouse", description="Test mouse",
        cost=Decimal("50.00"), category_id=category.id,
        status=ProductStatus.AVAILABLE,
    )
    db_session.add(p2)
    await db_session.flush()

    ci1 = CartItem(
        user_id=verified_user.id,
        product_id=product.id,           # Laptop 1000.00
        quantity=2,
        product_cost=product.cost,
    )
    ci2 = CartItem(
        user_id=verified_user.id,
        product_id=p2.id,                # Mouse 50.00
        quantity=3,
        product_cost=p2.cost,
    )
    db_session.add_all([ci1, ci2])
    await db_session.flush()
    await db_session.refresh(ci1)
    await db_session.refresh(ci2)
    return ci1, ci2


# ============ Order fixtures ============

@pytest_asyncio.fixture
async def order(
    db_session: AsyncSession,
    verified_user: UserModel,
    address: Address,
    product,
) -> Order:
    """Готовый заказ в статусе pending с одной позицией."""
    from decimal import Decimal

    o = Order(
        user_id=verified_user.id,
        total=Decimal("2000.00"),
        status=OrderStatus.PENDING,
        shipping_address_id=address.id,
    )
    db_session.add(o)
    await db_session.flush()

    oi = OrderItem(
        order_id=o.id,
        product_id=product.id,
        product_cost=Decimal("1000.00"),
        product_count=2,
    )
    db_session.add(oi)
    await db_session.flush()
    await db_session.refresh(o)
    return o


@pytest_asyncio.fixture
async def paid_order(
    db_session: AsyncSession,
    verified_user: UserModel,
    address: Address,
    product,
) -> Order:
    """Заказ в статусе paid с одним Payment (completed)."""
    from datetime import datetime
    from decimal import Decimal

    o = Order(
        user_id=verified_user.id,
        total=Decimal("1000.00"),
        status=OrderStatus.PAID,
        shipping_address_id=address.id,
    )
    db_session.add(o)
    await db_session.flush()

    oi = OrderItem(
        order_id=o.id,
        product_id=product.id,
        product_cost=Decimal("1000.00"),
        product_count=1,
    )
    db_session.add(oi)
    await db_session.flush()

    p = Payment(
        order_id=o.id,
        amount=Decimal("1000.00"),
        currency="RUB",
        payment_method=PaymentMethod.CARD,
        status=PaymentStatus.COMPLETED,
        external_id="test-external-paid-1",
        paid_at=datetime.now(UTC),
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(o)
    return o


from datetime import datetime, timedelta

from app.db.enum import DiscountType
from app.models.promo_code import PromoCode


@pytest_asyncio.fixture
async def promo_code(db_session: AsyncSession) -> PromoCode:
    """
    Активный промокод 10% без лимитов и минимальной суммы.

    Валиден «сейчас» — valid_from в прошлом, valid_until в будущем.
    """
    now = datetime.now(UTC)
    p = PromoCode(
        code="SUMMER10",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        min_order_amount=None,
        max_uses=None,
        used_count=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        is_active=True,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def promo_code_fixed(db_session: AsyncSession) -> PromoCode:
    """Фиксированный промокод на 500 ₽."""
    now = datetime.now(UTC)
    p = PromoCode(
        code="FIX500",
        discount_type=DiscountType.FIXED,
        discount_value=Decimal("500.00"),
        min_order_amount=None,
        max_uses=None,
        used_count=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        is_active=True,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)
    return p

from app.models.order import Order
from app.models.review import Review


@pytest_asyncio.fixture
async def delivered_order(
    db_session: AsyncSession,
    verified_user: UserModel,
    address,
    product,
) -> Order:
    """
    Заказ в статусе DELIVERED с product.

    Нужен для тестов отзывов: только после delivered-заказа
    юзер может оставить отзыв.
    """
    from decimal import Decimal

    o = Order(
        user_id=verified_user.id,
        total=Decimal("1000.00"),
        status=OrderStatus.DELIVERED,
        shipping_address_id=address.id,
    )
    db_session.add(o)
    await db_session.flush()

    db_session.add(OrderItem(
        order_id=o.id,
        product_id=product.id,
        product_cost=Decimal("1000.00"),
        product_count=1,
    ))
    await db_session.flush()
    await db_session.refresh(o)
    return o


@pytest_asyncio.fixture
async def review(
    db_session: AsyncSession,
    verified_user: UserModel,
    product,
    delivered_order: Order,
) -> Review:
    """
    Готовый активный отзыв verified_user на product.

    is_verified=True (соответствует логике: только после delivered).
    """
    r = Review(
        user_id=verified_user.id,
        product_id=product.id,
        order_id=delivered_order.id,
        rating=5,
        title="Great laptop",
        comment="Very good!",
        is_verified=True,
    )
    db_session.add(r)
    await db_session.flush()
    await db_session.refresh(r)
    return r


from sqlalchemy_utils import Ltree

from app.models.category import Category

# ============ Category fixtures ============

@pytest_asyncio.fixture
async def category_root(db_session: AsyncSession) -> Category:
    """Корневая категория: electronics."""
    cat = Category(
        path=Ltree("electronics"),
        category_name="Electronics",
    )
    db_session.add(cat)
    await db_session.flush()
    await db_session.refresh(cat)
    return cat


@pytest_asyncio.fixture
async def category_child(
    db_session: AsyncSession, category_root: Category
) -> Category:
    """Дочерняя: electronics.laptops."""
    cat = Category(
        parent_id=category_root.id,
        path=Ltree("electronics.laptops"),
        category_name="Laptops",
    )
    db_session.add(cat)
    await db_session.flush()
    await db_session.refresh(cat)
    return cat


@pytest_asyncio.fixture
async def category_grandchild(
    db_session: AsyncSession, category_child: Category
) -> Category:
    """Внучатая: electronics.laptops.gaming."""
    cat = Category(
        parent_id=category_child.id,
        path=Ltree("electronics.laptops.gaming"),
        category_name="Gaming Laptops",
    )
    db_session.add(cat)
    await db_session.flush()
    await db_session.refresh(cat)
    return cat


@pytest_asyncio.fixture
async def category_for_admin(db_session: AsyncSession) -> Category:
    """Отдельная корневая категория — для тестов перемещения и ownership."""
    cat = Category(
        path=Ltree("furniture"),
        category_name="Furniture",
    )
    db_session.add(cat)
    await db_session.flush()
    await db_session.refresh(cat)
    return cat


# tests/conftest.py — добавить в конец

from app.db.enum import RefundStatus
from app.models.refund import Refund


@pytest_asyncio.fixture
async def payment_for_refund(
    db_session: AsyncSession,
    verified_user: UserModel,
    address: Address,
    product,
) -> Payment:
    """
    Платёж в статусе completed для тестов возвратов.

    Отдельно от `paid_order`: у paid_order платёж привязан к order,
    который уже paid. Здесь нам нужен просто completed payment
    с суммой 1000.00.
    """
    from datetime import datetime
    from decimal import Decimal

    from app.db.enum import OrderStatus
    from app.models.order import Order
    from app.models.order_item import OrderItem

    o = Order(
        user_id=verified_user.id,
        total=Decimal("1000.00"),
        status=OrderStatus.PAID,
        shipping_address_id=address.id,
    )
    db_session.add(o)
    await db_session.flush()

    db_session.add(OrderItem(
        order_id=o.id, product_id=product.id,
        product_cost=Decimal("1000.00"), product_count=1,
    ))
    await db_session.flush()

    p = Payment(
        order_id=o.id,
        amount=Decimal("1000.00"),
        currency="RUB",
        payment_method=PaymentMethod.CARD,
        status=PaymentStatus.COMPLETED,
        external_id="test-payment-refund-1",
        paid_at=datetime.now(UTC),
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def completed_refund(
    db_session: AsyncSession,
    payment_for_refund: Payment,
) -> Refund:
    """Готовый completed-возврат на 300 ₽."""
    from datetime import datetime
    from decimal import Decimal

    r = Refund(
        payment_id=payment_for_refund.id,
        amount=Decimal("300.00"),
        reason="customer_request",
        status=RefundStatus.COMPLETED,
        external_id="test-refund-1",
        refunded_at=datetime.now(UTC),
    )
    db_session.add(r)
    await db_session.flush()
    await db_session.refresh(r)
    return r