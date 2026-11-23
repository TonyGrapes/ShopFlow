start_period: 60s для backend healthcheck в docker-compose.yml. Локально backend healthy за 41.7s (alembic 20–25s + lifespan до 17s). На медленном runner'е up --wait может ложно упасть.

Backend fail_under 78 → 80 (факт 80.31%), ratchet-коммит.

docker-compose.prod.yml — убедиться, что там тоже pgsty/minio (в коммите #3 мог не попасть).

backend/.env.test — пароль захардкожен. Идеально: POSTGRES_PASSWORD=${POSTGRES_TEST_PASSWORD:-shopflow_password_2026}, чтобы CI мог подставлять что угодно без sed в коммитнутый файл.

pg_hba.conf-ловушка — не проверять креды через psql -h 127.0.0.1 внутри контейнера (trust для loopback). Только -h localhost -p <mapped> с хоста или -h <service> из другого контейнера. Годится и для db, не только db-test.

vite@^7 → ^6 (убрать дубликат, снять as any)

actionlint в pre-push (или в CI как отдельный job)

Убрать env: POSTGRES_* из ci.yml после 2–3 зелёных прогонов. Сейчас это defense-in-depth; после подтверждения, что env_file стабилен в CI, override становится шумом.

backend/.env.test сейчас содержит много лишнего для db-test: REDIS_URL, MINIO_ENDPOINT, POSTGRES_HOST=localhost, POSTGRES_PORT=5433. Postgres entrypoint игнорирует всё, кроме POSTGRES_*, так что это безопасно, но в docker compose config засоряет вывод. Если будет желание — можно завести отдельный backend/.env.db-test с тремя строками и переключить env_file. Но это уже полировка; текущий вариант работает и понятен.