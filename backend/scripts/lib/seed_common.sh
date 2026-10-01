#!/usr/bin/env bash
# scripts/lib/seed_common.sh
# Общие функции для seed и cleanup скриптов.

# ============================================================
# Загрузка .env (до конфигурации)
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
    # Читаем .env, игнорируя комментарии и пустые строки
    set -o allexport
    # shellcheck disable=SC1090
    source <(grep -v '^#' "$ENV_FILE" | grep -v '^$')
    set +o allexport
fi

# ============================================================
# Цветной вывод — ВЕЗДЕ в stderr
# ============================================================
# ✅ -v VAR: не перезаписываем, если уже установлена
# Предотвращает warning при повторном source.
[[ -v RED    ]] || readonly RED='\033[0;31m'
[[ -v GREEN  ]] || readonly GREEN='\033[0;32m'
[[ -v YELLOW ]] || readonly YELLOW='\033[0;33m'
[[ -v BLUE   ]] || readonly BLUE='\033[0;34m'
[[ -v NC     ]] || readonly NC='\033[0m'

log_info()  { echo -e "${BLUE}ℹ️  $*${NC}" >&2; }
log_ok()    { echo -e "${GREEN}✅ $*${NC}" >&2; }
log_warn()  { echo -e "${YELLOW}⚠️  $*${NC}" >&2; }
log_error() { echo -e "${RED}❌ $*${NC}" >&2; }

fail() {
    log_error "$1"
    exit 1
}

# ============================================================
# Конфигурация (с fallback через :-)
# ============================================================
: "${API_URL:=http://localhost:8000}"
: "${AUTH_HEADER:=Authorization: Bearer test-token}"
: "${DB_CONTAINER:=shopflow-db}"
: "${DB_USER:=shopflow_user}"
: "${DB_NAME:=shopflow}"
: "${MINIO_CONTAINER:=shopflow-minio}"
: "${MINIO_BUCKET:=shopflow-media}"
: "${REDIS_CONTAINER:=shopflow-redis}"
: "${BACKEND_CONTAINER:=shopflow-backend}"
: "${REDIS_PASSWORD:=redisadmin123}"

[[ -v SEED_CATEGORY_PATH ]] || readonly SEED_CATEGORY_PATH="test"
[[ -v SEED_CATEGORY_NAME ]] || readonly SEED_CATEGORY_NAME="Тестовая категория"

# ============================================================
# Проверка окружения
# ============================================================
check_env() {
    log_info "Проверка окружения..."

    if ! docker info >/dev/null 2>&1; then
        fail "Docker daemon не запущен"
    fi

    for c in "$DB_CONTAINER" "$BACKEND_CONTAINER" "$MINIO_CONTAINER" "$REDIS_CONTAINER"; do
        if ! docker ps --format '{{.Names}}' | grep -q "^$c$"; then
            fail "Контейнер $c не запущен. Запустите: docker-compose up -d"
        fi
    done

    if ! curl -fsS "$API_URL/health" >/dev/null 2>&1; then
        fail "Backend не отвечает на $API_URL/health"
    fi

    if ! command -v jq >/dev/null 2>&1; then
        fail "jq не установлен. Установите: sudo apt install jq"
    fi

    log_ok "Окружение готово"
}

# ============================================================
# Работа с категорией
# ============================================================

get_category_id() {
    # ✅ -tAc: только значение, без заголовков
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT id FROM categories WHERE path = '$SEED_CATEGORY_PATH' LIMIT 1"
}

ensure_category() {
    local cat_id
    cat_id=$(get_category_id)

    if [ -n "$cat_id" ]; then
        log_info "Использую существующую категорию id=$cat_id"
        echo "$cat_id"
        return 0
    fi

    log_info "Категория '$SEED_CATEGORY_PATH' не найдена, создаю..."

    # ✅ INSERT без RETURNING, stdout в /dev/null
    # Это подавляет command tag "INSERT 0 1"
    if ! docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -q -c \
        "INSERT INTO categories (path, category_name, created_at, updated_at)
         VALUES ('$SEED_CATEGORY_PATH', '$SEED_CATEGORY_NAME', now(), now())" \
        >/dev/null 2>&1; then
        fail "Не удалось создать категорию '$SEED_CATEGORY_PATH'"
    fi

    # ✅ Отдельный SELECT — только ID
    cat_id=$(get_category_id)

    if [ -z "$cat_id" ]; then
        fail "Категория создана, но SELECT не вернул ID"
    fi

    log_ok "Создана категория id=$cat_id"
    echo "$cat_id"
}

# ============================================================
# Работа с товарами
# ============================================================
count_active_products() {
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT COUNT(*) FROM products WHERE deleted_at IS NULL"
}

product_exists() {
    local name="$1"
    local count
    count=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT COUNT(*) FROM products WHERE name = '$name' AND deleted_at IS NULL")
    [ "$count" -gt 0 ]
}

# ============================================================
# Работа с Redis
# ============================================================
flush_cache() {
    log_info "Сброс кэша Redis..."

    local keys
    keys=$(docker exec "$REDIS_CONTAINER" redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
        --scan --pattern "products:list:*" 2>/dev/null | wc -l)

    if [ "$keys" -gt 0 ]; then
        docker exec "$REDIS_CONTAINER" redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
            --scan --pattern "products:list:*" 2>/dev/null | \
            while read -r key; do
                [ -n "$key" ] && docker exec "$REDIS_CONTAINER" redis-cli \
                    -a "$REDIS_PASSWORD" --no-auth-warning DEL "$key" >/dev/null
            done
        log_ok "Удалено ключей: $keys"
    else
        log_info "Ключей не было"
    fi
}

# ============================================================
# Работа с MinIO
# ============================================================
ensure_mc_alias() {
    docker exec "$MINIO_CONTAINER" sh -c "
        mc alias set local http://localhost:9000 \
            \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null 2>&1
    " || fail "Не удалось настроить mc alias"
}

count_minio_files() {
    ensure_mc_alias
    docker exec "$MINIO_CONTAINER" sh -c "
        mc ls --recursive local/$MINIO_BUCKET/products/ 2>/dev/null | wc -l
    " || echo 0
}

# ============================================================
# Утилиты
# ============================================================
require_jq() {
    command -v jq >/dev/null 2>&1 || fail "jq не установлен"
}
