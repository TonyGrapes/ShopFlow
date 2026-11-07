import styles from "../styles/States.module.css";

interface Props {
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: Props) {
  return (
    <div className={`${styles.state} ${styles.error}`} role="alert">
      <div className={styles.illustration} aria-hidden="true">
        !
      </div>
      <h2 className={styles.title}>Что-то пошло не так</h2>
      <p className={styles.text}>{message}</p>
      <button type="button" className={styles.action} onClick={onRetry}>
        Повторить загрузку
      </button>
    </div>
  );
}
