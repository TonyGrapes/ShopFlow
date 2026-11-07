import { useEffect, useMemo, useState } from "react";
import { fetchCategories } from "../../api/categories";
import { useApiQuery } from "../../shared/hooks/useApiQuery";
import { useDebouncedValue } from "../../shared/hooks/useDebouncedValue";
import type { ProductListItem } from "../../types/product";
import { CatalogToolbar } from "./components/CatalogToolbar";
import { EmptyState } from "./components/EmptyState";
import { ErrorState } from "./components/ErrorState";
import { FilterSidebar } from "./components/FilterSidebar";
import { MobileFilterDrawer } from "./components/MobileFilterDrawer";
import { Pagination } from "./components/Pagination";
import { ProductCardSkeleton } from "./components/ProductCardSkeleton";
import { ProductGrid } from "./components/ProductGrid";
import { QuickView } from "./components/QuickView";
import { RecentlyViewedStrip } from "./components/RecentlyViewedStrip";
import { SortDropdown } from "./components/SortDropdown";
import { SparkIcon } from "./components/icons";
import { useCatalogFilters } from "./hooks/useCatalogFilters";
import {
  toProductParams,
  useCatalogPriceRange,
  useCatalogProducts,
} from "./hooks/useCatalogQuery";
import { useRecentlyViewed } from "./hooks/useRecentlyViewed";
import { formatProductCount } from "./utils/format";
import type { CatalogFilters, PriceBounds } from "./types";
import styles from "./styles/CatalogPage.module.css";

const PAGE_SIZE = 12;

export function CatalogPage() {
  const categoryQuery = useApiQuery("categories", fetchCategories, []);
  const categories = useMemo(
    () => categoryQuery.data ?? [],
    [categoryQuery.data]
  );
  const categoryNames = useMemo(
    () =>
      new Map(categories.map((category) => [category.id, category.category_name])),
    [categories]
  );

  const {
    filters,
    patch,
    reset,
    removeChip,
    activeChips,
    activeCount,
  } = useCatalogFilters(categoryNames);

  const [quickView, setQuickView] = useState<ProductListItem | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const recentlyViewed = useRecentlyViewed();
  const { push: pushRecentlyViewed } = recentlyViewed;

  const debouncedQuery = useDebouncedValue(filters.query, 300);
  const effectiveFilters = useMemo<CatalogFilters>(
    () => ({ ...filters, query: debouncedQuery }),
    [filters, debouncedQuery]
  );
  const params = useMemo(
    () => toProductParams(effectiveFilters),
    [effectiveFilters]
  );

  const productsQuery = useCatalogProducts(params);
  const rangeQuery = useCatalogPriceRange(effectiveFilters);

  const items = useMemo(
    () => productsQuery.data?.items ?? [],
    [productsQuery.data]
  );
  const total = productsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const bounds = useMemo<PriceBounds>(() => {
    const min = Number(rangeQuery.data?.min_cost ?? 0);
    const max = Number(rangeQuery.data?.max_cost ?? 0);
    return {
      min: Number.isFinite(min) ? min : 0,
      max: Number.isFinite(max) ? max : 0,
    };
  }, [rangeQuery.data]);

  useEffect(() => {
    if (!productsQuery.loading && total > 0 && filters.page > totalPages) {
      patch({ page: totalPages });
    }
  }, [productsQuery.loading, total, totalPages, filters.page, patch]);

  useEffect(() => {
    if (quickView) pushRecentlyViewed(quickView.id);
  }, [quickView, pushRecentlyViewed]);

  const recentProducts = useMemo(() => {
    const byId = new Map(items.map((product) => [product.id, product]));
    return recentlyViewed.ids
      .map((id) => byId.get(id))
      .filter((product): product is ProductListItem => Boolean(product));
  }, [items, recentlyViewed.ids]);

  const sidebarProps = {
    filters,
    bounds,
    categories,
    activeChips,
    onCategoryChange: (categoryId: number | null) => patch({ categoryId }),
    onStatusChange: (status: CatalogFilters["status"]) => patch({ status }),
    onPriceChange: (min: number | null, max: number | null) =>
      patch({ minCost: min, maxCost: max }),
    onReset: reset,
    onRemoveChip: removeChip,
  };

  const hasFilters = activeCount > 0;
  const loading = productsQuery.loading;
  const error = productsQuery.error;

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <span className={styles.heroBadge}>
            <SparkIcon width={16} height={16} />
            Каталог ShopFlow
          </span>
          <h1 className={styles.heroTitle}>Техника для жизни и работы</h1>
          <p className={styles.heroText}>
            {loading
              ? "Загружаем каталог…"
              : `Более ${formatProductCount(total)} в наличии. Фильтруйте по категории, цене и доступности.`}
          </p>
        </div>
      </section>

      <CatalogToolbar
        query={filters.query}
        onQueryChange={(query) => patch({ query })}
        onOpenFilters={() => setFiltersOpen(true)}
        activeFilterCount={activeCount}
      />

      <div className={styles.layout}>
        <aside className={styles.aside} aria-label="Фильтры">
          <FilterSidebar {...sidebarProps} />
        </aside>

        <main className={styles.content}>
          <div className={styles.toolbar}>
            <p className={styles.resultCount} aria-live="polite">
              {loading
                ? "Загрузка товаров…"
                : `${formatProductCount(total)} · показано ${items.length}`}
            </p>
            <SortDropdown
              value={filters.sort}
              onChange={(sort) => patch({ sort })}
            />
          </div>

          {loading && <ProductCardSkeleton count={PAGE_SIZE} />}

          {!loading && error && (
            <ErrorState message={error} onRetry={productsQuery.refetch} />
          )}

          {!loading && !error && total === 0 && (
            <EmptyState
              query={hasFilters ? filters.query : ""}
              onReset={reset}
            />
          )}

          {!loading && !error && total > 0 && (
            <>
              <ProductGrid products={items} onQuickView={setQuickView} />
              <Pagination
                page={filters.page}
                totalPages={totalPages}
                onChange={(page) => {
                  patch({ page });
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              />
            </>
          )}

          <RecentlyViewedStrip
            products={recentProducts}
            onQuickView={setQuickView}
            onClear={recentlyViewed.clear}
          />
        </main>
      </div>

      <MobileFilterDrawer
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        {...sidebarProps}
      />

      <QuickView product={quickView} onClose={() => setQuickView(null)} />
    </div>
  );
}
