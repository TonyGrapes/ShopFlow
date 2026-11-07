import styles from "../styles/ProductGrid.module.css";

interface Props {
  count?: number;
}

export function ProductCardSkeleton({ count = 8 }: Props) {
  return (
    <div className={styles.grid} aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className={styles.skeletonCard}>
          <div className={styles.skeletonMedia} />
          <div className={styles.skeletonBody}>
            <div className={styles.skeletonLine} style={{ width: "40%" }} />
            <div className={styles.skeletonLine} style={{ width: "90%" }} />
            <div className={styles.skeletonLine} style={{ width: "60%" }} />
            <div className={styles.skeletonButton} />
          </div>
        </div>
      ))}
    </div>
  );
}
