# app/api/v1/endpoints/auth.py
import logging
from datetime import datetime, timedelta, timezone

from app.api.v1.deps import User, get_current_active_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.enum import UserRole, UserStatus
from app.db.session import get_db
from app.models.email_verification import EmailVerification
from app.models.refresh_token import RefreshToken
from app.models.user import User as UserModel
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    revoke_family,
    revoke_family_independently,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ============================================================
#  Вспомогательные: cookie, refresh-lifecycle
# ============================================================

def _set_refresh_cookie(response: Response, raw_token: str, expires_days: int) -> None:
    """
    Ставит httpOnly-cookie с refresh-токеном.

    Path узкий (/api/v1/auth) — cookie не ездит в другие эндпоинты.
    SameSite=Lax — dev: localhost:5173 → :8000 = same-site, кука уходит.
    Secure=False в dev (http), True в prod (https).
    """
    s = get_settings()
    response.set_cookie(
        key=s.REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=expires_days * 24 * 3600,
        httponly=True,
        secure=s.REFRESH_COOKIE_SECURE,
        samesite=s.REFRESH_COOKIE_SAMESITE,
        path=s.REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        key=s.REFRESH_COOKIE_NAME,
        path=s.REFRESH_COOKIE_PATH,
    )


async def _issue_token_pair(
    db: AsyncSession,
    response: Response,
    user: UserModel,
    family_id=None,
) -> TokenResponse:
    """
    Выдаёт access + refresh. Refresh кладёт в БД (хеш) и в cookie.

    family_id=None → новый логин (новая семья).
    family_id=UUID → ротация внутри существующей семьи.
    """
    s = get_settings()

    # Access
    access = create_access_token(str(user.public_id))

    # Refresh — opaque, в БД хеш
    raw_refresh, token_hash = generate_refresh_token()
    now = datetime.now(timezone.utc)
    record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(days=s.REFRESH_TOKEN_EXPIRES_DAYS),
        revoked=False,
    )
    if family_id is not None:
        record.family_id = family_id
    db.add(record)
    await db.flush()                # commit — в get_db

    _set_refresh_cookie(response, raw_refresh, s.REFRESH_TOKEN_EXPIRES_DAYS)

    return TokenResponse(
        access_token=access,
        expires_in=s.ACCESS_TOKEN_EXPIRES_MINUTES * 60,
    )


# ============================================================
#  POST /auth/register
# ============================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Регистрация. Создаёт PENDING/unverified юзера + токен верификации.

    'Письмо' пишется в лог (реальный SMTP — позже).
    Логин-oracle: не различаем 'email занят' и 'ok'? Нет — на register
    это неизбежно (юзер сам знает свой email). Оставляем 409.
    """
    existing = await db.execute(
        select(UserModel).where(
            UserModel.email == data.email,
            UserModel.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    s = get_settings()
    user = UserModel(
        email=data.email,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        phone_number=data.phone_number,
        role=UserRole.CUSTOMER,
        status=UserStatus.PENDING,       # ✅ инвариант: PENDING ⟺ !is_email_verified
        is_email_verified=False,
    )
    db.add(user)
    await db.flush()

    # Токен верификации
    verification = EmailVerification(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=s.EMAIL_VERIFICATION_EXPIRES_HOURS),
    )
    db.add(verification)
    await db.flush()

    # 'Письмо' в лог
    logger.info(
        "📧 Verification email for %s: GET /api/v1/auth/verify-email?token=%s",
        user.email, verification.token,
    )

    return UserResponse.model_validate(user)


# ============================================================
#  POST /auth/login
# ============================================================

@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Логин.

    - Неизвестный email и неверный пароль → одинаковый 401 (login-oracle off).
    - banned → 403.
    - !is_email_verified → 403 с подсказкой про resend.
    - При необходимости — прозрачный rehash пароля.
    """
    result = await db.execute(
        select(UserModel).where(
            UserModel.email == data.email,
            UserModel.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    # ✅ Единый 401 — не даём оракулу различить 'email нет' vs 'пароль неверен'
    if user is None or not verify_password(data.password, user.password_hash)[0]:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ✅ Прозрачный rehash при устаревших параметрах
    is_valid, needs_rehash = verify_password(data.password, user.password_hash)
    # (is_valid гарантированно True — мы уже проверили выше; но rehash — второй проход)
    if needs_rehash:
        user.password_hash = hash_password(data.password)

    if user.status == UserStatus.BANNED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is banned")

    if not user.is_email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Email not verified. Use POST /api/v1/auth/resend-verification",
        )

    return await _issue_token_pair(db, response, user)


# ============================================================
#  POST /auth/refresh
# ============================================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Ротация refresh-токена.

    Reuse-detection: если пришёл revoked-токен — отзываем ВСЮ семью.
    """
    s = get_settings()
    raw_token = request.cookies.get(s.REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token missing")

    token_hash = hash_refresh_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()

    if record is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    now = datetime.now(timezone.utc)

    # ✅ Reuse-detection: revoked-токен в живом запросе → компрометация семьи
    if record.revoked:
        # Лог — точный: любое обращение к revoked-токену = сигнал для оператора.
        # HTTP detail — нейтральный: клиент не должен различать "logout" и "reuse".
        logger.warning(
            "Attempt to use revoked refresh token: family=%s user=%s token_hash=%s",
            record.family_id, record.user_id, record.token_hash[:8],
        )
        await revoke_family_independently(record.family_id)
        _clear_refresh_cookie(response)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Refresh token is revoked",
        )
        
    if record.expires_at <= now:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    # Ротация: отзываем старый, выдаём новый в той же семье
    record.revoked = True
    record.revoked_at = now

    user = await db.get(UserModel, record.user_id)
    if user is None or user.deleted_at is not None:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if user.status == UserStatus.BANNED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is banned")

    return await _issue_token_pair(db, response, user, family_id=record.family_id)


# ============================================================
#  POST /auth/logout
# ============================================================

@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    s = get_settings()
    raw_token = request.cookies.get(s.REFRESH_COOKIE_NAME)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()
        if record is not None:
            await revoke_family(db, record.family_id)   # ← было _revoke_family
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out")

# ============================================================
#  GET /auth/me
# ============================================================

@router.get("/me", response_model=UserResponse)
async def me(current: User = Depends(get_current_active_user)):
    """Текущий пользователь. get_current_active_user уже загрузил ORM-объект."""
    return UserResponse.model_validate(current.orm)


# ============================================================
#  GET /auth/verify-email
# ============================================================

@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """
    Верификация email по токену из 'письма'.

    Меняет status и is_email_verified В ОДНОЙ функции (инвариант).
    """
    result = await db.execute(
        select(EmailVerification).where(EmailVerification.token == token)
    )
    verification = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if verification is None or verification.verified_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or used token")
    if verification.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired")

    user = await db.get(UserModel, verification.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "User not found")

    verification.verified_at = now
    # ✅ Инвариант: два флага меняем вместе
    user.is_email_verified = True
    user.status = UserStatus.ACTIVE

    await db.flush()

    return MessageResponse(message="Email verified")


# ============================================================
#  POST /auth/resend-verification
# ============================================================

@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    data: ResendVerificationRequest,        # email в теле — без auth (юзер ещё не верифицирован)
    db: AsyncSession = Depends(get_db),
):
    """
    Повторная отправка письма.

    Защита от email-oracle: ВСЕГДА 200 с нейтральным текстом.
    Не подтверждаем, существует ли email и верифицирован ли он.
    """
    result = await db.execute(
        select(UserModel).where(
            UserModel.email == data.email,
            UserModel.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if user is not None and not user.is_email_verified:
        # ✅ Инвалидируем все pending-токены — 'действующим' остаётся только новый
        now = datetime.now(timezone.utc)
        await db.execute(
            update(EmailVerification)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.verified_at.is_(None),
            )
            .values(verified_at=now)     # помечаем как 'погашенные'
        )

        s = get_settings()
        verification = EmailVerification(
            user_id=user.id,
            expires_at=now + timedelta(hours=s.EMAIL_VERIFICATION_EXPIRES_HOURS),
        )
        db.add(verification)
        await db.flush()

        logger.info(
            "📧 Resent verification email for %s: GET /api/v1/auth/verify-email?token=%s",
            user.email, verification.token,
        )

    return MessageResponse(
        message="If the address is registered and unverified, an email has been sent."
    )