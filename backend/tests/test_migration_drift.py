"""
TST-003: тест дрейфа миграций.

Проверяет, что схема после `alembic upgrade head` совпадает с моделью.

Зачем:
- conftest.py создаёт тестовую схему через `Base.metadata.create_all`,
  минуя миграции. Если модель и миграция разойдутся (добавили колонку
  в модель, но забыли миграцию; создали индекс в миграции, но не в
  модели; переименовали CHECK), текущие тесты этого НЕ поймают.
- Этот тест накатывает миграции на изолированную БД `shopflow_drift_test`
  и сравнивает результат с `Base.metadata`.

Что сравнивается (первая итерация):
- Таблицы (имена, минус alembic_version).
- Колонки: имена, nullable, membership в PK.
- Уникальность (UNIQUE constraints + partial unique indexes) — по НАБОРУ
  КОЛОНОК, не по именам: PG автогенерит `<table>_<col>_key` для UNIQUE,
  а в модели `unique=True` даёт безымянный UniqueConstraint.
- Обычные (не-unique) индексы — по именам (idx_* семантичны).
- CHECK-констрейнты: имена.

Что НЕ сравнивается (сознательно — иначе будут ложные падения):
- Точные типы (VARCHAR vs String(255), Enum, Ltree — сложно нормализовать
  между SQLAlchemy и information_schema).
- Server defaults (now() vs CURRENT_TIMESTAMP — эквивалентны, но строкой
  не совпадут).
- Точные выражения CHECK / partial-index-WHERE (PostgreSQL добавляет касты
  вроде `discount_value > 0::numeric`; сравниваем только имена для CHECK,
  и колонки для partial unique).
- Имена UNIQUE constraints (PG автогенерит; в модели может быть None).
- Имена FK (autogen даёт `<table>_<col>_fkey`, в модели имя не задаётся;
  дрейф по FK-именам ловим через сравнение таблиц/колонок).

Запуск:
    pytest tests/test_migration_drift.py -v
    pytest -m integration -v      # или через маркер

При обнаружении дрейфа: тест падает с diff, а починка (правка миграции
или модели) — отдельная задача. См. backend/MIGRATIONS.md.
"""
import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401 — регистрирует все модели в Base.metadata
from app.db.base import Base

DRIFT_DB_NAME = "shopflow_drift_test"
BACKEND_DIR = Path(__file__).parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


# ============================================================
#  URL-хелперы
# ============================================================

def _async_db_url(db_name: str) -> str:
    """Async URL для указанной БД (для инспекции)."""
    return (
        f"postgresql+asyncpg://{os.getenv('POSTGRES_USER')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{db_name}"
    )


async def _admin_conn():
    """Соединение к системной БД `postgres` (для CREATE/DROP DATABASE)."""
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database="postgres",
    )


async def _create_db(db_name: str) -> None:
    conn = await _admin_conn()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _drop_db(db_name: str) -> None:
    conn = await _admin_conn()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await conn.close()


# ============================================================
#  Миграции
# ============================================================

def _run_migrations(drift_url: str) -> None:
    """
    Синхронный `alembic upgrade head` (Alembic работает через sync engine).

    Env-override SHOPFLOW_MIGRATIONS_DB_URL — см. alembic/env.py.
    URL стрипается до sync (psycopg2) — Alembic не поддерживает async URL
    в `engine_from_config`.
    """
    cfg = Config(str(ALEMBIC_INI))
    os.environ["SHOPFLOW_MIGRATIONS_DB_URL"] = drift_url.replace("+asyncpg", "")
    try:
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("SHOPFLOW_MIGRATIONS_DB_URL", None)


# ============================================================
#  Fixture — чистая БД на время теста
# ============================================================

@pytest_asyncio.fixture(scope="function")
async def drift_db_url():
    """Создаёт shopflow_drift_test, удаляет после теста (даже при падении)."""
    await _create_db(DRIFT_DB_NAME)
    try:
        yield _async_db_url(DRIFT_DB_NAME)
    finally:
        await _drop_db(DRIFT_DB_NAME)


# ============================================================
#  Сравнение схем
# ============================================================

def _collect_drift(metadata, inspector) -> list[str]:
    """
    Сравнивает `metadata` (модели) с `inspector` (фактическая БД).

    Возвращает список человекочитаемых строк — по одной на расхождение.
    Пустой список = дрейфа нет.
    """
    drifts: list[str] = []

    # 1. Таблицы
    model_tables = set(metadata.tables.keys()) - {"alembic_version"}
    db_tables = set(inspector.get_table_names()) - {"alembic_version"}

    only_model = model_tables - db_tables
    only_db = db_tables - model_tables
    if only_model:
        drifts.append(f"tables in model but NOT in DB: {sorted(only_model)}")
    if only_db:
        drifts.append(f"tables in DB but NOT in model: {sorted(only_db)}")

    # 2. По каждой таблице
    for table_name in sorted(model_tables & db_tables):
        table = metadata.tables[table_name]

        # 2.1. Колонки
        model_cols = {c.name: c for c in table.columns}
        db_cols = {c["name"]: c for c in inspector.get_columns(table_name)}

        if model_cols.keys() - db_cols.keys():
            drifts.append(
                f"{table_name}: columns in model but not in DB: "
                f"{sorted(model_cols.keys() - db_cols.keys())}"
            )
        if db_cols.keys() - model_cols.keys():
            drifts.append(
                f"{table_name}: columns in DB but not in model: "
                f"{sorted(db_cols.keys() - model_cols.keys())}"
            )

        # 2.2. Nullable (только для колонок, которые есть в обоих)
        for name in model_cols.keys() & db_cols.keys():
            m_nullable = model_cols[name].nullable
            d_nullable = db_cols[name]["nullable"]
            if m_nullable != d_nullable:
                drifts.append(
                    f"{table_name}.{name}: nullable mismatch "
                    f"(model={m_nullable}, db={d_nullable})"
                )

        # 2.3. Primary key
        model_pk = {c.name for c in table.primary_key.columns}
        db_pk = set(
            inspector.get_pk_constraint(table_name)["constrained_columns"]
        )
        if model_pk != db_pk:
            drifts.append(
                f"{table_name}: PK mismatch "
                f"(model={sorted(model_pk)}, db={sorted(db_pk)})"
            )

        # 2.4. Уникальность — по НАБОРУ КОЛОНОК, не по именам.
        #      PG автогенерит `<table>_<col>_key` для UNIQUE constraints,
        #      а в модели `unique=True` даёт безымянный UniqueConstraint.
        #      Сравнение по именам даст ложные срабатывания.
        model_unique: set[frozenset[str]] = {
            frozenset(c.name for c in cst.columns)
            for cst in table.constraints
            if isinstance(cst, UniqueConstraint)
        }
        # partial unique indexes — тоже "уникальность", но это Index, не UniqueConstraint
        model_unique |= {
            frozenset(c.name for c in idx.columns)
            for idx in table.indexes
            if idx.unique
        }

        db_unique: set[frozenset[str]] = {
            frozenset(cst["column_names"])
            for cst in inspector.get_unique_constraints(table_name)
        }
        db_unique |= {
            frozenset(idx["column_names"])
            for idx in inspector.get_indexes(table_name)
            if idx.get("unique")
        }

        if model_unique - db_unique:
            drifts.append(
                f"{table_name}: unique (by columns) in model but NOT in DB: "
                f"{sorted(tuple(sorted(s)) for s in model_unique - db_unique)}"
            )
        if db_unique - model_unique:
            drifts.append(
                f"{table_name}: unique (by columns) in DB but NOT in model: "
                f"{sorted(tuple(sorted(s)) for s in db_unique - model_unique)}"
            )

        # 2.5. Обычные (не-unique) индексы — по ИМЕНАМ.
        #      Имена семантичны (idx_*), автогенерённых среди них нет.
        model_plain = {
            idx.name for idx in table.indexes
            if idx.name and not idx.unique
        }
        db_plain = {
            idx["name"] for idx in inspector.get_indexes(table_name)
            if idx["name"] and not idx.get("unique")
        }

        if model_plain - db_plain:
            drifts.append(
                f"{table_name}: indexes in model but NOT in DB: "
                f"{sorted(model_plain - db_plain)}"
            )
        if db_plain - model_plain:
            drifts.append(
                f"{table_name}: indexes in DB but NOT in model: "
                f"{sorted(db_plain - model_plain)}"
            )

        # 2.6. CHECK constraints (только имена — выражения нормализовать сложно)
        model_checks = {
            c.name
            for c in table.constraints
            if isinstance(c, CheckConstraint) and c.name
        }
        db_checks = {
            c["name"] for c in inspector.get_check_constraints(table_name)
        }

        if model_checks - db_checks:
            drifts.append(
                f"{table_name}: check in model but NOT in DB: "
                f"{sorted(model_checks - db_checks)}"
            )
        if db_checks - model_checks:
            drifts.append(
                f"{table_name}: check in DB but NOT in model: "
                f"{sorted(db_checks - model_checks)}"
            )

    return drifts


# ============================================================
#  Тест
# ============================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_migrations_match_models(drift_db_url: str):
    """
    ✅ TST-003: схема после `alembic upgrade head` == `Base.metadata`.

    При расхождении — падаем с детальным diff. Починка — отдельная задача.
    """
    # 1. Миграции в отдельном потоке (Alembic синхронный)
    await asyncio.to_thread(_run_migrations, drift_db_url)

    # 2. Инспектор фактической схемы
    engine = create_async_engine(drift_db_url, echo=False, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            def _inspect(sync_conn) -> list[str]:
                return _collect_drift(Base.metadata, inspect(sync_conn))

            drifts = await conn.run_sync(_inspect)
    finally:
        await engine.dispose()

    # 3. Вердикт
    if drifts:
        msg = "\n".join(f"  - {d}" for d in drifts)
        pytest.fail(
            f"\n\nMigration drift detected ({len(drifts)} issue(s)):\n"
            f"{msg}\n\n"
            f"Fix: update the migration or the model, then re-run. "
            f"See backend/MIGRATIONS.md."
        )