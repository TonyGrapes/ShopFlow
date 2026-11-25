import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CartPage } from "./CartPage";
import { renderWithProviders } from "../test/render";
import type { CartItemResponse, CartResponse } from "../types/cart";
import type { PromoCodePreviewResponse } from "../types/promo";

function makeItem(overrides: Partial<CartItemResponse> = {}): CartItemResponse {
  return {
    product_id: 1,
    name: "Laptop",
    cover_url: null,
    quantity: 2,
    snapshot_cost: "1000.00",
    current_cost: "1000.00",
    status: "available",
    is_available: true,
    ...overrides,
  };
}

function makeCart(overrides: Partial<CartResponse> = {}): CartResponse {
  const items = overrides.items ?? [makeItem()];
  return {
    items,
    total_items: items.reduce((sum, item) => sum + item.quantity, 0),
    total_cost: "2000.00",
    hidden_items_count: 0,
    ...overrides,
  };
}

const PROMO: PromoCodePreviewResponse = {
  code: "SALE10",
  discount_type: "percentage",
  discount_value: "10.00",
  subtotal: "2000.00",
  discount_amount: "200.00",
  final_total: "1800.00",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CartPage", () => {
  it("пустая корзина → EmptyState «Корзина пуста»", () => {
    renderWithProviders(<CartPage />);
    expect(screen.getByText("Корзина пуста")).toBeInTheDocument();
  });

  it("с позицией показывает имя товара и итог", () => {
    const cart = makeCart();
    renderWithProviders(<CartPage />, {
      cart: { cart, totalItems: 2 },
    });
    expect(screen.getByText("Laptop")).toBeInTheDocument();
    const totalRow = screen
      .getByText(/К оплате/i)
      .closest(".cart-summary__row--total");
    expect(totalRow).toHaveTextContent(/2\s*000,00\s*₽/);
  });

  it("loading без cart → LoadingState", () => {
    renderWithProviders(<CartPage />, {
      cart: { cart: null, loading: true },
    });
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("cart === null без loading → LoadingState", () => {
    renderWithProviders(<CartPage />, {
      cart: { cart: null, loading: false },
    });
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("error без cart → ErrorState, retry вызывает refreshCart", async () => {
    const user = userEvent.setup();
    const refreshCart = vi.fn().mockRejectedValue(new Error("ignored"));
    renderWithProviders(<CartPage />, {
      cart: { cart: null, error: "boom", refreshCart },
    });

    expect(screen.getByText(/Ошибка: boom/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    await waitFor(() => expect(refreshCart).toHaveBeenCalledTimes(1));
  });

  it("скрытые товары: заметка и отключённая очистка", () => {
    renderWithProviders(<CartPage />, {
      cart: {
        cart: makeCart({
          items: [],
          total_items: 0,
          total_cost: "0.00",
          hidden_items_count: 3,
        }),
      },
    });

    expect(
      screen.getByText(/Скрыто товаров, которых больше нет в каталоге: 3/)
    ).toBeInTheDocument();
    expect(
      screen.getByText("Нет доступных товаров для оформления заказа.")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Очистить корзину" })
    ).toBeDisabled();
  });

  it("доступная позиция: обложка, статус и предупреждение о цене", () => {
    renderWithProviders(<CartPage />, {
      cart: {
        cart: makeCart({
          items: [
            makeItem({
              cover_url: "https://cdn.example/laptop.png",
              snapshot_cost: "1000.00",
              current_cost: "1200.00",
            }),
          ],
        }),
      },
    });

    expect(screen.getByRole("img", { name: "Laptop" })).toHaveAttribute(
      "src",
      "https://cdn.example/laptop.png"
    );
    expect(screen.getByText("В наличии")).toBeInTheDocument();
    expect(screen.getByText(/Цена изменилась/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Перейти к оформлению" })
    ).toBeInTheDocument();
  });

  it("недоступные позиции → отдельная секция", () => {
    renderWithProviders(<CartPage />, {
      cart: {
        cart: makeCart({
          items: [
            makeItem({
              product_id: 5,
              name: "Old phone",
              status: "out_of_stock",
              is_available: false,
            }),
          ],
        }),
      },
    });

    expect(screen.getByText("Недоступны для заказа")).toBeInTheDocument();
    expect(screen.getByText("Нет в наличии")).toBeInTheDocument();
    expect(
      screen.getByText("Нет доступных товаров для оформления заказа.")
    ).toBeInTheDocument();
  });

  it("изменение количества вызывает updateItem", async () => {
    const user = userEvent.setup();
    const updateItem = vi.fn().mockResolvedValue(makeCart());
    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), updateItem },
    });

    await user.click(
      screen.getByRole("button", { name: "Увеличить количество" })
    );

    await waitFor(() => expect(updateItem).toHaveBeenCalledWith(1, 3));
  });

  it("кнопка «−» заблокирована при quantity=1", () => {
    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart({ items: [makeItem({ quantity: 1 })] }) },
    });

    expect(
      screen.getByRole("button", { name: "Уменьшить количество" })
    ).toBeDisabled();
  });

  it("ошибка updateItem → toast error", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const updateItem = vi.fn().mockRejectedValue(new Error("upd fail"));
    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), updateItem },
      toast: { showToast },
    });

    await user.click(
      screen.getByRole("button", { name: "Увеличить количество" })
    );

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("upd fail", "error")
    );
  });

  it("удаление позиции → removeItem + toast info", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const removeItem = vi.fn().mockResolvedValue(makeCart());
    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), removeItem },
      toast: { showToast },
    });

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(removeItem).toHaveBeenCalledWith(1));
    expect(showToast).toHaveBeenCalledWith("Товар удалён из корзины", "info");
  });

  it("ошибка removeItem → toast error", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const removeItem = vi.fn().mockRejectedValue(new Error("rm fail"));
    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), removeItem },
      toast: { showToast },
    });

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("rm fail", "error")
    );
  });

  it("очистка: подтверждение → clearCart + toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const clearCart = vi.fn().mockResolvedValue(undefined);
    const confirmMock = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirmMock);

    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), clearCart },
      toast: { showToast },
    });

    await user.click(screen.getByRole("button", { name: "Очистить корзину" }));

    expect(confirmMock).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(clearCart).toHaveBeenCalledTimes(1));
    expect(showToast).toHaveBeenCalledWith("Корзина очищена", "info");
  });

  it("очистка отменена → clearCart не вызывается", async () => {
    const user = userEvent.setup();
    const clearCart = vi.fn();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));

    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), clearCart },
    });

    await user.click(screen.getByRole("button", { name: "Очистить корзину" }));

    expect(clearCart).not.toHaveBeenCalled();
  });

  it("ошибка очистки → toast error", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const clearCart = vi.fn().mockRejectedValue(new Error("clear fail"));
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));

    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), clearCart },
      toast: { showToast },
    });

    await user.click(screen.getByRole("button", { name: "Очистить корзину" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("clear fail", "error")
    );
  });

  it("промокод: пустой ввод → ошибка", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CartPage />, { cart: { cart: makeCart() } });

    await user.click(screen.getByRole("button", { name: "Применить" }));

    expect(screen.getByText("Введите промокод")).toBeInTheDocument();
  });

  it("промокод: успешное применение показывает превью", async () => {
    const user = userEvent.setup();
    const applyPromo = vi.fn().mockResolvedValue(PROMO);
    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), applyPromo },
    });

    await user.type(screen.getByLabelText(/Промокод/i), "  SALE10  ");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    await waitFor(() => expect(applyPromo).toHaveBeenCalledWith("SALE10"));
    expect(await screen.findByText("Скидка")).toBeInTheDocument();
    const totalRow = screen
      .getByText(/К оплате/i)
      .closest(".cart-summary__row--total");
    expect(totalRow).toHaveTextContent(/1\s*800,00\s*₽/);
  });

  it("промокод: ошибка применения показывается", async () => {
    const user = userEvent.setup();
    const applyPromo = vi.fn().mockRejectedValue(new Error("promo fail"));
    renderWithProviders(<CartPage />, {
      cart: { cart: makeCart(), applyPromo },
    });

    await user.type(screen.getByLabelText(/Промокод/i), "BAD");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    expect(await screen.findByText("promo fail")).toBeInTheDocument();
  });

});
