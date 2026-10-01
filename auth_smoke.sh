#!/usr/bin/env bash
# Auth smoke-сценарий: register → verify → login → me → refresh → reuse → logout → ban
# Требует: запущенный backend на http://localhost:8000, jq, docker compose

set -euo pipefail

BASE="http://localhost:8000/api/v1/auth"
EMAIL="curl@example.com"
PASSWORD="curl-password-1234"
C1="/tmp/c1.txt"
C2="/tmp/c2.txt"

step() { echo; echo "═══ $1 ═══"; }

# ------------------------------------------------------------
step "0. Чистый старт"
rm -f "$C1" "$C2"
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "DELETE FROM products WHERE name IN ('Forbidden Product', 'Admin Product Smoke')" >/dev/null
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "DELETE FROM categories WHERE path='rbac_smoke'" >/dev/null
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "DELETE FROM users WHERE email='$EMAIL'" >/dev/null
echo "OK"

# ------------------------------------------------------------
step "1. Register (ожидаю 201, status=pending, is_email_verified=false)"
curl -s -X POST "$BASE/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Curl\",\"last_name\":\"Test\",\"phone_number\":\"+79991112233\"}" \
  | jq '{email, status, is_email_verified}'

# ------------------------------------------------------------
step "2. Verify email (токен из логов backend)"
TOKEN=$(docker compose logs backend --tail=200 \
  | grep "Verification email for $EMAIL" | tail -1 \
  | sed 's/.*token=//' | tr -d '[:space:]')
echo "TOKEN=$TOKEN"

curl -s -w "\nHTTP %{http_code}\n" \
  "$BASE/verify-email?token=$TOKEN"

# ------------------------------------------------------------
step "3. Login (Set-Cookie: shopflow_refresh=...; HttpOnly; Path=/api/v1/auth)"
curl -s -c "$C1" -D /tmp/login_headers.txt -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | jq '{access_token: (.access_token[0:30] + "..."), token_type, expires_in}'
echo "--- Set-Cookie header:"
grep -i "set-cookie" /tmp/login_headers.txt

# ------------------------------------------------------------
step "4. /me с access-токеном (ожидаю профиль, status=active)"
ACCESS=$(curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)
curl -s "$BASE/me" -H "Authorization: Bearer $ACCESS" | jq '{email, status, is_email_verified}'

# ------------------------------------------------------------
step "5. Refresh (ротация: c1 → c2, старый refresh revoked)"
curl -s -b "$C1" -c "$C2" -X POST "$BASE/refresh" \
  | jq '{access_token: (.access_token[0:30] + "..."), expires_in}'

# ------------------------------------------------------------
step "6. Reuse старого refresh (ожидаю 401 All sessions revoked)"
curl -s -b "$C1" -w "\nHTTP %{http_code}\n" -X POST "$BASE/refresh"

# ------------------------------------------------------------
step "7. Проверка что НОВЫЙ refresh тоже мёртв (вся семья отозвана)"
curl -s -b "$C2" -w "\nHTTP %{http_code}\n" -X POST "$BASE/refresh"

# ------------------------------------------------------------
step "8. Новый логин → logout → refresh после logout (ожидаю 401)"
rm -f "$C1"
curl -s -c "$C1" -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" >/dev/null

echo "--- logout response headers (set-cookie):"
curl -s -i -b "$C1" -c "$C1" -X POST "$BASE/logout" \
  | grep -i "^set-cookie" \
  | tee /tmp/logout_setcookie.txt

# ✅ Проверяем: Set-Cookie содержит Max-Age=0 (или expires в прошлом)
if grep -qiE "max-age=0|expires=.*1970" /tmp/logout_setcookie.txt; then
    echo "✅ Logout стирает cookie (Max-Age=0 / past expires)"
else
    echo "❌ Logout НЕ стирает cookie"
fi

# refresh после logout
curl -s -b "$C1" -w "\nHTTP %{http_code}\n" -X POST "$BASE/refresh"
# ------------------------------------------------------------
step "9. Ban-политика (banned → 403 на login)"
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET status='banned' WHERE email='$EMAIL'" >/dev/null

curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  -w "\nHTTP %{http_code}\n"

# ------------------------------------------------------------
step "10. Протухший access-токен (ожидаю 401 с detail про expired)"
# Генерим просроченный токен через Python-скрипт в контейнере
EXPIRED=$(docker compose exec -T backend uv run --no-sync python -c "
import jwt, uuid
from datetime import datetime, timedelta, timezone
from app.core.config import get_settings
s = get_settings()
now = datetime.now(timezone.utc)
print(jwt.encode(
    {'sub':'00000000-0000-0000-0000-000000000000','type':'access',
     'iat': now - timedelta(hours=2), 'exp': now - timedelta(hours=1),
     'jti': uuid.uuid4().hex},
    s.SECRET_KEY.get_secret_value(), algorithm=s.ALGORITHM))
" | tail -1)

curl -s "$BASE/me" -H "Authorization: Bearer $EXPIRED" \
  -w "\nHTTP %{http_code}\n"

# ------------------------------------------------------------
step "11. Неверный пароль (ожидаю 401 Invalid credentials, тот же detail)"
# Сначала разбаним, иначе тест не показателен
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET status='active' WHERE email='$EMAIL'" >/dev/null

curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"wrong-password\"}" \
  -w "\nHTTP %{http_code}\n"

step "12. Неизвестный email (ожидаю тот же 401 Invalid credentials)"
curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"nobody@example.com","password":"any-password-1234"}' \
  -w "\nHTTP %{http_code}\n"

# ------------------------------------------------------------
step "13. Login-oracle off: оба detail идентичны"
R_UNKNOWN=$(curl -s -X POST "$BASE/login" -H "Content-Type: application/json" \
  -d '{"email":"nobody@example.com","password":"any-password-1234"}')
R_WRONG=$(curl -s -X POST "$BASE/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"wrong-password\"}")
echo "unknown: $R_UNKNOWN"
echo "wrong:   $R_WRONG"
[ "$R_UNKNOWN" = "$R_WRONG" ] && echo "✅ IDENTICAL" || echo "❌ DIFFERENT"

# ------------------------------------------------------------
step "14. RBAC: customer → 403 на POST /products"

CATEGORY_ID=$(docker compose exec -T db psql -U shopflow_user -d shopflow -tAc \
  "INSERT INTO categories (path, category_name) VALUES ('rbac_smoke', 'RBAC Smoke')
   ON CONFLICT (path) DO UPDATE SET category_name = EXCLUDED.category_name
   RETURNING id" | head -1 | tr -d '[:space:]')
echo "CATEGORY_ID=$CATEGORY_ID"

ACCESS_CUSTOMER=$(curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)

# -o → тело в файл, -w → код в stdout
CUSTOMER_CODE=$(curl -s -o /tmp/customer_resp.json -w "%{http_code}" \
  -X POST "http://localhost:8000/api/v1/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_CUSTOMER" \
  -d "{\"name\":\"Forbidden Product\",\"description\":\"Test\",\"cost\":\"100.00\",\"category_id\":$CATEGORY_ID}")

echo "HTTP_CODE=$CUSTOMER_CODE"
jq . /tmp/customer_resp.json

# ------------------------------------------------------------
step "15. RBAC: admin → 201 на POST /products"

docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "UPDATE users SET role='admin', status='active' WHERE email='$EMAIL'" >/dev/null

ACCESS_ADMIN=$(curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r .access_token)

ADMIN_CODE=$(curl -s -o /tmp/admin_resp.json -w "%{http_code}" \
  -X POST "http://localhost:8000/api/v1/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_ADMIN" \
  -d "{\"name\":\"Admin Product Smoke\",\"description\":\"Test\",\"cost\":\"100.00\",\"category_id\":$CATEGORY_ID}")

echo "HTTP_CODE=$ADMIN_CODE"
jq '{id, name}' /tmp/admin_resp.json
# ------------------------------------------------------------
step "16. JWT payload: свежесть iat и уникальность jti после refresh"

# Хелпер декодирует payload JWT в JSON
decode_jwt_payload() {
    local payload_b64
    payload_b64=$(echo "$1" | cut -d. -f2 | tr '_-' '/+')
    local mod=$(( ${#payload_b64} % 4 ))
    if [ "$mod" -eq 2 ]; then payload_b64="${payload_b64}=="
    elif [ "$mod" -eq 3 ]; then payload_b64="${payload_b64}="
    fi
    echo "$payload_b64" | base64 -d
}

# Свежий логин
rm -f "$C1" "$C2"
L1=$(curl -s -c "$C1" -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
T1=$(echo "$L1" | jq -r .access_token)
P1=$(decode_jwt_payload "$T1")
IAT1=$(echo "$P1" | jq -r .iat)
JTI1=$(echo "$P1" | jq -r .jti)
echo "iat_1=$IAT1  jti_1=$JTI1"

sleep 2

# Refresh
L2=$(curl -s -b "$C1" -c "$C2" -X POST "$BASE/refresh")
T2=$(echo "$L2" | jq -r .access_token)
P2=$(decode_jwt_payload "$T2")
IAT2=$(echo "$P2" | jq -r .iat)
JTI2=$(echo "$P2" | jq -r .jti)
echo "iat_2=$IAT2  jti_2=$JTI2"

# Проверки
if [ "$JTI1" = "$JTI2" ]; then
    echo "❌ FAIL: jti одинаковый"
else
    echo "✅ jti уникален"
fi
if [ "$IAT1" = "$IAT2" ]; then
    echo "❌ FAIL: iat не обновился (оба = $IAT1)"
else
    echo "✅ iat обновился"
fi
# ------------------------------------------------------------
step "17. Чистим за собой"
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "DELETE FROM products WHERE name IN ('Forbidden Product','Admin Product Smoke')" >/dev/null
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "DELETE FROM categories WHERE path='rbac_smoke'" >/dev/null
docker compose exec -T db psql -U shopflow_user -d shopflow -c \
  "DELETE FROM users WHERE email='$EMAIL'" >/dev/null
rm -f "$C1" "$C2" /tmp/login_headers.txt
echo "OK"
