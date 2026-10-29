# app/services/auth_service.py
"""
Сервис аутентификации.

Секьюрити-операции (отзыв семьи refresh-токенов при reuse-detection)
выполняются в ОТДЕЛЬНОЙ транзакции — чтобы 401 в основном запросе
их не откатил через get_db.rollback().
"""
import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session_factory
from app.models.refresh_token import RefreshToken

logger = logging.getLogger(__name__)


async def revoke_family(db: AsyncSession, family_id) -> int:
    """
    Отзыв семьи в ПЕРЕДАННОЙ сессии (без commit).

    Использование:
    - logout (в основной сессии — commit сделает get_db);
    - внутри revoke_family_independently (со своим commit).
    """
    now = datetime.now(UTC)
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked.is_(False),
        )
        .values(revoked=True, revoked_at=now)
    )
    await db.flush()
    return result.rowcount or 0


async def revoke_family_independently(family_id) -> int:
    """
    Отзыв семьи в ОТДЕЛЬНОЙ сессии с собственным commit.

    Используется в reuse-detection: основной запрос бросает 401,
    get_db делает rollback основной сессии. Если бы мы писали в ту же
    сессию — отзыв бы откатился. Поэтому — своя транзакция.

    Возвращает число отозванных строк.
    """
    factory = get_async_session_factory()
    async with factory() as session:
        count = await revoke_family(session, family_id)
        await session.commit()
        logger.warning(
            "Revoked %d refresh-tokens in family=%s", count, family_id
        )
        return count