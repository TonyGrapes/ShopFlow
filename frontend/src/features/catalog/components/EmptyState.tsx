import { SearchIcon } from "./icons";
import styles from "../styles/States.module.css";

interface Props {
  query: string;
  onReset: () => void;
}

export function EmptyState({ query, onReset }: Props) {
  return (
    <div className={styles.state}>
      <div className={styles.illustration} aria-hidden="true">
        <SearchIcon width={40} height={40} />
      </div>
      <h2 className={styles.title}>Ничего не найдено</h2>
      <p className={styles.text}>
        {query
          ? `По запросу «${query}» товаров нет. Попробуйте изменить фильтры.`
          : "По выбранным фильтрам товаров нет. Попробуйте изменить условия."}
      </p>
      <button type="button" className={styles.action} onClick={onReset}>
        Сбросить фильтры
      </button>
    </div>
  );
}
