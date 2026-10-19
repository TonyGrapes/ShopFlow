# app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import models  # noqa: F401
from app.api.v1.endpoints import (
    addresses,
    admin_orders,
    admin_refunds,
    admin_reviews,
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

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ShopFlow API starting up")

    # ✅ Прогреваем Redis — ранний fail-fast
    redis = get_redis()
    await redis.ping()
    logger.info("Redis connection OK")

    yield

    logger.info("👋 ShopFlow API shutting down")
    await close_redis()


app = FastAPI(
    title="ShopFlow API",
    description="A simple shop API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/")
async def root():
    return {"message": "Welcome to ShopFlow API", "docs": "/docs"}


@app.get("/health")
async def health_check(response: Response):
    """
    Healthcheck: БД + Redis.
    """
    db_ok = False
    redis_ok = False

    try:
        from app.db.session import get_async_session_factory
        factory = get_async_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Health: DB unavailable")

    try:
        redis = get_redis()
        await redis.ping()
        redis_ok = True
    except Exception:
        logger.exception("Health: Redis unavailable")

    if db_ok and redis_ok:
        return {"status": "healthy", "database": "connected", "redis": "connected"}

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "unhealthy",
        "database": "connected" if db_ok else "unavailable",
        "redis": "connected" if redis_ok else "unavailable",
    }