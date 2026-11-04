# ShopFlow Backend

FastAPI + PostgreSQL + Redis + MinIO.

## Run

    docker compose up -d
    docker compose exec -T backend uv run --no-sync alembic upgrade head

## Test

    cd backend
    uv run pytest tests/ -v

Полный прогон включает coverage (`addopts` в `pyproject.toml`) и занимает
~2:40. Для быстрой итерации — точечный прогон с `--no-cov` (см. ниже).

### Точечные прогоны

`addopts` включает `--cov=app --cov-report=term-missing` по умолчанию.
Для прогона одного файла это даст низкий coverage и `fail_under`
сработает как ложное падение. Используйте `--no-cov`:

    uv run pytest tests/test_smoke.py -v --no-cov

### Coverage

- Baseline: **~81%** (statement coverage, `app/` без `smoke_models.py`).
- `fail_under = 78` в `[tool.coverage.report]` — защита от регресса.
- HTML-отчёт (локально, не коммитится):

      uv run pytest tests/ --cov=app --cov-report=html
      # → htmlcov/index.html

### Известные аномалии покрытия

Две задачи в бэклоге (не блокируют TST-004, но требуют внимания):

- `app/api/v1/endpoints/auth.py` — 44% при 27 тестах. Гипотеза:
  `get_redis()` в `login` вызывается напрямую (мимо Depends override)
  → ветки login/refresh/logout/me не покрываются savepoint-тестами.
  (TST-007)
- `app/services/address_service.py` — 38% при 17 тестах. Гипотеза:
  `test_addresses.py` через `client` использует savepoint, а сервис
  вызывается с другой сессией. (TST-008)

## Migrations

See [MIGRATIONS.md](MIGRATIONS.md).