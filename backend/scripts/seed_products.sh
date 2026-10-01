#!/usr/bin/env bash
# scripts/seed_products.sh
#
# Наполняет каталог ShopFlow тестовыми товарами.
#
# Режимы:
#   --mode=api    — только API (товары с картинками)
#   --mode=bulk   — только SQL (товары без картинок, много)
#   --mode=hybrid — API + bulk (по умолчанию)
#
# Переменные окружения:
#   SEED_API_COUNT   — сколько товаров через API (по умолчанию 10)
#   SEED_BULK_COUNT  — сколько товаров через SQL (по умолчанию 40)
#
# Идемпотентен: существующие товары (по имени) не пересоздаются.
#
# Примеры:
#   bash scripts/seed_products.sh                    # 10 API + 40 SQL
#   SEED_API_COUNT=5 bash scripts/seed_products.sh   # 5 API + 40 SQL
#   bash scripts/seed_products.sh --mode=api         # только API
#   bash scripts/seed_products.sh --mode=bulk        # только SQL

set -euo pipefail

# ============================================================
# Импорт общих функций
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/seed_common.sh
source "$SCRIPT_DIR/lib/seed_common.sh"

# ============================================================
# Параметры
# ============================================================
MODE="hybrid"
: "${SEED_API_COUNT:=10}"
: "${SEED_BULK_COUNT:=40}"
: "${SEED_IMAGES_DIR:=test_data/products}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode=*) MODE="${1#*=}"; shift ;;
        --mode)   MODE="$2"; shift 2 ;;
        *)        fail "Неизвестный аргумент: $1" ;;
    esac
done

# ============================================================
# Данные для API-режима (10 предопределённых товаров)
# ============================================================
# name|description|cost|status|image_filename
readonly PRODUCTS_DATA=(
    "MacBook Pro 16|Мощный ноутбук для профессионалов|249990.00|available|laptop.png"
    "iPhone 15 Pro|Флагманский смартфон Apple|129990.00|available|phone.png"
    "iPad Air|Лёгкий планшет для работы и творчества|64990.00|available|tablet.png"
    "Sony WH-1000XM5|Наушники с активным шумоподавлением|39990.00|available|headphones.png"
    "LG UltraWide 34|Изогнутый монитор 34 дюйма|89990.00|available|monitor.png"
    "Samsung Galaxy S24|Смартфон на Android|109990.00|out_of_stock|phone.png"
    "Xiaomi Pad 6|Бюджетный планшет|29990.00|available|tablet.png"
    "Logitech MX Master 3|Эргономичная мышь|9990.00|available|laptop.png"
    "Kindle Paperwhite|Электронная книга|14990.00|available|tablet.png"
    "AirPods Pro 2|Беспроводные наушники|20990.00|discontinued|headphones.png"
)

# ============================================================
# Функция: создать товар через API
# ============================================================
create_product_api() {
    local name="$1"
    local description="$2"
    local cost="$3"
    local status="$4"
    local image_file="$5"
    local category_id="$6"

    # Проверка на существование
    if product_exists "$name"; then
        log_warn "Товар '$name' уже существует — пропускаю"
        return 0
    fi

    # Создание товара
    local payload
    payload=$(jq -n \
        --arg name "$name" \
        --arg desc "$description" \
        --arg cost "$cost" \
        --arg status "$status" \
        --argjson cat_id "$category_id" \
        '{name: $name, description: $desc, cost: $cost, status: $status, category_id: $cat_id}')

    local response http_code body
    response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/v1/products" \
        -H "$AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d "$payload")

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" != "201" ]; then
        log_error "POST /products '$name' → HTTP $http_code"
        echo "$body" | jq . 2>/dev/null || echo "$body"
        return 1
    fi

    local product_id
    product_id=$(echo "$body" | jq -r '.id')
    log_ok "Товар '$name' создан (id=$product_id)"

    # Загрузка картинки
    local image_path="$SEED_IMAGES_DIR/$image_file"
    if [ ! -f "$image_path" ]; then
        log_warn "   Картинка не найдена: $image_path"
        return 0
    fi

    response=$(curl -s -w "\n%{http_code}" -X POST \
        "$API_URL/api/v1/products/$product_id/images" \
        -H "$AUTH_HEADER" \
        -F "file=@$image_path")

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" != "200" ]; then
        log_warn "   Загрузка картинки → HTTP $http_code"
        return 0
    fi

    local image_url
    image_url=$(echo "$body" | jq -r '.images[0].url // empty')

    if [ -n "$image_url" ] && [ "$image_url" != "null" ]; then
        log_ok "   Картинка: $image_url"
    fi
}

# ============================================================
# Функция: запустить API seed
# ============================================================
seed_via_api() {
    local category_id="$1"
    local count=0
    local success=0

    log_info "Режим API: создаю до $SEED_API_COUNT товаров с картинками"

    for spec in "${PRODUCTS_DATA[@]}"; do
        if [ "$count" -ge "$SEED_API_COUNT" ]; then
            break
        fi

        IFS='|' read -r name description cost status image <<< "$spec"

        if create_product_api "$name" "$description" "$cost" "$status" "$image" "$category_id"; then
            success=$((success + 1))
        fi

        count=$((count + 1))
        sleep 0.3   # не перегружаем backend
    done

    log_ok "API: обработано $count, успешно $success"
}

# ============================================================
# Функция: запустить bulk seed (SQL)
# ============================================================
seed_via_sql() {
    local category_id="$1"

    log_info "Режим SQL: создаю $SEED_BULK_COUNT товаров без картинок"

    docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
DECLARE
    cat_id BIGINT := $category_id;
    statuses product_status[] := ARRAY['available', 'out_of_stock', 'discontinued']::product_status[];
    names text[] := ARRAY[
        'Ноутбук', 'Смартфон', 'Планшет', 'Наушники', 'Монитор',
        'Клавиатура', 'Мышь', 'Веб-камера', 'Колонки', 'Микрофон'
    ];
    brands text[] := ARRAY[
        'Apple', 'Samsung', 'Xiaomi', 'Sony', 'LG',
        'Logitech', 'HP', 'Dell', 'Asus', 'Lenovo'
    ];
    i int;
    product_name text;
    product_cost numeric;
    product_status product_status;
    created int := 0;
BEGIN
    FOR i IN 1..$SEED_BULK_COUNT LOOP
        product_name := brands[1 + (i % array_length(brands, 1))]
                     || ' ' || names[1 + (i % array_length(names, 1))]
                     || ' #' || (100 + i);

        -- Идемпотентность: не создавать, если уже есть
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM products
            WHERE name = product_name AND deleted_at IS NULL
        );

        product_cost := (10000 + i * 5000)::numeric(10,2);
        product_status := statuses[1 + (i % array_length(statuses, 1))];

        INSERT INTO products (
            category_id, name, description, cost, status,
            created_at, updated_at
        ) VALUES (
            cat_id,
            product_name,
            'Тестовое описание для ' || product_name || '. Характеристики, особенности.',
            product_cost,
            product_status,
            now() - (i || ' minutes')::interval,
            now() - (i || ' minutes')::interval
        );
        created := created + 1;
    END LOOP;

    RAISE NOTICE 'Создано товаров: %', created;
END \$\$;
SQL

    log_ok "SQL: создано товаров"
}

# ============================================================
# MAIN
# ============================================================
main() {
    echo
    echo "═══════════════════════════════════════════════════"
    echo "  SEED PRODUCTS (mode=$MODE)"
    echo "═══════════════════════════════════════════════════"
    echo

    check_env

    local category_id
    category_id=$(ensure_category)
    log_info "CATEGORY_ID = $category_id"

    case "$MODE" in
        api)
            seed_via_api "$category_id"
            ;;
        bulk)
            seed_via_sql "$category_id"
            ;;
        hybrid)
            seed_via_api "$category_id"
            seed_via_sql "$category_id"
            ;;
        *)
            fail "Неизвестный режим: $MODE (api | bulk | hybrid)"
            ;;
    esac

    # Сброс кэша — чтобы свежие данные отдавались сразу
    flush_cache

    # Итоги
    local total
    total=$(count_active_products)
    local files
    files=$(count_minio_files)

    echo
    echo "═══════════════════════════════════════════════════"
    log_ok "SEED COMPLETED"
    echo "   Товаров в БД:         $total"
    echo "   Файлов в MinIO:       $files"
    echo "   Категория:            id=$category_id"
    echo "═══════════════════════════════════════════════════"
    echo
    echo "🔗 Открыть каталог: http://localhost:5173/"
    echo
}

main "$@"
