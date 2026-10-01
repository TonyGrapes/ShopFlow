// frontend/src/pages/CatalogPage.tsx
import { useEffect, useState } from "react";
import { fetchProductList } from "../api/products";
import { ApiError } from "../api/client";
import { ProductGrid } from "../components/ProductGrid";
import { FilterBar } from "../components/FilterBar";
import { Pagination } from "../components/Pagination";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { EmptyState } from "../components/EmptyState";
import type {
  Paginated,
  ProductListItem,
  ProductListParams,
} from "../types/product";

const DEFAULT_PAGE_SIZE = 20;

export function CatalogPage() {
  const [params, setParams] = useState<ProductListParams>({
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
    sort_by: "id",
    sort_order: "asc",
  });
  const [data, setData] = useState<Paginated<ProductListItem> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchProductList(params);
        if (!cancelled) setData(result);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError) setError(`${err.status}: ${err.detail}`);
        else if (err instanceof Error) setError(err.message);
        else setError("Неизвестная ошибка");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [params]);

  return (
    <div className="catalog-page">
      <h1>Каталог</h1>

      <FilterBar params={params} onChange={setParams} />

      {loading && <LoadingState />}
      {error && (
        <ErrorState
          message={error}
          onRetry={() => setParams({ ...params })}
        />
      )}
      {!loading && !error && data && (
        <>
          {data.items.length === 0 ? (
            <EmptyState />
          ) : (
            <ProductGrid products={data.items} />
          )}
          <Pagination
            page={params.page ?? 1}
            pageSize={params.page_size ?? DEFAULT_PAGE_SIZE}
            total={data.total}
            onChange={(page) => setParams({ ...params, page })}
          />
        </>
      )}
    </div>
  );
}