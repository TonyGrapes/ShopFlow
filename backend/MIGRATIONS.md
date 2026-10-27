# Миграции ShopFlow

> Документ про **безопасное переигрывание** миграций на существующей БД.
> Дополняет `alembic upgrade head` и `clean_chain_test.sh`.

## TL;DR

- `clean_chain_test.sh` делает `docker compose down -v` → **всегда на чистой БД**.
  Опасные миграции на нём не проявляются.
- На **непустой** БД две миграции могут упасть. Они **уже применены** — не трогать.
- Если нужно переиграть — сначала pre-check данных и backfill, потом `alembic upgrade`.

---

## Опасные миграции (не трогать)

### `1baf713bcd33_fix_productimage_table.py` — MIG-03

```python
op.add_column(
    'product_images',
    sa.Column('key', sa.Text(), nullable=False),
)
```

`key TEXT NOT NULL` **без** `server_default`. На **пустой** таблице `product_images`
— ок. На **непустой** — Postgres не может заполнить существующие строки →
`IntegrityError: column "key" contains null values`.

**Когда применена:** до появления данных в `product_images`. Сейчас — **не трогать**.

**Если нужно переиграть на непустой БД:**
новая миграция: `add_column` с `server_default=''` → backfill → `alter_column(nullable=False)` → `server_default=None`.
Применённую миграцию **не править** — Alembic хранит только `revision`, diff накапливается.

---

### `685f1b95cdef_drop_product_images_image_url.py` — MIG-04

```python
def downgrade() -> None:
    op.add_column(
        'product_images',
        sa.Column('image_url', sa.TEXT(), autoincrement=False, nullable=False),
    )
```

`downgrade()` добавляет `image_url NOT NULL` **без default**. На **непустой**
таблице — та же проблема, что в MIG-03.

**Когда применён downgrade:** никогда (это downgrade). Сейчас — **не трогать**.

**Если нужно переиграть:** тот же паттерн — `add_column` с default, backfill,
потом `alter_column`.

---

## Почему `clean_chain_test.sh` их не ловит

Скрипт делает:

```bash
docker compose down -v      # удаляет volumes → БД пустая
docker compose up -d --wait
alembic upgrade head        # на пустой БД обе миграции проходят
```

Это **сильная** проверка «цепочка миграций работает на чистой БД», но
**слабая** — «цепочка работает на данных». Для последнего нужен отдельный
тест дрейфа миграций (TST-003, см. backlog ниже).

---

## Как безопасно переиграть на существующей БД

**Не запускать `alembic downgrade` на проде** без бэкапа. Downgrade
`685f1b95cdef` упадёт на непустой таблице.

### Процедура

1. **Бэкап**:
   ```bash
   docker compose exec -T db pg_dump -U shopflow_user shopflow \
     > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Pre-check** — убедиться, что нет данных, которые сломают миграцию:
   ```sql
   SELECT count(*) FROM product_images;
   ```

3. **Если таблица непустая** — два варианта:
   - **Backfill**: новая миграция `add_column` с `server_default`,
     потом `alter_column(nullable=False)`, потом `server_default=None`.
   - **Truncate** (если данные не нужны и допустимо потерять).

4. **Только после этого** — `alembic upgrade`.

---

## Backlog (отложенные улучшения миграций)

| ID | Что | Почему отложено |
|----|-----|-----------------|
| MIG-06 | Индекс `products(cost)` под фильтры `min_cost`/`max_cost` | Нужен `EXPLAIN ANALYZE` на реальной нагрузке. На 20 товарах B-tree не нужен. |
| MIG-07 | Индекс `orders(created_at DESC)` под сортировку списков | То же: `EXPLAIN ANALYZE` сначала. `CREATE INDEX CONCURRENTLY` на большой таблице — вне транзакции Alembic. |
| MIG-08 | `compare_type`/`compare_server_default` в `alembic/env.py` | Даст много ложных срабатываний при `alembic check` (VARCHAR vs TEXT и т.п.). Отложить до стабилизации схемы. |
| TST-003 | Тест дрейфа миграций: `alembic upgrade head` на чистой схеме → сравнение `information_schema` с `Base.metadata` | Требует изоляции (отдельная схема / контейнер) и правки `env.py` (поддержка `search_path`). |

---

## Полезные команды

```bash
# Текущая ревизия
docker compose exec -T backend uv run --no-sync alembic current

# История ревизий (цепочка)
docker compose exec -T backend uv run --no-sync alembic history

# Дрейф модели vs БД
docker compose exec -T backend uv run --no-sync alembic check

# Чистая цепочка (down -v → up → upgrade → smoke)
bash clean_chain_test.sh
```

---

## Ссылки

- `alembic/versions/` — история ревизий.
- `clean_chain_test.sh` — 8 шагов, проверка цепочки на чистой БД.
- `alembic check` — дрейф модели vs БД.