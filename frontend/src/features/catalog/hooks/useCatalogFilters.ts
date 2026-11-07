import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { ProductStatus } from "../../../types/product";
import {
  ALL_STATUSES,
  DEFAULT_FILTERS,
  SORT_OPTIONS,
} from "../types";
import type { ActiveChip, CatalogFilters, CatalogSort } from "../types";

function numberOrNull(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function parseFilters(params: URLSearchParams): CatalogFilters {
  const sort = params.get("sort");
  const status = params.get("status");
  const category = Number(params.get("category"));
  const page = Number(params.get("page"));

  return {
    query: params.get("q") ?? "",
    categoryId:
      Number.isInteger(category) && category > 0 ? category : null,
    minCost: numberOrNull(params.get("min")),
    maxCost: numberOrNull(params.get("max")),
    status: ALL_STATUSES.includes(status as ProductStatus)
      ? (status as ProductStatus)
      : "",
    sort: SORT_OPTIONS.some((option) => option.value === sort)
      ? (sort as CatalogSort)
      : DEFAULT_FILTERS.sort,
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

function serialize(filters: CatalogFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.query.trim()) params.set("q", filters.query.trim());
  if (filters.categoryId !== null) {
    params.set("category", String(filters.categoryId));
  }
  if (filters.minCost !== null) params.set("min", String(filters.minCost));
  if (filters.maxCost !== null) params.set("max", String(filters.maxCost));
  if (filters.status) params.set("status", filters.status);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

export function useCatalogFilters(
  categoryNames: ReadonlyMap<number, string>
) {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);

  const patch = useCallback(
    (partial: Partial<CatalogFilters>) => {
      const next: CatalogFilters = {
        ...parseFilters(searchParams),
        ...partial,
        page: partial.page ?? 1,
      };
      setSearchParams(serialize(next), { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const reset = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true });
  }, [setSearchParams]);

  const removeChip = useCallback(
    (key: ActiveChip["key"]) => {
      switch (key) {
        case "query":
          patch({ query: "" });
          break;
        case "category":
          patch({ categoryId: null });
          break;
        case "minCost":
          patch({ minCost: null });
          break;
        case "maxCost":
          patch({ maxCost: null });
          break;
        case "status":
          patch({ status: "" });
          break;
      }
    },
    [patch]
  );

  const activeChips = useMemo<ActiveChip[]>(() => {
    const chips: ActiveChip[] = [];
    if (filters.query) {
      chips.push({ key: "query", label: `«${filters.query}»` });
    }
    if (filters.categoryId !== null) {
      chips.push({
        key: "category",
        label:
          categoryNames.get(filters.categoryId) ?? "Категория",
      });
    }
    if (filters.minCost !== null) {
      chips.push({ key: "minCost", label: `от ${filters.minCost} ₽` });
    }
    if (filters.maxCost !== null) {
      chips.push({ key: "maxCost", label: `до ${filters.maxCost} ₽` });
    }
    if (filters.status) {
      chips.push({ key: "status", label: statusLabel(filters.status) });
    }
    return chips;
  }, [categoryNames, filters]);

  return {
    filters,
    patch,
    reset,
    removeChip,
    activeChips,
    activeCount: activeChips.length,
  };
}

function statusLabel(status: ProductStatus): string {
  switch (status) {
    case "available":
      return "В наличии";
    case "out_of_stock":
      return "Нет в наличии";
    case "discontinued":
      return "Снят с производства";
  }
}
