import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../hooks/useAuth";
import { useCart } from "../../../hooks/useCart";
import { useFavorites } from "../../../hooks/useFavorites";
import { useToast } from "../../../hooks/useToast";
import { getErrorMessage } from "../../../utils/errors";
import type { ProductListItem } from "../../../types/product";
import { formatPrice } from "../utils/format";
import { STATUS_LABELS, STATUS_TONES } from "../utils/status";
import { CartIcon, CloseIcon, HeartIcon } from "./icons";
import styles from "../styles/QuickView.module.css";

interface Props {
  product: ProductListItem | null;
  onClose: () => void;
}

export function QuickView({ product, onClose }: Props) {
  const { user } = useAuth();
  const { cart, addItem, updateItem } = useCart();
  const { isFavorite, toggleFavorite } = useFavorites();
  const { showToast } = useToast();
  const [imageFailed, setImageFailed] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!product) return;
    setImageFailed(false);

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [product, onClose]);

  if (!product) return null;

  const currentProduct = product;
  const cartItem = cart?.items.find((item) => item.product_id === product.id);
  const qty = cartItem?.quantity ?? 0;
  const favorite = isFavorite(product.id);
  const unavailable = product.status !== "available";

  async function handleAdd() {
    setPending(true);
    try {
      await addItem(currentProduct.id, 1);
      showToast(`«${currentProduct.name}» добавлен в корзину`);
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
      await updateItem(currentProduct.id, next);
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
      await toggleFavorite(currentProduct.id);
      showToast(
        favorite ? "Удалено из избранного" : "Добавлено в избранное",
        favorite ? "info" : "success"
      );
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.overlay} onClick={onClose} aria-hidden="true" />
      <div
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label={product.name}
      >
        <button
          type="button"
          className={styles.close}
          onClick={onClose}
          aria-label="Закрыть"
        >
          <CloseIcon />
        </button>

        <div className={styles.media}>
          {product.cover_url && !imageFailed ? (
            <img
              src={product.cover_url}
              alt={product.name}
              className={styles.image}
              onError={() => setImageFailed(true)}
            />
          ) : (
            <div className={styles.imageFallback} aria-hidden="true">
              {product.name.charAt(0)}
            </div>
          )}
        </div>

        <div className={styles.body}>
          <span className={styles.category}>
            {product.category?.category_name ?? "Без категории"}
          </span>
          <h2 className={styles.name}>{product.name}</h2>

          <span
            className={`${styles.status} ${styles[STATUS_TONES[product.status]]}`}
          >
            {STATUS_LABELS[product.status]}
          </span>

          <div className={styles.priceRow}>
            <span className={styles.price}>{formatPrice(product.cost)}</span>
          </div>

          <div className={styles.actions}>
            {qty > 0 ? (
              <div className={styles.stepper} role="group" aria-label="Количество">
                <button
                  type="button"
                  className={styles.stepperButton}
                  onClick={() => handleQty(qty - 1)}
                  disabled={pending}
                  aria-label="Уменьшить количество"
                >
                  −
                </button>
                <span className={styles.stepperValue}>{qty}</span>
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
                disabled={unavailable || pending}
                onClick={handleAdd}
              >
                <CartIcon width={18} height={18} />
                {unavailable ? "Недоступно" : pending ? "Добавляем…" : "В корзину"}
              </button>
            )}

            <button
              type="button"
              className={`${styles.favorite} ${
                favorite ? styles.favoriteActive : ""
              }`}
              onClick={handleFavorite}
              aria-pressed={favorite}
            >
              <HeartIcon filled={favorite} />
              {favorite ? "В избранном" : "В избранное"}
            </button>
          </div>

          <Link to={`/products/${product.id}`} className={styles.detailsLink}>
            Открыть карточку товара
          </Link>
        </div>
      </div>
    </div>
  );
}
