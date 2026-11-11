import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchAdminDashboard } from "../../../api/admin";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import { formatMoney } from "../../../utils/format";
import styles from "../Admin.module.css";

const PERIOD_OPTIONS = [
  { value: 7, label: "7 дней" },
  { value: 30, label: "30 дней" },
  { value: 90, label: "90 дней" },
];

export function AdminDashboardPage() {
  const [periodDays, setPeriodDays] = useState(7);
  const q = useApiQuery(
    `admin:dashboard:${periodDays}`,
    () => fetchAdminDashboard(periodDays)
  );

  return (
    <div>
      <div className={styles.heading}>
        <div>
          <h1 className={styles.title}>Обзор</h1>
          <p className={styles.subtitle}>
            Метрики магазина за выбранный период.
          </p>
        </div>
        <select
          className={styles.select}
          value={periodDays}
          onChange={(e) => setPeriodDays(Number(e.target.value))}
        >
          {PERIOD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {q.loading && <p className={styles.muted}>Загрузка…</p>}
      {q.error && <p className={styles.error}>{q.error}</p>}

      {!q.loading && !q.error && q.data && (
        <>
          <div className={styles.cards}>
            <div className={styles.card}>
              <span className={styles.cardLabel}>Заказы</span>
              <strong className={styles.cardValue}>{q.data.orders_count}</strong>
              <span className={styles.cardHint}>за {q.data.period_days} дн.</span>
            </div>

            <div className={styles.card}>
              <span className={styles.cardLabel}>Выручка</span>
              <strong className={styles.cardValue}>
                {formatMoney(q.data.revenue_net)}
              </strong>
              <span className={styles.cardHint}>
                gross: {formatMoney(q.data.revenue_gross)}
                {q.data.refunds_total !== "0.00" &&
                  ` · возвраты: ${formatMoney(q.data.refunds_total)}`}
              </span>
            </div>

            <div className={styles.card}>
              <span className={styles.cardLabel}>Новые пользователи</span>
              <strong className={styles.cardValue}>{q.data.new_users_count}</strong>
              <span className={styles.cardHint}>за {q.data.period_days} дн.</span>
            </div>

            <div className={styles.card}>
              <span className={styles.cardLabel}>Возвраты</span>
              <strong className={styles.cardValue}>
                {formatMoney(q.data.refunds_total)}
              </strong>
              <span className={styles.cardHint}>за {q.data.period_days} дн.</span>
            </div>
          </div>

          <section className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>Топ-5 товаров по выручке</h2>
              <Link to="/admin/orders" className={styles.link}>
                Все заказы →
              </Link>
            </div>

            {q.data.top_products.length === 0 ? (
              <p className={styles.muted}>За период продаж не было.</p>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Товар</th>
                      <th>Количество</th>
                      <th>Выручка</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.top_products.map((p, i) => (
                      <tr key={p.product_id}>
                        <td>{i + 1}</td>
                        <td>{p.product_name}</td>
                        <td>{p.total_quantity}</td>
                        <td>{formatMoney(p.total_revenue)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}