# app/services/address_service.py
"""
Сервис адресов доставки.

Инвариант: у пользователя не больше одного is_default=True.
Обеспечивается partial unique index'ом в БД
(idx_one_default_address_per_user) + логикой здесь.

При создании/обновлении с is_default=True автоматически снимаем
флаг с предыдущего дефолтного адреса (не 409) — UX лучше, чем
заставлять клиента делать два запроса.

Race condition между двумя параллельными «сделать дефолтным»
защищена:
1. SELECT ... FOR UPDATE на существующий дефолтный адрес — блокирует
   строку, второй запрос ждёт.
2. Catch IntegrityError на partial unique index (крайний случай:
   оба INSERT прошли параллельно, у юзера вообще не было дефолтных).
"""
import logging

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.address import Address
from app.schemas.address import AddressCreate, AddressUpdate

logger = logging.getLogger(__name__)

_DEFAULT_ADDRESS_CONSTRAINT = "idx_one_default_address_per_user"


async def list_addresses(db: AsyncSession, user_id: int) -> list[Address]:
    """Список адресов юзера, сначала дефолтный, потом по created_at."""
    result = await db.execute(
        select(Address)
        .where(Address.user_id == user_id)
        .order_by(Address.is_default.desc(), Address.created_at)
    )
    return list(result.scalars().all())


async def get_address(
    db: AsyncSession, user_id: int, address_id: int
) -> Address | None:
    """Адрес по id, только если он принадлежит юзеру."""
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _clear_existing_default(db: AsyncSession, user_id: int) -> None:
    """
    Снимает is_default с текущего дефолтного адреса юзера (если есть).

    SELECT ... FOR UPDATE — блокирует строку до конца транзакции,
    чтобы параллельный запрос не смог одновременно сбросить тот же
    флаг и создать второй дефолтный.
    """
    result = await db.execute(
        select(Address)
        .where(
            Address.user_id == user_id,
            Address.is_default.is_(True),
        )
        .with_for_update()
    )
    current = result.scalar_one_or_none()
    if current is not None:
        current.is_default = False


async def create_address(
    db: AsyncSession, user_id: int, data: AddressCreate
) -> Address:
    """
    Создаёт адрес.

    Если data.is_default=True — предварительно сбрасывает флаг
    с существующего дефолтного (если есть).
    """
    if data.is_default:
        await _clear_existing_default(db, user_id)

    address = Address(
        user_id=user_id,
        address_line1=data.address_line1,
        address_line2=data.address_line2,
        city=data.city,
        postal_code=data.postal_code,
        country=data.country,
        is_default=data.is_default,
    )
    db.add(address)

    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_default_conflict(exc):
            raise ConflictError("default address conflict", code="default_conflict") from exc
        logger.exception("Unexpected IntegrityError on create_address")
        raise

    await db.refresh(address)
    return address


async def update_address(
    db: AsyncSession, user_id: int, address_id: int, data: AddressUpdate
) -> Address | None:
    """
    PATCH. Возвращает None если адрес не найден у юзера.

    Если data.is_default=True — сбрасывает флаг с другого дефолтного.
    """
    address = await get_address(db, user_id, address_id)
    if address is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # is_default=True — сначала снять с других
    if update_data.get("is_default") is True and not address.is_default:
        await _clear_existing_default(db, user_id)

    for field, value in update_data.items():
        setattr(address, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_default_conflict(exc):
            raise ConflictError("default address conflict", code="default_conflict") from exc
        logger.exception("Unexpected IntegrityError on update_address")
        raise

    await db.refresh(address)
    return address


async def delete_address(
    db: AsyncSession, user_id: int, address_id: int
) -> bool:
    """Удаляет адрес. False — если не найден или чужой."""
    address = await get_address(db, user_id, address_id)
    if address is None:
        return False

    await db.delete(address)
    await db.flush()
    return True


async def set_default(
    db: AsyncSession, user_id: int, address_id: int
) -> Address | None:
    """
    Явная установка is_default. Идемпотентно: если уже дефолтный — no-op.

    Возвращает None, если адрес не найден у юзера.
    """
    address = await get_address(db, user_id, address_id)
    if address is None:
        return None

    if address.is_default:
        return address   # идемпотентно

    await _clear_existing_default(db, user_id)
    address.is_default = True

    try:
        await db.flush()
    except IntegrityError as exc:
        if _is_default_conflict(exc):
            raise ConflictError("default address conflict", code="default_conflict") from exc
        logger.exception("Unexpected IntegrityError on set_default")
        raise

    await db.refresh(address)
    return address


# ============================================================
#  Внутренние утилиты
# ============================================================

def _is_default_conflict(exc: IntegrityError) -> bool:
    """
    Проверяет, что IntegrityError — это конфликт partial unique index
    на дефолтный адрес.

    Аналог `_is_active_name_conflict` в product_service: sqlstate 23505
    + имя индекса. Для partial index asyncpg может не заполнять
    diag.constraint_name → ищем в тексте.
    """
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
        constraint_name == _DEFAULT_ADDRESS_CONSTRAINT
        or _DEFAULT_ADDRESS_CONSTRAINT in message
    )