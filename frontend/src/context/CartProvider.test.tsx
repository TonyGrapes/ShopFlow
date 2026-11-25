import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CartProvider } from "./CartProvider";
import { useCart } from "../hooks/useCart";
import type { CartContextValue } from "./cartContext";
import {
  addCartItem,
  applyPromo,
  clearCart,
  fetchCart,
  removeCartItem,
  updateCartItem,
} from "../api/cart";
import type { CartResponse } from "../types/cart";
import type { PromoCodePreviewResponse } from "../types/promo";
import type { UserResponse } from "../types/auth";

const { authState } = vi.hoisted(() => ({
  authState: { user: null as UserResponse | null, loading: false },
}));

vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));

vi.mock("../api/cart", () => ({
  fetchCart: vi.fn(),
  addCartItem: vi.fn(),
  updateCartItem: vi.fn(),
  removeCartItem: vi.fn(),
  clearCart: vi.fn(),
  applyPromo: vi.fn(),
}));

const mFetch = vi.mocked(fetchCart);
const mAdd = vi.mocked(addCartItem);
const mUpdate = vi.mocked(updateCartItem);
const mRemove = vi.mocked(removeCartItem);
const mClear = vi.mocked(clearCart);
const mPromo = vi.mocked(applyPromo);

const USER: UserResponse = {
  public_id: "u-1",
  email: "user@example.com",
  first_name: "Ann",
  last_name: "Lee",
  phone_number: "+10000000000",
  role: "customer",
  status: "active",
  is_email_verified: true,
  created_at: "2026-01-01T00:00:00Z",
};

const CART: CartResponse = {
  items: [],
  total_items: 2,
  total_cost: "100.00",
  hidden_items_count: 0,
};

const CART2: CartResponse = {
  items: [],
  total_items: 5,
  total_cost: "250.00",
  hidden_items_count: 1,
};

const PROMO: PromoCodePreviewResponse = {
  code: "SUMMER10",
  discount_type: "percentage",
  discount_value: "10.00",
  subtotal: "100.00",
  discount_amount: "10.00",
  final_total: "90.00",
};

let ctx: CartContextValue;

function Capture() {
  ctx = useCart();
  return null;
}

function renderProvider() {
  return render(
    <CartProvider>
      <Capture />
    </CartProvider>
  );
}

beforeEach(() => {
  [mFetch, mAdd, mUpdate, mRemove, mClear, mPromo].forEach((m) =>
    m.mockReset()
  );
  mFetch.mockResolvedValue(CART);
  authState.user = null;
  authState.loading = false;
});

afterEach(() => {
  cleanup();
});

describe("initial load", () => {
  it("authLoading=true → не грузит корзину", () => {
    authState.loading = true;
    renderProvider();

    expect(mFetch).not.toHaveBeenCalled();
    expect(ctx.loading).toBe(false);
  });

  it("гость: загружает корзину, totalItems из cart", async () => {
    renderProvider();

    await waitFor(() => expect(ctx.loading).toBe(false));

    expect(mFetch).toHaveBeenCalledTimes(1);
    expect(ctx.cart).toEqual(CART);
    expect(ctx.totalItems).toBe(2);
    expect(ctx.error).toBeNull();
  });

  it("ошибка загрузки → error, cart=null", async () => {
    mFetch.mockRejectedValue(new Error("boom"));
    renderProvider();

    await waitFor(() => expect(ctx.error).toBe("boom"));

    expect(ctx.loading).toBe(false);
    expect(ctx.cart).toBeNull();
    expect(ctx.totalItems).toBe(0);
  });

  it("перезагрузка при смене пользователя (public_id)", async () => {
    const { rerender } = renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));
    expect(mFetch).toHaveBeenCalledTimes(1);

    authState.user = USER;
    rerender(
      <CartProvider>
        <Capture />
      </CartProvider>
    );

    await waitFor(() => expect(mFetch).toHaveBeenCalledTimes(2));
  });

  it("отмена до завершения fetch не обновляет состояние", async () => {
    let resolveFetch!: (value: CartResponse) => void;
    mFetch.mockReturnValue(
      new Promise<CartResponse>((resolve) => {
        resolveFetch = resolve;
      })
    );

    const { unmount } = renderProvider();
    unmount();

    await act(async () => {
      resolveFetch(CART);
    });

    expect(ctx.cart).toBeNull();
  });
});

describe("refreshCart", () => {
  it("успех: обновляет cart", async () => {
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    mFetch.mockResolvedValueOnce(CART2);
    await act(async () => {
      await ctx.refreshCart();
    });

    expect(ctx.cart).toEqual(CART2);
    expect(ctx.loading).toBe(false);
  });

  it("ошибка: ставит error и пробрасывает", async () => {
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));

    mFetch.mockRejectedValueOnce(new Error("refresh failed"));
    await act(async () => {
      await expect(ctx.refreshCart()).rejects.toThrow("refresh failed");
    });

    expect(ctx.error).toBe("refresh failed");
    expect(ctx.loading).toBe(false);
  });
});

describe("mutations", () => {
  beforeEach(async () => {
    renderProvider();
    await waitFor(() => expect(ctx.loading).toBe(false));
  });

  it("addItem: default quantity=1, обновляет cart", async () => {
    mAdd.mockResolvedValue(CART2);

    let result: CartResponse | undefined;
    await act(async () => {
      result = await ctx.addItem(7);
    });

    expect(mAdd).toHaveBeenCalledWith({ product_id: 7, quantity: 1 });
    expect(result).toEqual(CART2);
    expect(ctx.cart).toEqual(CART2);
  });

  it("addItem: явный quantity", async () => {
    mAdd.mockResolvedValue(CART2);

    await act(async () => {
      await ctx.addItem(7, 3);
    });

    expect(mAdd).toHaveBeenCalledWith({ product_id: 7, quantity: 3 });
  });

  it("updateItem: PATCH {quantity}", async () => {
    mUpdate.mockResolvedValue(CART2);

    await act(async () => {
      await ctx.updateItem(7, 4);
    });

    expect(mUpdate).toHaveBeenCalledWith(7, { quantity: 4 });
    expect(ctx.cart).toEqual(CART2);
  });

  it("removeItem: удаляет и обновляет cart", async () => {
    mRemove.mockResolvedValue(CART2);

    await act(async () => {
      await ctx.removeItem(7);
    });

    expect(mRemove).toHaveBeenCalledWith(7);
    expect(ctx.cart).toEqual(CART2);
  });

  it("clearCart: очищает, затем перезагружает", async () => {
    mClear.mockResolvedValue(undefined);
    mFetch.mockResolvedValueOnce(CART2);

    await act(async () => {
      await ctx.clearCart();
    });

    expect(mClear).toHaveBeenCalledTimes(1);
    expect(ctx.cart).toEqual(CART2);
  });

  it("applyPromo: прокидывает код и возвращает превью", async () => {
    mPromo.mockResolvedValue(PROMO);

    let result: PromoCodePreviewResponse | undefined;
    await act(async () => {
      result = await ctx.applyPromo("SUMMER10");
    });

    expect(mPromo).toHaveBeenCalledWith({ code: "SUMMER10" });
    expect(result).toEqual(PROMO);
  });
});

describe("useCart", () => {
  it("вне CartProvider бросает", () => {
    function Orphan() {
      useCart();
      return null;
    }
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Orphan />)).toThrow(
      "useCart must be used within CartProvider"
    );

    errSpy.mockRestore();
  });
});
