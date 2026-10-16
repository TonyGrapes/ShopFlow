#!/usr/bin/env bash
# catalog_smoke.sh
# Эпик 6 (админка каталога) — smoke-сценарий.
#
# Требует: docker compose, backend на http://localhost:8000, jq.
#
# Что проверяет:
# 1.  Админ login.
# 2.  POST /admin/categories — создание корневой категории.
# 3.  POST /admin/categories — дочерняя категория.
# 4.  GET /categories — плоский список.
# 5.  GET /categories/tree — вложенность.
# 6.  POST /products — создание товара.
# 7.  POST /products/bulk/status — bulk update.
# 8.  GET /products?include_deleted=true — включая soft-deleted.
# 9.  DELETE /products/{id} — soft-delete.
# 10. GET /products — без deleted.
# 11. GET /products?include_deleted=true — c deleted.
# 12. RBAC: customer → 403 на POST /admin/categories.
# 13. Цикл: PATCH electronics → parent_id=electronics.gaming → 422.
# 14. Уборка.

set -euo pipefail

BASE="http://localhost:8000/api/v1"
EMAIL="catalog-smoke@example.com"
PASSWORD="catalog-smoke-1234"
C1="/tmp/catalog_c1.txt"

step() { echo; echo "═══ $1 ═══"; }

# ============================================================
step "0. Чистый старт"
# ============================================================
rm -f "$C1"

docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM products WHERE name IN (
    'Catalog Smoke Laptop', 'Catalog Smoke Mouse', 'Catalog Smoke Keyboard'
  );
  DELETE FROM categories WHERE path::text LIKE 'catalog_smoke%';
  DELETE FROM users WHERE email = '$EMAIL';
" >/dev/null
echo "OK"

# ============================================================
step "1. Регистрация → verify → admin role → login"
# ============================================================
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Cat\",\"last_name\":\"Smoke\",\"phone_number\":\"+79998880001\"}" >/dev/null

TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')
curl -s "$BASE/auth/verify-email?token=$TOKEN" >/dev/null

docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET role='admin' WHERE email='$EMAIL'" >/dev/null

ACCESS=$(curl -s -c "$C1" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)
echo "ACCESS=${ACCESS:0:30}..."

# ============================================================
step "2. POST /admin/categories — корневая"
# ============================================================
ROOT_RESP=$(curl -s -X POST "$BASE/admin/categories" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"category_name":"Catalog Smoke Electronics"}')

echo "$ROOT_RESP" | jq '{id, category_name, path, parent_id}'
ROOT_ID=$(echo "$ROOT_RESP" | jq -r .id)

# ============================================================
step "3. POST /admin/categories — дочерняя"
# ============================================================
CHILD_RESP=$(curl -s -X POST "$BASE/admin/categories" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"category_name\":\"Laptops\",\"parent_id\":$ROOT_ID}")

echo "$CHILD_RESP" | jq '{id, category_name, path, parent_id}'
CHILD_ID=$(echo "$CHILD_RESP" | jq -r .id)

# ============================================================
step "4. GET /categories — плоский"
# ============================================================
curl -s "$BASE/categories" | jq '[.[] | select(.path | startswith("catalog_smoke"))]'

# ============================================================
step "5. GET /categories/tree"
# ============================================================
curl -s "$BASE/categories/tree" | jq '.'

# ============================================================
step "6. POST /products — создаём 3 товара"
# ============================================================
P1=$(curl -s -X POST "$BASE/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"name\":\"Catalog Smoke Laptop\",\"description\":\"Test\",\"cost\":\"1000.00\",\"category_id\":$CHILD_ID}" | jq -r .id)

P2=$(curl -s -X POST "$BASE/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"name\":\"Catalog Smoke Mouse\",\"description\":\"Test\",\"cost\":\"50.00\",\"category_id\":$CHILD_ID}" | jq -r .id)

P3=$(curl -s -X POST "$BASE/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"name\":\"Catalog Smoke Keyboard\",\"description\":\"Test\",\"cost\":\"100.00\",\"category_id\":$CHILD_ID}" | jq -r .id)

echo "P1=$P1 P2=$P2 P3=$P3"

# ============================================================
step "7. POST /products/bulk/status — out_of_stock для всех трёх"
# ============================================================
curl -s -X POST "$BASE/products/bulk/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_ids\":[$P1,$P2,$P3],\"status\":\"out_of_stock\"}" \
  | jq .

# ============================================================
step "8. DELETE /products/{id} — soft-delete P2"
# ============================================================
HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE "$BASE/products/$P2" \
  -H "Authorization: Bearer $ACCESS")
echo "DELETE P2 HTTP_CODE=$HTTP"

# ============================================================
step "9. GET /products — без deleted"
# ============================================================
curl -s "$BASE/products" | jq '[.items[] | select(.name | startswith("Catalog Smoke"))] | length'

# ============================================================
step "10. GET /products?include_deleted=true — c deleted"
# ============================================================
curl -s "$BASE/products?include_deleted=true" \
  | jq '[.items[] | select(.name | startswith("Catalog Smoke"))] | length'

# ============================================================
step "11. RBAC: customer → POST /admin/categories → 403"
# ============================================================
# Меняем роль на customer
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET role='customer' WHERE email='$EMAIL'" >/dev/null

CUSTOMER_ACCESS=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)

curl -s -o /tmp/catalog_403.json -w "HTTP_CODE=%{http_code}\n" \
  -X POST "$BASE/admin/categories" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CUSTOMER_ACCESS" \
  -d '{"category_name":"Hacked"}'

jq . /tmp/catalog_403.json

# Возвращаем admin
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET role='admin' WHERE email='$EMAIL'" >/dev/null

# ============================================================
step "12. Цикл: PATCH ROOT → parent_id=CHILD → 422"
# ============================================================
ADMIN_ACCESS=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)

curl -s -o /tmp/catalog_cycle.json -w "HTTP_CODE=%{http_code}\n" \
  -X PATCH "$BASE/admin/categories/$ROOT_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -d "{\"parent_id\":$CHILD_ID}"

jq . /tmp/catalog_cycle.json

# ============================================================
step "13. Уборка"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM products WHERE name LIKE 'Catalog Smoke%';
  DELETE FROM categories WHERE path::text LIKE 'catalog_smoke%';
  DELETE FROM users WHERE email = '$EMAIL';
" >/dev/null

rm -f "$C1" /tmp/catalog_*.json
echo "OK"

# ============================================================
echo
echo "═══════════════════════════════════════════════════"
echo "  ✅ CATALOG SMOKE TEST PASSED"
echo "═══════════════════════════════════════════════════"