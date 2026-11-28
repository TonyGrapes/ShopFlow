# TODO / техдолг

## Done

- [x] Backend healthcheck: `--start-period=60s` в `backend/Dockerfile`. Локально backend healthy за 41.7s (alembic 20–25s + lifespan до 17s); без запаса `up --wait` мог ложно упасть на медленном runner'е.
- [x] Backend `fail_under` 78 → 80 (факт 80.31%), ratchet-коммит.
- [x] `docker-compose.prod.yml`: проверено — наследует `pgsty/minio` из базового compose, правок не требует.
- [x] `backend/.env.test`: пароль больше не единственный источник. `docker-compose.yml` (`db-test`) читает `${POSTGRES_TEST_PASSWORD:-shopflow_password_2026}`, а `tests/conftest.py` подставляет `POSTGRES_TEST_PASSWORD` в `POSTGRES_PASSWORD`. CI может задавать любой пароль без sed.
- [x] pg_hba.conf-ловушка задокументирована в `backend/README.md`: не проверять креды через `psql -h 127.0.0.1` внутри контейнера (loopback = trust). Только `-h localhost -p <mapped>` с хоста или `-h <service>` из другого контейнера. Относится и к `db`, не только `db-test`.
- [x] Дубликат vite: `@vitejs/plugin-react@6` требует `vite ^8`, а `vitest@3` — `vite ≤7`. Оставлены `vite ^7` + `plugin-react ^5.2`, один `vite` в дереве, `as any` в `vitest.config.ts` снят.
- [x] actionlint: добавлен отдельный job в CI (`raven-actions/actionlint@v2`).
- [x] Убран `env: POSTGRES_*` из шага `db-test` в `ci.yml`. Проверено пересозданием `db-test` с нуля: пароль `shopflow_password_2026`, smoke 7/7.
- [x] Удалён неиспользуемый legacy `frontend/src/pages/CatalogPage.tsx` (роутер использует `features/catalog/CatalogPage.tsx`).
- [x] Покрыт `AdminCategoriesPage` (H.15): 100%, общий coverage 81.43%.
- [x] Покрыт `AdminOrdersPage` (H.14): 100% (+ shared `Pagination` 100%), общий coverage 79.50%.
- [x] Покрыт `AdminUsersPage` (H.13): 100%, общий coverage 77.20%.
- [x] Покрыт `AdminProductsPage` (H.12): 100%, общий coverage 73.82%.
- [x] Покрыт `RegisterPage` (H.11): 184/187 (недостижимая ветка resend при валидном email), общий coverage 69.10%.
- [x] Покрыт `OrderDetailPage` (H.10): 100%, общий coverage 65.99%. Заодно убран флейк catalog-теста слайдера (ждать применения bounds).
- [x] Покрыт `CheckoutPage` + `AddressForm` (H.9): Checkout 99%, AddressForm 100%, общий coverage 62.30%.
- [x] Покрыт реальный `features/catalog/CatalogPage` + компоненты/хуки/utils (H.8): `features/catalog` ~99%, общий coverage 54.86%. Попутно исправлен баг `FilterSidebar`: при загрузке `bounds` (0 → реальный диапазон) debounce применял stale `onPriceChange(null, 0)` и ставил `max_cost=0`.

## Open

- [ ] Остальные страницы: `AddressesPage`, `ProfilePage`, admin: Dashboard/RevenueChart, AdminLayout, guards/router/providers; `App`/`router`/`providers`/`guards`.
- [ ] Опционально: отдельный `backend/.env.db-test` только с `POSTGRES_*`, чтобы не засорять `docker compose config` лишними переменными. Текущий вариант рабочий.
- [ ] Branch/function coverage gates отложены: v8 даёт странные числа для непокрытого кода (vitest-dev/vitest#2390). Сейчас gate только по `lines` (81.43%, порог 79).
