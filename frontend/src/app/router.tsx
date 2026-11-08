import { lazy, Suspense } from "react";
import type { ComponentType, ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { LoadingState } from "../components/LoadingState";
import { CatalogPage } from "../features/catalog/CatalogPage";
import type { UserRole } from "../types/auth";
import { RootProviders } from "./RootProviders";
import { RequireAuth } from "./guards/RequireAuth";
import { RequireRole } from "./guards/RequireRole";
import { AdminLayout } from "./layouts/AdminLayout";
import { StorefrontLayout } from "./layouts/StorefrontLayout";

const ProductPage = lazyNamed(() => import("../pages/ProductPage"), "ProductPage");
const LoginPage = lazyNamed(() => import("../pages/LoginPage"), "LoginPage");
const RegisterPage = lazyNamed(() => import("../pages/RegisterPage"), "RegisterPage");
const VerifyEmailPage = lazyNamed(() => import("../pages/VerifyEmailPage"), "VerifyEmailPage");
const CartPage = lazyNamed(() => import("../pages/CartPage"), "CartPage");
const CheckoutPage = lazyNamed(() => import("../pages/CheckoutPage"), "CheckoutPage");
const OrdersPage = lazyNamed(() => import("../pages/OrdersPage"), "OrdersPage");
const OrderDetailPage = lazyNamed(() => import("../pages/OrderDetailPage"), "OrderDetailPage");
const FavoritesPage = lazyNamed(() => import("../pages/FavoritesPage"), "FavoritesPage");
const AddressesPage = lazyNamed(() => import("../pages/AddressesPage"), "AddressesPage");
const AdminDashboardPage = lazyNamed(
  () => import("../features/admin/pages/AdminDashboardPage"),
  "AdminDashboardPage"
);
const ProfilePage = lazyNamed(
  () => import("../pages/ProfilePage"),
  "ProfilePage"
);
const AdminOrdersPage = lazyNamed(
  () => import("../features/admin/pages/AdminOrdersPage"),
  "AdminOrdersPage"
);
const AdminCategoriesPage = lazyNamed(
  () => import("../features/admin/pages/AdminCategoriesPage"),
  "AdminCategoriesPage"
);

const ADMIN_ROLES: UserRole[] = ["admin", "moderator"];

function lazyNamed(
  loader: () => Promise<Record<string, unknown>>,
  exportName: string
) {
  return lazy(async () => {
    const module = await loader();
    return { default: module[exportName] as ComponentType };
  });
}

function page(node: ReactNode) {
  return <Suspense fallback={<LoadingState />}>{node}</Suspense>;
}

function protectedPage(node: ReactNode) {
  return <RequireAuth>{page(node)}</RequireAuth>;
}

export const router = createBrowserRouter([
  {
    element: <RootProviders />,
    children: [
      {
        element: <StorefrontLayout />,
        children: [
          { index: true, element: <CatalogPage /> },
          { path: "products/:id", element: page(<ProductPage />) },
          { path: "login", element: page(<LoginPage />) },
          { path: "register", element: page(<RegisterPage />) },
          { path: "verify-email", element: page(<VerifyEmailPage />) },
          { path: "cart", element: page(<CartPage />) },
          { path: "checkout", element: protectedPage(<CheckoutPage />) },
          { path: "orders", element: protectedPage(<OrdersPage />) },
          { path: "orders/:publicId", element: protectedPage(<OrderDetailPage />) },
          { path: "favorites", element: protectedPage(<FavoritesPage />) },
          { path: "addresses", element: protectedPage(<AddressesPage />) },
          { path: "*", element: <Navigate to="/" replace /> },
        ],
      },
      {
        path: "admin",
        element: (
          <RequireRole roles={ADMIN_ROLES}>
            <AdminLayout />
          </RequireRole>
        ),
        children: [
          { index: true, element: page(<AdminDashboardPage />) },
          { path: "orders", element: page(<AdminOrdersPage />) },
          { path: "categories", element: page(<AdminCategoriesPage />) },
          { path: "profile", element: protectedPage(<ProfilePage />) },
        ],
      },
    ],
  },
]);
