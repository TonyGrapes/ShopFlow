import type { CatalogSort } from "../types";
import { SORT_OPTIONS } from "../types";
import { ChevronDownIcon } from "./icons";
import styles from "../styles/Controls.module.css";

interface Props {
  value: CatalogSort;
  onChange: (value: CatalogSort) => void;
}

export function SortDropdown({ value, onChange }: Props) {
  return (
    <label className={styles.sort}>
      <span className={styles.sortLabel}>Сортировка:</span>
      <span className={styles.selectWrap}>
        <select
          className={styles.select}
          value={value}
          onChange={(event) => onChange(event.target.value as CatalogSort)}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDownIcon className={styles.selectIcon} />
      </span>
    </label>
  );
}
