#!/usr/bin/env bash
# backend/clean_chain_test.sh
#
# Проверка «чистой цепочки» проекта ShopFlow.
#
# Что делает:
# 1. Полный сброс (down -v) — удаляет ВСЕ данные.
# 2. Поднимает стек с нуля (up -d --wait).
# 3. Применяет миграции Alembic.
# 4. Проверяет, что все таблицы созданы.
# 5. Проверяет, что БД на head.
# 6. Прогоняет smoke-тест моделей.
# 7. Проверяет публичную policy MinIO.
#
# Запуск: bash clean_chain_test.sh
#
# Требует: docker-compose, jq, psql в контейнере, mc в контейнере MinIO.

set -euo pipefail

# ============================================================
# Конфигурация
# ============================================================
DB_USER="${POSTGRES_USER:-shopflow_user}"
DB_NAME="${POSTGRES_DB:-shopflow}"
MINIO_CONTAINER="shopflow-minio"
MINIO_BUCKET="${MINIO_BUCKET:-shopflow-media}"
MINIO_USER="${MINIO_ROOT_USER:-shopflow_admin}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-SuperSecretP@ssw0rd!2026}"

# Минимальное количество таблиц (14 из миграций + alembic_version)
MIN_TABLES=16

# ============================================================
# Утилиты
# ============================================================
step() {
    echo
    echo "═══════════════════════════════════════════════════"
    echo "  $1"
    echo "═══════════════════════════════════════════════════"
}

fail() {
    echo "❌ FAIL: $1"
    exit 1
}

ok() {
    echo "✅ $1"
}

# ============================================================
# Шаг 1: Полный сброс
# ============================================================
step "1/8 docker compose down -v (полный сброс volumes)"
docker compose down -v

ok "Контейнеры, volumes и сети удалены"

# ============================================================
# Шаг 2: Подъём стека
# ============================================================
step "2/8 docker compose up -d --wait (ждём healthy)"
docker compose up -d --wait

ok "Все контейнеры healthy"

# ============================================================
# Шаг 3: Применение миграций
# ============================================================
step "3/8 alembic upgrade head"
docker compose exec -T backend uv run --no-sync alembic upgrade head

ok "Миграции применены"

# ============================================================
# Шаг 4: Проверка таблиц
# ============================================================
step "4/8 psql \dt (все таблицы на месте?)"
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -c "\dt"

TABLE_COUNT=$(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")

echo
echo "   Таблиц в public: $TABLE_COUNT"

if [ "$TABLE_COUNT" -lt "$MIN_TABLES" ]; then
    fail "Ожидалось >= $MIN_TABLES таблиц, получено $TABLE_COUNT"
fi

ok "Таблиц: $TABLE_COUNT (>= $MIN_TABLES)"

# ============================================================
# Шаг 5: Проверка ревизии Alembic
# ============================================================
step "5/8 alembic current (БД на head?)"
docker compose exec -T backend uv run --no-sync alembic current

# Проверка, что ревизия содержит "(head)"
CURRENT=$(docker compose exec -T backend uv run --no-sync alembic current 2>&1 | tail -1)
if ! echo "$CURRENT" | grep -q "(head)"; then
    fail "БД не на head: $CURRENT"
fi

ok "БД на head: $CURRENT"

# ============================================================
# Шаг 6: Smoke-тест моделей
# ============================================================
step "6/8 smoke models (write + read back)"
docker compose exec -T backend uv run --no-sync python -m app.smoke_models

ok "Smoke-тест моделей пройден"

# ============================================================
# Шаг 7: Проверка MinIO policy
# ============================================================
step "7/8 MinIO policy check"

# 7.1. Убеждаемся, что bucket создан и policy применена
# Прогоняем ensure_bucket через приложение
docker compose exec -T backend uv run --no-sync python -c "
from app.services.storage_service import get_storage
storage = get_storage()
storage.ensure_bucket()
print('   ensure_bucket OK')
"

# 7.2. Настраиваем mc alias внутри контейнера MinIO
docker exec "$MINIO_CONTAINER" sh -c "
    mc alias set local http://localhost:9000 '$MINIO_USER' '$MINIO_PASS' >/dev/null 2>&1
" || fail "Не удалось настроить mc alias"

# 7.3. Получаем policy в JSON
POLICY_JSON=$(docker exec "$MINIO_CONTAINER" sh -c "
    mc anonymous get-json local/$MINIO_BUCKET 2>/dev/null
" || echo "{}")

echo "   Policy: $POLICY_JSON" | head -c 200
echo

# 7.4. Проверяем наличие s3:GetObject
if ! echo "$POLICY_JSON" | grep -q '"s3:GetObject"'; then
    fail "Bucket policy: s3:GetObject НЕ найден"
fi
ok "Bucket policy содержит s3:GetObject"

# 7.5. Проверяем отсутствие s3:ListBucket
if echo "$POLICY_JSON" | grep -q '"s3:ListBucket"'; then
    fail "Bucket policy содержит s3:ListBucket (не должно быть)"
fi
ok "Bucket policy НЕ содержит s3:ListBucket"

# ============================================================
# Шаг 8: Проверка обязательных таблиц
# ============================================================
step "8/8 Main tables check"

REQUIRED_TABLES=(users categories products cart_items orders order_items
                 product_images payments refunds reviews promo_codes
                 addresses email_verifications refresh_tokens
                 favorites
                 alembic_version)

for t in "${REQUIRED_TABLES[@]}"; do
    COUNT=$(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='$t'")
    if [ "$COUNT" != "1" ]; then
        fail "Таблица $t отсутствует"
    fi
done
ok "Все обязательные таблицы на месте"

# ============================================================
# Итог
# ============================================================
echo
echo "═══════════════════════════════════════════════════"
echo "  ✅ CLEAN CHAIN TEST PASSED"
echo "═══════════════════════════════════════════════════"