// frontend/src/pages/CheckoutPage.tsx
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchAddresses } from "../api/addresses";
import { createOrder } from "../api/orders";
import { AddressForm } from "../components/AddressForm";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { useCart } from "../hooks/useCart";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import { formatMoney } from "../utils/format";
import type { AddressResponse } from "../types/address";
import type { PromoCodePreviewResponse } from "../types/promo";

export function CheckoutPage() {
  const {
    cart,
    loading: cartLoading,
    error: cartError,
    refreshCart,
    applyPromo,
  } = useCart();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const [addresses, setAddresses] = useState<AddressResponse[]>([]);
  const [addressesLoading, setAddressesLoading] = useState(true);
  const [addressesError, setAddressesError] = useState<string | null>(null);
  const [addressesReloadKey, setAddressesReloadKey] = useState(0);
  const [selectedAddressId, setSelectedAddressId] = useState<number | null>(
    null
  );
  const [showAddressForm, setShowAddressForm] = useState(false);

  const [promoCode, setPromoCode] = useState("");
  const [promo, setPromo] = useState<PromoCodePreviewResponse | null>(null);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [promoLoading, setPromoLoading] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    let cancelled = false;
    setAddressesLoading(true);
    setAddressesError(null);

    fetchAddresses()
      .then((data) => {
        if (!cancelled) setAddresses(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setAddressesError(getErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setAddressesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [addressesReloadKey]);

  useEffect(() => {
    if (addresses.length === 0) {
      setSelectedAddressId(null);
      return;
    }

    const current = addresses.find(
      (address) => address.id === selectedAddressId
    );
    if (current !== undefined) return;

    const fallback =
      addresses.find((address) => address.is_default) ?? addresses[0];
    setSelectedAddressId(fallback.id);
  }, [addresses, selectedAddressId]);

  useEffect(() => {
    setPromo(null);
    setPromoError(null);
  }, [cart?.total_cost, cart?.total_items]);

  if (cartLoading && cart === null) {
    return <LoadingState />;
  }

  if (cartError !== null && cart === null) {
    return (
      <ErrorState
        message={cartError}
        onRetry={() => {
          void refreshCart().catch(() => undefined);
        }}
      />
    );
  }

  if (cart === null) {
    return <LoadingState />;
  }

  if (cart.items.length === 0) {
    return (
      <div className="checkout-page">
        <h1>Оформление заказа</h1>
        <EmptyState message="Корзина пуста" />
        <Link to="/">Перейти в каталог</Link>
      </div>
    );
  }

  const hasUnavailable = cart.items.some((item) => !item.is_available);
  const canSubmit =
    !submitting &&
    !hasUnavailable &&
    selectedAddressId !== null &&
    cart.items.length > 0;

  function handleAddressCreated(address: AddressResponse) {
    setAddresses((prev) => [...prev, address]);
    setSelectedAddressId(address.id);
    setShowAddressForm(false);
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

  async function handleCreateOrder() {
    if (selectedAddressId === null) {
      setOrderError("Выберите адрес доставки");
      return;
    }

    setSubmitting(true);
    setOrderError(null);
    try {
      const order = await createOrder(
        {
          address_id: selectedAddressId,
          promo_code: promoCode.trim() ? promoCode.trim() : null,
        },
        idempotencyKey
      );

      await refreshCart().catch(() => undefined);
      showToast("Заказ создан. Осталось оплатить.", "success");
      navigate(`/orders/${order.public_id}`, {
        replace: true,
        state: { justCreated: true },
      });
    } catch (err) {
      setOrderError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="checkout-page">
      <div className="page-heading">
        <h1>Оформление заказа</h1>
        <Link to="/cart">← Вернуться в корзину</Link>
      </div>

      {hasUnavailable && (
        <p className="form__error">
          В корзине есть недоступные товары.{" "}
          <Link to="/cart">Удалите их</Link>, чтобы оформить заказ.
        </p>
      )}

      <div className="checkout-layout">
        <div className="checkout-main">
          <section className="checkout-section">
            <div className="section-heading">
              <h2>Адрес доставки</h2>
              <Link to="/addresses">Управление адресами</Link>
            </div>

            {addressesLoading && <LoadingState />}

            {addressesError !== null && (
              <ErrorState
                message={addressesError}
                onRetry={() => setAddressesReloadKey((key) => key + 1)}
              />
            )}

            {!addressesLoading && addressesError === null && (
              <>
                {addresses.length === 0 && !showAddressForm && (
                  <div className="form__hint">
                    <p>У вас пока нет адресов доставки.</p>
                    <button
                      type="button"
                      className="btn btn--primary btn--sm"
                      onClick={() => setShowAddressForm(true)}
                    >
                      Добавить адрес
                    </button>
                  </div>
                )}

                {addresses.length > 0 && (
                  <div className="address-list">
                    {addresses.map((address) => (
                      <label
                        key={address.id}
                        className={
                          address.id === selectedAddressId
                            ? "address-option address-option--selected"
                            : "address-option"
                        }
                      >
                        <input
                          type="radio"
                          name="address"
                          value={address.id}
                          checked={address.id === selectedAddressId}
                          onChange={() => setSelectedAddressId(address.id)}
                        />
                        <span>
                          {address.city}, {address.address_line1}
                          {address.address_line2
                            ? `, ${address.address_line2}`
                            : ""}
                          , {address.postal_code}, {address.country}
                          {address.is_default && (
                            <span className="badge badge--default">
                              По умолчанию
                            </span>
                          )}
                        </span>
                      </label>
                    ))}

                    {!showAddressForm && (
                      <button
                        type="button"
                        className="btn btn--secondary btn--sm"
                        onClick={() => setShowAddressForm(true)}
                      >
                        Добавить новый адрес
                      </button>
                    )}
                  </div>
                )}

                {showAddressForm && (
                  <AddressForm
                    onCreated={handleAddressCreated}
                    onCancel={
                      addresses.length > 0
                        ? () => setShowAddressForm(false)
                        : undefined
                    }
                  />
                )}
              </>
            )}
          </section>

          <section className="checkout-section">
            <h2>Состав заказа</h2>
            <div className="cart-list cart-list--compact">
              {cart.items.map((item) => (
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
                    <span className="cart-item__name">{item.name}</span>
                    <p className="muted">{item.quantity} шт.</p>
                  </div>
                  <div className="cart-item__price">
                    {formatMoney(item.current_cost)}
                  </div>
                </div>
              ))}
            </div>
          </section>
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

          {orderError !== null && (
            <p className="form__error">{orderError}</p>
          )}

          <button
            type="button"
            className="btn btn--primary btn--block"
            onClick={() => void handleCreateOrder()}
            disabled={!canSubmit}
          >
            {submitting ? "Оформляем..." : "Оформить заказ"}
          </button>
        </aside>
      </div>
    </div>
  );
}
