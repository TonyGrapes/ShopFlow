# app/main.py
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models  # noqa: F401
from app.api.v1.endpoints import (
    addresses,
    admin_orders,
    admin_products,
    admin_refunds,
    admin_reviews,
    admin_users,
    auth,
    cart,
    categories,
    favorites,
    orders,
    products,
    reviews,
)
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.redis import close_redis, get_redis
from app.core.request_id import (
    RequestIDLogFilter,
    RequestIDMiddleware,
)
from app.db.session import get_db
from app.services.storage_service import MinioStorage, get_storage

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
# ✅ OBS-001: Filter на root logger + formatter с request_id
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s"
))
_handler.addFilter(RequestIDLogFilter())

root = logging.getLogger()
root.handlers.clear()
root.addHandler(_handler)
root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ShopFlow API starting up")

    # Redis: fail-fast (как было) — без Redis приложение не работает.
    redis = get_redis()
    await redis.ping()
    logger.info("Redis connection OK")

    # CLN-012: MinIO bucket — fail-soft с retry.
    # Идея: docker compose up -d --wait ориентируется на /health.
    # Если /health → 503, --wait не завершится до появления MinIO,
    # поэтому фактически это fail-fast на уровне compose, но в dev можно
    # стартовать и отлаживать без MinIO.
    storage = get_storage()
    app.state.minio_ready = False
    retry_delays = [2, 5, 10]           # суммарно 17с ожидания — влезает в
                                        # таймаут docker compose --wait (60с)
    for attempt, delay in enumerate(retry_delays, start=1):
        try:
            await asyncio.to_thread(storage.ensure_bucket)
            app.state.minio_ready = True
            logger.info("MinIO bucket ensured (attempt %d/%d)", attempt, len(retry_delays))
            break
        except Exception:
            if attempt < len(retry_delays):
                logger.warning(
                    "MinIO ensure_bucket failed (attempt %d/%d), retry in %ds",
                    attempt, len(retry_delays), delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "MinIO ensure_bucket failed after %d attempts; "
                    "/health will report 'minio: unavailable' until next restart",
                    len(retry_delays),
                )

    yield

    logger.info("👋 ShopFlow API shutting down")
    await close_redis()

app = FastAPI(
    title="ShopFlow API",
    description="A simple shop API",
    version="1.0.0",
    lifespan=lifespan,
    # ✅ CFG-002: в prod docs/openapi отключены
    docs_url="/docs" if settings.ENVIRONMENT == "dev" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "dev" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "dev" else None,
)


# ✅ CFG-003: origins из Settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ OBS-001: middleware до CORS (порядок: CORS снаружи, request-id внутри)
app.add_middleware(RequestIDMiddleware)

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """
    Единый формат доменных ошибок.

    Формат: {"detail": "<строка>", "code": "<машинный код>"}
    Совместим с frontend/src/api/client.ts (читает body.detail как строку).
    """
    body = {"detail": exc.message, "code": exc.code}
    if exc.extra:
        body.update(exc.extra)
    return JSONResponse(status_code=exc.status_code, content=body)

app.include_router(products.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(cart.router, prefix="/api/v1")
app.include_router(favorites.router, prefix="/api/v1")
app.include_router(addresses.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(admin_orders.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(admin_reviews.router, prefix="/api/v1")
app.include_router(categories.public_router, prefix="/api/v1")
app.include_router(categories.admin_router, prefix="/api/v1")
app.include_router(admin_refunds.router, prefix="/api/v1")
app.include_router(admin_products.router, prefix="/api/v1")
app.include_router(admin_users.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Welcome to ShopFlow API", "docs": "/docs"}


@app.get("/health")
async def health_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    storage: MinioStorage = Depends(get_storage),
):
    """
    Healthcheck: БД + Redis + MinIO.

    ✅ TST-005: все три источника через Depends — override'ы в тестах
    работают (db_session, mock_storage, fake_redis). Не требует живого стека.

    Fail-soft: возвращает 503 при недоступности любого компонента
    с детализацией по каждому.
    """
    db_ok = False
    redis_ok = False
    minio_ok = False

    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Health: DB unavailable")

    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        logger.exception("Health: Redis unavailable")

        # CLN-012: лёгкая проверка MinIO.
    # - minio_ready is False (lifespan упал) → сразу 503 без S3-вызова.
    # - minio_ready is None (тесты через ASGITransport, lifespan не запускался)
    #   или True (успешный старт) → bucket_exists (1 дешёвый S3-вызов
    #   вместо ensure_bucket на каждый healthcheck).
    minio_ready = getattr(app.state, "minio_ready", None)
    if minio_ready is False:
        minio_ok = False
    else:
        try:
            minio_ok = await asyncio.to_thread(storage.bucket_exists)
        except Exception:
            logger.exception("Health: MinIO unavailable")
            minio_ok = False
            
    if db_ok and redis_ok and minio_ok:
        return {
            "status": "healthy",
            "database": "connected",
            "redis": "connected",
            "minio": "connected",
        }

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "unhealthy",
        "database": "connected" if db_ok else "unavailable",
        "redis": "connected" if redis_ok else "unavailable",
        "minio": "connected" if minio_ok else "unavailable",
    }