import { useEffect, useState } from "react";
import type { Category } from "../../../types/category";
import type { ProductStatus } from "../../../types/product";
import { useDebouncedValue } from "../../../shared/hooks/useDebouncedValue";
import type { ActiveChip, CatalogFilters, PriceBounds } from "../types";
import { ALL_STATUSES } from "../types";
import { STATUS_LABELS } from "../utils/status";
import { ActiveFilterChips } from "./ActiveFilterChips";
import { PriceRangeSlider } from "./PriceRangeSlider";
import styles from "../styles/FilterSidebar.module.css";

interface Props {
  filters: CatalogFilters;
  bounds: PriceBounds;
  categories: Category[];
  activeChips: ActiveChip[];
  onCategoryChange: (categoryId: number | null) => void;
  onStatusChange: (status: ProductStatus | "") => void;
  onPriceChange: (min: number | null, max: number | null) => void;
  onReset: () => void;
  onRemoveChip: (key: ActiveChip["key"]) => void;
}

export function FilterSidebar({
  filters,
  bounds,
  categories,
  activeChips,
  onCategoryChange,
  onStatusChange,
  onPriceChange,
  onReset,
  onRemoveChip,
}: Props) {
  const [priceMin, setPriceMin] = useState(filters.minCost ?? bounds.min);
  const [priceMax, setPriceMax] = useState(filters.maxCost ?? bounds.max);

  useEffect(() => {
    setPriceMin(filters.minCost ?? bounds.min);
  }, [filters.minCost, bounds.min]);

  useEffect(() => {
    setPriceMax(filters.maxCost ?? bounds.max);
  }, [filters.maxCost, bounds.max]);

  const debouncedMin = useDebouncedValue(priceMin, 350);
  const debouncedMax = useDebouncedValue(priceMax, 350);

  useEffect(() => {
    const min = debouncedMin <= bounds.min ? null : debouncedMin;
    const max = debouncedMax >= bounds.max ? null : debouncedMax;
    if (min !== filters.minCost || max !== filters.maxCost) {
      onPriceChange(min, max);
    }
    // The price callback is intentionally read from the latest render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedMin, debouncedMax, bounds.min, bounds.max]);

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <h2 className={styles.title}>Фильтры</h2>
        {activeChips.length > 0 && (
          <button type="button" className={styles.resetLink} onClick={onReset}>
            Сбросить
          </button>
        )}
      </div>

      <ActiveFilterChips chips={activeChips} onRemove={onRemoveChip} />

      <section className={styles.group} aria-labelledby="filter-category">
        <h3 id="filter-category" className={styles.groupTitle}>
          Категория
        </h3>
        <label className={styles.selectWrap}>
          <span className="visually-hidden">Категория товара</span>
          <select
            className={styles.select}
            value={filters.categoryId ?? ""}
            onChange={(event) =>
              onCategoryChange(
                event.target.value ? Number(event.target.value) : null
              )
            }
          >
            <option value="">Все категории</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {"— ".repeat(Math.max(0, category.path.split(".").length - 1))}
                {category.category_name}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className={styles.group} aria-labelledby="filter-price">
        <h3 id="filter-price" className={styles.groupTitle}>
          Цена
        </h3>
        {bounds.max > bounds.min ? (
          <PriceRangeSlider
            bounds={bounds}
            min={Math.min(Math.max(priceMin, bounds.min), bounds.max)}
            max={Math.min(Math.max(priceMax, bounds.min), bounds.max)}
            onChange={(min, max) => {
              setPriceMin(min);
              setPriceMax(max);
            }}
          />
        ) : (
          <p className={styles.rangeEmpty}>Нет товаров для выбора цены</p>
        )}
      </section>

      <section className={styles.group} aria-labelledby="filter-status">
        <h3 id="filter-status" className={styles.groupTitle}>
          Наличие
        </h3>
        <fieldset className={styles.statusFieldset}>
          <legend className="visually-hidden">Статус товара</legend>

          <label className={styles.radio}>
            <input
              type="radio"
              name="catalog-status"
              checked={filters.status === ""}
              onChange={() => onStatusChange("")}
            />
            <span>Все товары</span>
          </label>

          {ALL_STATUSES.map((status) => (
            <label key={status} className={styles.radio}>
              <input
                type="radio"
                name="catalog-status"
                checked={filters.status === status}
                onChange={() => onStatusChange(status)}
              />
              <span>{STATUS_LABELS[status]}</span>
            </label>
          ))}
        </fieldset>
      </section>

      <button type="button" className={styles.resetButton} onClick={onReset}>
        Сбросить фильтры
      </button>
    </div>
  );
}
