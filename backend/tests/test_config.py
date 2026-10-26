# tests/test_config.py
"""
Тесты Settings-валидации (CFG-001, CFG-002, CFG-003).

Проверяют fail-fast для prod: слабая конфигурация не даёт стартовать.
"""
import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _valid_env() -> dict:
    """Минимальный валидный набор env для Settings."""
    return {
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "POSTGRES_DB": "d",
        "POSTGRES_HOST": "h",
        "POSTGRES_PORT": "5432",
        "REDIS_URL": "redis://r:6379/0",
        "REDIS_PASSWORD": "r",
        "MINIO_ENDPOINT": "m:9000",
        "MINIO_PUBLIC_ENDPOINT": "m:9000",
        "MINIO_ACCESS_KEY": "a",
        "MINIO_SECRET_KEY": "s",
        "SECRET_KEY": "x" * 32,
    }


class TestEnvironmentDefaults:
    def test_default_is_dev(self):
        """ENVIRONMENT по умолчанию — dev."""
        with patch.dict(os.environ, _valid_env(), clear=True):
            s = Settings(_env_file=None)
            assert s.ENVIRONMENT == "dev"

    def test_dev_allows_insecure_cookie(self):
        """В dev REFRESH_COOKIE_SECURE=False — ок."""
        with patch.dict(os.environ, _valid_env(), clear=True):
            s = Settings(_env_file=None, REFRESH_COOKIE_SECURE=False)
            assert s.ENVIRONMENT == "dev"


class TestProdSecurity:
    def test_prod_requires_secure_cookie(self):
        """CFG-001: в prod REFRESH_COOKIE_SECURE=False → ValidationError."""
        env = _valid_env()
        env.update({
            "ENVIRONMENT": "prod",
            "REFRESH_COOKIE_SECURE": "false",
        })
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc:
                Settings(_env_file=None)
            assert "REFRESH_COOKIE_SECURE" in str(exc.value)

    def test_prod_secure_cookie_ok(self):
        """В prod REFRESH_COOKIE_SECURE=True — ок."""
        env = _valid_env()
        env.update({
            "ENVIRONMENT": "prod",
            "REFRESH_COOKIE_SECURE": "true",
            "CORS_ORIGINS": '["https://shopflow.example.com"]',
        })
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
            assert s.ENVIRONMENT == "prod"

    def test_prod_rejects_localhost_in_cors(self):
        """CFG-003: localhost в CORS_ORIGINS prod → ValidationError."""
        env = _valid_env()
        env.update({
            "ENVIRONMENT": "prod",
            "REFRESH_COOKIE_SECURE": "true",
            "CORS_ORIGINS": '["http://localhost:5173"]',
        })
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc:
                Settings(_env_file=None)
            assert "localhost" in str(exc.value).lower()

    def test_cors_origins_from_env(self):
        """CFG-003: CORS_ORIGINS парсится из env как JSON-список."""
        env = _valid_env()
        env["CORS_ORIGINS"] = '["https://a.com", "https://b.com"]'
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=None)
            assert s.CORS_ORIGINS == ["https://a.com", "https://b.com"]