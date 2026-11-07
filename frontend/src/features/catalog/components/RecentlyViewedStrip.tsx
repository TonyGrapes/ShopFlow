import type { ProductListItem } from "../../../types/product";
import { formatPrice } from "../utils/format";
import styles from "../styles/RecentlyViewed.module.css";

interface Props {
  products: ProductListItem[];
  onQuickView: (product: ProductListItem) => void;
  onClear: () => void;
}

export function RecentlyViewedStrip({ products, onQuickView, onClear }: Props) {
  if (products.length === 0) return null;

  return (
    <section className={styles.section} aria-labelledby="recent-heading">
      <div className={styles.head}>
        <h2 id="recent-heading" className={styles.title}>
          Вы недавно смотрели
        </h2>
        <button type="button" className={styles.clear} onClick={onClear}>
          Очистить
        </button>
      </div>

      <ul className={styles.list}>
        {products.map((product) => (
          <li key={product.id}>
            <button
              type="button"
              className={styles.item}
              onClick={() => onQuickView(product)}
            >
              {product.cover_url ? (
                <img
                  className={styles.thumb}
                  src={product.cover_url}
                  alt=""
                  loading="lazy"
                  onError={(event) => {
                    event.currentTarget.style.visibility = "hidden";
                  }}
                />
              ) : (
                <span className={styles.thumb} aria-hidden="true" />
              )}
              <span className={styles.name}>{product.name}</span>
              <span className={styles.price}>{formatPrice(product.cost)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
