import type { ActiveChip } from "../types";
import styles from "../styles/FilterSidebar.module.css";

interface Props {
  chips: ActiveChip[];
  onRemove: (key: ActiveChip["key"]) => void;
}

export function ActiveFilterChips({ chips, onRemove }: Props) {
  if (chips.length === 0) return null;

  return (
    <ul className={styles.chips} aria-label="Активные фильтры">
      {chips.map((chip) => (
        <li key={chip.key} className={styles.chip}>
          <span>{chip.label}</span>
          <button
            type="button"
            className={styles.chipRemove}
            onClick={() => onRemove(chip.key)}
            aria-label={`Убрать фильтр: ${chip.label}`}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}
