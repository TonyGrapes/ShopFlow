# ShopFlow

E-commerce API + SPA. FastAPI (async) + SQLAlchemy 2 + PostgreSQL + Redis + MinIO.
Frontend — React 19 + TypeScript + Vite. Production-ready: RBAC, идемпотентность,
кэш, наблюдаемость, миграции, drift-тесты, CI, unit + smoke-тесты.

## Quick start (dev)

    cp .env.example .env
    # Отредактируйте .env — заполните пароли и SECRET_KEY (openssl rand -hex 32)
    docker compose up -d --wait
    docker compose exec -T backend uv run --no-sync alembic upgrade head

Frontend: http://localhost:5173
API + Swagger: http://localhost:8000/docs

## Architecture

- **Backend:** `backend/`, FastAPI + SQLAlchemy 2.x (async) + Alembic.
- **Frontend:** `frontend/`, React 19 + Vite (SPA).
- **Инфраструктура:** `docker-compose.yml` (db, db-test, redis, minio, backend, frontend).

Ключевые архитектурные решения — в `backend/MIGRATIONS.md` и комментариях в коде.

## Tests

Backend (616 тестов, coverage 80.3%, fail_under=78):

    cd backend
    uv run pytest tests/ -q

Точечные прогоны — с `--no-cov` (иначе fail_under сработает на неполном прогоне).

Frontend (21 тест, vitest + @testing-library/react):

    cd frontend
    npm run test

E2E «чистая цепочка» (down -v → up → migrate → smoke → MinIO):

    bash clean_chain_test.sh

API smoke-сценарии (требуют запущенного стека):

    bash auth_smoke.sh
    bash catalog_smoke.sh
    bash order_smoke.sh
    bash promo_smoke.sh
    bash refund_smoke.sh
    bash review_smoke.sh

## Migrations

См. [backend/MIGRATIONS.md](backend/MIGRATIONS.md).

Короткое:

    docker compose exec -T backend uv run --no-sync alembic current
    docker compose exec -T backend uv run --no-sync alembic upgrade head

`alembic` с хоста не работает без env-override — читает `.env` с `POSTGRES_HOST=db`.

## Production

Multi-stage сборка frontend (node build → nginx serve) + nginx proxy `/api/` на backend.

    cp .env.example .env.prod
    # Для production: ENVIRONMENT=prod, SECRET_KEY=openssl rand -hex 32,
    # REFRESH_COOKIE_SECURE=true, CORS_ORIGINS=["https://your-domain.com"],
    # MINIO_PUBLIC_ENDPOINT=https://media.your-domain.com
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

Открывается на http://localhost/ (порт 80 nginx). Backend доступен только
внутри сети `backend_net`. MinIO — на 9000 (для локального теста) или за
CDN/reverse proxy (в реальном деплое — см. `MINIO_PUBLIC_ENDPOINT`).

## CI

`.github/workflows/ci.yml` — на каждый push/PR: `ruff` + `pytest` (backend) +
`npm run lint` + `npm run build` + `npm run test` (frontend).
`.github/workflows/clean_chain.yml` — nightly + manual: полная E2E-цепочка.

## Known limitations

- `SEC-X-01`: `.env.test` в git (тестовые креды; в истории — `2acafc1`, `6e535ef`).
  Требуется ротация секретов + `git filter-repo`.
- `QA-X-03`: coverage не видит async+SQLAlchemy код (`auth.py` 49%,
  `address_service.py` 38%) — tooling limitation, функциональность покрыта
  тестами.
- `CLN-017/018`: ломающие API-изменения (`payment_id` → `public_id`, пагинация
  в 4 списках) — требуют согласования фронта.