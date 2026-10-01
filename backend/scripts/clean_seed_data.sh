#!/usr/bin/env bash
# scripts/clean_seed_data.sh
# Полная очистка seed-данных каталога.
#
# Порядок:
# 1. Redis — сбросить кэш.
# 2. PostgreSQL — удалить product_images и products.
# 3. MinIO — удалить файлы товаров.
#
# Опционально: --keep-files — оставить файлы в MinIO (orphan).
#              --soft       — soft delete товаров.

set -euo pipefail

MODE="${1:-hard}"

echo "═══════════════════════════════════════════════════"
echo "Очистка seed-данных каталога (mode=$MODE)"
echo "═══════════════════════════════════════════════════"

# ============================================================
# 1. Redis — инвалидация кэша
# ============================================================
echo
echo "── 1. Redis: сброс кэша каталога ──"

KEYS_BEFORE=$(docker exec shopflow-redis redis-cli -a redisadmin123 --no-auth-warning \
    --scan --pattern "products:list:*" 2>/dev/null | wc -l)
echo "   Ключей до: $KEYS_BEFORE"

# Удалить все ключи products:list:*
docker exec shopflow-redis redis-cli -a redisadmin123 --no-auth-warning \
    --scan --pattern "products:list:*" 2>/dev/null | \
    while read -r key; do
        [ -n "$key" ] && docker exec shopflow-redis redis-cli -a redisadmin123 --no-auth-warning DEL "$key" > /dev/null
    done

KEYS_AFTER=$(docker exec shopflow-redis redis-cli -a redisadmin123 --no-auth-warning \
    --scan --pattern "products:list:*" 2>/dev/null | wc -l)
echo "   Ключей после: $KEYS_AFTER"

# ============================================================
# 2. PostgreSQL — удаление записей
# ============================================================
echo
echo "── 2. PostgreSQL: удаление записей ──"

PRODUCTS_BEFORE=$(docker exec shopflow-db psql -U shopflow_user -d shopflow -t -c \
    "SELECT COUNT(*) FROM products;" | tr -d ' ')
IMAGES_BEFORE=$(docker exec shopflow-db psql -U shopflow_user -d shopflow -t -c \
    "SELECT COUNT(*) FROM product_images;" | tr -d ' ')
echo "   Товаров до:    $PRODUCTS_BEFORE"
echo "   Изображений до: $IMAGES_BEFORE"

if [ "$MODE" = "soft" ]; then
    echo "   Режим: soft delete"
    docker exec shopflow-db psql -U shopflow_user -d shopflow -c \
        "UPDATE products SET deleted_at = now() WHERE deleted_at IS NULL;"
else
    echo "   Режим: hard delete"
    # Порядок важен: сначала images (FK), потом products
    docker exec shopflow-db psql -U shopflow_user -d shopflow -c \
        "DELETE FROM product_images;"
    docker exec shopflow-db psql -U shopflow_user -d shopflow -c \
        "DELETE FROM products;"
fi

PRODUCTS_AFTER=$(docker exec shopflow-db psql -U shopflow_user -d shopflow -t -c \
    "SELECT COUNT(*) FROM products WHERE deleted_at IS NULL;" | tr -d ' ')
IMAGES_AFTER=$(docker exec shopflow-db psql -U shopflow_user -d shopflow -t -c \
    "SELECT COUNT(*) FROM product_images;" | tr -d ' ')
echo "   Товаров после:    $PRODUCTS_AFTER"
echo "   Изображений после: $IMAGES_AFTER"

# ============================================================
# 3. MinIO — удаление файлов
# ============================================================
echo
echo "── 3. MinIO: удаление файлов ──"

FILES_BEFORE=$(docker exec shopflow-minio mc ls --recursive local/shopflow-media/products/ 2>/dev/null | wc -l)
echo "   Файлов до: $FILES_BEFORE"

if [ "$MODE" = "soft" ]; then
    echo "   ⚠️  Soft delete: файлы остаются"
elif [ "$MODE" = "keep-files" ]; then
    echo "   ⚠️  --keep-files: файлы остаются (orphan)"
else
    docker exec shopflow-minio mc rm --recursive --force local/shopflow-media/products/ 2>/dev/null || true
    FILES_AFTER=$(docker exec shopflow-minio mc ls --recursive local/shopflow-media/products/ 2>/dev/null | wc -l)
    echo "   Файлов после: $FILES_AFTER"
fi

# ============================================================
# Итог
# ============================================================
echo
echo "═══════════════════════════════════════════════════"
echo "✅ Очистка завершена (mode=$MODE)"
echo "═══════════════════════════════════════════════════"
