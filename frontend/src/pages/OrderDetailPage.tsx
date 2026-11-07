// frontend/src/pages/OrderDetailPage.tsx
import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { fetchOrder, payOrder } from "../api/orders";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../utils/errors";
import { formatDate, formatMoney } from "../utils/format";
import {
  paymentMethodLabel,
  paymentStatusLabel,
} from "../utils/labels";
import type { OrderResponse } from "../types/order";
import type { PaymentMethod } from "../types/payment";

const PAYMENT_METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "card", label: "Банковская карта" },
  { value: "bank_transfer", label: "Банковский перевод" },
  { value: "crypto", label: "Криптовалюта" },
  { value: "cash", label: "Наличные" },
];

export function OrderDetailPage() {
  const { publicId } = useParams<{ publicId: string }>();
  const location = useLocation();
  const { showToast } = useToast();

  const [order, setOrder] = useState<OrderResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("card");
  const [paying, setPaying] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  const justCreated =
    typeof location.state === "object" &&
    location.state !== null &&
    "justCreated" in location.state &&
    (location.state as { justCreated?: unknown }).justCreated === true;

  useEffect(() => {
    if (publicId === undefined) {
      setError("Некорректный идентификатор заказа");
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchOrder(publicId)
      .then((data) => {
        if (!cancelled) setOrder(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [publicId, reloadKey]);

  async function handlePay() {
    if (order === null) return;

    setPaying(true);
    setPaymentError(null);
    try {
      await payOrder(order.public_id, {
        method: paymentMethod,
        external_id: crypto.randomUUID(),
      });
      const updated = await fetchOrder(order.public_id);
      setOrder(updated);
      showToast("Заказ оплачен", "success");
    } catch (err) {
      setPaymentError(getErrorMessage(err));
    } finally {
      setPaying(false);
    }
  }

  if (loading && order === null) {
    return <LoadingState />;
  }

  if (error !== null) {
    return (
      <ErrorState
        message={error}
        onRetry={() => setReloadKey((key) => key + 1)}
      />
    );
  }

  if (order === null) {
    return <LoadingState />;
  }

  return (
    <div className="order-detail">
      <div className="page-heading">
        <h1>Заказ {order.public_id}</h1>
        <Link to="/orders">← Мои заказы</Link>
      </div>

      {justCreated && (
        <p className="form__hint form__hint--success">
          Заказ создан. Выберите способ оплаты и подтвердите платёж.
        </p>
      )}

      <div className="order-detail__header">
        <StatusBadge kind="order" status={order.status} />
        <span className="muted">{formatDate(order.created_at)}</span>
      </div>

      <div className="order-detail__layout">
        <div className="order-detail__main">
          <section className="checkout-section">
            <h2>Товары</h2>
            <div className="cart-list cart-list--compact">
              {order.items.map((item) => (
                <div className="cart-item" key={item.public_id}>
                  <div className="cart-item__cover">
                    {item.product.cover_url !== null ? (
                      <img
                        src={item.product.cover_url}
                        alt={item.product.name}
                      />
                    ) : (
                      <div className="cart-item__no-cover">
                        Нет изображения
                      </div>
                    )}
                  </div>
                  <div className="cart-item__info">
                    <Link
                      to={`/products/${item.product.id}`}
                      className="cart-item__name"
                    >
                      {item.product.name}
                    </Link>
                    <p className="muted">{item.product_count} шт.</p>
                  </div>
                  <div className="cart-item__price">
                    {formatMoney(item.product_cost)}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="checkout-section">
            <h2>Адрес доставки</h2>
            <p>
              {order.shipping_address.city},{" "}
              {order.shipping_address.address_line1},{" "}
              {order.shipping_address.postal_code},{" "}
              {order.shipping_address.country}
            </p>
          </section>

          <section className="checkout-section">
            <h2>Платежи</h2>
            {order.payments.length === 0 ? (
              <p className="muted">Платежей пока нет.</p>
            ) : (
              <div className="payments-list">
                {order.payments.map((payment) => (
                  <div className="payment-row" key={payment.public_id}>
                    <span>{paymentMethodLabel(payment.method)}</span>
                    <span>{formatMoney(payment.amount)}</span>
                    <span>{paymentStatusLabel(payment.status)}</span>
                    <span className="muted">
                      {payment.paid_at !== null
                        ? formatDate(payment.paid_at)
                        : formatDate(payment.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <aside className="cart-summary">
          <h2>Суммы</h2>

          <div className="cart-summary__row">
            <span>Сумма</span>
            <span>{formatMoney(order.subtotal)}</span>
          </div>

          {order.discount_amount !== null && (
            <div className="cart-summary__row cart-summary__row--discount">
              <span>Скидка</span>
              <span>−{formatMoney(order.discount_amount)}</span>
            </div>
          )}

          {order.promo_code !== null && (
            <div className="cart-summary__row">
              <span>Промокод</span>
              <span>{order.promo_code}</span>
            </div>
          )}

          <div className="cart-summary__row cart-summary__row--total">
            <span>Итого</span>
            <span>{formatMoney(order.total)}</span>
          </div>

          {order.status === "pending" && (
            <div className="payment-form">
              <h3>Оплата</h3>
              <label className="form__field">
                <span>Способ оплаты</span>
                <select
                  value={paymentMethod}
                  onChange={(e) =>
                    setPaymentMethod(e.target.value as PaymentMethod)
                  }
                >
                  {PAYMENT_METHODS.map((method) => (
                    <option key={method.value} value={method.value}>
                      {method.label}
                    </option>
                  ))}
                </select>
              </label>

              {paymentError !== null && (
                <p className="form__error">{paymentError}</p>
              )}

              <button
                type="button"
                className="btn btn--primary btn--block"
                onClick={() => void handlePay()}
                disabled={paying}
              >
                {paying ? "Оплачиваем..." : "Оплатить"}
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
