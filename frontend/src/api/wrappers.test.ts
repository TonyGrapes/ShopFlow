import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
import { refreshAccessToken, getAccessToken } from "./session";
import { API_BASE_URL } from "./config";

import {
  fetchAddresses,
  createAddress,
  updateAddress,
  deleteAddress,
  setDefaultAddress,
} from "./addresses";
import {
  registerUser,
  loginUser,
  logoutUser,
  fetchMe,
  refreshSession,
  resendVerification,
  verifyEmail,
  verifyEmailOnce,
  updateProfile,
  changePassword,
} from "./auth";
import {
  fetchCart,
  addCartItem,
  updateCartItem,
  removeCartItem,
  clearCart,
  applyPromo,
} from "./cart";
import { fetchCategories, fetchCategoryTree } from "./categories";
import { fetchFavorites, addFavorite, removeFavorite } from "./favorites";
import { createOrder, listOrders, fetchOrder, payOrder } from "./orders";
import {
  fetchProductList,
  fetchProductPriceRange,
  fetchProduct,
} from "./products";
import {
  listAdminOrders,
  updateAdminOrderStatus,
  createCategory,
  updateCategory,
  deleteCategory,
  listAdminProducts,
  createAdminProduct,
  updateAdminProduct,
  deleteAdminProduct,
  listAdminUsers,
  updateUserRole,
  updateUserStatus,
  fetchAdminDashboard,
  fetchAdminDashboardSeries,
  downloadDashboardCsv,
} from "./admin";

vi.mock("./client", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));

vi.mock("./session", () => ({
  refreshAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
}));

type AnyMock = ReturnType<typeof vi.fn>;

const mGet = apiGet as unknown as AnyMock;
const mPost = apiPost as unknown as AnyMock;
const mPatch = apiPatch as unknown as AnyMock;
const mDelete = apiDelete as unknown as AnyMock;
const mRefresh = refreshAccessToken as unknown as AnyMock;
const mToken = getAccessToken as unknown as AnyMock;

/** Фикстура-«что угодно»: значения тел нам не важны, важна передача ссылки. */
const payload = { dummy: 1 } as never;

beforeEach(() => {
  [mGet, mPost, mPatch, mDelete, mRefresh, mToken].forEach((m) => m.mockReset());
  mGet.mockResolvedValue(undefined);
  mPost.mockResolvedValue(undefined);
  mPatch.mockResolvedValue(undefined);
  mDelete.mockResolvedValue(undefined);
  mToken.mockReturnValue(null);
});

describe("addresses", () => {
  it("fetchAddresses → GET /api/v1/addresses", async () => {
    await fetchAddresses();
    expect(mGet).toHaveBeenCalledWith("/api/v1/addresses");
  });

  it("createAddress → POST + body", async () => {
    await createAddress(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/addresses", payload);
  });

  it("updateAddress → PATCH /{id} + body", async () => {
    await updateAddress(5, payload);
    expect(mPatch).toHaveBeenCalledWith("/api/v1/addresses/5", payload);
  });

  it("deleteAddress → DELETE /{id}", async () => {
    await deleteAddress(5);
    expect(mDelete).toHaveBeenCalledWith("/api/v1/addresses/5");
  });

  it("setDefaultAddress → POST /{id}/set-default", async () => {
    await setDefaultAddress(5);
    expect(mPost).toHaveBeenCalledWith("/api/v1/addresses/5/set-default");
  });
});

describe("auth", () => {
  it("registerUser → POST auth:false skipAuthRefresh", async () => {
    await registerUser(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/auth/register", payload, {
      auth: false,
      skipAuthRefresh: true,
    });
  });

  it("loginUser → POST auth:false skipAuthRefresh", async () => {
    await loginUser(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/auth/login", payload, {
      auth: false,
      skipAuthRefresh: true,
    });
  });

  it("logoutUser → POST без тела, auth:false", async () => {
    await logoutUser();
    expect(mPost).toHaveBeenCalledWith("/api/v1/auth/logout", undefined, {
      auth: false,
      skipAuthRefresh: true,
    });
  });

  it("fetchMe → GET /auth/me", async () => {
    await fetchMe();
    expect(mGet).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("refreshSession → refreshAccessToken", async () => {
    mRefresh.mockResolvedValue(null);
    await refreshSession();
    expect(mRefresh).toHaveBeenCalledTimes(1);
  });

  it("resendVerification → POST auth:false", async () => {
    await resendVerification(payload);
    expect(mPost).toHaveBeenCalledWith(
      "/api/v1/auth/resend-verification",
      payload,
      { auth: false, skipAuthRefresh: true }
    );
  });

  it("verifyEmail → GET с query token", async () => {
    await verifyEmail("tok");
    expect(mGet).toHaveBeenCalledWith("/api/v1/auth/verify-email", {
      token: "tok",
    });
  });

  it("verifyEmailOnce кэширует промис по токену", async () => {
    const p1 = verifyEmailOnce("once-1");
    const p2 = verifyEmailOnce("once-1");

    expect(mGet).toHaveBeenCalledTimes(1);
    expect(p2).toBe(p1);

    await p1;
    verifyEmailOnce("once-2");
    expect(mGet).toHaveBeenCalledTimes(2);
  });

  it("updateProfile → PATCH /auth/me", async () => {
    await updateProfile(payload);
    expect(mPatch).toHaveBeenCalledWith("/api/v1/auth/me", payload);
  });

  it("changePassword → POST /auth/change-password", async () => {
    await changePassword(payload);
    expect(mPost).toHaveBeenCalledWith(
      "/api/v1/auth/change-password",
      payload
    );
  });
});

describe("cart", () => {
  it("fetchCart → GET /cart", async () => {
    await fetchCart();
    expect(mGet).toHaveBeenCalledWith("/api/v1/cart");
  });

  it("addCartItem → POST /cart/items", async () => {
    await addCartItem(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/cart/items", payload);
  });

  it("updateCartItem → PATCH /cart/items/{productId}", async () => {
    await updateCartItem(3, payload);
    expect(mPatch).toHaveBeenCalledWith("/api/v1/cart/items/3", payload);
  });

  it("removeCartItem → DELETE /cart/items/{productId}", async () => {
    await removeCartItem(3);
    expect(mDelete).toHaveBeenCalledWith("/api/v1/cart/items/3");
  });

  it("clearCart → DELETE /cart", async () => {
    await clearCart();
    expect(mDelete).toHaveBeenCalledWith("/api/v1/cart");
  });

  it("applyPromo → POST /cart/apply-promo", async () => {
    await applyPromo(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/cart/apply-promo", payload);
  });
});

describe("categories", () => {
  it("fetchCategories → GET /categories", async () => {
    await fetchCategories();
    expect(mGet).toHaveBeenCalledWith("/api/v1/categories");
  });

  it("fetchCategoryTree → GET /categories/tree", async () => {
    await fetchCategoryTree();
    expect(mGet).toHaveBeenCalledWith("/api/v1/categories/tree");
  });
});

describe("favorites", () => {
  it("fetchFavorites → GET /favorites", async () => {
    await fetchFavorites();
    expect(mGet).toHaveBeenCalledWith("/api/v1/favorites");
  });

  it("addFavorite → POST /favorites", async () => {
    await addFavorite(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/favorites", payload);
  });

  it("removeFavorite → DELETE /favorites/{productId}", async () => {
    await removeFavorite(9);
    expect(mDelete).toHaveBeenCalledWith("/api/v1/favorites/9");
  });
});

describe("orders", () => {
  it("createOrder с Idempotency-Key", async () => {
    await createOrder(payload, "key-1");
    expect(mPost).toHaveBeenCalledWith("/api/v1/orders", payload, {
      headers: { "Idempotency-Key": "key-1" },
    });
  });

  it("createOrder без ключа → headers: undefined", async () => {
    await createOrder(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/orders", payload, {
      headers: undefined,
    });
  });

  it("listOrders → GET с параметрами (по умолчанию {})", async () => {
    await listOrders();
    expect(mGet).toHaveBeenCalledWith("/api/v1/orders", {});
  });

  it("listOrders пробрасывает параметры", async () => {
    await listOrders({ page: 2 });
    expect(mGet).toHaveBeenCalledWith("/api/v1/orders", { page: 2 });
  });

  it("fetchOrder → GET /orders/{publicId}", async () => {
    await fetchOrder("pub-1");
    expect(mGet).toHaveBeenCalledWith("/api/v1/orders/pub-1");
  });

  it("payOrder → POST /orders/{publicId}/pay", async () => {
    await payOrder("pub-1", payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/orders/pub-1/pay", payload);
  });
});

describe("products", () => {
  it("fetchProductList → GET с параметрами", async () => {
    await fetchProductList({ q: "x" });
    expect(mGet).toHaveBeenCalledWith("/api/v1/products", { q: "x" });
  });

  it("fetchProductList по умолчанию {}", async () => {
    await fetchProductList();
    expect(mGet).toHaveBeenCalledWith("/api/v1/products", {});
  });

  it("fetchProductPriceRange → GET /products/price-range", async () => {
    await fetchProductPriceRange({ q: "x" });
    expect(mGet).toHaveBeenCalledWith("/api/v1/products/price-range", {
      q: "x",
    });
  });

  it("fetchProduct → GET /products/{id}", async () => {
    await fetchProduct(7);
    expect(mGet).toHaveBeenCalledWith("/api/v1/products/7");
  });
});

describe("admin", () => {
  it("listAdminOrders → GET /admin/orders", async () => {
    await listAdminOrders();
    expect(mGet).toHaveBeenCalledWith("/api/v1/admin/orders", {});
  });

  it("updateAdminOrderStatus → PATCH /admin/orders/{id}/status", async () => {
    await updateAdminOrderStatus("pub-1", "paid" as never);
    expect(mPatch).toHaveBeenCalledWith("/api/v1/admin/orders/pub-1/status", {
      status: "paid",
    });
  });

  it("createCategory → POST /admin/categories", async () => {
    await createCategory(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/admin/categories", payload);
  });

  it("updateCategory → PATCH /admin/categories/{id}", async () => {
    await updateCategory(4, payload);
    expect(mPatch).toHaveBeenCalledWith("/api/v1/admin/categories/4", payload);
  });

  it("deleteCategory → DELETE /admin/categories/{id}", async () => {
    await deleteCategory(4);
    expect(mDelete).toHaveBeenCalledWith("/api/v1/admin/categories/4");
  });

  it("listAdminProducts → GET /admin/products", async () => {
    await listAdminProducts();
    expect(mGet).toHaveBeenCalledWith("/api/v1/admin/products", {});
  });

  it("createAdminProduct → POST /admin/products", async () => {
    await createAdminProduct(payload);
    expect(mPost).toHaveBeenCalledWith("/api/v1/admin/products", payload);
  });

  it("updateAdminProduct → PATCH /admin/products/{id}", async () => {
    await updateAdminProduct(6, payload);
    expect(mPatch).toHaveBeenCalledWith("/api/v1/admin/products/6", payload);
  });

  it("deleteAdminProduct → DELETE /admin/products/{id}", async () => {
    await deleteAdminProduct(6);
    expect(mDelete).toHaveBeenCalledWith("/api/v1/admin/products/6");
  });

  it("listAdminUsers → GET /admin/users", async () => {
    await listAdminUsers();
    expect(mGet).toHaveBeenCalledWith("/api/v1/admin/users", {});
  });

  it("updateUserRole → PATCH /admin/users/{id}/role", async () => {
    await updateUserRole("pub-1", payload);
    expect(mPatch).toHaveBeenCalledWith(
      "/api/v1/admin/users/pub-1/role",
      payload
    );
  });

  it("updateUserStatus → PATCH /admin/users/{id}/status", async () => {
    await updateUserStatus("pub-1", payload);
    expect(mPatch).toHaveBeenCalledWith(
      "/api/v1/admin/users/pub-1/status",
      payload
    );
  });

  it("fetchAdminDashboard → GET с period_days (по умолчанию 7)", async () => {
    await fetchAdminDashboard();
    expect(mGet).toHaveBeenCalledWith("/api/v1/admin/dashboard", {
      period_days: 7,
    });
  });

  it("fetchAdminDashboard пробрасывает period_days", async () => {
    await fetchAdminDashboard(30);
    expect(mGet).toHaveBeenCalledWith("/api/v1/admin/dashboard", {
      period_days: 30,
    });
  });

  it("fetchAdminDashboardSeries → GET /admin/dashboard/series", async () => {
    await fetchAdminDashboardSeries(14);
    expect(mGet).toHaveBeenCalledWith("/api/v1/admin/dashboard/series", {
      period_days: 14,
    });
  });
});

describe("downloadDashboardCsv", () => {
  let fetchMock: AnyMock;

  // URL.createObjectURL/revokeObjectURL уже замоканы в src/test/setup.ts
  // (jsdom их не реализует). Берём эти же vi.fn, чтобы проверять вызовы.
  const createObjectURL = URL.createObjectURL as unknown as AnyMock;
  const revokeObjectURL = URL.revokeObjectURL as unknown as AnyMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubAnchor() {
    const anchor = { href: "", download: "", click: vi.fn() };
    const original = document.createElement.bind(document);
    const spy = vi
      .spyOn(document, "createElement")
      .mockImplementation(
        ((tagName: string) =>
          tagName === "a"
            ? (anchor as unknown as HTMLElement)
            : original(tagName)) as typeof document.createElement
      );
    return { anchor, restore: () => spy.mockRestore() };
  }

  it("скачивает blob с Bearer и именем файла", async () => {
    mToken.mockReturnValue("tok");
    const blob = new Blob(["a,b"], { type: "text/csv" });
    fetchMock.mockResolvedValue({ ok: true, blob: async () => blob });
    const { anchor, restore } = stubAnchor();

    await downloadDashboardCsv(30);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${API_BASE_URL}/api/v1/admin/dashboard/export.csv?period_days=30`
    );
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok"
    );
    expect(init.credentials).toBe("include");
    expect(anchor.href).toBe("blob:mock");
    expect(anchor.download).toBe("shopflow-dashboard-30d.csv");
    expect(anchor.click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");

    restore();
  });

  it("без токена не ставит Authorization, имя файла по умолчанию 7d", async () => {
    mToken.mockReturnValue(null);
    fetchMock.mockResolvedValue({ ok: true, blob: async () => new Blob([]) });
    const { anchor, restore } = stubAnchor();

    await downloadDashboardCsv();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(
      (init.headers as Record<string, string>).Authorization
    ).toBeUndefined();
    expect(anchor.download).toBe("shopflow-dashboard-7d.csv");

    restore();
  });

  it("не-ok ответ → Error('HTTP <status>')", async () => {
    mToken.mockReturnValue(null);
    fetchMock.mockResolvedValue({ ok: false, status: 500 });

    await expect(downloadDashboardCsv()).rejects.toThrow("HTTP 500");
  });
});
