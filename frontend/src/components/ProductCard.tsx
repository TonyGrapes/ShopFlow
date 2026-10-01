// frontend/src/components/ProductCard.tsx
import { Link } from "react-router-dom";
import type { ProductListItem } from "../types/product";

interface Props {
  product: ProductListItem;
}

/**
 * Карточка товара в каталоге.
 *
 * Обложка берётся из cover_url (публичный MinIO).
 * Если null — placeholder.
 */
export function ProductCard({ product }: Props) {
  return (
    <Link to={`/products/${product.id}`} className="product-card">
      <div className="product-card__cover">
        {product.cover_url ? (
          <img
            src={product.cover_url}
            alt={product.name}
            loading="lazy"
          />
        ) : (
          <div className="product-card__no-cover">Нет изображения</div>
        )}
      </div>
      <div className="product-card__body">
        <h3 className="product-card__name">{product.name}</h3>
        <p className="product-card__cost">{product.cost} ₽</p>
        <p className="product-card__status">
          {formatStatus(product.status)}
        </p>
      </div>
    </Link>
  );
}

function formatStatus(status: string): string {
  switch (status) {
    case "available":
      return "В наличии";
    case "out_of_stock":
      return "Нет в наличии";
    case "discontinued":
      return "Снят с производства";
    default:
      return status;
  }
}