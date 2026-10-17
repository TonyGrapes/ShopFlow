#!/usr/bin/env bash
# refund_smoke.sh
# Эпик 6 (возвраты) — smoke-сценарий.
#
# Требует: docker compose, backend на http://localhost:8000, jq.
#
# Что проверяет:
# 1.  Чистый старт.
# 2.  Регистрация → verify → admin role → login.
# 3.  Категория + товар.
# 4.  Заказ через psql + оплата через POST /orders/{id}/pay.
# 5.  POST /admin/payments/{id}/refund — частичный возврат 300 из 1000.
# 6.  Payment.status остаётся completed (частичный).
# 7.  GET /admin/refunds/{public_id} — детали.
# 8.  GET /admin/payments/{id}/refunds — список (1 запись).
# 9.  Повторный refund с тем же external_id → 200 (idempotent).
# 10. Второй частичный возврат 700 → сумма 1000 = полный → payment=refunded.
# 11. Попытка вернуть ещё 1 ₽ → 422 amount_exceeds_remaining.
# 12. invalid reason → 422.
# 13. RBAC: customer → 403.
# 14. Уборка.

set -euo pipefail

BASE="http://localhost:8000/api/v1"
EMAIL="refund-smoke@example.com"
PASSWORD="refund-smoke-1234"
C1="/tmp/refund_c1.txt"

step() { echo; echo "═══ $1 ═══"; }

# ============================================================
step "0. Чистый старт"
# ============================================================
rm -f "$C1"

docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM refunds WHERE payment_id IN (
    SELECT p.id FROM payments p
    JOIN orders o ON o.id = p.order_id
    JOIN users u ON u.id = o.user_id
    WHERE u.email = '$EMAIL'
  );
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
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM users WHERE email = '$EMAIL';
  DELETE FROM products WHERE name = 'Refund Smoke Product';
  DELETE FROM categories WHERE path = 'refund_smoke';
" >/dev/null
echo "OK"

# ============================================================
step "1. Регистрация → verify → admin → login"
# ============================================================
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Refund\",\"last_name\":\"Smoke\",\"phone_number\":\"+79997770001\"}" >/dev/null

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
step "2. Категория + товар + адрес"
# ============================================================
CATEGORY_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO categories (path, category_name)
  VALUES ('refund_smoke', 'Refund Smoke')
  ON CONFLICT (path) DO UPDATE SET category_name = EXCLUDED.category_name
  RETURNING id
" | head -1 | tr -d '[:space:]')

PRODUCT_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO products (category_id, name, description, cost, status, created_at, updated_at)
  VALUES ($CATEGORY_ID, 'Refund Smoke Product', 'Test', 1000.00, 'available', now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')

ADDRESS_ID=$(curl -s -X POST "$BASE/addresses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"address_line1":"ул. Возвратная, 1","city":"Москва","postal_code":"101000","country":"RU","is_default":true}' \
  | jq -r .id)

echo "CATEGORY_ID=$CATEGORY_ID PRODUCT_ID=$PRODUCT_ID ADDRESS_ID=$ADDRESS_ID"

# ============================================================
step "3. Корзина → заказ → оплата"
# ============================================================
curl -s -X POST "$BASE/cart/items" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$PRODUCT_ID,\"quantity\":1}" >/dev/null

ORDER=$(curl -s -X POST "$BASE/orders" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"address_id\":$ADDRESS_ID}")

ORDER_PUBLIC_ID=$(echo "$ORDER" | jq -r .public_id)
ORDER_TOTAL=$(echo "$ORDER" | jq -r .total)
echo "ORDER_ID=$ORDER_PUBLIC_ID total=$ORDER_TOTAL"

PAYMENT=$(curl -s -X POST "$BASE/orders/$ORDER_PUBLIC_ID/pay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"external_id":"refund-pay-1","method":"card"}')

PAYMENT_PUBLIC_ID=$(echo "$PAYMENT" | jq -r .public_id)
PAYMENT_AMOUNT=$(echo "$PAYMENT" | jq -r .amount)
PAYMENT_STATUS=$(echo "$PAYMENT" | jq -r .status)

# Внутренний id платежа для URL
PAYMENT_DB_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT p.id FROM payments p
   JOIN orders o ON o.id = p.order_id
   WHERE o.public_id = '$ORDER_PUBLIC_ID'" | tr -d '[:space:]')

echo "PAYMENT_PUBLIC_ID=$PAYMENT_PUBLIC_ID PAYMENT_DB_ID=$PAYMENT_DB_ID amount=$PAYMENT_AMOUNT status=$PAYMENT_STATUS"

if [ "$PAYMENT_STATUS" != "completed" ]; then
    echo "❌ FAIL: payment expected completed, got $PAYMENT_STATUS"
    exit 1
fi

# ============================================================
step "4. POST /admin/payments/{id}/refund — частичный 300"
# ============================================================
REFUND1=$(curl -s -X POST "$BASE/admin/payments/$PAYMENT_DB_ID/refund" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"amount":"300.00","reason":"customer_request","external_id":"refund-ext-1"}')

echo "$REFUND1" | jq '{public_id, amount, reason, status, external_id}'
REFUND1_PUBLIC_ID=$(echo "$REFUND1" | jq -r .public_id)

# ============================================================
step "5. Payment остаётся completed (частичный возврат)"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT status FROM payments WHERE id = $PAYMENT_DB_ID" \
  | tr -d '[:space:]'

# ============================================================
step "6. GET /admin/refunds/{public_id}"
# ============================================================
curl -s "$BASE/admin/refunds/$REFUND1_PUBLIC_ID" \
  -H "Authorization: Bearer $ACCESS" \
  | jq '{public_id, amount, status}'

# ============================================================
step "7. GET /admin/payments/{id}/refunds"
# ============================================================
curl -s "$BASE/admin/payments/$PAYMENT_DB_ID/refunds" \
  -H "Authorization: Bearer $ACCESS" \
  | jq 'length'

# ============================================================
step "8. Повторный refund с тем же external_id — idempotent"
# ============================================================
REFUND1_REPLAY=$(curl -s -X POST "$BASE/admin/payments/$PAYMENT_DB_ID/refund" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"amount":"300.00","reason":"customer_request","external_id":"refund-ext-1"}')

REFUND1_REPLAY_PUBLIC_ID=$(echo "$REFUND1_REPLAY" | jq -r .public_id)

if [ "$REFUND1_PUBLIC_ID" != "$REFUND1_REPLAY_PUBLIC_ID" ]; then
    echo "❌ FAIL: idempotency broken"
    exit 1
fi
echo "✅ idempotent: same public_id=$REFUND1_PUBLIC_ID"

# ============================================================
step "9. Второй возврат 700 → полный → payment=refunded"
# ============================================================
curl -s -X POST "$BASE/admin/payments/$PAYMENT_DB_ID/refund" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"amount":"700.00","reason":"defective","external_id":"refund-ext-2"}' \
  | jq '{public_id, amount, status}'

echo "--- payment status after full refund:"
docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT status FROM payments WHERE id = $PAYMENT_DB_ID" \
  | tr -d '[:space:]'

PAYMENT_STATUS_AFTER=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT status FROM payments WHERE id = $PAYMENT_DB_ID" | tr -d '[:space:]')

if [ "$PAYMENT_STATUS_AFTER" != "refunded" ]; then
    echo "❌ FAIL: payment expected refunded, got $PAYMENT_STATUS_AFTER"
    exit 1
fi
echo "✅ payment fully refunded"

# ============================================================
step "10. Попытка вернуть ещё 1 ₽ → 422 amount_exceeds_remaining"
# ============================================================
OVERFLOW_CODE=$(curl -s -o /tmp/refund_overflow.json -w "%{http_code}" \
  -X POST "$BASE/admin/payments/$PAYMENT_DB_ID/refund" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"amount":"1.00","external_id":"refund-ext-3"}')

echo "HTTP_CODE=$OVERFLOW_CODE"
jq . /tmp/refund_overflow.json

if [ "$OVERFLOW_CODE" != "422" ]; then
    echo "❌ FAIL: expected 422, got $OVERFLOW_CODE"
    exit 1
fi

# ============================================================
step "11. invalid reason → 422"
# ============================================================
INVALID_CODE=$(curl -s -o /tmp/refund_invalid.json -w "%{http_code}" \
  -X POST "$BASE/admin/payments/$PAYMENT_DB_ID/refund" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"amount":"1.00","reason":"hacked","external_id":"refund-ext-4"}')

echo "HTTP_CODE=$INVALID_CODE"
jq . /tmp/refund_invalid.json

if [ "$INVALID_CODE" != "422" ]; then
    echo "❌ FAIL: expected 422, got $INVALID_CODE"
    exit 1
fi

# ============================================================
step "12. RBAC: customer → 403"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET role='customer' WHERE email='$EMAIL'" >/dev/null

CUSTOMER_ACCESS=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)

RBAC_CODE=$(curl -s -o /tmp/refund_rbac.json -w "%{http_code}" \
  -X POST "$BASE/admin/payments/$PAYMENT_DB_ID/refund" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $CUSTOMER_ACCESS" \
  -d '{"amount":"1.00"}')

echo "HTTP_CODE=$RBAC_CODE"
jq . /tmp/refund_rbac.json

if [ "$RBAC_CODE" != "403" ]; then
    echo "❌ FAIL: expected 403, got $RBAC_CODE"
    exit 1
fi

# ============================================================
step "13. Уборка"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM refunds WHERE payment_id IN (
    SELECT p.id FROM payments p
    JOIN orders o ON o.id = p.order_id
    JOIN users u ON u.id = o.user_id
    WHERE u.email = '$EMAIL'
  );
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
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email = '$EMAIL'
  );
  DELETE FROM users WHERE email = '$EMAIL';
  DELETE FROM products WHERE name = 'Refund Smoke Product';
  DELETE FROM categories WHERE path = 'refund_smoke';
" >/dev/null

rm -f "$C1" /tmp/refund_*.json
echo "OK"

# ============================================================
echo
echo "═══════════════════════════════════════════════════"
echo "  ✅ REFUND SMOKE TEST PASSED"
echo "═══════════════════════════════════════════════════"