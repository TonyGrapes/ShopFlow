#!/usr/bin/env bash
# scripts/cleanup_seed.sh
#
# Удаляет seed-данные каталога.
#
# Режимы:
#   --mode=hard        — удалить товары, файлы, кэш (по умолчанию)
#   --mode=soft        — только soft delete товаров (файлы остаются)
#   --mode=keep-files  — удалить товары, но оставить файлы в MinIO
#
# Флаги:
#   --keep-category    — не удалять категорию 'test' (по умолчанию true)
#   --remove-category  — удалить категорию 'test'
#
# Переменные окружения:
#   CLEANUP_DELETE_CATEGORY=true — удалить категорию
#
# Примеры:
#   bash scripts/cleanup_seed.sh                    # hard + keep category
#   bash scripts/cleanup_seed.sh --mode=soft        # soft delete
#   bash scripts/cleanup_seed.sh --remove-category  # удалить и категорию

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/seed_common.sh
source "$SCRIPT_DIR/lib/seed_common.sh"

# ============================================================
# Параметры
# ============================================================
MODE="hard"
DELETE_CATEGORY="${CLEANUP_DELETE_CATEGORY:-false}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode=*)         MODE="${1#*=}"; shift ;;
        --mode)           MODE="$2"; shift 2 ;;
        --keep-category)  DELETE_CATEGORY=false; shift ;;
        --remove-category) DELETE_CATEGORY=true; shift ;;
        *)                fail "Неизвестный аргумент: $1" ;;
    esac
done

# ============================================================
# Функция: очистка MinIO
# ============================================================
cleanup_minio() {
    log_info "Очистка MinIO..."

    ensure_mc_alias

    local before
    before=$(count_minio_files)
    log_info "Файлов до: $before"

    if [ "$before" -gt 0 ]; then
        docker exec "$MINIO_CONTAINER" sh -c "
            mc rm --recursive --force local/$MINIO_BUCKET/products/ 2>/dev/null || true
        "
    fi

    local after
    after=$(count_minio_files)
    log_ok "Файлов после: $after"
}

# ============================================================
# Функция: очистка БД
# ============================================================
cleanup_database_hard() {
    log_info "Hard delete товаров..."

    local products_before
    local images_before
    products_before=$(count_active_products)
    images_before=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT COUNT(*) FROM product_images")

    log_info "Товаров до: $products_before, изображений до: $images_before"

    # Удаляем в правильном порядке (FK)
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "DELETE FROM product_images;" >/dev/null

    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "DELETE FROM products;" >/dev/null

    local products_after
    local images_after
    products_after=$(count_active_products)
    images_after=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT COUNT(*) FROM product_images")

    log_ok "Товаров после: $products_after, изображений после: $images_after"
}

cleanup_database_soft() {
    log_info "Soft delete товаров..."

    local before
    before=$(count_active_products)
    log_info "Активных до: $before"

    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "UPDATE products SET deleted_at = now() WHERE deleted_at IS NULL;" >/dev/null

    local after
    after=$(count_active_products)
    log_ok "Активных после: $after"
}

# ============================================================
# Функция: удаление категории
# ============================================================
cleanup_category() {
    if [ "$DELETE_CATEGORY" != "true" ]; then
        log_info "Категория '$SEED_CATEGORY_PATH' сохранена"
        return 0
    fi

    log_info "Удаление категории '$SEED_CATEGORY_PATH'..."

    # Проверка, что нет товаров
    local products_count
    products_count=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT COUNT(*) FROM products WHERE category_id IN
            (SELECT id FROM categories WHERE path = '$SEED_CATEGORY_PATH')")

    if [ "$products_count" -gt 0 ]; then
        log_warn "Нельзя удалить категорию: есть $products_count товаров"
        return 0
    fi

    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "DELETE FROM categories WHERE path = '$SEED_CATEGORY_PATH';" >/dev/null

    log_ok "Категория удалена"
}

# ============================================================
# MAIN
# ============================================================
main() {
    echo
    echo "═══════════════════════════════════════════════════"
    echo "  CLEANUP SEED (mode=$MODE)"
    echo "═══════════════════════════════════════════════════"
    echo

    # Для cleanup проверки окружения мягче: backend может не работать
    if ! docker ps --format '{{.Names}}' | grep -q "^$DB_CONTAINER$"; then
        fail "Контейнер $DB_CONTAINER не запущен"
    fi

    case "$MODE" in
        hard)
            flush_cache
            cleanup_database_hard
            cleanup_minio
            ;;
        soft)
            flush_cache
            cleanup_database_soft
            ;;
        keep-files)
            flush_cache
            cleanup_database_hard
            log_warn "Файлы в MinIO сохранены (orphan)"
            ;;
        *)
            fail "Неизвестный режим: $MODE (hard | soft | keep-files)"
            ;;
    esac

    cleanup_category

    # Итоги
    local products
    local files
    products=$(count_active_products)
    files=$(count_minio_files)

    echo
    echo "═══════════════════════════════════════════════════"
    log_ok "CLEANUP COMPLETED (mode=$MODE)"
    echo "   Активных товаров:     $products"
    echo "   Файлов в MinIO:       $files"
    echo "═══════════════════════════════════════════════════"
    echo
}

main "$@"
