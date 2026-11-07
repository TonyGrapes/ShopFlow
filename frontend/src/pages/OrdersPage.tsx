// frontend/src/pages/OrdersPage.tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listOrders } from "../api/orders";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { getErrorMessage } from "../utils/errors";
import { formatDate, formatMoney } from "../utils/format";
import { orderStatusLabel } from "../utils/labels";
import type { Paginated } from "../types/common";
import type {
  OrderListItem,
  OrderListParams,
  OrderStatus,
} from "../types/order";

const PAGE_SIZE = 10;

const STATUS_OPTIONS: { value: OrderStatus | ""; label: string }[] = [
  { value: "", label: "Все статусы" },
  { value: "pending", label: "Ожидает оплаты" },
  { value: "paid", label: "Оплачен" },
  { value: "shipped", label: "Отправлен" },
  { value: "delivered", label: "Доставлен" },
  { value: "canceled", label: "Отменён" },
];

export function OrdersPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<OrderStatus | "">("");
  const [data, setData] = useState<Paginated<OrderListItem> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const params: OrderListParams = {
      page,
      page_size: PAGE_SIZE,
    };
    if (statusFilter !== "") {
      params.status = statusFilter;
    }

    setLoading(true);
    setError(null);

    listOrders(params)
      .then((result) => {
        if (!cancelled) setData(result);
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
  }, [page, statusFilter, reloadKey]);

  return (
    <div className="orders-page">
      <div className="page-heading">
        <h1>Мои заказы</h1>
        <Link to="/">← В каталог</Link>
      </div>

      <div className="filter-bar">
        <label>
          Статус:
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as OrderStatus | "");
              setPage(1);
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <LoadingState />}

      {error !== null && (
        <ErrorState
          message={error}
          onRetry={() => setReloadKey((key) => key + 1)}
        />
      )}

      {!loading && error === null && data !== null && (
        <>
          {data.items.length === 0 ? (
            <EmptyState message="Заказов пока нет" />
          ) : (
            <div className="orders-list">
              {data.items.map((order) => (
                <Link
                  key={order.public_id}
                  to={`/orders/${order.public_id}`}
                  className="order-card"
                >
                  <div className="order-card__header">
                    <span className="order-card__number">
                      Заказ {order.public_id.slice(0, 8)}
                    </span>
                    <StatusBadge kind="order" status={order.status} />
                  </div>

                  <div className="order-card__meta">
                    <span>{formatDate(order.created_at)}</span>
                    <span>{order.items_count} поз.</span>
                    <span className="order-card__total">
                      {formatMoney(order.total)}
                    </span>
                  </div>

                  {order.discount_amount !== null && (
                    <p className="muted">
                      Скидка: −{formatMoney(order.discount_amount)}
                    </p>
                  )}

                  <span className="muted">
                    {orderStatusLabel(order.status)}
                  </span>
                </Link>
              ))}
            </div>
          )}

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={data.total}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
