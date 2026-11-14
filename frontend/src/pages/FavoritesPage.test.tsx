import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";

import { FavoritesPage } from "./FavoritesPage";
import { renderWithProviders } from "../test/render";

describe("FavoritesPage", () => {
  it("пустое избранное → EmptyState", () => {
    renderWithProviders(<FavoritesPage />);
    expect(screen.getByText("В избранном пока ничего нет"))
      .toBeInTheDocument();
  });

  it("с элементом показывает имя товара", () => {
    renderWithProviders(<FavoritesPage />, {
      favorites: {
        favorites: [
          {
            id: 1,
            product_id: 10,
            product_name: "Laptop",
            cover_url: null,
            cost: "1000.00",
            status: "available",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      },
    });
    expect(screen.getByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText("В наличии")).toBeInTheDocument();
  });
});