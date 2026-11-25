import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { useCatalogFilters } from "./useCatalogFilters";

const CATEGORIES = new Map<number, string>([
  [2, "Phones"],
  [5, "Laptops"],
]);

function makeWrapper(initialEntry: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
    );
  };
}

function renderFilters(initialEntry = "/") {
  return renderHook(
    () => ({
      filters: useCatalogFilters(CATEGORIES),
      location: useLocation(),
    }),
    { wrapper: makeWrapper(initialEntry) }
  );
}

const FULL_SEARCH =
  "/?q=phone&category=2&min=10&max=100&status=available&sort=price_asc&page=3";

describe("useCatalogFilters", () => {
  it("без параметров → DEFAULT_FILTERS", () => {
    const { result } = renderFilters();

    expect(result.current.filters.filters).toEqual({
      query: "",
      categoryId: null,
      minCost: null,
      maxCost: null,
      status: "",
      sort: "new",
      page: 1,
    });
    expect(result.current.filters.activeChips).toEqual([]);
    expect(result.current.filters.activeCount).toBe(0);
  });

  it("парсит все параметры и строит активные чипы", () => {
    const { result } = renderFilters(FULL_SEARCH);

    expect(result.current.filters.filters).toEqual({
      query: "phone",
      categoryId: 2,
      minCost: 10,
      maxCost: 100,
      status: "available",
      sort: "price_asc",
      page: 3,
    });
    expect(result.current.filters.activeChips).toEqual([
      { key: "query", label: "«phone»" },
      { key: "category", label: "Phones" },
      { key: "minCost", label: "от 10 ₽" },
      { key: "maxCost", label: "до 100 ₽" },
      { key: "status", label: "В наличии" },
    ]);
    expect(result.current.filters.activeCount).toBe(5);
  });

  it("невалидные значения → дефолты", () => {
    const { result } = renderFilters(
      "/?category=0&min=-5&max=abc&status=weird&sort=weird&page=0"
    );

    expect(result.current.filters.filters).toEqual({
      query: "",
      categoryId: null,
      minCost: null,
      maxCost: null,
      status: "",
      sort: "new",
      page: 1,
    });
    expect(result.current.filters.activeCount).toBe(0);
  });

  it("patch мержит и сбрасывает страницу на 1", () => {
    const { result } = renderFilters(FULL_SEARCH);

    act(() => result.current.filters.patch({ query: "tv" }));

    expect(result.current.filters.filters.query).toBe("tv");
    expect(result.current.filters.filters.page).toBe(1);
    expect(result.current.filters.filters.categoryId).toBe(2);
    expect(result.current.location.search).toContain("q=tv");
    expect(result.current.location.search).not.toContain("page=3");
  });

  it("patch с page сохраняет явную страницу", () => {
    const { result } = renderFilters(FULL_SEARCH);

    act(() => result.current.filters.patch({ page: 2 }));

    expect(result.current.filters.filters.page).toBe(2);
    expect(result.current.location.search).toContain("page=2");
  });

  it("reset очищает параметры", () => {
    const { result } = renderFilters(FULL_SEARCH);

    act(() => result.current.filters.reset());

    expect(result.current.filters.filters.page).toBe(1);
    expect(result.current.filters.filters.query).toBe("");
    expect(result.current.filters.activeChips).toEqual([]);
    expect(result.current.location.search).toBe("");
  });

  it("removeChip убирает конкретный фильтр", () => {
    const { result } = renderFilters(FULL_SEARCH);

    act(() => result.current.filters.removeChip("query"));
    expect(result.current.filters.filters.query).toBe("");

    act(() => result.current.filters.removeChip("category"));
    expect(result.current.filters.filters.categoryId).toBeNull();

    act(() => result.current.filters.removeChip("minCost"));
    expect(result.current.filters.filters.minCost).toBeNull();

    act(() => result.current.filters.removeChip("maxCost"));
    expect(result.current.filters.filters.maxCost).toBeNull();

    act(() => result.current.filters.removeChip("status"));
    expect(result.current.filters.filters.status).toBe("");

    expect(result.current.filters.activeCount).toBe(0);
  });

  it("категория без имени в map → generic-чип", () => {
    const { result } = renderFilters("/?category=99");
    expect(result.current.filters.activeChips).toEqual([
      { key: "category", label: "Категория" },
    ]);
  });
});
