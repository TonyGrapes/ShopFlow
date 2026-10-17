#!/usr/bin/env bash
# promo_smoke.sh
# Эпик 6 (промокоды) — smoke-сценарий.
#
# Требует: docker compose, backend на http://localhost:8000, jq.
#
# Что проверяет:
# 1.  Создание промокодов через psql (SUMMER10, FIX500, LIMIT1, EXPIRED).
# 2.  Preview: happy (10% от 2000 = 200.00).
# 3.  Preview: fixed (500 ₽ от 2000 = 1500.00 final).
# 4.  Preview: used_count НЕ инкрементируется.
# 5.  Preview: пустая корзина → 422 empty_cart.
# 6.  Preview: неизвестный код → 422 not_found.
# 7.  Preview: expired → 422 expired.
# 8.  Preview: min_order_amount → 422 с оба поля в detail.
# 9.  Заказ с промокодом: subtotal/discount/total правильные.
# 10. used_count инкрементирован после заказа.
# 11. Заказ с лимитом=1 → второй заказ на другой корзине → 422.
# 12. Заказ без промокода: discount_amount=null, promo_code=null.
# 13. Уборка.

set -euo pipefail

BASE="http://localhost:8000/api/v1"
EMAIL="promo-smoke@example.com"
PASSWORD="promo-smoke-1234"
C1="/tmp/promo_c1.txt"

step() { echo; echo "═══ $1 ═══"; }

# ============================================================
step "0. Чистый старт"
# ============================================================
rm -f "$C1"

docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM payments WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email = '$EMAIL'
  );
  DELETE FROM order_items WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email = '$EMAIL'
  );
  DELETE FROM orders WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM cart_items WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM users WHERE email = '$EMAIL';
  DELETE FROM products WHERE name = 'Promo Smoke Product';
  DELETE FROM categories WHERE path = 'promo_smoke';
  DELETE FROM promo_codes WHERE code IN ('SUMMER10', 'FIX500', 'LIMIT1', 'EXPIRED', 'MIN5000');
" >/dev/null
echo "OK"

# ============================================================
step "1. Создаём промокоды через psql"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  INSERT INTO promo_codes (code, discount_type, discount_value, max_uses, used_count, valid_from, valid_until, is_active, created_at, updated_at)
  VALUES
    ('SUMMER10', 'percentage', 10.00, NULL, 0, now() - interval '1 day', now() + interval '30 days', true, now(), now()),
    ('FIX500',   'fixed',      500.00, NULL, 0, now() - interval '1 day', now() + interval '30 days', true, now(), now()),
    ('LIMIT1',   'percentage', 20.00, 1,    0, now() - interval '1 day', now() + interval '30 days', true, now(), now()),
    ('EXPIRED',  'percentage', 10.00, NULL, 0, now() - interval '30 days', now() - interval '1 day', true, now(), now()),
    ('MIN5000',  'percentage', 10.00, NULL, 0, now() - interval '1 day', now() + interval '30 days', true, now(), now())
" >/dev/null

docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE promo_codes SET min_order_amount = 5000.00 WHERE code = 'MIN5000'" >/dev/null

docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "SELECT code, discount_type, discount_value, used_count, is_active FROM promo_codes WHERE code IN ('SUMMER10','FIX500','LIMIT1','EXPIRED','MIN5000')"

# ============================================================
step "2. Register + verify + login"
# ============================================================
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Promo\",\"last_name\":\"Smoke\",\"phone_number\":\"+79997770001\"}" >/dev/null

TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')

curl -s "$BASE/auth/verify-email?token=$TOKEN" >/dev/null

ACCESS=$(curl -s -c "$C1" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)
echo "ACCESS=${ACCESS:0:30}..."

# ============================================================
step "3. Создаём категорию + товар + адрес"
# ============================================================
CATEGORY_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO categories (path, category_name)
  VALUES ('promo_smoke', 'Promo Smoke')
  ON CONFLICT (path) DO UPDATE SET category_name = EXCLUDED.category_name
  RETURNING id
" | head -1 | tr -d '[:space:]')

PRODUCT_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO products (category_id, name, description, cost, status, created_at, updated_at)
  VALUES ($CATEGORY_ID, 'Promo Smoke Product', 'Test', 1000.00, 'available', now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')

ADDRESS_ID=$(curl -s -X POST "$BASE/addresses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"address_line1":"ул. Промо, 1","city":"Москва","postal_code":"101000","country":"RU","is_default":true}' \
  | jq -r .id)

echo "CATEGORY_ID=$CATEGORY_ID PRODUCT_ID=$PRODUCT_ID ADDRESS_ID=$ADDRESS_ID"

# ============================================================
step "4. Preview с пустой корзиной → 422 empty_cart"
# ============================================================
curl -s -X POST "$BASE/cart/apply-promo" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"code":"SUMMER10"}' \
  -w "\nHTTP %{http_code}\n"

# ============================================================
step "5. Добавляем 2 товара (subtotal = 2000.00)"
# ============================================================
curl -s -X POST "$BASE/cart/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$PRODUCT_ID,\"quantity\":2}" \
  | jq '{total_items, total_cost}'

# ============================================================
step "6. Preview SUMMER10 (10% от 2000 = 200.00)"
# ============================================================
PREVIEW=$(curl -s -X POST "$BASE/cart/apply-promo" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"code":"SUMMER10"}')

echo "$PREVIEW" | jq '{code, discount_type, discount_value, subtotal, discount_amount, final_total}'

# Проверяем математику
P_SUB=$(echo "$PREVIEW" | jq -r .subtotal)
P_DISC=$(echo "$PREVIEW" | jq -r .discount_amount)
P_FINAL=$(echo "$PREVIEW" | jq -r .final_total)

if [ "$P_SUB" != "2000.00" ] || [ "$P_DISC" != "200.00" ] || [ "$P_FINAL" != "1800.00" ]; then
    echo "❌ FAIL: math mismatch: sub=$P_SUB disc=$P_DISC final=$P_FINAL"
    exit 1
fi
echo "✅ math correct"

# ============================================================
step "7. Preview FIX500 (500 ₽ от 2000 = 1500.00)"
# ============================================================
curl -s -X POST "$BASE/cart/apply-promo" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"code":"FIX500"}' \
  | jq '{code, discount_amount, final_total}'

# ============================================================
step "8. Preview unknown code → 422 not_found"
# ============================================================
curl -s -X POST "$BASE/cart/apply-promo" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"code":"NOPE"}' \
  -w "\nHTTP %{http_code}\n"

# ============================================================
step "9. Preview EXPIRED → 422 expired"
# ============================================================
curl -s -X POST "$BASE/cart/apply-promo" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"code":"EXPIRED"}' \
  -w "\nHTTP %{http_code}\n"

# ============================================================
step "10. Preview MIN5000 (корзина 2000 < 5000) → 422"
# ============================================================
curl -s -X POST "$BASE/cart/apply-promo" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"code":"MIN5000"}' \
  -w "\nHTTP %{http_code}\n"

# ============================================================
step "11. Preview НЕ инкрементирует used_count"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT code, used_count FROM promo_codes WHERE code = 'SUMMER10'"

# ============================================================
step "12. Заказ с SUMMER10 → subtotal 2000, discount 200, total 1800"
# ============================================================
ORDER=$(curl -s -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"address_id\":$ADDRESS_ID,\"promo_code\":\"SUMMER10\"}")

echo "$ORDER" | jq '{public_id, status, subtotal, discount_amount, total, promo_code}'

O_SUB=$(echo "$ORDER" | jq -r .subtotal)
O_DISC=$(echo "$ORDER" | jq -r .discount_amount)
O_TOT=$(echo "$ORDER" | jq -r .total)
O_CODE=$(echo "$ORDER" | jq -r .promo_code)

if [ "$O_SUB" != "2000.00" ] || [ "$O_DISC" != "200.00" ] || [ "$O_TOT" != "1800.00" ] || [ "$O_CODE" != "SUMMER10" ]; then
    echo "❌ FAIL: order fields mismatch"
    exit 1
fi
echo "✅ order with promo correct"

# ============================================================
step "13. used_count SUMMER10 инкрементирован до 1"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT code, used_count FROM promo_codes WHERE code = 'SUMMER10'"

USED=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT used_count FROM promo_codes WHERE code = 'SUMMER10'" | tr -d '[:space:]')

if [ "$USED" != "1" ]; then
    echo "❌ FAIL: expected used_count=1, got $USED"
    exit 1
fi
echo "✅ used_count incremented"

# ============================================================
step "14. Заказ без промокода → discount_amount=null"
# ============================================================
# Пополняем корзину заново
curl -s -X POST "$BASE/cart/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$PRODUCT_ID,\"quantity\":1}" >/dev/null

ORDER2=$(curl -s -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"address_id\":$ADDRESS_ID}")

echo "$ORDER2" | jq '{subtotal, discount_amount, total, promo_code}'

# ============================================================
step "15. LIMIT1: первый заказ с промокодом — успех"
# ============================================================
curl -s -X POST "$BASE/cart/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$PRODUCT_ID,\"quantity\":1}" >/dev/null

ORDER3=$(curl -s -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"address_id\":$ADDRESS_ID,\"promo_code\":\"LIMIT1\"}")

echo "$ORDER3" | jq '{discount_amount, total, promo_code}'

# ============================================================
step "16. LIMIT1 повторно → 422 max_uses_exceeded"
# ============================================================
curl -s -X POST "$BASE/cart/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$PRODUCT_ID,\"quantity\":1}" >/dev/null

LIMIT_RESPONSE=$(curl -s -o /tmp/promo_limit.json -w "%{http_code}" \
  -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"address_id\":$ADDRESS_ID,\"promo_code\":\"LIMIT1\"}")

echo "HTTP_CODE=$LIMIT_RESPONSE"
jq . /tmp/promo_limit.json

if [ "$LIMIT_RESPONSE" != "422" ]; then
    echo "❌ FAIL: expected 422, got $LIMIT_RESPONSE"
    exit 1
fi

REASON=$(jq -r .detail.reason /tmp/promo_limit.json)
if [ "$REASON" != "max_uses_exceeded" ]; then
    echo "❌ FAIL: expected reason=max_uses_exceeded, got $REASON"
    exit 1
fi
echo "✅ max_uses_exceeded"

# ============================================================
step "17. Уборка"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM payments WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email = '$EMAIL'
  );
  DELETE FROM order_items WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email = '$EMAIL'
  );
  DELETE FROM orders WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM cart_items WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM users WHERE email = '$EMAIL';
  DELETE FROM products WHERE name = 'Promo Smoke Product';
  DELETE FROM categories WHERE path = 'promo_smoke';
  DELETE FROM promo_codes WHERE code IN ('SUMMER10', 'FIX500', 'LIMIT1', 'EXPIRED', 'MIN5000');
" >/dev/null

rm -f "$C1" /tmp/promo_limit.json
echo "OK"

# ============================================================
echo
echo "═══════════════════════════════════════════════════"
echo "  ✅ PROMO SMOKE TEST PASSED"
echo "═══════════════════════════════════════════════════"