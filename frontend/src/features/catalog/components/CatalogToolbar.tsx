import { FilterIcon, SearchIcon } from "./icons";
import styles from "../styles/CatalogPage.module.css";

interface Props {
  query: string;
  onQueryChange: (value: string) => void;
  onOpenFilters: () => void;
  activeFilterCount: number;
}

export function CatalogToolbar({
  query,
  onQueryChange,
  onOpenFilters,
  activeFilterCount,
}: Props) {
  return (
    <div className={styles.searchRow}>
      <form
        className={styles.search}
        role="search"
        onSubmit={(event) => event.preventDefault()}
      >
        <SearchIcon className={styles.searchIcon} />
        <input
          type="search"
          className={styles.searchInput}
          placeholder="Поиск по названию, описанию или категории…"
          aria-label="Поиск товаров"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
      </form>

      <button
        type="button"
        className={styles.filterToggle}
        onClick={onOpenFilters}
        aria-label="Открыть фильтры"
      >
        <FilterIcon />
        Фильтры
        {activeFilterCount > 0 && (
          <span className={styles.filterBadge}>{activeFilterCount}</span>
        )}
      </button>
    </div>
  );
}
