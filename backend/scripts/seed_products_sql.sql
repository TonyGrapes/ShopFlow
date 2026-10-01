-- scripts/seed_products_sql.sql
-- Быстрое наполнение каталога через SQL.
-- ВНИМАНИЕ: картинки НЕ создаются — cover_url будет null.

DO $$
DECLARE
    cat_id BIGINT;
    statuses product_status[] := ARRAY['available', 'out_of_stock', 'discontinued']::product_status[];
    names text[] := ARRAY[
        'Ноутбук', 'Смартфон', 'Планшет', 'Наушники', 'Монитор',
        'Клавиатура', 'Мышь', 'Веб-камера', 'Колонки', 'Микрофон',
        'Принтер', 'Сканер', 'Роутер', 'Коммутатор', 'Кабель HDMI'
    ];
    brands text[] := ARRAY[
        'Apple', 'Samsung', 'Xiaomi', 'Sony', 'LG',
        'Logitech', 'HP', 'Dell', 'Asus', 'Lenovo',
        'MSI', 'Acer', 'Huawei', 'Google', 'Microsoft'
    ];
    i int;
    product_name text;
    product_cost numeric;
    product_status product_status;
BEGIN
    -- Найти или создать категорию
    SELECT id INTO cat_id FROM categories WHERE path = 'test' LIMIT 1;

    IF cat_id IS NULL THEN
        INSERT INTO categories (path, category_name, created_at, updated_at)
        VALUES ('test', 'Тестовая категория', now(), now())
        RETURNING id INTO cat_id;
    END IF;

    -- Создать 45 товаров
    FOR i IN 1..45 LOOP
        product_name := brands[1 + (i % array_length(brands, 1))]
                     || ' ' || names[1 + (i % array_length(names, 1))]
                     || ' #' || i;

        product_cost := (10000 + i * 5000)::numeric(10,2);
        product_status := statuses[1 + (i % array_length(statuses, 1))];

        INSERT INTO products (
            category_id, name, description, cost, status,
            created_at, updated_at
        )
        VALUES (
            cat_id,
            product_name,
            'Тестовое описание для ' || product_name || '. Характеристики, особенности, преимущества.',
            product_cost,
            product_status,
            now() - (i || ' minutes')::interval,
            now() - (i || ' minutes')::interval
        );
    END LOOP;

    RAISE NOTICE 'Создано 45 товаров в категории %', cat_id;
END $$;
