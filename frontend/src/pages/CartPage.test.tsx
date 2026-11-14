import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";

import { CartPage } from "./CartPage";
import { renderWithProviders } from "../test/render";
import type { CartResponse } from "../types/cart";

describe("CartPage", () => {
  it("пустая корзина → EmptyState «Корзина пуста»", () => {
    renderWithProviders(<CartPage />);
    expect(screen.getByText("Корзина пуста")).toBeInTheDocument();
  });

  it("с позицией показывает имя товара и итог", () => {
    const cart: CartResponse = {
      items: [
        {
          product_id: 1,
          name: "Laptop",
          cover_url: null,
          quantity: 2,
          snapshot_cost: "1000.00",
          current_cost: "1000.00",
          status: "available",
          is_available: true,
        },
      ],
      total_items: 2,
      total_cost: "2000.00",
      hidden_items_count: 0,
    };
    renderWithProviders(<CartPage />, {
      cart: { cart, totalItems: 2 },
    });
        expect(screen.getByText("Laptop")).toBeInTheDocument();
    // "2 000,00 ₽" встречается дважды: "Товары (2)" и "К оплате".
    // Проверяем, что итог действительно в строке «К оплате» (--total),
    // а не просто что число где-то есть.
    const totalRow = screen
      .getByText(/К оплате/i)
      .closest(".cart-summary__row--total");
    expect(totalRow).toHaveTextContent(/2\s*000,00\s*₽/);
  });
});