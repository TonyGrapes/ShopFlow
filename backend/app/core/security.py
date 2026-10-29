# app/core/security.py
"""
Безопасность: хеширование паролей, JWT access-токены, opaque refresh-токены.

Контракт:
- Пароли: Argon2id. Параметры — в Settings, не в коде.
- Rehash при логине, если параметры устарели.
- Access: JWT HS256, sub=public_id, type=access, exp/iat. Без role/email.
- Refresh: opaque-строка (secrets.token_urlsafe), НЕ JWT.
  В БД храним SHA-256 хеш. Сравнение — constant-time.
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type

from app.core.config import get_settings

# ============================================================
#  Пароли: Argon2id
# ============================================================

def _build_hasher() -> PasswordHasher:
    """Собирает hasher из параметров Settings (не констант)."""
    s = get_settings()
    return PasswordHasher(
        time_cost=s.ARGON2_TIME_COST,
        memory_cost=s.ARGON2_MEMORY_COST,
        parallelism=s.ARGON2_PARALLELISM,
        hash_len=s.ARGON2_HASH_LEN,
        salt_len=s.ARGON2_SALT_LEN,
        type=Type.ID,               # Argon2id — устойчив к side-channel и GPU
    )


def hash_password(password: str) -> str:
    """Хеширует пароль. Строка содержит все параметры — verify их прочитает."""
    return _build_hasher().hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, bool]:
    """
    Проверяет пароль.

    Возвращает (is_valid, needs_rehash):
    - is_valid: пароль верен.
    - needs_rehash: параметры хеша устарели → перехешировать при следующем логине.

    Пустой/битый hash → (False, False) — не падаем, но и не пускаем.
    """
    hasher = _build_hasher()
    try:
        hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False, False
    except (InvalidHashError, ValueError):
        # Битый hash в БД — не пускаем, но и не рехешируем вслепую
        return False, False

    # Пароль верен — проверяем, не устарели ли параметры
    return True, hasher.check_needs_rehash(password_hash)


# ============================================================
#  Access-токен: JWT
# ============================================================

TOKEN_TYPE_ACCESS = "access"


def create_access_token(public_id: str) -> str:
    """
    Создаёт access-токен.

    Payload: sub=public_id, type=access, exp, iat, jti (для отладки).
    НЕ кладём role/email — они берутся из БД на каждом запросе.
    """
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": public_id,
        "type": TOKEN_TYPE_ACCESS,
        "iat": now,
        "exp": now + timedelta(minutes=s.ACCESS_TOKEN_EXPIRES_MINUTES),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload,
        s.SECRET_KEY.get_secret_value(),
        algorithm=s.ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Декодирует и валидирует access-токен.

    Бросает jwt.InvalidTokenError (или подклассы):
    - ExpiredSignatureError
    - InvalidSignatureError
    - DecodeError (невалидный формат)
    """
    s = get_settings()
    payload = jwt.decode(
        token,
        s.SECRET_KEY.get_secret_value(),
        algorithms=[s.ALGORITHM],
        options={"require": ["sub", "exp", "iat", "type"]},
    )
    # ✅ Явная проверка типа токена — refresh не должен проходить как access
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise jwt.InvalidTokenError("Token type is not 'access'")
    return payload


# ============================================================
#  Refresh-токен: opaque + SHA-256
# ============================================================

def generate_refresh_token() -> tuple[str, str]:
    """
    Генерирует refresh-токен и его хеш.

    Возвращает (raw_token, token_hash):
    - raw_token: отдаём клиенту в httpOnly-cookie.
    - token_hash: кладём в БД. Утечка дампа ≠ угон сессий.

    raw_token — opaque (не JWT): ~43 символа base64url, 256 бит энтропии.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 от raw. Детерминирован — позволяет искать по индексу."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_refresh_token_hash(raw_token: str, stored_hash: str) -> bool:
    """Constant-time сравнение. Защита от timing-атак на сравнении хешей."""
    computed = hash_refresh_token(raw_token)
    return hmac.compare_digest(computed, stored_hash)