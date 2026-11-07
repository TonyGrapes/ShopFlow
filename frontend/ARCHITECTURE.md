# ShopFlow Frontend Architecture

Status: implemented foundation, storefront catalog, and admin shell.

## 1. Goals and constraints

- Keep the storefront and admin area in one React application.
- Use **zero new runtime dependencies**: React, React DOM, React Router, and native CSS only.
- Treat FastAPI/OpenAPI schemas as the source of truth. Types under `src/types/` mirror backend Pydantic models.
- Keep auth, cart, favorites, orders, and payments server-authoritative. No duplicate business state in the browser.
- Support responsive storefront UX and a guarded admin area without giving the frontend any security authority.

## 2. Runtime shape

```text
main.tsx
  -> tokens.css + base.css
  -> App
       -> AppProviders (Toast -> Auth -> Favorites -> Cart)
            -> RouterProvider
                 -> StorefrontLayout (Header + Outlet + toasts)
                 -> AdminLayout      (admin nav + Outlet + toasts)
```

### Routing

- `createBrowserRouter` with route-level `React.lazy` for non-critical pages.
- Storefront routes live under `StorefrontLayout`.
- Admin routes live under `/admin` and are wrapped by `RequireRole(["admin", "moderator"])`.
- Customer-only routes are wrapped by `RequireAuth`.
- Route guards are UX only. Backend RBAC remains the security boundary.

### Providers

- `ToastProvider`: transient notifications.
- `AuthProvider`: current user + login/register/logout/refresh.
- `FavoritesProvider`: server favorites for authenticated users.
- `CartProvider`: server cart, guest cookie cart, merge-on-login, promo preview.

The provider order is intentional: auth must resolve before favorites/cart reload for the current owner.

## 3. Folder structure

```text
src/
├── app/
│   ├── guards/             # RequireAuth, RequireRole
│   ├── layouts/            # StorefrontLayout, AdminLayout
│   ├── styles/             # design tokens, base/reset
│   ├── providers.tsx
│   └── router.tsx
├── api/                    # typed fetch modules, one per backend area
├── types/                  # backend contract types
├── shared/
│   ├── components/         # generic AsyncState
│   └── hooks/              # useApiQuery, useDebouncedValue
├── features/
│   ├── catalog/            # real-API catalog UX
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── styles/         # CSS Modules
│   │   ├── utils/
│   │   ├── types.ts
│   │   └── CatalogPage.tsx
│   └── admin/              # guarded admin shell
│       ├── pages/
│       └── Admin.module.css
├── context/                # providers + context objects (legacy boundary)
├── components/             # shared storefront components (legacy boundary)
├── pages/                  # storefront pages (legacy boundary)
├── hooks/
└── utils/
```

The catalog and admin are feature-first. Existing storefront pages are still imported through the legacy `pages/` boundary and can be migrated into feature folders incrementally without blocking delivery.

## 4. Data and contracts

### Typed fetch layer

`api/client.ts` is the only network primitive:

- base URL from `VITE_API_URL`;
- `credentials: "include"` for refresh and guest-cart cookies;
- one refresh/replay attempt on 401;
- `ApiError` with `status`, `detail`, `code`, and extra fields;
- no automatic retries for business errors.

### Query hook

`shared/hooks/useApiQuery.ts` is a deliberately small, dependency-free query primitive:

- stable string `key` triggers refetch;
- latest loader is always used;
- handles loading, error, data, cancellation, and manual `refetch`;
- avoids adding TanStack Query while keeping view code declarative.

### Catalog contract additions

Backend now supports the catalog UX directly:

- `GET /api/v1/products?q=...` searches product name, description, and category name;
- `GET /api/v1/products/price-range` returns `{ min_cost, max_cost }` for the current category/status/search slice;
- `ProductListItem.category` is a `CategoryBrief | null` for card badges and category display;
- list cache keys include normalized `q`;
- `GET /api/v1/categories` and `/categories/tree` are available to the storefront.

Catalog filters use exact `category_id` matching (not subtree expansion). This is an explicit backend semantics decision.

## 5. Catalog state model

- URL is the source of truth for shareable state: `q`, `category`, `min`, `max`, `status`, `sort`, `page`.
- `useCatalogFilters` parses and writes `URLSearchParams` via React Router.
- Search input is debounced (300 ms) before it becomes a request key; URL/chips update immediately.
- Price bounds come from the backend for the current query/category/status slice.
- Price slider changes are debounced (350 ms) before updating URL and requests.
- Any filter change resets page to 1 unless a page was explicitly supplied.
- "Recently viewed" is a non-critical `localStorage` list of product IDs (max 8), never business state.

### Storefront actions

- Add/update cart uses `CartProvider` and server responses. Cards remain usable for guests.
- Favorite toggle requires authentication; unauthenticated users receive a toast, not a fake local favorite.
- Quick view is a catalog convenience. The canonical product page remains `/products/:id`.
- No discount fields are invented: the backend has no discount/old-price contract on products.

## 6. Styling

- Semantic tokens in `app/styles/tokens.css`; base resets in `app/styles/base.css`.
- Feature styles are CSS Modules (`features/catalog/styles/*.module.css`).
- The legacy `App.css` is retained for already-built storefront pages; tokens expose compatibility aliases (`--text`, `--bg`, `--border`, etc.) so both systems coexist.
- The old fixed-width `#root` from `index.css` is no longer loaded. Layout width is owned by page/layout containers.
- Dark mode and reduced motion follow the token definitions.

## 7. Admin area

Implemented:

- `/admin` dashboard with order/category summaries;
- `/admin/orders` list with status filtering and status transitions;
- `/admin/categories` list with root/child creation and guarded deletion;
- `AdminLayout` navigation and role guard;
- storefront header link to `/admin` for admins/moderators.

Next admin modules (not yet built): product CRUD/bulk status, refunds, review moderation, promo-code management.

## 8. Error and loading UX

- Route-level lazy pages use a shared `LoadingState` fallback.
- Catalog has dedicated skeleton, empty, and retry states.
- Admin screens expose inline loading/error states and toast mutation feedback.
- Auth/refresh failures remain centralized in `api/client.ts`; feature code does not reimplement token logic.

## 9. Testing and verification

- Backend contract test checks OpenAPI field sets against frontend expectations.
- `ProductListItem` contract includes `category`; `ProductPriceRange` is covered.
- Cache-key tests cover the `q` parameter and whitespace normalization.
- Product endpoint tests cover `q`, category serialization, and price ranges.
- Commands:

```bash
cd backend
.venv/bin/pytest -q --no-cov

cd frontend
npm run lint
npm run build
```

Use `--no-cov` for targeted backend runs; the project-wide coverage threshold is intended for the full suite.

## 10. Extension rules

1. Add backend schema first, then mirror it in `src/types/`.
2. Add an API function under `src/api/`; do not call `fetch` from components.
3. Keep server state in providers/hooks; URL state for filters; local state only for ephemeral UI.
4. Use `useApiQuery` for read screens or a small feature hook that wraps it.
5. Add styles as CSS Modules in the owning feature.
6. Add/adjust contract tests when response fields change.
7. Never add a runtime dependency without an explicit decision; prefer native browser APIs.
