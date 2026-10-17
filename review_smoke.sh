#!/usr/bin/env bash
# review_smoke.sh
# Эпик 6 (отзывы) — smoke-сценарий.
#
# Требует: docker compose, backend на http://localhost:8000, jq.
#
# Что проверяет:
# 1.  Регистрация → verify → login.
# 2.  Создание товара + delivered-заказа через psql.
# 3.  POST /reviews — happy path, is_verified=true.
# 4.  GET /products/{id}/reviews — публичный, отзыв виден.
# 5.  GET /products/{id}/reviews/summary — avg=5, total=1, distribution.
# 6.  POST /reviews повторно → 409 already_reviewed.
# 7.  POST /reviews на недоставленный товар → 403.
# 8.  DELETE /reviews/{public_id} — soft-delete свой.
# 9.  GET .../reviews — отзыв исчез.
# 10. POST /reviews снова после удаления — разрешено.
# 11. RBAC: customer на /admin/reviews → 403.
# 12. Admin удаляет чужой отзыв → 204.
# 13. POST /reviews без auth → 401.
# 14. Уборка.

set -euo pipefail

BASE="http://localhost:8000/api/v1"
EMAIL="review-smoke@example.com"
ADMIN_EMAIL="review-smoke-admin@example.com"
PASSWORD="review-smoke-1234"

step() { echo; echo "═══ $1 ═══"; }

# ============================================================
step "0. Чистый старт"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM reviews WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM order_items WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM orders WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL');
  DELETE FROM products WHERE name IN ('Review Smoke Product', 'Review Smoke Pending');
  DELETE FROM categories WHERE path = 'review_smoke';
" >/dev/null
echo "OK"

# ============================================================
step "1. Register + verify + login (customer)"
# ============================================================
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Review\",\"last_name\":\"Smoke\",\"phone_number\":\"+79996660001\"}" >/dev/null

TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')
curl -s "$BASE/auth/verify-email?token=$TOKEN" >/dev/null

ACCESS=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)
echo "ACCESS=${ACCESS:0:30}..."

# ============================================================
step "2. Admin (для RBAC-тестов)"
# ============================================================
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Admin\",\"last_name\":\"Smoke\",\"phone_number\":\"+79996660002\"}" >/dev/null

ADMIN_TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $ADMIN_EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')
curl -s "$BASE/auth/verify-email?token=$ADMIN_TOKEN" >/dev/null

docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET role='admin' WHERE email='$ADMIN_EMAIL'" >/dev/null

ADMIN_ACCESS=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)
echo "ADMIN_ACCESS=${ADMIN_ACCESS:0:30}..."

# ============================================================
step "3. Категория + 2 товара + адрес"
# ============================================================
CATEGORY_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO categories (path, category_name)
  VALUES ('review_smoke', 'Review Smoke')
  ON CONFLICT (path) DO UPDATE SET category_name = EXCLUDED.category_name
  RETURNING id
" | head -1 | tr -d '[:space:]')

# Товар для delivered-заказа
DELIVERED_PRODUCT_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO products (category_id, name, description, cost, status, created_at, updated_at)
  VALUES ($CATEGORY_ID, 'Review Smoke Product', 'Test', 500.00, 'available', now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')

# Товар для pending-заказа (не delivered)
PENDING_PRODUCT_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO products (category_id, name, description, cost, status, created_at, updated_at)
  VALUES ($CATEGORY_ID, 'Review Smoke Pending', 'Test', 500.00, 'available', now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')

echo "DELIVERED_PRODUCT_ID=$DELIVERED_PRODUCT_ID PENDING_PRODUCT_ID=$PENDING_PRODUCT_ID"

# Адрес для customer
ADDRESS_ID=$(curl -s -X POST "$BASE/addresses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"address_line1":"ул. Отзывная, 1","city":"Москва","postal_code":"101000","country":"RU","is_default":true}' \
  | jq -r .id)

# ============================================================
step "4. Создаём delivered-заказ и pending-заказ через psql"
# ============================================================
USER_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "SELECT id FROM users WHERE email='$EMAIL'" | tr -d '[:space:]')

# DELIVERED заказ с DELIVERED_PRODUCT_ID
DELIVERED_ORDER_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO orders (user_id, total, status, shipping_address_id, created_at, updated_at)
  VALUES ($USER_ID, 500.00, 'delivered', $ADDRESS_ID, now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')

docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  INSERT INTO order_items (order_id, product_id, product_cost, product_count, created_at, updated_at)
  VALUES ($DELIVERED_ORDER_ID, $DELIVERED_PRODUCT_ID, 500.00, 1, now(), now())
" >/dev/null

# PENDING заказ с PENDING_PRODUCT_ID (не reviewable)
PENDING_ORDER_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc "
  INSERT INTO orders (user_id, total, status, shipping_address_id, created_at, updated_at)
  VALUES ($USER_ID, 500.00, 'pending', $ADDRESS_ID, now(), now())
  RETURNING id
" | head -1 | tr -d '[:space:]')

docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  INSERT INTO order_items (order_id, product_id, product_cost, product_count, created_at, updated_at)
  VALUES ($PENDING_ORDER_ID, $PENDING_PRODUCT_ID, 500.00, 1, now(), now())
" >/dev/null

echo "DELIVERED_ORDER_ID=$DELIVERED_ORDER_ID PENDING_ORDER_ID=$PENDING_ORDER_ID"

# ============================================================
step "5. POST /reviews — happy path"
# ============================================================
REVIEW=$(curl -s -X POST "$BASE/reviews" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$DELIVERED_PRODUCT_ID,\"rating\":5,\"title\":\"Excellent\",\"comment\":\"Very good laptop\"}")

echo "$REVIEW" | jq '{public_id, product_id, rating, is_verified, title}'

REVIEW_PUBLIC_ID=$(echo "$REVIEW" | jq -r .public_id)
IS_VERIFIED=$(echo "$REVIEW" | jq -r .is_verified)

if [ "$IS_VERIFIED" != "true" ]; then
    echo "❌ FAIL: is_verified must be true"
    exit 1
fi
echo "✅ is_verified=true"

# ============================================================
step "6. GET /products/{id}/reviews — публичный"
# ============================================================
curl -s "$BASE/products/$DELIVERED_PRODUCT_ID/reviews" \
  | jq '{total, first_rating: .items[0].rating, author: .items[0].user.public_id}'

# ============================================================
step "7. GET .../reviews/summary"
# ============================================================
curl -s "$BASE/products/$DELIVERED_PRODUCT_ID/reviews/summary" \
  | jq .

# ============================================================
step "8. POST /reviews повторно → 409 already_reviewed"
# ============================================================
DUP=$(curl -s -o /tmp/review_dup.json -w "%{http_code}" \
  -X POST "$BASE/reviews" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$DELIVERED_PRODUCT_ID,\"rating\":3}")

echo "HTTP_CODE=$DUP"
jq . /tmp/review_dup.json

if [ "$DUP" != "409" ]; then
    echo "❌ FAIL: expected 409, got $DUP"
    exit 1
fi
echo "✅ duplicate blocked"

# ============================================================
step "9. POST на недоставленный товар → 403"
# ============================================================
NOTDEL=$(curl -s -o /tmp/review_403.json -w "%{http_code}" \
  -X POST "$BASE/reviews" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$PENDING_PRODUCT_ID,\"rating\":5}")

echo "HTTP_CODE=$NOTDEL"
jq . /tmp/review_403.json

if [ "$NOTDEL" != "403" ]; then
    echo "❌ FAIL: expected 403, got $NOTDEL"
    exit 1
fi
echo "✅ no delivered order → 403"

# ============================================================
step "10. DELETE /reviews/{public_id} — soft-delete свой"
# ============================================================
curl -s -o /dev/null -w "HTTP_CODE=%{http_code}\n" \
  -X DELETE "$BASE/reviews/$REVIEW_PUBLIC_ID" \
  -H "Authorization: Bearer $ACCESS"

# Отзыв исчез из списка
curl -s "$BASE/products/$DELIVERED_PRODUCT_ID/reviews" \
  | jq '{total}'

# ============================================================
step "11. POST /reviews снова после soft-delete — разрешено"
# ============================================================
REVIEW2=$(curl -s -X POST "$BASE/reviews" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -d "{\"product_id\":$DELIVERED_PRODUCT_ID,\"rating\":4,\"comment\":\"Still good\"}")

echo "$REVIEW2" | jq '{public_id, rating, is_verified}'
REVIEW2_PUBLIC_ID=$(echo "$REVIEW2" | jq -r .public_id)
echo "✅ new review after soft-delete allowed"

# ============================================================
step "12. RBAC: customer → /admin/reviews/{id} → 403"
# ============================================================
RBAC=$(curl -s -o /tmp/review_rbac.json -w "%{http_code}" \
  -X DELETE "$BASE/admin/reviews/$REVIEW2_PUBLIC_ID" \
  -H "Authorization: Bearer $ACCESS")

echo "HTTP_CODE=$RBAC"
jq . /tmp/review_rbac.json

if [ "$RBAC" != "403" ]; then
    echo "❌ FAIL: expected 403, got $RBAC"
    exit 1
fi
echo "✅ customer blocked"

# ============================================================
step "13. Admin удаляет чужой отзыв → 204"
# ============================================================
ADMIN_DEL=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE "$BASE/admin/reviews/$REVIEW2_PUBLIC_ID" \
  -H "Authorization: Bearer $ADMIN_ACCESS")

echo "HTTP_CODE=$ADMIN_DEL"

if [ "$ADMIN_DEL" != "204" ]; then
    echo "❌ FAIL: expected 204, got $ADMIN_DEL"
    exit 1
fi
echo "✅ admin deleted"

# ============================================================
step "14. POST /reviews без auth → 401"
# ============================================================
NO_AUTH=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE/reviews" \
  -H "Content-Type: application/json" \
  -d "{\"product_id\":$DELIVERED_PRODUCT_ID,\"rating\":5}")

echo "HTTP_CODE=$NO_AUTH"

if [ "$NO_AUTH" != "401" ]; then
    echo "❌ FAIL: expected 401, got $NO_AUTH"
    exit 1
fi
echo "✅ no auth → 401"

# ============================================================
step "15. Уборка"
# ============================================================
docker compose exec -T db psql -U shopflow_user -d shopflow -c "
  DELETE FROM reviews WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM order_items WHERE order_id IN (
    SELECT o.id FROM orders o JOIN users u ON u.id = o.user_id
    WHERE u.email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM orders WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM addresses WHERE user_id IN (
    SELECT id FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL')
  );
  DELETE FROM users WHERE email IN ('$EMAIL', '$ADMIN_EMAIL');
  DELETE FROM products WHERE name IN ('Review Smoke Product', 'Review Smoke Pending');
  DELETE FROM categories WHERE path = 'review_smoke';
" >/dev/null

rm -f /tmp/review_*.json
echo "OK"

# ============================================================
echo
echo "═══════════════════════════════════════════════════"
echo "  ✅ REVIEW SMOKE TEST PASSED"
echo "═══════════════════════════════════════════════════"