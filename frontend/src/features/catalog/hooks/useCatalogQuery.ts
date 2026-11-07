import { useMemo } from "react";
import { fetchProductList, fetchProductPriceRange } from "../../../api/products";
import type { ProductListParams } from "../../../types/product";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import { SORT_OPTIONS } from "../types";
import type { CatalogFilters } from "../types";

export function toProductParams(filters: CatalogFilters): ProductListParams {
  const sort =
    SORT_OPTIONS.find((option) => option.value === filters.sort) ??
    SORT_OPTIONS[0];

  return {
    page: filters.page,
    page_size: 12,
    q: filters.query.trim() || undefined,
    category_id: filters.categoryId ?? undefined,
    min_cost: filters.minCost !== null ? String(filters.minCost) : undefined,
    max_cost: filters.maxCost !== null ? String(filters.maxCost) : undefined,
    status: filters.status || undefined,
    sort_by: sort.sortBy,
    sort_order: sort.sortOrder,
  };
}

export function useCatalogProducts(params: ProductListParams) {
  const key = useMemo(() => JSON.stringify(params), [params]);
  return useApiQuery(key, () => fetchProductList(params));
}

export function useCatalogPriceRange(filters: CatalogFilters) {
  const q = filters.query.trim() || undefined;
  const categoryId = filters.categoryId ?? undefined;
  const status = filters.status || undefined;
  const key = JSON.stringify({ q, categoryId, status });

  return useApiQuery(key, () =>
    fetchProductPriceRange({ q, category_id: categoryId, status })
  );
}
