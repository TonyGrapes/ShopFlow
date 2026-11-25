import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CatalogPage } from "./CatalogPage";
import { renderWithProviders } from "../test/render";
import { fetchProductList } from "../api/products";
import { ApiError } from "../api/client";
import type { Paginated } from "../types/common";
import type { ProductListItem } from "../types/product";

vi.mock("../api/products", () => ({ fetchProductList: vi.fn() }));

const mList = vi.mocked(fetchProductList);

function makeProduct(
  overrides: Partial<ProductListItem> = {}
): ProductListItem {
  return {
    id: 1,
    name: "Laptop",
    cost: "1000.00",
    status: "available",
    cover_url: null,
    category: null,
    ...overrides,
  };
}

function makePage(
  items: ProductListItem[],
  total = items.length,
  page = 1
): Paginated<ProductListItem> {
  return { items, total, page, page_size: 20 };
}

beforeEach(() => {
  mList.mockReset();
});

describe("CatalogPage", () => {
  it("загружает и рендерит товары", async () => {
    mList.mockResolvedValue(makePage([makeProduct()]));
    renderWithProviders(<CatalogPage />);

    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText(/1\s*000,00\s*₽/)).toBeInTheDocument();
    expect(screen.getAllByText("В наличии").length).toBeGreaterThan(0);
    expect(mList).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 1,
        page_size: 20,
        sort_by: "id",
        sort_order: "asc",
      })
    );
  });

  it("пустой каталог → EmptyState", async () => {
    mList.mockResolvedValue(makePage([]));
    renderWithProviders(<CatalogPage />);

    expect(await screen.findByText("Товары не найдены")).toBeInTheDocument();
  });

  it("loading → LoadingState", async () => {
    let resolve!: (value: Paginated<ProductListItem>) => void;
    mList.mockReturnValue(
      new Promise<Paginated<ProductListItem>>((r) => {
        resolve = r;
      })
    );
    renderWithProviders(<CatalogPage />);

    expect(screen.getByText("Загрузка...")).toBeInTheDocument();

    await act(async () => {
      resolve(makePage([]));
    });
  });

  it("ApiError → ErrorState, retry перезапрашивает", async () => {
    const user = userEvent.setup();
    mList
      .mockRejectedValueOnce(new ApiError(500, "boom"))
      .mockResolvedValueOnce(makePage([makeProduct()]));
    renderWithProviders(<CatalogPage />);

    expect(
      await screen.findByText("Ошибка: 500: boom")
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    await waitFor(() => expect(mList).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Laptop")).toBeInTheDocument();
  });

  it("обычная Error → сообщение", async () => {
    mList.mockRejectedValue(new Error("net down"));
    renderWithProviders(<CatalogPage />);

    expect(await screen.findByText("Ошибка: net down")).toBeInTheDocument();
  });

  it("не-Error → «Неизвестная ошибка»", async () => {
    mList.mockRejectedValue("weird");
    renderWithProviders(<CatalogPage />);

    expect(
      await screen.findByText("Ошибка: Неизвестная ошибка")
    ).toBeInTheDocument();
  });

  it("фильтр по статусу → запрос с status и page=1", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([makeProduct()]));
    renderWithProviders(<CatalogPage />);
    await screen.findByText("Laptop");

    await user.selectOptions(screen.getByLabelText(/Статус:/i), "available");

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "available", page: 1 })
      )
    );
  });

  it("сортировка → запрос с sort_by/sort_order", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([makeProduct()]));
    renderWithProviders(<CatalogPage />);
    await screen.findByText("Laptop");

    await user.selectOptions(
      screen.getByLabelText(/Сортировка:/i),
      "cost:desc"
    );

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({
          sort_by: "cost",
          sort_order: "desc",
          page: 1,
        })
      )
    );
  });

  it("пагинация: переход на следующую страницу", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([makeProduct()], 45));
    renderWithProviders(<CatalogPage />);

    expect(
      await screen.findByText("Страница 1 из 3 (всего 45)")
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Следующая страница" })
    );

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 })
      )
    );
  });
});
