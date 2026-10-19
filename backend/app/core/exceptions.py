"""
Доменные исключения приложения.

Зачем:
- Сервисы не должны управлять транзакцией (rollback — обязанность get_db).
- Сервисы бросают доменные исключения, FastAPI-обработчик превращает
  их в HTTP-ответы единого формата.

Формат ответа (совместим с frontend/src/api/client.ts):
    {"detail": "<человекочитаемое сообщение>", "code": "<машинный код>"}

- detail — ВСЕГДА строка (фронт рендерит её как есть).
- code — опциональный машинный код для клиентской логики.
"""

from typing import Any


class AppError(Exception):
    """
    Базовое доменное исключение.

    Атрибуты:
    - message: человекочитаемое сообщение (уходит клиенту в detail).
    - code: машинный код для клиента (опционально).
    - status_code: HTTP-статус (устанавливается наследниками).
    - extra: дополнительные поля (попадают в ответ как есть, если нужны).
    """
    status_code: int = 500
    default_code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.extra = extra or {}


class NotFoundError(AppError):
    """404. Ресурс не найден."""
    status_code = 404
    default_code = "not_found"


class ConflictError(AppError):
    """409. Конфликт состояния (race, дубликат, недопустимый переход)."""
    status_code = 409
    default_code = "conflict"


class ValidationError(AppError):
    """422. Семантическая ошибка входных данных."""
    status_code = 422
    default_code = "validation_error"


class ForbiddenError(AppError):
    """403. Действие запрещено для текущего пользователя."""
    status_code = 403
    default_code = "forbidden"


class UnauthorizedError(AppError):
    """401. Аутентификация не пройдена."""
    status_code = 401
    default_code = "unauthorized"