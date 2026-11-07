import type { ProductListItem } from "../../../types/product";
import { ProductCard } from "./ProductCard";
import styles from "../styles/ProductGrid.module.css";

interface Props {
  products: ProductListItem[];
  onQuickView: (product: ProductListItem) => void;
}

export function ProductGrid({ products, onQuickView }: Props) {
  return (
    <div className={styles.grid}>
      {products.map((product, index) => (
        <ProductCard
          key={product.id}
          product={product}
          index={index}
          onQuickView={onQuickView}
        />
      ))}
    </div>
  );
}
