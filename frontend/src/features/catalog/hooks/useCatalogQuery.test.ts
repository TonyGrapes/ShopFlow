import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS } from "../types";
import type { CatalogSort } from "../types";
import { toProductParams } from "./useCatalogQuery";

describe("toProductParams", () => {
  it("дефолтные фильтры → сортировка created_at desc", () => {
    expect(toProductParams(DEFAULT_FILTERS)).toEqual({
      page: 1,
      page_size: 12,
      q: undefined,
      category_id: undefined,
      min_cost: undefined,
      max_cost: undefined,
      status: undefined,
      sort_by: "created_at",
      sort_order: "desc",
    });
  });

  it("пробрасывает все фильтры и обрезает query", () => {
    expect(
      toProductParams({
        query: "  phone  ",
        categoryId: 3,
        minCost: 10,
        maxCost: 99,
        status: "available",
        sort: "price_asc",
        page: 2,
      })
    ).toEqual({
      page: 2,
      page_size: 12,
      q: "phone",
      category_id: 3,
      min_cost: "10",
      max_cost: "99",
      status: "available",
      sort_by: "cost",
      sort_order: "asc",
    });
  });

  it("неизвестная сортировка → fallback на первую опцию", () => {
    const params = toProductParams({
      ...DEFAULT_FILTERS,
      sort: "weird" as CatalogSort,
    });
    expect(params.sort_by).toBe("created_at");
    expect(params.sort_order).toBe("desc");
  });
});
