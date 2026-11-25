import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CatalogPage } from "./CatalogPage";
import { renderWithProviders } from "../../test/render";
import { fetchCategories } from "../../api/categories";
import {
  fetchProductList,
  fetchProductPriceRange,
} from "../../api/products";
import type { Category } from "../../types/category";
import type { Paginated } from "../../types/common";
import type { ProductListItem } from "../../types/product";

vi.mock("../../api/categories", () => ({ fetchCategories: vi.fn() }));
vi.mock("../../api/products", () => ({
  fetchProductList: vi.fn(),
  fetchProductPriceRange: vi.fn(),
}));

const mCategories = vi.mocked(fetchCategories);
const mList = vi.mocked(fetchProductList);
const mRange = vi.mocked(fetchProductPriceRange);

const RECENT_KEY = "shopflow.recently-viewed";

const CATEGORY: Category = {
  id: 1,
  category_name: "Laptops",
  path: "1",
  parent_id: null,
};

const PRODUCT: ProductListItem = {
  id: 1,
  name: "Laptop",
  cost: "1000.00",
  status: "available",
  cover_url: null,
  category: { id: 1, category_name: "Laptops" },
};

const PRODUCT2: ProductListItem = {
  id: 2,
  name: "Mouse",
  cost: "50.00",
  status: "out_of_stock",
  cover_url: null,
  category: null,
};

function makePage(
  items: ProductListItem[],
  total = items.length,
  page = 1
): Paginated<ProductListItem> {
  return { items, total, page, page_size: 12 };
}

beforeEach(() => {
  mCategories.mockReset();
  mList.mockReset();
  mRange.mockReset();
  mCategories.mockResolvedValue([]);
  mList.mockResolvedValue(makePage([]));
  mRange.mockResolvedValue({ min_cost: "100", max_cost: "2000" });
  localStorage.clear();
});

function renderPage(route = "/") {
  return renderWithProviders(<CatalogPage />, { route });
}

describe("CatalogPage (features/catalog)", () => {
  it("загружает и рендерит товары со счётчиками", async () => {
    mCategories.mockResolvedValue([CATEGORY]);
    mList.mockResolvedValue(makePage([PRODUCT, PRODUCT2], 2));
    renderPage();

    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText(/Более 2 товара в наличии/)).toBeInTheDocument();
    expect(screen.getByText(/2 товара · показано 2/)).toBeInTheDocument();
    expect(screen.getByText(/1\s*000\s*₽/)).toBeInTheDocument();
    expect(screen.getAllByText("Нет в наличии").length).toBeGreaterThan(0);
    expect(mList).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 1,
        page_size: 12,
        sort_by: "created_at",
        sort_order: "desc",
      })
    );
  });

  it("loading → hero/счётчик и skeleton, затем данные", async () => {
    let resolveList!: (value: Paginated<ProductListItem>) => void;
    mList.mockReturnValue(
      new Promise<Paginated<ProductListItem>>((resolve) => {
        resolveList = resolve;
      })
    );
    renderPage();

    expect(screen.getByText("Загружаем каталог…")).toBeInTheDocument();
    expect(screen.getByText("Загрузка товаров…")).toBeInTheDocument();

    await act(async () => {
      resolveList(makePage([PRODUCT], 1));
    });

    expect(await screen.findByText("Laptop")).toBeInTheDocument();
  });

  it("пустой результат → EmptyState и сброс", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([], 0));
    renderPage();

    const heading = await screen.findByRole("heading", {
      name: "Ничего не найдено",
    });
    expect(
      screen.getByText(/По выбранным фильтрам товаров нет/)
    ).toBeInTheDocument();

    const state = heading.parentElement as HTMLElement;
    await user.click(
      within(state).getByRole("button", { name: "Сбросить фильтры" })
    );
  });

  it("пустой результат с query → текст про запрос", async () => {
    mList.mockResolvedValue(makePage([], 0));
    renderPage("/?q=phone");

    expect(
      await screen.findByText(/По запросу «phone» товаров нет/)
    ).toBeInTheDocument();
    expect(mList).toHaveBeenCalledWith(
      expect.objectContaining({ q: "phone" })
    );
  });

  it("ошибка → ErrorState и повторная загрузка", async () => {
    const user = userEvent.setup();
    mList.mockRejectedValue(new Error("boom"));
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Что-то пошло не так" })
    ).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Повторить загрузку" })
    );

    await waitFor(() =>
      expect(mList.mock.calls.length).toBeGreaterThanOrEqual(2)
    );
  });

  it("пагинация: переход по страницам", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([PRODUCT], 25));
    renderPage();

    expect(
      await screen.findByRole("navigation", { name: "Пагинация" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Страница 1" })
    ).toHaveAttribute("aria-current", "page");

    await user.click(
      screen.getByRole("button", { name: "Следующая страница" })
    );

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 })
      )
    );
    expect(window.scrollTo).toHaveBeenCalledWith({
      top: 0,
      behavior: "smooth",
    });
  });

  it("фильтр по категории и чип активного фильтра", async () => {
    const user = userEvent.setup();
    mCategories.mockResolvedValue([{ ...CATEGORY, path: "1.2" }]);
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();

    const option = await screen.findByRole("option", { name: /Laptops/ });
    expect(option.textContent).toMatch(/—\s*Laptops/);

    await user.selectOptions(
      screen.getByLabelText("Категория товара"),
      "1"
    );

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ category_id: 1, page: 1 })
      )
    );
    const chips = await screen.findByRole("list", {
      name: "Активные фильтры",
    });
    expect(within(chips).getByText("Laptops")).toBeInTheDocument();
  });

  it("фильтр по статусу", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("radio", { name: "Нет в наличии" }));

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "out_of_stock", page: 1 })
      )
    );
  });

  it("сортировка", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();
    await screen.findByText("Laptop");

    await user.selectOptions(
      screen.getByLabelText(/Сортировка:/i),
      "price_desc"
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

  it("active chips: удаление чипа query", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([], 0));
    renderPage("/?q=phone");

    const chipButton = await screen.findByRole("button", {
      name: "Убрать фильтр: «phone»",
    });
    await user.click(chipButton);

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: undefined })
      )
    );
  });

  it("quick view открывается, пишет историю и закрывается", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();
    await screen.findByText("Laptop");

    await user.click(screen.getByRole("button", { name: "Laptop" }));

    const dialog = await screen.findByRole("dialog", { name: "Laptop" });
    expect(
      within(dialog).getByRole("heading", { name: "Laptop" })
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/1\s*000\s*₽/)).toBeInTheDocument();

    expect(screen.getByText("Вы недавно смотрели")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]")).toEqual([1]);

    await user.click(
      within(dialog).getByRole("button", { name: "Закрыть" })
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Laptop" })
      ).not.toBeInTheDocument()
    );
  });

  it("мобильный drawer: открытие, блокировка scroll, закрытие", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();
    await screen.findByText("Laptop");

    await user.click(
      screen.getByRole("button", { name: "Открыть фильтры" })
    );

    const drawer = await screen.findByRole("dialog", {
      name: "Фильтры каталога",
    });
    expect(document.body.style.overflow).toBe("hidden");

    await user.click(
      within(drawer).getByRole("button", { name: "Показать товары" })
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Фильтры каталога" })
      ).not.toBeInTheDocument()
    );
    expect(document.body.style.overflow).toBe("");

    await user.click(
      screen.getByRole("button", { name: "Открыть фильтры" })
    );
    await screen.findByRole("dialog", { name: "Фильтры каталога" });

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Фильтры каталога" })
      ).not.toBeInTheDocument()
    );
  });

  it("история просмотров из localStorage и очистка", async () => {
    const user = userEvent.setup();
    localStorage.setItem(RECENT_KEY, JSON.stringify([1]));
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();

    const heading = await screen.findByText("Вы недавно смотрели");
    const strip = heading.closest("section") as HTMLElement;
    expect(within(strip).getByText("Laptop")).toBeInTheDocument();

    await user.click(
      within(strip).getByRole("button", { name: "Очистить" })
    );

    await waitFor(() =>
      expect(
        screen.queryByText("Вы недавно смотрели")
      ).not.toBeInTheDocument()
    );
    expect(localStorage.getItem(RECENT_KEY)).toBeNull();
  });

  it("слайдер цены применяет min_cost после debounce", async () => {
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();
    await screen.findByText("Laptop");

    fireEvent.input(screen.getByLabelText("Минимальная цена"), {
      target: { value: "480" },
    });

    await waitFor(
      () =>
        expect(mList).toHaveBeenLastCalledWith(
          expect.objectContaining({ min_cost: "480" })
        ),
      { timeout: 2000 }
    );
  });

  it("без диапазона цен → заглушка", async () => {
    mRange.mockResolvedValue({ min_cost: null, max_cost: null });
    mList.mockResolvedValue(makePage([PRODUCT], 1));
    renderPage();

    expect(
      await screen.findByText("Нет товаров для выбора цены")
    ).toBeInTheDocument();
  });
});
