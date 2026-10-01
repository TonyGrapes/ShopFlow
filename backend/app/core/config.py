# app/core/config.py
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Единая точка правды для всех настроек приложения.

    Принципы:
    - Никаких дефолтов для секретов → fail fast при отсутствии .env
    - extra='forbid' → падаем при неизвестных переменных
    """
    # ==========================================
    # CACHE
    # ==========================================
    PRODUCT_LIST_CACHE_TTL_SECONDS: int = Field(
        default=60, gt=0,
        description="Base TTL кэша списка товаров",
    )
    PRODUCT_LIST_CACHE_TTL_JITTER_SECONDS: int = Field(
        default=10, ge=0, le=60,
        description="Случайный разброс TTL для защиты от лавины",
    )
    # ==========================================
    # DATABASE
    # ==========================================
    # DATABASE_URL: SecretStr = "postgresql+asyncpg://user:pass@db:5432/shopflow"
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    SQL_ECHO: bool = False

    # ==========================================
    # REDIS
    # ==========================================
    REDIS_URL: str
    REDIS_PASSWORD: SecretStr

    # ==========================================
    # MINIO
    # ==========================================
    MINIO_ENDPOINT: str                                     # внутренний: minio:9000
    MINIO_PUBLIC_ENDPOINT: str                              # ✅ НОВОЕ: публичный для URL
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: SecretStr
    MINIO_BUCKET: str = "shopflow-media"
    MINIO_USE_SSL: bool = False
    MINIO_PORT: int = 9000
    MINIO_CONSOLE_PORT: int = 9001

    # ==========================================
    # AUTH
    # ==========================================
    SECRET_KEY: SecretStr = Field(..., description="JWT signing key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRES_MINUTES: int = Field(default=30, gt=0)

    # ==========================================
    # AUTH: Argon2id parameters
    # ==========================================
    ARGON2_TIME_COST: int = Field(default=2, ge=1, le=10)
    ARGON2_MEMORY_COST: int = Field(default=19456, ge=8192, le=262144)  # 19 MiB — OWASP
    ARGON2_PARALLELISM: int = Field(default=1, ge=1, le=4)
    ARGON2_HASH_LEN: int = Field(default=32, ge=16, le=64)
    ARGON2_SALT_LEN: int = Field(default=16, ge=8, le=32)

    # ==========================================
    # AUTH: Refresh tokens
    # ==========================================
    REFRESH_TOKEN_EXPIRES_DAYS: int = Field(default=30, gt=0)
    EMAIL_VERIFICATION_EXPIRES_HOURS: int = Field(default=24, gt=0)

    # ==========================================
    # AUTH: Cookie
    # ==========================================
    REFRESH_COOKIE_NAME: str = "shopflow_refresh"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_SECURE: bool = False    # True в prod (https)
    REFRESH_COOKIE_SAMESITE: str = "lax"   # localhost:5173 → :8000 = same-site


    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key_strength(cls, v: SecretStr) -> SecretStr:
        """
        ✅ Fail-fast: SECRET_KEY для HS256 обязан быть ≥ 32 байт (RFC 7518 §3.2).

        Почему именно в Settings, а не warning в рантайме:
        - приложение НЕ должно стартовать со слабым ключом — это инвариант;
        - согласуется с принципом extra='forbid' (слабая конфигурация = падение);
        - dev-.env копируют в prod, и warning там никто не читает.

        Проверяем БАЙТЫ, а не длину строки: HMAC видит именно байты.
        """
        raw = v.get_secret_value()
        if len(raw.encode("utf-8")) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 bytes (256 bits) for HS256. "
                "Generate one with: openssl rand -hex 32"
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        frozen=True,
        extra="forbid",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD.get_secret_value()}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url_with_password(self) -> str:
        """
        Возвращает URL с паролем для redis.asyncio.

        Формат: redis://:PASSWORD@HOST:PORT/DB
        Пароль вставляется только если не задан в URL.
        """
        url = str(self.REDIS_URL).strip()
        password = self.REDIS_PASSWORD.get_secret_value()

        # Если пароль уже в URL или пустой — вернуть как есть
        if not password or "@" in url.split("://", 1)[-1]:
            return url

        scheme, rest = url.split("://", 1)
        return f"{scheme}://:{password}@{rest}"

    @property
    def minio_client_kwargs(self) -> dict:
        return {
            "endpoint": self.MINIO_ENDPOINT,
            "access_key": self.MINIO_ACCESS_KEY,
            "secret_key": self.MINIO_SECRET_KEY.get_secret_value(),
            "secure": self.MINIO_USE_SSL,
        }


@lru_cache()
def get_settings() -> Settings:
    return Settings()