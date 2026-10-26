# app/core/request_id.py
"""
Request ID: контекст запроса + лог-фильтр.

- contextvars: request_id доступен в любом месте (сервисы, эндпоинты).
- LoggingFilter: добавляет request_id в каждую запись лога.
- Middleware: читает X-Request-ID (валидирует), генерирует UUID4 если нет,
  кладёт в контекст, отдаёт обратно в ответе.

P-14: клиентский X-Request-ID валидируется regex — защита от log injection.
"""
import logging
import re
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9-]{1,64}$")
_REQUEST_ID_HEADER = "X-Request-ID"

# ✅ ContextVar — потокобезопасен, доступен в async-контексте запроса
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Текущий request_id (или '-' вне запроса)."""
    return request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware: request_id в контекст + X-Request-ID в ответе.

    Валидация клиентского заголовка:
    - допустимые символы: a-z, A-Z, 0-9, дефис;
    - длина 1..64;
    - иначе — генерим UUID4 (не доверяем клиенту).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(_REQUEST_ID_HEADER, "")
        if _REQUEST_ID_RE.match(incoming):
            request_id = incoming
        else:
            request_id = uuid.uuid4().hex

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_var.reset(token)


class RequestIDLogFilter(logging.Filter):
    """
    LoggingFilter: добавляет request_id в каждую запись.

    Позволяет в formatter'е использовать %(request_id)s.
    Вне запроса — '-'.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True