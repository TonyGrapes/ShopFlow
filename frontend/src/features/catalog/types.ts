import type { ProductStatus } from "../../types/product";

export type CatalogSort = "new" | "price_asc" | "price_desc" | "name_asc";

export interface CatalogFilters {
  query: string;
  categoryId: number | null;
  minCost: number | null;
  maxCost: number | null;
  status: ProductStatus | "";
  sort: CatalogSort;
  page: number;
}

export interface PriceBounds {
  min: number;
  max: number;
}

export interface ActiveChip {
  key: "query" | "category" | "minCost" | "maxCost" | "status";
  label: string;
}

export const DEFAULT_FILTERS: CatalogFilters = {
  query: "",
  categoryId: null,
  minCost: null,
  maxCost: null,
  status: "",
  sort: "new",
  page: 1,
};

export const SORT_OPTIONS: {
  value: CatalogSort;
  label: string;
  sortBy: "created_at" | "cost" | "name";
  sortOrder: "asc" | "desc";
}[] = [
  { value: "new", label: "Сначала новые", sortBy: "created_at", sortOrder: "desc" },
  { value: "price_asc", label: "Сначала дешёвые", sortBy: "cost", sortOrder: "asc" },
  { value: "price_desc", label: "Сначала дорогие", sortBy: "cost", sortOrder: "desc" },
  { value: "name_asc", label: "По названию", sortBy: "name", sortOrder: "asc" },
];

export const ALL_STATUSES: ProductStatus[] = [
  "available",
  "out_of_stock",
  "discontinued",
];
