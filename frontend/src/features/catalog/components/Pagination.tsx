import { ChevronDownIcon } from "./icons";
import styles from "../styles/Controls.module.css";

interface Props {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}

function buildPages(page: number, totalPages: number): (number | "…")[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages: (number | "…")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);

  if (start > 2) pages.push("…");
  for (let i = start; i <= end; i += 1) pages.push(i);
  if (end < totalPages - 1) pages.push("…");
  pages.push(totalPages);

  return pages;
}

export function Pagination({ page, totalPages, onChange }: Props) {
  if (totalPages <= 1) return null;

  const pages = buildPages(page, totalPages);

  return (
    <nav className={styles.pagination} aria-label="Пагинация">
      <button
        type="button"
        className={styles.pageArrow}
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        aria-label="Предыдущая страница"
      >
        <ChevronDownIcon className={styles.arrowPrev} />
      </button>

      <ul className={styles.pageList}>
        {pages.map((item, index) =>
          item === "…" ? (
            <li key={`gap-${index}`} className={styles.pageGap} aria-hidden="true">
              …
            </li>
          ) : (
            <li key={item}>
              <button
                type="button"
                className={`${styles.pageButton} ${
                  item === page ? styles.pageButtonActive : ""
                }`}
                onClick={() => onChange(item)}
                aria-current={item === page ? "page" : undefined}
                aria-label={`Страница ${item}`}
              >
                {item}
              </button>
            </li>
          )
        )}
      </ul>

      <button
        type="button"
        className={styles.pageArrow}
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        aria-label="Следующая страница"
      >
        <ChevronDownIcon className={styles.arrowNext} />
      </button>
    </nav>
  );
}
