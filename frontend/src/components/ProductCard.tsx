// frontend/src/components/ProductCard.tsx
import { Link } from "react-router-dom";
import { AddToCartButton } from "./AddToCartButton";
import { FavoriteButton } from "./FavoriteButton";
import { formatMoney } from "../utils/format";
import { productStatusLabel } from "../utils/labels";
import type { ProductListItem } from "../types/product";

interface Props {
  product: ProductListItem;
}

/**
 * Карточка товара в каталоге.
 *
 * Обложка берётся из cover_url (публичный MinIO).
 * Если null — placeholder.
 *
 * Кнопки действий вынесены из <Link>, чтобы не было
 * вложенных интерактивных элементов.
 */
export function ProductCard({ product }: Props) {
  return (
    <article className="product-card">
      <Link
        to={`/products/${product.id}`}
        className="product-card__link"
      >
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
          <p className="product-card__cost">
            {formatMoney(product.cost)}
          </p>
          <p className="product-card__status">
            {productStatusLabel(product.status)}
          </p>
        </div>
      </Link>

      <div className="product-card__actions">
        <AddToCartButton
          productId={product.id}
          available={product.status === "available"}
        />
        <FavoriteButton productId={product.id} />
      </div>
    </article>
  );
}
