"""
Утилиты для разбора ошибок БД.

Единая точка правды для определения "какой unique-constraint нарушен".
До CLN-007 логика лежала 7 копиями в сервисах (`_is_*_conflict`), и любая
правка (новый драйвер, третий уровень проверки) требовала синхронных
изменений в 7 местах.

Использование:
    from app.db.errors import is_unique_violation

    _ACTIVE_NAME_CONSTRAINT = "idx_product_active_name"

    try:
        await db.flush()
    except IntegrityError as exc:
        if is_unique_violation(exc, _ACTIVE_NAME_CONSTRAINT):
            raise ConflictError(...) from exc
        raise
"""
from sqlalchemy.exc import IntegrityError

# PostgreSQL SQLSTATE для unique_violation
_UNIQUE_VIOLATION = "23505"


def is_unique_violation(exc: IntegrityError, constraint_name: str) -> bool:
    """
    Проверяет, что IntegrityError вызван указанным unique-constraint.

    Двухуровневая проверка (нужна из-за partial unique index):
    1. sqlstate = 23505 — обязательное условие. Отсекает FK/CHECK/прочее.
    2. Имя констрейнта — либо в diag, либо в тексте сообщения:
       asyncpg для partial unique index иногда не заполняет
       diag.constraint_name, и приходится искать подстроку в str(orig).

    Args:
        exc: исключение SQLAlchemy IntegrityError.
        constraint_name: имя индекса/констрейнта в PostgreSQL
            (например, "idx_product_active_name", "uq_orders_user_idempotency_key").

    Returns:
        True, если IntegrityError вызван именно этим unique-constraint.
        False — если это FK, CHECK, NOT NULL или другой unique-индекс.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False

    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != _UNIQUE_VIOLATION:
        return False

    message = str(orig)
    diag = getattr(orig, "diag", None)
    found = getattr(diag, "constraint_name", None) if diag else None

    return found == constraint_name or constraint_name in message