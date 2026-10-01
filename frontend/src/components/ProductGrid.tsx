// frontend/src/components/ProductGrid.tsx
import { ProductCard } from "./ProductCard";
import type { ProductListItem } from "../types/product";

interface Props {
  products: ProductListItem[];
}

export function ProductGrid({ products }: Props) {
  return (
    <div className="product-grid">
      {products.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
    </div>
  );
}