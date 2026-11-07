import { useState } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../hooks/useAuth";
import { useCart } from "../../../hooks/useCart";
import { useFavorites } from "../../../hooks/useFavorites";
import { useToast } from "../../../hooks/useToast";
import { getErrorMessage } from "../../../utils/errors";
import type { ProductListItem } from "../../../types/product";
import { formatPrice } from "../utils/format";
import { STATUS_LABELS, STATUS_TONES } from "../utils/status";
import { CartIcon, EyeIcon, HeartIcon } from "./icons";
import styles from "../styles/ProductCard.module.css";

interface Props {
  product: ProductListItem;
  index: number;
  onQuickView: (product: ProductListItem) => void;
}

function placeholder(name: string): string {
  const letter = name.trim().charAt(0).toUpperCase() || "?";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#efeafd"/><stop offset="1" stop-color="#e2d5fb"/></linearGradient></defs><rect width="600" height="600" fill="url(#g)"/><text x="50%" y="50%" font-family="system-ui, sans-serif" font-size="200" fill="#aa3bff" text-anchor="middle" dominant-baseline="central" opacity="0.5">${letter}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export function ProductCard({ product, index, onQuickView }: Props) {
  const { user } = useAuth();
  const { cart, addItem, updateItem } = useCart();
  const { isFavorite, isPending, toggleFavorite } = useFavorites();
  const { showToast } = useToast();
  const [imageFailed, setImageFailed] = useState(false);
  const [pending, setPending] = useState(false);

  const cartItem = cart?.items.find((item) => item.product_id === product.id);
  const qty = cartItem?.quantity ?? 0;
  const favorite = isFavorite(product.id);
  const favoritePending = isPending(product.id);
  const unavailable = product.status !== "available";
  const statusTone = STATUS_TONES[product.status];
  const style = { "--i": index } as CSSProperties;

  async function handleAdd() {
    setPending(true);
    try {
      await addItem(product.id, 1);
      showToast(`«${product.name}» добавлен в корзину`);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  async function handleQty(next: number) {
    if (next < 1) return;
    setPending(true);
    try {
      await updateItem(product.id, next);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  async function handleFavorite() {
    if (user === null) {
      showToast("Войдите, чтобы добавлять товары в избранное", "info");
      return;
    }
    try {
      await toggleFavorite(product.id);
      showToast(
        favorite ? "Удалено из избранного" : "Добавлено в избранное",
        favorite ? "info" : "success"
      );
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    }
  }

  return (
    <article className={styles.card} style={style}>
      <div className={styles.media}>
        <button
          type="button"
          className={styles.mediaButton}
          onClick={() => onQuickView(product)}
          aria-label={`Быстрый просмотр: ${product.name}`}
        >
          <img
            className={styles.image}
            src={
              imageFailed || !product.cover_url
                ? placeholder(product.name)
                : product.cover_url
            }
            alt={product.name}
            loading="lazy"
            decoding="async"
            onError={() => setImageFailed(true)}
          />
        </button>

        <div className={styles.badges}>
          <span className={`${styles.statusBadge} ${styles[statusTone]}`}>
            {STATUS_LABELS[product.status]}
          </span>
        </div>

        <button
          type="button"
          className={`${styles.favorite} ${favorite ? styles.favoriteActive : ""}`}
          onClick={handleFavorite}
          disabled={favoritePending}
          aria-pressed={favorite}
          aria-label={favorite ? "Убрать из избранного" : "В избранное"}
        >
          <HeartIcon filled={favorite} />
        </button>

        <button
          type="button"
          className={styles.quickView}
          onClick={() => onQuickView(product)}
          tabIndex={-1}
        >
          <EyeIcon width={16} height={16} />
          Быстрый просмотр
        </button>
      </div>

      <div className={styles.body}>
        <span className={styles.category}>
          {product.category?.category_name ?? "Без категории"}
        </span>

        <button
          type="button"
          className={styles.name}
          onClick={() => onQuickView(product)}
        >
          {product.name}
        </button>

        <div className={styles.priceRow}>
          <span className={styles.price}>{formatPrice(product.cost)}</span>
        </div>

        {qty > 0 ? (
          <div className={styles.stepper} role="group" aria-label="Количество в корзине">
            <button
              type="button"
              className={styles.stepperButton}
              onClick={() => handleQty(qty - 1)}
              disabled={pending}
              aria-label="Уменьшить количество"
            >
              −
            </button>
            <span className={styles.stepperValue} aria-live="polite">
              {qty}
            </span>
            <button
              type="button"
              className={styles.stepperButton}
              onClick={() => handleQty(qty + 1)}
              disabled={pending}
              aria-label="Увеличить количество"
            >
              +
            </button>
          </div>
        ) : (
          <button
            type="button"
            className={styles.addButton}
            onClick={handleAdd}
            disabled={unavailable || pending}
          >
            <CartIcon width={18} height={18} />
            {unavailable ? "Недоступно" : pending ? "Добавляем…" : "В корзину"}
          </button>
        )}

        <Link to={`/products/${product.id}`} className={styles.detailsLink}>
          Подробнее
        </Link>
      </div>
    </article>
  );
}
