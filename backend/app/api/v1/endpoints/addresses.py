# app/api/v1/endpoints/addresses.py
"""
CRUD адресов доставки.

Все эндпоинты требуют аутентификации.
Адрес привязан к user_id — чужой получить/изменить нельзя (404).
"""
import logging

from app.api.v1.deps import User, get_current_active_user
from app.db.session import get_db
from app.schemas.address import AddressCreate, AddressResponse, AddressUpdate
from app.services import address_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/addresses", tags=["addresses"])


# ============================================================
#  GET /addresses — список
# ============================================================

@router.get("", response_model=list[AddressResponse])
async def list_addresses(
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Список адресов юзера.

    Порядок: сначала дефолтный (если есть), потом по created_at asc.
    """
    addresses = await address_service.list_addresses(db, current.id)
    return [AddressResponse.model_validate(a) for a in addresses]


# ============================================================
#  POST /addresses — создание
# ============================================================

@router.post(
    "",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_address(
    data: AddressCreate,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Создаёт адрес.

    Если data.is_default=True — снимает флаг с предыдущего дефолтного.
    Идемпотентности нет: два POST с одинаковым payload создадут
    два адреса (это не «создать или обновить», а «создать новый»).
    """
    address = await address_service.create_address(db, current.id, data)
    return AddressResponse.model_validate(address)


# ============================================================
#  GET /addresses/{id} — чтение
# ============================================================

@router.get("/{address_id}", response_model=AddressResponse)
async def get_address(
    address_id: int,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Адрес по id. 404 если чужой или не существует."""
    address = await address_service.get_address(db, current.id, address_id)
    if address is None:
        raise HTTPException(404, "Address not found")
    return AddressResponse.model_validate(address)


# ============================================================
#  PATCH /addresses/{id} — обновление
# ============================================================

@router.patch("/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: int,
    data: AddressUpdate,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """PATCH. 404 если чужой или не существует."""
    address = await address_service.update_address(
        db, current.id, address_id, data
    )
    if address is None:
        raise HTTPException(404, "Address not found")
    return AddressResponse.model_validate(address)


# ============================================================
#  DELETE /addresses/{id}
# ============================================================

@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Удаляет адрес. 404 если чужой или не существует."""
    deleted = await address_service.delete_address(db, current.id, address_id)
    if not deleted:
        raise HTTPException(404, "Address not found")
    return None


# ============================================================
#  POST /addresses/{id}/set-default
# ============================================================

@router.post("/{address_id}/set-default", response_model=AddressResponse)
async def set_default_address(
    address_id: int,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Явная установка дефолтного адреса.

    Идемпотентно: если адрес уже дефолтный — no-op.
    Снимает флаг с предыдущего дефолтного (partial unique index).
    """
    address = await address_service.set_default(db, current.id, address_id)
    if address is None:
        raise HTTPException(404, "Address not found")
    return AddressResponse.model_validate(address)