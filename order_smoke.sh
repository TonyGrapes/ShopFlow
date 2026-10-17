#!/usr/bin/env bash
# order_smoke.sh
# Эпик 5 — smoke-сценарий заказов.
#
# Требует: docker compose, запущенный backend на http://localhost:8000, jq.
#
# Что проверяет:
# 1.  Регистрация → верификация → логин.
# 2.  Создание адреса.
# 3.  Добавление двух товаров в корзину (через psql — товары создаём напрямую).
# 4.  POST /orders — заказ создан, корзина очищена, total правильный.
# 5.  GET /orders — заказ в списке.
# 6.  GET /orders/{public_id} — детали.
# 7.  POST /orders/{public_id}/pay — оплата, status=paid.
# 8.  Повторный pay с тем же external_id — 200, тот же Payment (идемпотентность).
# 9.  RBAC: customer на /admin/orders → 403.
# 10. Admin: PATCH /admin/orders/{id}/status — paid→shipped (200).
# 11. Admin: PATCH shipped→paid → 422 invalid_transition.
# 12. Ownership: чужой заказ → 404.
# 13. POST /orders без токена → 401.
# 14. POST /orders с пустой корзиной → 422.
# 15. Уборка.

set -euo pipefail

BASE="http://localhost:8000/api/v1"
EMAIL="order-smoke@example.com"
ADMIN_EMAIL="order-smoke-admin@example.com"
PASSWORD="order-smoke-1234"
C1="/tmp/order_c1.txt"
C2="/tmp/order_c2.txt"

step() { echo; echo "═══ $1 ═══"; }

# ============================================================
step "0. Чистый старт"
# ============================================================
rm -f "$C1" "$C2"

# Удаляем всё, что мог оставить прошлый прогон. Порядок важен из-за FK.
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM payments WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM order_items WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM orders WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM cart_items WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL');
  DELETE FROM products WHERE name IN ('Order Smoke Laptop', 'Order Smoke Mouse');
  DELETE FROM categories WHERE path = 'order_smoke';
" >/dev/null
echo "OK"

# ============================================================
step "1. Register + verify + login (customer)"
# ============================================================
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Order\",\"last_name\":\"Smoke\",\"phone_number\":\"+79995550001\"}" \
  | jq '{email, status}'

TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')

curl -s "$BASE/auth/verify-email?token=$TOKEN" | jq

ACCESS=$(curl -s -c "$C1" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)
echo "ACCESS=${ACCESS:0:30}..."

# ============================================================
step "2. Создаём admin-пользователя (для RBAC-тестов)"
# ============================================================
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Admin\",\"last_name\":\"Smoke\",\"phone_number\":\"+79995550002\"}" >/dev/null

ADMIN_TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $ADMIN_EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')

curl -s "$BASE/auth/verify-email?token=$ADMIN_TOKEN" >/dev/null

# Меняем роль на admin + получаем свежий access
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET role='admin' WHERE email='$ADMIN_EMAIL'" >/dev/null

ADMIN_ACCESS=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)
echo "ADMIN_ACCESS=${ADMIN_ACCESS:0:30}..."

# ============================================================
step "3. Создаём категорию + 2 товара через psql"
# ============================================================
CATEGORY_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO categories (path, category_name)
  VALUES ('order_smoke', 'Order Smoke')
  ON CONFLICT (path) DO UPDATE SET category_name = EXCLUDED.category_name
  RETURNING id
" | head -1 | tr -d '[:space:]')
echo "CATEGORY_ID=$CATEGORY_ID"

LAPTOP_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO products (category_id, name, description, cost, status, created_at, updated_at)
  VALUES ($CATEGORY_ID, 'Order Smoke Laptop', 'Test laptop', 1000.00, 'available', now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')
echo "LAPTOP_ID=$LAPTOP_ID"

MOUSE_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO products (category_id, name, description, cost, status, created_at, updated_at)
  VALUES ($CATEGORY_ID, 'Order Smoke Mouse', 'Test mouse', 50.00, 'available', now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')
echo "MOUSE_ID=$MOUSE_ID"

# ============================================================
step "4. POST /addresses — создаём адрес"
# ============================================================
ADDRESS_ID=$(curl -s -X POST "$BASE/addresses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"address_line1":"ул. Тестовая, 1","city":"Москва","postal_code":"101000","country":"RU","is_default":true}' \
  | jq -r .id)
echo "ADDRESS_ID=$ADDRESS_ID"

# ============================================================
step "5. POST /cart/items — добавляем 2 позиции"
# ============================================================
curl -s -X POST "$BASE/cart/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$LAPTOP_ID,\"quantity\":2}" >/dev/null

curl -s -X POST "$BASE/cart/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$MOUSE_ID,\"quantity\":3}" \
  | jq '{total_items, total_cost}'

# ============================================================
step "6. POST /orders — оформляем заказ"
#   Ожидание: 201, total=2150.00 (1000*2 + 50*3), status=pending
# ============================================================
ORDER=$(curl -s -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"address_id\":$ADDRESS_ID}")

echo "$ORDER" | jq '{public_id, status, total, items_count: (.items | length)}'

ORDER_PUBLIC_ID=$(echo "$ORDER" | jq -r .public_id)
ORDER_TOTAL=$(echo "$ORDER" | jq -r .total)

if [ "$ORDER_TOTAL" != "2150.00" ]; then
    echo "❌ FAIL: expected total=2150.00, got $ORDER_TOTAL"
    exit 1
fi
echo "✅ total=2150.00"

# ============================================================
step "7. GET /cart — корзина очищена"
# ============================================================
curl -s "$BASE/cart" -H "Authorization: Bearer $ACCESS" \
  | jq '{total_items, items_count: (.items | length)}'

# ============================================================
step "8. GET /orders — заказ в списке"
# ============================================================
curl -s "$BASE/orders" -H "Authorization: Bearer $ACCESS" \
  | jq '{total, items: [.items[] | {public_id, status, total, items_count}]}'

# ============================================================
step "9. GET /orders/{public_id} — детали"
# ============================================================
curl -s "$BASE/orders/$ORDER_PUBLIC_ID" -H "Authorization: Bearer $ACCESS" \
  | jq '{status, total, items: [.items[] | {product: .product.name, product_cost, product_count}]}'

# ============================================================
step "10. POST /orders/{public_id}/pay — оплата"
#   Ожидание: 200, status=completed
# ============================================================
PAYMENT=$(curl -s -X POST "$BASE/orders/$ORDER_PUBLIC_ID/pay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"external_id":"smoke-ext-1","method":"card"}')

echo "$PAYMENT" | jq '{public_id, status, amount, external_id}'
PAYMENT_PUBLIC_ID_1=$(echo "$PAYMENT" | jq -r .public_id)

# Заказ теперь paid
curl -s "$BASE/orders/$ORDER_PUBLIC_ID" -H "Authorization: Bearer $ACCESS" \
  | jq '{status}'

# ============================================================
step "11. Повторный pay с тем же external_id — идемпотентность"
#   Ожидание: 200, public_id тот же, никакого дубля
# ============================================================
PAYMENT_REPLAY=$(curl -s -X POST "$BASE/orders/$ORDER_PUBLIC_ID/pay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"external_id":"smoke-ext-1","method":"card"}')

PAYMENT_PUBLIC_ID_2=$(echo "$PAYMENT_REPLAY" | jq -r .public_id)
echo "$PAYMENT_REPLAY" | jq '{public_id, status, external_id}'

if [ "$PAYMENT_PUBLIC_ID_1" != "$PAYMENT_PUBLIC_ID_2" ]; then
    echo "❌ FAIL: idempotency broken — different public_id"
    exit 1
fi
echo "✅ idempotent: same payment public_id"

# ============================================================
step "12. RBAC: customer на /admin/orders → 403"
# ============================================================
ADMIN_403=$(curl -s -o /tmp/order_admin_403.json -w "%{http_code}" \
  "$BASE/admin/orders" -H "Authorization: Bearer $ACCESS")
echo "HTTP_CODE=$ADMIN_403"
jq . /tmp/order_admin_403.json

if [ "$ADMIN_403" != "403" ]; then
    echo "❌ FAIL: expected 403, got $ADMIN_403"
    exit 1
fi
echo "✅ customer blocked on admin endpoint"

# ============================================================
step "13. Admin: PATCH /admin/orders/{id}/status — paid → shipped (200)"
# ============================================================
SHIPPED=$(curl -s -X PATCH "$BASE/admin/orders/$ORDER_PUBLIC_ID/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -d '{"status":"shipped"}')
echo "$SHIPPED" | jq '{status}'

STATUS_AFTER=$(echo "$SHIPPED" | jq -r .status)
if [ "$STATUS_AFTER" != "shipped" ]; then
    echo "❌ FAIL: expected shipped, got $STATUS_AFTER"
    exit 1
fi

# ============================================================
step "14. Admin: PATCH shipped → paid (422 invalid_transition)"
# ============================================================
INVALID=$(curl -s -o /tmp/order_invalid.json -w "%{http_code}" \
  -X PATCH "$BASE/admin/orders/$ORDER_PUBLIC_ID/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  -d '{"status":"paid"}')
echo "HTTP_CODE=$INVALID"
jq . /tmp/order_invalid.json

if [ "$INVALID" != "422" ]; then
    echo "❌ FAIL: expected 422, got $INVALID"
    exit 1
fi
echo "✅ invalid transition blocked"

# ============================================================
step "15. Ownership: admin видит чужой заказ, customer — нет"
# ============================================================
echo "--- admin на чужой заказ:"
curl -s "$BASE/admin/orders/$ORDER_PUBLIC_ID" \
  -H "Authorization: Bearer $ADMIN_ACCESS" \
  | jq '{public_id, status, user_id: (.public_id)}' 2>/dev/null || true

# Создаём вторую customer-сессию и пробуем чужой заказ
OTHER_EMAIL="other-smoke@example.com"
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "DELETE FROM users WHERE email='$OTHER_EMAIL'" >/dev/null
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$OTHER_EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Other\",\"last_name\":\"User\",\"phone_number\":\"+79995550003\"}" >/dev/null

OTHER_TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $OTHER_EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')
curl -s "$BASE/auth/verify-email?token=$OTHER_TOKEN" >/dev/null

OTHER_ACCESS=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$OTHER_EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)

OWNERSHIP=$(curl -s -o /tmp/order_ownership.json -w "%{http_code}" \
  "$BASE/orders/$ORDER_PUBLIC_ID" -H "Authorization: Bearer $OTHER_ACCESS")
echo "HTTP_CODE=$OWNERSHIP"
jq . /tmp/order_ownership.json

if [ "$OWNERSHIP" != "404" ]; then
    echo "❌ FAIL: expected 404 for foreign order, got $OWNERSHIP"
    exit 1
fi
echo "✅ foreign order → 404 (не 403)"

# ============================================================
step "16. POST /orders без токена → 401"
# ============================================================
NO_AUTH=$(curl -s -o /tmp/order_no_auth.json -w "%{http_code}" \
  -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -d "{\"address_id\":$ADDRESS_ID}")
echo "HTTP_CODE=$NO_AUTH"
jq . /tmp/order_no_auth.json

if [ "$NO_AUTH" != "401" ]; then
    echo "❌ FAIL: expected 401, got $NO_AUTH"
    exit 1
fi
echo "✅ no auth → 401"

# ============================================================
step "17. POST /orders с пустой корзиной → 422 empty_cart"
# ============================================================
EMPTY=$(curl -s -o /tmp/order_empty.json -w "%{http_code}" \
  -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"address_id\":$ADDRESS_ID}")
echo "HTTP_CODE=$EMPTY"
jq . /tmp/order_empty.json

if [ "$EMPTY" != "422" ]; then
    echo "❌ FAIL: expected 422, got $EMPTY"
    exit 1
fi
echo "✅ empty cart → 422"

# ============================================================
step "18. Уборка"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM payments WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email IN ('$EMAIL', '$ADMIN_EMAIL', '$OTHER_EMAIL')
  );
  DELETE FROM order_items WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email IN ('$EMAIL', '$ADMIN_EMAIL', '$OTHER_EMAIL')
  );
  DELETE FROM orders WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL', '$OTHER_EMAIL')
  );
  DELETE FROM cart_items WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL', '$OTHER_EMAIL')
  );
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL', '$OTHER_EMAIL')
  );
  DELETE FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL', '$OTHER_EMAIL');
  DELETE FROM products WHERE name IN ('Order Smoke Laptop', 'Order Smoke Mouse');
  DELETE FROM categories WHERE path = 'order_smoke';
" >/dev/null

rm -f "$C1" "$C2" /tmp/order_*.json
echo "OK"

# ============================================================
echo
echo "═══════════════════════════════════════════════════"
echo "  ✅ ORDER SMOKE TEST PASSED"
echo "═══════════════════════════════════════════════════"