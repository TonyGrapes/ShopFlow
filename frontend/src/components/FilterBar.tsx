// frontend/src/components/FilterBar.tsx
import type { ProductListParams, ProductStatus } from "../types/product";
import { useEffect, useState } from "react";
import { useDebouncedValue } from "../hooks/useDebouncedValue";

interface Props {
  params: ProductListParams;
  onChange: (params: ProductListParams) => void;
}

const STATUS_OPTIONS: { value: ProductStatus | ""; label: string }[] = [
  { value: "", label: "Все" },
  { value: "available", label: "В наличии" },
  { value: "out_of_stock", label: "Нет в наличии" },
  { value: "discontinued", label: "Снят с производства" },
];

const SORT_OPTIONS = [
  { value: "id:asc", label: "По умолчанию" },
  { value: "cost:asc", label: "Цена ↑" },
  { value: "cost:desc", label: "Цена ↓" },
  { value: "created_at:desc", label: "Сначала новые" },
  { value: "name:asc", label: "По названию" },
];

export function FilterBar({ params, onChange }: Props) {
  const sortValue = `${params.sort_by ?? "id"}:${params.sort_order ?? "asc"}`;

  // Локальный state для текстовых полей — чтобы ввод был мгновенным
  const [minCost, setMinCost] = useState(params.min_cost ?? "");
  const [maxCost, setMaxCost] = useState(params.max_cost ?? "");

  // Debounce — 400 мс
  const debouncedMin = useDebouncedValue(minCost, 400);
  const debouncedMax = useDebouncedValue(maxCost, 400);

  // Синхронизация наружу: только когда debounced-значения изменились
  useEffect(() => {
    if (debouncedMin !== (params.min_cost ?? "") ||
        debouncedMax !== (params.max_cost ?? "")) {
      onChange({
        ...params,
        min_cost: debouncedMin || undefined,
        max_cost: debouncedMax || undefined,
        page: 1,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedMin, debouncedMax]);

  return (
    <div className="filter-bar">
      {/* Category, Status, Sort — без debounce, они и так «событийные» */}

      <label>
        Цена от:
        <input
          type="text"
          inputMode="decimal"
          value={minCost}
          onChange={(e) => setMinCost(e.target.value)}
        />
      </label>

      <label>
        Цена до:
        <input
          type="text"
          inputMode="decimal"
          value={maxCost}
          onChange={(e) => setMaxCost(e.target.value)}
        />
      </label>


      <label>
        Статус:
        <select
          value={params.status ?? ""}
          onChange={(e) =>
            onChange({
              ...params,
              status: (e.target.value || undefined) as ProductStatus | undefined,
              page: 1,
            })
          }
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        Сортировка:
        <select
          value={sortValue}
          onChange={(e) => {
            const [sort_by, sort_order] = e.target.value.split(":") as [
              ProductListParams["sort_by"],
              ProductListParams["sort_order"]
            ];
            onChange({ ...params, sort_by, sort_order, page: 1 });
          }}
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}