# app/api/v1/deps.py
"""
FastAPI-зависимости.

- get_current_active_user: decode → load user → проверки status/deleted_at/verified.
- require_roles: фабрика для RBAC (роль — в роутере).
- Ownership: business-правило — в сервисе (не здесь).
"""
import secrets
from dataclasses import dataclass
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, Response, status, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.db.enum import UserRole, UserStatus
from app.db.session import get_db
from app.models.user import User as UserModel
from app.services.cache_service import CacheService
from app.services.cart_service import GuestCartStore

security = HTTPBearer(auto_error=False)


@dataclass
class User:
    """
    Текущий пользователь.

    orm — исходный SQLAlchemy-объект (нужен для business-правил ownership).
    Атрибуты продублированы для удобства и обратной совместимости с Эпиком 2.
    """
    id: int
    public_id: str
    role: UserRole
    status: UserStatus
    is_email_verified: bool
    orm: UserModel

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE and self.is_email_verified


async def get_current_active_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Аутентификация:
    1. Bearer-токен обязателен.
    2. decode_access_token (проверка подписи, exp, type).
    3. Загрузка user из БД по public_id.
    4. Проверки: не удалён, не забанен, email верифицирован.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    public_id = payload["sub"]
    result = await db.execute(
        select(UserModel).where(
            UserModel.public_id == public_id,
            UserModel.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status == UserStatus.BANNED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is banned")

    if not user.is_email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Email not verified. Use POST /api/v1/auth/resend-verification",
        )

    return User(
        id=user.id,
        public_id=str(user.public_id),
        role=user.role,
        status=user.status,
        is_email_verified=user.is_email_verified,
        orm=user,
    )


def require_roles(*allowed: UserRole) -> Callable:
    """
    Фабрика RBAC-зависимостей.

    Использование:
        @router.post("", dependencies=[Depends(require_roles(UserRole.ADMIN))])

    Роль проверяется в роутере (что можно войти в дверь).
    Ownership — в сервисе (что можно сделать с этим объектом).
    """
    async def _checker(current: User = Depends(get_current_active_user)) -> User:
        if current.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed]}",
            )
        return current

    return _checker


def get_cache_service(redis: Redis = Depends(get_redis)) -> CacheService:
    return CacheService(redis)

# ============================================================
#  Cart owner (guest или user)
# ============================================================

@dataclass
class CartOwner:
    """
    Кто владеет корзиной.

    Гость: user_id=None, session_id=<uuid>, is_guest=True.
    Юзер:  user_id=<id>,  session_id=None, is_guest=False.
    """
    user_id: int | None
    session_id: str | None
    is_guest: bool


async def get_cart_owner(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CartOwner:
    """
    Определяет владельца корзины.

    Логика:
    - Есть валидный Bearer → юзер.
    - Нет Bearer или он пустой → гость (генерим cookie session_id).
    - Bearer ЕСТЬ, но невалидный → 401 (не маскируем под гостя).
    """
    # Есть ли вообще заголовок?
    if credentials is not None and credentials.credentials:
        # Пробуем аутентифицировать. Если невалидный — пусть падает 401.
        user = await get_current_active_user(credentials, db)
        return CartOwner(user_id=user.id, session_id=None, is_guest=False)

    # Гость
    s = get_settings()
    sid = request.cookies.get(s.GUEST_CART_COOKIE_NAME)
    if sid is None:
        sid = secrets.token_hex(16)
        response.set_cookie(
            key=s.GUEST_CART_COOKIE_NAME,
            value=sid,
            max_age=s.GUEST_CART_COOKIE_MAX_AGE_DAYS * 24 * 3600,
            httponly=True,
            secure=s.REFRESH_COOKIE_SECURE,
            samesite=s.REFRESH_COOKIE_SAMESITE,
            path=s.GUEST_CART_COOKIE_PATH,
        )
    return CartOwner(user_id=None, session_id=sid, is_guest=True)


def get_guest_cart_store(
    redis: Redis = Depends(get_redis),
) -> "GuestCartStore":
    """FastAPI-dependency для GuestCartStore."""
    from app.services.cart_service import GuestCartStore
    return GuestCartStore(redis)


async def require_deleted_access(
    include_deleted: bool = Query(False),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """
    Проверяет, может ли клиент видеть soft-deleted товары.

    Возвращает include_deleted (флаг).

    Правила:
    - include_deleted=False → OK для всех (публичный доступ).
    - include_deleted=True + аноним → 403 (флаг админский).
    - include_deleted=True + CUSTOMER → 403.
    - include_deleted=True + ADMIN/MODERATOR → OK.

    Не используем get_current_active_user напрямую, потому что:
    - аноним не должен получать 401 (эндпоинт публичный);
    - нужен 403 только при include_deleted=True.
    """
    if not include_deleted:
        return False

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="include_deleted requires admin or moderator role",
        )

    try:
        user = await get_current_active_user(credentials, db)
    except HTTPException:
        # Битый/просроченный Bearer — 403, не 401
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="include_deleted requires admin or moderator role",
        )

    if user.role not in (UserRole.ADMIN, UserRole.MODERATOR):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="include_deleted requires admin or moderator role",
        )

    return True
