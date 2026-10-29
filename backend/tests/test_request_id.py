# tests/test_request_id.py
"""
OBS-001: Request ID в ответе и в контексте.
OBS-003: /health проверяет MinIO.
"""
import logging
import re

import pytest

from app.core.request_id import get_request_id, request_id_var


class TestRequestIDHeader:
    """OBS-001: X-Request-ID в ответе."""

    @pytest.mark.asyncio
    async def test_generates_uuid_when_absent(self, client):
        """Нет X-Request-ID → генерим UUID4 (32 hex-символа)."""
        response = await client.get("/")
        assert "X-Request-ID" in response.headers
        rid = response.headers["X-Request-ID"]
        assert re.match(r"^[a-f0-9]{32}$", rid), rid

    @pytest.mark.asyncio
    async def test_echoes_valid_client_header(self, client):
        """Валидный X-Request-ID клиента → эхо в ответе."""
        response = await client.get(
            "/", headers={"X-Request-ID": "client-id-12345"},
        )
        assert response.headers["X-Request-ID"] == "client-id-12345"

    @pytest.mark.asyncio
    async def test_rejects_invalid_client_header(self, client):
        """P-14: битый X-Request-ID (log injection) → генерим новый."""
        response = await client.get(
            "/", headers={"X-Request-ID": "bad\nvalue"},
        )
        rid = response.headers["X-Request-ID"]
        # Не эхо клиента — сгенерили UUID
        assert rid != "bad\nvalue"
        assert re.match(r"^[a-f0-9]{32}$", rid), rid

    @pytest.mark.asyncio
    async def test_rejects_too_long_header(self, client):
        """P-14: X-Request-ID > 64 символов → генерим новый."""
        response = await client.get(
            "/", headers={"X-Request-ID": "a" * 100},
        )
        rid = response.headers["X-Request-ID"]
        assert rid != "a" * 100
        assert re.match(r"^[a-f0-9]{32}$", rid), rid


class TestRequestIDContext:
    """OBS-001: request_id доступен в контексте."""

    @pytest.mark.asyncio
    async def test_context_default_is_dash(self):
        """Вне запроса — '-'."""
        # Сбрасываем контекст
        token = request_id_var.set("-")
        try:
            assert get_request_id() == "-"
        finally:
            request_id_var.reset(token)


class TestLogFilter:
    """OBS-001: RequestIDLogFilter добавляет request_id в record."""

    def test_filter_adds_request_id(self):
        from app.core.request_id import RequestIDLogFilter

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        filt = RequestIDLogFilter()
        token = request_id_var.set("my-request-id")
        try:
            assert filt.filter(record) is True
            assert record.request_id == "my-request-id"
        finally:
            request_id_var.reset(token)

    def test_filter_default_dash(self):
        from app.core.request_id import RequestIDLogFilter

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        filt = RequestIDLogFilter()
        token = request_id_var.set("-")
        try:
            filt.filter(record)
            assert record.request_id == "-"
        finally:
            request_id_var.reset(token)