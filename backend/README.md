# ShopFlow Backend

FastAPI + PostgreSQL + Redis + MinIO.

## Run

    docker compose up -d
    docker compose exec -T backend uv run --no-sync alembic upgrade head

## Test

    docker compose exec -T backend uv run pytest tests/ -v

## Migrations

See [MIGRATIONS.md](MIGRATIONS.md).