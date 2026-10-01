# app/db/session.py
from functools import lru_cache
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine():
    """Создаёт engine лениво."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.SQL_ECHO, 
        pool_pre_ping=True,
    )


@lru_cache
def get_async_session_factory():
    """Создаёт фабрику сессий лениво."""
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db():
    """
    Dependency для FastAPI.

    ✅ Единая точка фиксации транзакции:
    - commit после успешного ответа эндпоинта;
    - rollback при любом исключении;
    - session.close() в finally.

    Сервисы НЕ вызывают commit — только flush.
    """
    session = get_async_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
