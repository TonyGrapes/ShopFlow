# app/services/order_service.py
"""
Сервис заказов.

Ключевые контракты:
- Создание заказа из корзины — атомарно, в одной транзакции (get_db).
- Snapshot цены: OrderItem.product_cost ← CartItem.product_cost.
- Soft-deleted товары в корзине → тихо отсеиваются.
- out_of_stock товары → 422 со списком проблемных позиций.
- State machine в _ALLOWED_TRANSITIONS (не таблица — 5 статусов).
- Ownership: get_order_detail отдаёт 404 для чужих, не 403
  (не раскрываем существование).
"""
import hashlib
import json
import logging
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, ValidationError
from app.db.enum import OrderStatus, ProductStatus
from app.models.address import Address
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.schemas.address import AddressBrief
from app.schemas.order import (
    OrderItemProductBrief,
    OrderItemResponse,
    OrderListItem,
    OrderResponse,
)
from app.schemas.payment import PaymentResponse
from app.services import promo_service
from app.services.payment_service import serialize_payment
from app.services.storage_service import get_storage

logger = logging.getLogger(__name__)


# ============================================================
#  State machine
# ============================================================

_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING:   {OrderStatus.PAID, OrderStatus.CANCELED},
    OrderStatus.PAID:      {OrderStatus.SHIPPED, OrderStatus.CANCELED},
    OrderStatus.SHIPPED:   {OrderStatus.DELIVERED, OrderStatus.CANCELED},
    OrderStatus.DELIVERED: set(),   # терминальное
    OrderStatus.CANCELED:  set(),   # терминальное
}


def validate_transition(current: OrderStatus, new: OrderStatus) -> None:
    """
    Проверяет допустимость перехода. Бросает 422 с деталями.

    Бизнес-правило: после delivered и canceled ничего не меняется.
    """
    if new not in _ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_transition",
                "from": current.value,
                "to": new.value,
                "allowed": sorted(s.value for s in _ALLOWED_TRANSITIONS[current]),
            },
        )

_IDEMPOTENCY_CONSTRAINT = "uq_orders_user_idempotency_key"

def _is_idempotency_conflict(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False
    message = str(orig)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) if diag else None
    return (
        constraint_name == _IDEMPOTENCY_CONSTRAINT
        or _IDEMPOTENCY_CONSTRAINT in message
    )


# ============================================================
#  Создание заказа из корзины
# ============================================================

async def create_order_from_cart(
    db: AsyncSession,
    user: User,
    address_id: int,
    promo_code: str | None = None,
    idempotency_key: str | None = None,
) -> Order:
    """
    Создаёт заказ из корзины юзера. Всё в одной транзакции.

    Порядок (RACE-01: атомарный захват корзины):
    1. Валидация адреса.
    2. DELETE ... RETURNING cart_items — атомарно «забираем» корзину.
       Параллельный запрос получит пустой RETURNING → 422 empty_cart.
    3. Загрузка продуктов (soft-deleted — вне выборки).
    4. Валидация позиций (status == available).
    5. subtotal.
    6. promo validate + reserve (если передан).
    7. total.
    8. Order INSERT.
    9. OrderItem INSERT.
    10. reload для сериализации.

    При любой ошибке после шага 2 — get_db.rollback() вернёт корзину.
    То есть «при ошибке корзина не очищена» сохраняется.

    НЕ трогаем guest-cart в Redis: она уже очищена при login.

    DATA-01: идемпотентность по Idempotency-Key.
    - Повтор с тем же ключом + тем же телом → существующий Order (200).
    - Повтор с тем же ключом + другим телом → ConflictError(409).
    - Без ключа → обычное поведение.
      """
    # 0. Idempotency pre-check
    body_hash: Optional[str] = None
    if idempotency_key is not None:
        body_hash = _hash_idempotency_body(address_id, promo_code)
        existing = await _find_existing_by_idempotency_key(
            db, user.id, idempotency_key
        )
        if existing is not None:
            if existing.idempotency_body_hash == body_hash:
                # replay — возвращаем существующий
                logger.info(
                    "Idempotent replay: order public_id=%s key=%s",
                    existing.public_id, idempotency_key,
                )
                return await _load_order(db, existing.id)
            raise ConflictError(
                "Idempotency-Key reused with different body",
                code="idempotency_key_reused",
            )
        
    # 1. Валидация адреса
    address = await db.get(Address, address_id)
    if address is None or address.user_id != user.id:
        raise ValidationError(
            "Shipping address not found or not owned by user",
            code="invalid_address",
            extra={"address_id": address_id},
        )

    # 2. Атомарный захват корзины.
    #    DELETE ... RETURNING — один statement, атомарно в PostgreSQL.
    #    Второй параллельный DELETE получит rowcount=0 → пустой RETURNING.
    cart_result = await db.execute(
        delete(CartItem)
        .where(CartItem.user_id == user.id)
        .returning(
            CartItem.product_id,
            CartItem.quantity,
            CartItem.product_cost,
        )
    )
    cart_rows = cart_result.all()

    if not cart_rows:
        raise ValidationError("Cart is empty", code="empty_cart")

    # 3. Загрузка продуктов (soft-deleted — вне выборки, как было)
    product_ids = [row.product_id for row in cart_rows]
    products_result = await db.execute(
        select(Product).where(
            Product.id.in_(product_ids),
            Product.deleted_at.is_(None),
        )
    )
    products_by_id = {p.id: p for p in products_result.scalars()}

    # 4. Валидация позиций
    errors: list[dict] = []
    valid_items: list[tuple[Product, int, Decimal]] = []
    #                  ^ product, quantity, product_cost из корзины

    for row in cart_rows:
        product = products_by_id.get(row.product_id)
        if product is None:
            # Soft-deleted — тихо пропускаем (поведение как было)
            continue
        if product.status != ProductStatus.AVAILABLE:
            errors.append({
                "product_id": product.id,
                "name": product.name,
                "reason": product.status.value,
            })
            continue
        valid_items.append((product, row.quantity, row.product_cost))

    if errors:
        raise ValidationError(
            "Cart has unavailable items",
            code="cart_has_unavailable_items",
            extra={"errors": errors},
        )

    if not valid_items:
        # Все товары были soft-deleted — эффективно пустая корзина
        raise ValidationError("Cart is empty", code="empty_cart")

    # 5. subtotal
    subtotal = sum(
        (cost * qty for _, qty, cost in valid_items),
        start=Decimal("0.00"),
    )

    # 6. Промокод (если передан) — валидация + атомарный reserve
    discount: Decimal | None = None
    applied_code: str | None = None

    if promo_code is not None:
        promo, discount = await promo_service.validate_and_calculate(
            db, promo_code, subtotal
        )
        reserved = await promo_service.reserve_promo_use(db, promo.id)
        if not reserved:
            raise ValidationError(
                "Promo code max uses exceeded",
                code="invalid_promo",
                extra={"promo_code": promo_code, "reason": "max_uses_exceeded"},
            )
        applied_code = promo.code

    # 7. total
    total = subtotal - (discount or Decimal("0.00"))

        # 8. Order INSERT — добавить поля
    order = Order(
        user_id=user.id,
        total=total,
        status=OrderStatus.PENDING,
        shipping_address_id=address_id,
        promo_code=applied_code,
        discount_amount=discount,
        idempotency_key=idempotency_key,
        idempotency_body_hash=body_hash,
    )
    db.add(order)
    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_idempotency_conflict(exc):
            # Гонка: другой параллельный запрос уже создал заказ с этим ключом.
            # Пытаемся найти — если другой уже закоммитил, вернём его.
            existing = await _find_existing_by_idempotency_key(
                db, user.id, idempotency_key  # type: ignore[arg-type]
            )
            if existing is not None:
                if existing.idempotency_body_hash == body_hash:
                    logger.info(
                        "Idempotent replay (race): order public_id=%s key=%s",
                        existing.public_id, idempotency_key,
                    )
                    return await _load_order(db, existing.id)
                raise ConflictError(
                    "Idempotency-Key reused with different body",
                    code="idempotency_key_reused",
                ) from exc
            # Known limitation: другой запрос ещё не закоммитил.
            # 500 (get_db rollback), клиент может ретраить.
            logger.warning(
                "Idempotency race unresolved: key=%s, returning 500",
                idempotency_key,
            )
            raise
        logger.exception("Unexpected IntegrityError on create_order_from_cart")
        raise

    # 9. OrderItem INSERT
    #    product_cost — snapshot из cart_items, НЕ из products.cost.
    #    product_count = cart_item.quantity.
    for product, quantity, product_cost in valid_items:
        db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_cost=product_cost,
            product_count=quantity,
        ))

    await db.flush()

    # 10. reload для сериализации
    return await _load_order(db, order.id)

# ============================================================
#  Чтение заказов юзера
# ============================================================

async def get_user_orders(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[OrderStatus] = None,
) -> tuple[list[Order], int]:
    """
    Список заказов юзера с пагинацией и фильтром по статусу.

    items загружаются через selectinload — для items_count в
    OrderListItem. Для page_size=20 это ок (один доп. SELECT).
    """
    base_query = select(Order).where(Order.user_id == user_id)

    if status_filter is not None:
        base_query = base_query.where(Order.status == status_filter)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    items_query = (
        base_query
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    orders = (await db.execute(items_query)).scalars().all()
    return list(orders), total


async def get_order_detail(
    db: AsyncSession,
    user_id: int,
    order_public_id,
) -> Order | None:
    """
    Полные детали заказа.

    Возвращает None, если заказ не найден ИЛИ принадлежит другому юзеру.
    Роутер отдаёт 404 в обоих случаях — не раскрываем существование.
    """
    result = await db.execute(
        select(Order)
        .where(
            Order.public_id == order_public_id,
            Order.user_id == user_id,
        )
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images),
            selectinload(Order.shipping_address),
            selectinload(Order.payments),
        )
    )
    return result.scalar_one_or_none()


async def get_order_for_admin(
    db: AsyncSession, order_public_id
) -> Order | None:
    """Для админских эндпоинтов — без проверки ownership."""
    result = await db.execute(
        select(Order)
        .where(Order.public_id == order_public_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images),
            selectinload(Order.shipping_address),
            selectinload(Order.payments),
        )
    )
    return result.scalar_one_or_none()


async def list_orders_admin(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[OrderStatus] = None,
    user_id: Optional[int] = None,
) -> tuple[list[Order], int]:
    """Админский список заказов. Без ownership-проверок."""
    base_query = select(Order)

    if status_filter is not None:
        base_query = base_query.where(Order.status == status_filter)
    if user_id is not None:
        base_query = base_query.where(Order.user_id == user_id)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    items_query = (
        base_query
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    orders = (await db.execute(items_query)).scalars().all()
    return list(orders), total


# ============================================================
#  State machine — применение
# ============================================================

async def update_order_status(
    db: AsyncSession,
    order: Order,
    new_status: OrderStatus,
) -> Order:
    """
    Меняет статус с валидацией перехода.

    Проверка в сервисе, а не в роутере: это бизнес-правило,
    которое должно срабатывать и при внутренних вызовах
    (например, из фоновой задачи автоотмены).
    """
    validate_transition(order.status, new_status)
    order.status = new_status
    await db.flush()
    return order


# ============================================================
#  Сериализация
# ============================================================

def _serialize_order_item(oi: OrderItem) -> OrderItemResponse:
    """Позиция заказа. product загружен через selectinload."""
    storage = get_storage()
    product = oi.product

    return OrderItemResponse(
        public_id=oi.public_id,
        product=OrderItemProductBrief(
            id=product.id,
            name=product.name,
            cover_url=storage.get_url(product.cover_key) if product.cover_key else None,
            status=product.status,
        ),
        product_cost=oi.product_cost,
        product_count=oi.product_count,
        created_at=oi.created_at,
    )


def serialize_order(order: Order) -> OrderResponse:
    """
    Полный заказ. Требует предзагруженных items, shipping_address, payments
    (через selectinload в get_order_detail / get_order_for_admin).
    """
    # ✅ subtotal = сумма позиций до скидки. Производная, не хранится.
    subtotal = sum(
        (oi.product_cost * oi.product_count for oi in order.items),
        start=Decimal("0.00"),
    )

    return OrderResponse(
        public_id=order.public_id,
        status=order.status,
        subtotal=subtotal,
        discount_amount=order.discount_amount,
        total=order.total,
        promo_code=order.promo_code,
        shipping_address=AddressBrief.model_validate(order.shipping_address),
        items=[_serialize_order_item(oi) for oi in order.items],
        payments=[serialize_payment(p) for p in order.payments],
        created_at=order.created_at,
        updated_at=order.updated_at,
    )

def serialize_order_list_item(order: Order) -> OrderListItem:
    """Облегчённая карточка. items загружены для items_count."""
    return OrderListItem(
        public_id=order.public_id,
        status=order.status,
        discount_amount=order.discount_amount,
        total=order.total,
        items_count=len(order.items),
        created_at=order.created_at,
    )


# ============================================================
#  Внутренние утилиты
# ============================================================

async def _load_order(db: AsyncSession, order_id: int) -> Order:
    """Перезагрузка order со всеми связями для сериализации."""
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images),
            selectinload(Order.shipping_address),
            selectinload(Order.payments),
        )
    )
    return result.scalar_one()

def _hash_idempotency_body(address_id: int, promo_code: str | None) -> str:
    """
    SHA-256 от канонического тела запроса.

    Только поля, влияющие на заказ: address_id, promo_code.
    sort_keys=True — детерминированный JSON.
    """
    canonical = json.dumps(
        {"address_id": address_id, "promo_code": promo_code},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _find_existing_by_idempotency_key(
    db: AsyncSession, user_id: int, idempotency_key: str
) -> Optional[Order]:
    result = await db.execute(
        select(Order).where(
            Order.user_id == user_id,
            Order.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()