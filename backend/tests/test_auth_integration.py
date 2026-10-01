# tests/test_auth_integration.py
"""
Интеграционные тесты аутентификации.

Отличие от test_auth.py: НЕ override'им get_db.
Используем реальную прод-семантику get_db (commit/rollback в finally).
Это единственный способ поймать баги, где HTTPException откатывает
изменения, которые должны были выжить.
"""
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.enum import UserRole, UserStatus
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User as UserModel


TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)


@pytest_asyncio.fixture(scope="function")
async def real_db_engine():
    """
    Движок для интеграционных тестов. НЕ переиспользует db_session
    из conftest — там savepoint-изоляция, она ломает прод-семантику.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.execute(__import__("sqlalchemy").text('CREATE EXTENSION IF NOT EXISTS ltree'))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # После теста — очистка (drop_all, чтобы не мусорить)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def real_client(real_db_engine):
    """
    HTTP-клиент, работающий с реальной get_db-семантикой.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as tc:
        yield tc

@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_reuse_detection_persists_after_401(
    real_db_engine, real_client
):
    """
    ✅ Reuse-detection должен ОТОЗВАТЬ семью даже после 401.

    Проверяет прод-семантику get_db: HTTPException → rollback.
    Отзыв семьи обязан выжить — для этого он идёт в отдельной сессии.

    Без фикса (revoke_family_independently) этот тест ПАДАЕТ:
    revoked останутся False для всех токенов семьи.
    """
    # 1. Создать verified-юзера напрямую через реальную сессию
    factory = async_sessionmaker(real_db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = UserModel(
            email="reuse-test@example.com",
            password_hash=hash_password("reuse-password-1234"),
            first_name="Reuse", last_name="Test", phone_number="+79997770001",
            role=UserRole.CUSTOMER,
            status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    # 2. Login → refresh_1
    r1 = await real_client.post("/api/v1/auth/login", json={
        "email": "reuse-test@example.com",
        "password": "reuse-password-1234",
    })
    assert r1.status_code == 200
    from app.core.config import get_settings
    s = get_settings()
    refresh_1_raw = r1.cookies[s.REFRESH_COOKIE_NAME]

    # 3. Refresh → refresh_2 (в jar клиента теперь refresh_2)
    r2 = await real_client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200

    # 4. Reuse старого refresh_1 — насильно подкладываем в jar
    real_client.cookies.set(s.REFRESH_COOKIE_NAME, refresh_1_raw, path=s.REFRESH_COOKIE_PATH)
    reuse = await real_client.post("/api/v1/auth/refresh")
    assert reuse.status_code == 401
    assert "revoked" in reuse.json()["detail"].lower()

    # 5. ✅ ГЛАВНОЕ: проверяем БД — вся семья должна быть отозвана
    async with factory() as session:
        records = (await session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id)
        )).scalars().all()
        assert len(records) >= 2, f"Expected >=2 tokens, got {len(records)}"
        revoked_count = sum(1 for r in records if r.revoked)
        assert revoked_count == len(records), (
            f"Expected ALL {len(records)} revoked, got {revoked_count}. "
            f"Reuse-detection rollback bug?"
        )