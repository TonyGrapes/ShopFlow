import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { FavoritesPage } from "./FavoritesPage";
import { renderWithProviders } from "../test/render";
import type { FavoriteResponse } from "../types/favorite";

function makeFavorite(
  overrides: Partial<FavoriteResponse> = {}
): FavoriteResponse {
  return {
    id: 1,
    product_id: 10,
    product_name: "Laptop",
    cover_url: null,
    cost: "1000.00",
    status: "available",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("FavoritesPage", () => {
  it("пустое избранное → EmptyState", () => {
    renderWithProviders(<FavoritesPage />);
    expect(
      screen.getByText("В избранном пока ничего нет")
    ).toBeInTheDocument();
  });

  it("с элементом показывает имя товара", () => {
    renderWithProviders(<FavoritesPage />, {
      favorites: { favorites: [makeFavorite()] },
    });
    expect(screen.getByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText("В наличии")).toBeInTheDocument();
  });

  it("loading без элементов → LoadingState", () => {
    renderWithProviders(<FavoritesPage />, {
      favorites: { loading: true },
    });
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("error → ErrorState, retry вызывает refreshFavorites", async () => {
    const user = userEvent.setup();
    const refreshFavorites = vi.fn().mockRejectedValue(new Error("ignored"));
    renderWithProviders(<FavoritesPage />, {
      favorites: { error: "boom", refreshFavorites },
    });

    expect(screen.getByText(/Ошибка: boom/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    await waitFor(() => expect(refreshFavorites).toHaveBeenCalledTimes(1));
  });

  it("обложка, статусы и pending-состояние", () => {
    renderWithProviders(<FavoritesPage />, {
      favorites: {
        favorites: [
          makeFavorite({
            id: 1,
            product_id: 10,
            product_name: "Laptop",
            cover_url: "https://cdn.example/laptop.png",
          }),
          makeFavorite({
            id: 2,
            product_id: 11,
            product_name: "Phone",
            status: "out_of_stock",
          }),
          makeFavorite({
            id: 3,
            product_id: 12,
            product_name: "TV",
            status: "discontinued",
          }),
          makeFavorite({
            id: 4,
            product_id: 13,
            product_name: "Mystery",
            status: "archived",
          }),
        ],
        isPending: (productId) => productId === 11,
      },
    });

    expect(screen.getByRole("img", { name: "Laptop" })).toHaveAttribute(
      "src",
      "https://cdn.example/laptop.png"
    );
    expect(screen.getByText("Нет в наличии")).toBeInTheDocument();
    expect(screen.getByText("Снят с производства")).toBeInTheDocument();
    expect(screen.getByText("archived")).toBeInTheDocument();

    const pendingCard = screen.getByText("Phone").closest(".favorite-card");
    expect(pendingCard).not.toBeNull();
    const pendingButton = within(pendingCard as HTMLElement).getByRole(
      "button"
    );
    expect(pendingButton).toHaveTextContent("...");
    expect(pendingButton).toBeDisabled();
  });

  it("удаление → toggleFavorite + toast info", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const toggleFavorite = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<FavoritesPage />, {
      favorites: { favorites: [makeFavorite()], toggleFavorite },
      toast: { showToast },
    });

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(toggleFavorite).toHaveBeenCalledWith(10));
    expect(showToast).toHaveBeenCalledWith(
      "Товар удалён из избранного",
      "info"
    );
  });

  it("ошибка удаления → toast error", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    const toggleFavorite = vi.fn().mockRejectedValue(new Error("fav fail"));
    renderWithProviders(<FavoritesPage />, {
      favorites: { favorites: [makeFavorite()], toggleFavorite },
      toast: { showToast },
    });

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("fav fail", "error")
    );
  });
});
