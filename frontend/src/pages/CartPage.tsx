// frontend/src/pages/CartPage.tsx
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useCart } from "../hooks/useCart";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import { formatMoney } from "../utils/format";
import { productStatusLabel } from "../utils/labels";
import type { PromoCodePreviewResponse } from "../types/promo";

export function CartPage() {
  const {
    cart,
    loading,
    error,
    refreshCart,
    updateItem,
    removeItem,
    clearCart,
    applyPromo,
  } = useCart();
  const { showToast } = useToast();

  const [pendingIds, setPendingIds] = useState<number[]>([]);
  const [clearing, setClearing] = useState(false);
  const [promoCode, setPromoCode] = useState("");
  const [promo, setPromo] = useState<PromoCodePreviewResponse | null>(null);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [promoLoading, setPromoLoading] = useState(false);

  // Preview промокода относится к текущему состоянию корзины.
  // После изменения состава/суммы его нужно сбросить.
  useEffect(() => {
    setPromo(null);
    setPromoError(null);
  }, [cart?.total_cost, cart?.total_items]);

  if (loading && cart === null) {
    return <LoadingState />;
  }

  if (error !== null && cart === null) {
    return (
      <ErrorState
        message={error}
        onRetry={() => {
          void refreshCart().catch(() => undefined);
        }}
      />
    );
  }

  if (cart === null) {
    return <LoadingState />;
  }

  const availableItems = cart.items.filter((item) => item.is_available);
  const unavailableItems = cart.items.filter((item) => !item.is_available);
  const isEmpty =
    cart.items.length === 0 && cart.hidden_items_count === 0 && !loading;

  async function changeQuantity(productId: number, quantity: number) {
    if (quantity < 1 || quantity > 100 || pendingIds.includes(productId)) {
      return;
    }
    setPendingIds((prev) => [...prev, productId]);
    try {
      await updateItem(productId, quantity);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPendingIds((prev) => prev.filter((id) => id !== productId));
    }
  }

  async function handleRemove(productId: number) {
    if (pendingIds.includes(productId)) return;
    setPendingIds((prev) => [...prev, productId]);
    try {
      await removeItem(productId);
      showToast("Товар удалён из корзины", "info");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPendingIds((prev) => prev.filter((id) => id !== productId));
    }
  }

  async function handleClear() {
    if (!window.confirm("Очистить корзину полностью?")) {
      return;
    }
    setClearing(true);
    try {
      await clearCart();
      showToast("Корзина очищена", "info");
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setClearing(false);
    }
  }

  async function handleApplyPromo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = promoCode.trim();
    if (code.length === 0) {
      setPromoError("Введите промокод");
      return;
    }

    setPromoLoading(true);
    setPromoError(null);
    try {
      const preview = await applyPromo(code);
      setPromo(preview);
    } catch (err) {
      setPromo(null);
      setPromoError(getErrorMessage(err));
    } finally {
      setPromoLoading(false);
    }
  }

  return (
    <div className="cart-page">
      <div className="page-heading">
        <h1>Корзина</h1>
        <Link to="/">← Продолжить покупки</Link>
      </div>

      {isEmpty ? (
        <EmptyState message="Корзина пуста" />
      ) : (
        <div className="cart-layout">
          <div className="cart-main">
            {availableItems.length > 0 && (
              <div className="cart-list">
                {availableItems.map((item) => {
                  const pending = pendingIds.includes(item.product_id);
                  const priceChanged =
                    item.snapshot_cost !== item.current_cost;

                  return (
                    <div className="cart-item" key={item.product_id}>
                      <div className="cart-item__cover">
                        {item.cover_url !== null ? (
                          <img src={item.cover_url} alt={item.name} />
                        ) : (
                          <div className="cart-item__no-cover">
                            Нет изображения
                          </div>
                        )}
                      </div>

                      <div className="cart-item__info">
                        <Link
                          to={`/products/${item.product_id}`}
                          className="cart-item__name"
                        >
                          {item.name}
                        </Link>
                        <p className="muted">
                          {productStatusLabel(item.status)}
                        </p>
                        <p className="cart-item__price">
                          {formatMoney(item.current_cost)}
                        </p>
                        {priceChanged && (
                          <p className="cart-item__warning">
                            Цена изменилась: в корзине{" "}
                            {formatMoney(item.snapshot_cost)}
                          </p>
                        )}
                      </div>

                      <div className="cart-item__actions">
                        <div className="quantity">
                          <button
                            type="button"
                            onClick={() =>
                              void changeQuantity(
                                item.product_id,
                                item.quantity - 1
                              )
                            }
                            disabled={pending || item.quantity <= 1}
                            aria-label="Уменьшить количество"
                          >
                            −
                          </button>
                          <span>{item.quantity}</span>
                          <button
                            type="button"
                            onClick={() =>
                              void changeQuantity(
                                item.product_id,
                                item.quantity + 1
                              )
                            }
                            disabled={pending || item.quantity >= 100}
                            aria-label="Увеличить количество"
                          >
                            +
                          </button>
                        </div>

                        <button
                          type="button"
                          className="btn btn--danger btn--sm"
                          onClick={() => void handleRemove(item.product_id)}
                          disabled={pending}
                        >
                          Удалить
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {unavailableItems.length > 0 && (
              <section className="cart-unavailable">
                <h2>Недоступны для заказа</h2>
                <p className="muted">
                  Эти товары нельзя оформить. Удалите их, чтобы
                  продолжить.
                </p>
                {unavailableItems.map((item) => (
                  <div className="cart-item" key={item.product_id}>
                    <div className="cart-item__info">
                      <span className="cart-item__name">{item.name}</span>
                      <p className="muted">
                        {productStatusLabel(item.status)}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="btn btn--danger btn--sm"
                      onClick={() => void handleRemove(item.product_id)}
                      disabled={pendingIds.includes(item.product_id)}
                    >
                      Удалить
                    </button>
                  </div>
                ))}
              </section>
            )}

            {cart.hidden_items_count > 0 && (
              <p className="cart-note">
                Скрыто товаров, которых больше нет в каталоге:{" "}
                {cart.hidden_items_count}
              </p>
            )}

            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => void handleClear()}
              disabled={clearing || cart.items.length === 0}
            >
              {clearing ? "Очищаем..." : "Очистить корзину"}
            </button>
          </div>

          <aside className="cart-summary">
            <h2>Итого</h2>

            <div className="cart-summary__row">
              <span>Товары ({cart.total_items})</span>
              <span>{formatMoney(cart.total_cost)}</span>
            </div>

            <form className="promo" onSubmit={handleApplyPromo}>
              <label className="form__field">
                <span>Промокод</span>
                <input
                  type="text"
                  value={promoCode}
                  onChange={(e) => setPromoCode(e.target.value)}
                  maxLength={100}
                  placeholder="Например, SALE10"
                />
              </label>
              <button
                type="submit"
                className="btn btn--secondary btn--sm"
                disabled={promoLoading}
              >
                {promoLoading ? "Проверяем..." : "Применить"}
              </button>
            </form>

            {promoError !== null && (
              <p className="form__error">{promoError}</p>
            )}

            {promo !== null && (
              <div className="promo__result">
                <div className="cart-summary__row">
                  <span>Сумма</span>
                  <span>{formatMoney(promo.subtotal)}</span>
                </div>
                <div className="cart-summary__row cart-summary__row--discount">
                  <span>Скидка</span>
                  <span>−{formatMoney(promo.discount_amount)}</span>
                </div>
                <div className="cart-summary__row cart-summary__row--total">
                  <span>К оплате</span>
                  <span>{formatMoney(promo.final_total)}</span>
                </div>
              </div>
            )}

            {promo === null && (
              <div className="cart-summary__row cart-summary__row--total">
                <span>К оплате</span>
                <span>{formatMoney(cart.total_cost)}</span>
              </div>
            )}

            {availableItems.length > 0 ? (
              <Link to="/checkout" className="btn btn--primary btn--block">
                Перейти к оформлению
              </Link>
            ) : (
              <p className="muted">
                Нет доступных товаров для оформления заказа.
              </p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
