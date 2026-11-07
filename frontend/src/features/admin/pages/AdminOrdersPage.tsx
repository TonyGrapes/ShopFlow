import { useState } from "react";
import { listAdminOrders, updateAdminOrderStatus } from "../../../api/admin";
import { Pagination } from "../../../components/Pagination";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import { useToast } from "../../../hooks/useToast";
import { getErrorMessage } from "../../../utils/errors";
import { formatDate, formatMoney } from "../../../utils/format";
import { orderStatusLabel } from "../../../utils/labels";
import type { OrderStatus } from "../../../types/order";
import styles from "../Admin.module.css";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: OrderStatus | ""; label: string }[] = [
  { value: "", label: "Все статусы" },
  { value: "pending", label: "Ожидает оплаты" },
  { value: "paid", label: "Оплачен" },
  { value: "shipped", label: "Отправлен" },
  { value: "delivered", label: "Доставлен" },
  { value: "canceled", label: "Отменён" },
];

const NEXT_STATUSES: OrderStatus[] = [
  "pending",
  "paid",
  "shipped",
  "delivered",
  "canceled",
];

export function AdminOrdersPage() {
  const { showToast } = useToast();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [reloadKey, setReloadKey] = useState(0);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const query = useApiQuery(
    JSON.stringify({ page, status, reloadKey }),
    () =>
      listAdminOrders({
        page,
        page_size: PAGE_SIZE,
        status: status || undefined,
      })
  );

  async function handleStatus(publicId: string, next: OrderStatus) {
    setPendingId(publicId);
    try {
      await updateAdminOrderStatus(publicId, next);
      showToast("Статус заказа обновлён", "success");
      setReloadKey((key) => key + 1);
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div>
      <div className={styles.heading}>
        <div>
          <h1 className={styles.title}>Заказы</h1>
          <p className={styles.subtitle}>
            Все заказы магазина. Смена статуса валидируется backend-переходами.
          </p>
        </div>
        <select
          className={styles.select}
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as OrderStatus | "");
            setPage(1);
          }}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {query.loading && <p className={styles.muted}>Загрузка…</p>}
      {query.error && (
        <div className={styles.errorBox} role="alert">
          <p>{query.error}</p>
          <button type="button" className="btn btn--secondary btn--sm" onClick={query.refetch}>
            Повторить
          </button>
        </div>
      )}

      {!query.loading && !query.error && query.data && (
        <>
          {query.data.items.length === 0 ? (
            <p className={styles.muted}>Заказов нет.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Заказ</th>
                    <th>Дата</th>
                    <th>Позиции</th>
                    <th>Сумма</th>
                    <th>Статус</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((order) => (
                    <tr key={order.public_id}>
                      <td>#{order.public_id.slice(0, 8)}</td>
                      <td>{formatDate(order.created_at)}</td>
                      <td>{order.items_count}</td>
                      <td>{formatMoney(order.total)}</td>
                      <td>{orderStatusLabel(order.status)}</td>
                      <td>
                        <select
                          className={styles.select}
                          value={order.status}
                          disabled={pendingId === order.public_id}
                          onChange={(event) =>
                            void handleStatus(
                              order.public_id,
                              event.target.value as OrderStatus
                            )
                          }
                        >
                          {NEXT_STATUSES.map((next) => (
                            <option key={next} value={next}>
                              {orderStatusLabel(next)}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={query.data.total}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
