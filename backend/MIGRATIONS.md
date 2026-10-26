# Миграции ShopFlow

> Документ про **безопасное переигрывание** миграций на существующей БД.
> Дополняет `alembic upgrade head` и `clean_chain_test.sh`.

## TL;DR

- `clean_chain_test.sh` делает `docker compose down -v` → **всегда на чистой БД**.
  Опасные миграции не проявляются.
- На **непустой** БД две миграции могут упасть. Они **уже применены** — не трогать.
- Если нужно переиграть — pre-check данных, backfill, потом `alembic upgrade`.

---

## Опасные миграции (не трогать)

### `1baf713bcd33_fix_productimage_table.py` — MIG-03

```python
op.add_column(
    'product_images',
    sa.Column('key', sa.Text(), nullable=False),
)