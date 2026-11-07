import { useEffect } from "react";
import type { Category } from "../../../types/category";
import type { ProductStatus } from "../../../types/product";
import type { ActiveChip, CatalogFilters, PriceBounds } from "../types";
import { CloseIcon } from "./icons";
import { FilterSidebar } from "./FilterSidebar";
import styles from "../styles/FilterSidebar.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
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

export function MobileFilterDrawer({ open, onClose, ...rest }: Props) {
  useEffect(() => {
    if (!open) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className={styles.drawerRoot}>
      <div
        className={styles.drawerOverlay}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={styles.drawerPanel}
        role="dialog"
        aria-modal="true"
        aria-label="Фильтры каталога"
      >
        <div className={styles.drawerTop}>
          <span className={styles.drawerTitle}>Фильтры</span>
          <button
            type="button"
            className={styles.drawerClose}
            onClick={onClose}
            aria-label="Закрыть фильтры"
          >
            <CloseIcon />
          </button>
        </div>
        <div className={styles.drawerBody}>
          <FilterSidebar {...rest} />
        </div>
        <div className={styles.drawerFooter}>
          <button type="button" className={styles.drawerApply} onClick={onClose}>
            Показать товары
          </button>
        </div>
      </div>
    </div>
  );
}
