"""
Админские эндпоинты пользователей.

RBAC:
- list — ADMIN | MODERATOR
- смена роли — только ADMIN (эскалация привилегий)
- бан/разбан — ADMIN | MODERATOR

Защита от самомодификации: нельзя банить себя и менять себе роль
(иначе можно случайно выйти из админов / заблокировать себя).

При бане/смене роли — отзыв ВСЕХ refresh-токенов пользователя
(auth_service.revoke_all_user_families). Access-токен доживёт
до exp (30 мин), но `get_current_active_user` при каждом запросе
перечитывает role/status из БД → 403 сразу для забаненного и
новая роль — сразу для клиента.

Фронт после PATCH /status (banned) или /role вынужден
перелогиниться: refresh отозван, следующий refresh вернёт 401.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import User, get_current_active_user, require_roles
from app.core.exceptions import ValidationError
from app.db.enum import UserRole, UserStatus
from app.db.session import get_db
from app.models.user import User as UserModel
from app.schemas.admin import (
    AdminUserListItem,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from app.schemas.common import Paginated
from app.services.auth_service import revoke_all_user_families

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/users", tags=["admin:users"])


@router.get(
    "",
    response_model=Paginated[AdminUserListItem],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)
async def list_admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: UserRole | None = Query(None),
    status_filter: UserStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    """
    Список пользователей (soft-deleted исключены — их не показываем).

    Фильтры: role, status.
    """
    base = select(UserModel).where(UserModel.deleted_at.is_(None))
    if role is not None:
        base = base.where(UserModel.role == role)
    if status_filter is not None:
        base = base.where(UserModel.status == status_filter)

    count_query = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_query)).scalar_one()

    items = (await db.execute(
        base
        .order_by(UserModel.created_at.desc(), UserModel.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return Paginated[AdminUserListItem](
        items=[AdminUserListItem.model_validate(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/{public_id}/role",
    response_model=AdminUserListItem,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],   # только ADMIN
)
async def update_user_role(
    public_id: str,
    data: UserRoleUpdateRequest,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Смена роли. Только ADMIN.

    Нельзя менять свою роль — иначе можно случайно снять с себя ADMIN.

    После успеха — отзыв всех refresh-токенов пользователя: клиент
    должен перелогиниться, чтобы увидеть новую роль (роль при каждом
    запросе берётся из БД, но UI-кэш на клиенте опирается на login-ответ).
    """
    if str(current.public_id) == public_id:
        raise ValidationError(
            "Cannot change your own role",
            code="cannot_modify_self",
        )

    user = (await db.execute(
        select(UserModel).where(
            UserModel.public_id == public_id,
            UserModel.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")

    user.role = data.role
    await revoke_all_user_families(db, user.id)
    await db.flush()
    await db.refresh(user)

    logger.info(
        "Role changed: user=%s new_role=%s by=%s",
        user.public_id, data.role.value, current.public_id,
    )
    return AdminUserListItem.model_validate(user)


@router.patch(
    "/{public_id}/status",
    response_model=AdminUserListItem,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
)
async def update_user_status(
    public_id: str,
    data: UserStatusUpdateRequest,
    current: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Бан/разбан/перевод в pending. ADMIN | MODERATOR.

    Нельзя банить себя.

    При status=BANNED — отзыв всех refresh-токенов: после истечения
    access-токена (30 мин) пользователь не сможет обновиться, и
    следующий /auth/refresh вернёт 401. Уже выданный access-токен
    будет отклонён `get_current_active_user` (status=BANNED → 403).
    """
    if str(current.public_id) == public_id and data.status == UserStatus.BANNED:
        raise ValidationError(
            "Cannot ban yourself",
            code="cannot_modify_self",
        )

    user = (await db.execute(
        select(UserModel).where(
            UserModel.public_id == public_id,
            UserModel.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")

    user.status = data.status
    if data.status == UserStatus.BANNED:
        await revoke_all_user_families(db, user.id)
    await db.flush()
    await db.refresh(user)

    logger.info(
        "Status changed: user=%s new_status=%s by=%s",
        user.public_id, data.status.value, current.public_id,
    )
    return AdminUserListItem.model_validate(user)