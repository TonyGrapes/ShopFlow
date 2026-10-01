# backend/app/smoke_models.py
"""
Smoke-тест слоя данных: создаёт по строке в каждой таблице,
читает обратно, откатывает транзакцию, exit 0 при успехе.

Запуск:
    docker compose exec backend uv run python -m app.smoke_models
    docker compose exec backend uv run python app/smoke_models.py
"""
import asyncio
import sys
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# Корень проекта импортируемым при любом способе запуска
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Boolean, DateTime, Integer, Numeric, func, select
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app import models  # noqa: F401 — регистрирует все модели в Base.metadata
from app.db.base import Base
from app.db.session import get_engine


def now():
    return datetime.now(timezone.utc)


def dummy_value(col, created_ids):
    """Подбирает значение для колонки: FK → спецслучаи → тип."""
    name = col.name

    # 1. Внешний ключ -> id уже созданной родительской строки
    if col.foreign_keys:
        parent = next(iter(col.foreign_keys)).column.table.name
        return created_ids[parent]

    # 2. Спецслучаи: CHECK / UNIQUE ограничения
    special = {
        "rating": 5,
        "quantity": 1,
        "product_count": 1,
        "discount_value": Decimal("10.00"),
        "amount": Decimal("10.00"),
        "product_cost": Decimal("10.00"),
        "min_order_amount": Decimal("1.00"),
        "valid_from": now() - timedelta(days=1),
        "valid_until": now() + timedelta(days=30),
        "expires_at": now() + timedelta(days=1),
        "reason": "other",
        "email": f"smoke_{uuid.uuid4().hex[:8]}@example.com",
        "phone_number": f"+7999{uuid.uuid4().int % 10_000_000:07d}",
        "password_hash": "smoke_hash",
        "path": f"Smoke_{uuid.uuid4().hex[:6]}",
        "code": f"SMOKE-{uuid.uuid4().hex[:8].upper()}",
        "name": f"smoke_{uuid.uuid4().hex[:8]}",
        "first_name": "Smoke",
        "last_name": "Test",
        "description": "smoke description",
        "title": "smoke title",
        "comment": "smoke comment",
    }
    if name in special:
        return special[name]

    # 3. Фолбэк по типу колонки
    t = col.type
    if isinstance(t, SAEnum):
        return t.enums[0]
    if isinstance(t, PG_UUID):
        return uuid.uuid4()
    if isinstance(t, Boolean):
        return False
    if isinstance(t, DateTime):
        return now()
    if isinstance(t, Numeric):
        return Decimal("10.00")
    if isinstance(t, Integer):
        return 1
    return f"smoke_{name}_{uuid.uuid4().hex[:4]}"


async def main() -> int:
    engine = get_engine()
    tables = Base.metadata.sorted_tables
    created_ids: dict[str, object] = {}

    async with engine.connect() as conn:
        tx = await conn.begin()
        try:
            for table in tables:
                values = {}
                for col in table.columns:
                    if col.primary_key or col.nullable:
                        continue
                    if col.server_default is not None or col.default is not None:
                        continue
                    values[col.name] = dummy_value(col, created_ids)

                # 🛡️ Защита: callable не может быть значением колонки
                for k, v in values.items():
                    if callable(v):
                        raise TypeError(
                            f"{table.name}.{k}: значение — callable ({v!r}). "
                            f"Забыты скобки вызова?"
                        )

                try:
                    result = await conn.execute(table.insert().values(**values))
                except Exception:
                    # 🩺 Диагностика: на какой таблице упали и что генерировали
                    print(f"\n❌ FAILED on table: {table.name}")
                    print("values:", {k: type(v).__name__ for k, v in values.items()})
                    raise

                created_ids[table.name] = result.inserted_primary_key[0]

            # READ BACK
            print(f"{'table':<25} | rows")
            print("-" * 35)
            for table in tables:
                count = (await conn.execute(
                    select(func.count()).select_from(table)
                )).scalar_one()
                assert count == 1, f"{table.name}: expected 1, got {count}"
                print(f"{table.name:<25} | {count}")
        finally:
            await tx.rollback()

    await engine.dispose()
    print(f"\n✅ SMOKE OK: {len(tables)} tables written & read back, rolled back")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception:
        traceback.print_exc()
        sys.exit(1)