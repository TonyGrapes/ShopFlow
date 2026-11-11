import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchAdminDashboard, fetchAdminDashboardSeries, downloadDashboardCsv } from "../../../api/admin";
import { RevenueChart } from "../components/RevenueChart";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import { formatMoney } from "../../../utils/format";
import styles from "../Admin.module.css";
import { useToast } from "../../../hooks/useToast";


const PERIOD_OPTIONS = [
  { value: 7, label: "7 дней" },
  { value: 30, label: "30 дней" },
  { value: 90, label: "90 дней" },
];


export function AdminDashboardPage() {
  const { showToast } = useToast();
  const [periodDays, setPeriodDays] = useState(7);
  const q = useApiQuery(
    `admin:dashboard:${periodDays}`,
    () => fetchAdminDashboard(periodDays)
  );
  const series = useApiQuery(
    `admin:dashboard:series:${periodDays}`,
    () => fetchAdminDashboardSeries(periodDays)
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
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <select
            className={styles.select}
            value={periodDays}
            onChange={(e) => setPeriodDays(Number(e.target.value))}
          >
            {PERIOD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => {
              void downloadDashboardCsv(periodDays).catch((err) => {
                showToast(
                  err instanceof Error ? err.message : "Ошибка скачивания",
                  "error"
                );
              });
            }}
          >
            Скачать CSV
          </button>
        </div>
      </div>

      {q.loading && <p className={styles.muted}>Загрузка…</p>}
      {q.error && <p className={styles.error}>{q.error}</p>}

      {!q.loading && !q.error && q.data && (
        <>
          <div className={styles.cards}>
            <DeltaCard
              label="Заказы"
              value={String(q.data.orders_count)}
              deltaPct={q.data.orders_count_delta_pct}
              prev={String(q.data.orders_count_prev)}
              periodDays={q.data.period_days}
            />

            <DeltaCard
              label="Выручка"
              value={formatMoney(q.data.revenue_net)}
              deltaPct={q.data.revenue_gross_delta_pct}
              prev={formatMoney(q.data.revenue_gross_prev)}
              periodDays={q.data.period_days}
              hint={`gross: ${formatMoney(q.data.revenue_gross)} · возвраты: ${formatMoney(q.data.refunds_total)}`}
            />

            <DeltaCard
              label="Новые пользователи"
              value={String(q.data.new_users_count)}
              deltaPct={q.data.new_users_count_delta_pct}
              prev={String(q.data.new_users_count_prev)}
              periodDays={q.data.period_days}
            />

            <DeltaCard
              label="Возвраты"
              value={formatMoney(q.data.refunds_total)}
              deltaPct={q.data.refunds_total_delta_pct}
              prev={formatMoney(q.data.refunds_total_prev)}
              periodDays={q.data.period_days}
            />
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
            <section className={styles.panel} style={{ marginTop: "1rem" }}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>Выручка по дням</h2>
            </div>
            {series.loading && <p className={styles.muted}>Загрузка графика…</p>}
            {series.error && <p className={styles.error}>{series.error}</p>}
            {!series.loading && !series.error && series.data && (
              <RevenueChart items={series.data.items} />
            )}
          </section>
        </>
      )}
    </div>
  );
}

interface DeltaCardProps {
  label: string;
  value: string;
  deltaPct: number | null;
  prev: string;
  periodDays: number;
  hint?: string;
}

function DeltaCard({ label, value, deltaPct, prev, periodDays, hint }: DeltaCardProps) {
  return (
    <div className={styles.card}>
      <span className={styles.cardLabel}>{label}</span>
      <strong className={styles.cardValue}>{value}</strong>
      <DeltaBadge value={deltaPct} />
      <span className={styles.cardHint}>
        было {prev} за пред. {periodDays} дн.
      </span>
      {hint !== undefined && <span className={styles.cardHint}>{hint}</span>}
    </div>
  );
}

function DeltaBadge({ value }: { value: number | null }) {
  if (value === null) {
    return <span className={styles.muted}>—</span>;
  }
  if (value === 0) {
    return <span className={styles.muted}>→ 0%</span>;
  }
  const positive = value > 0;
  const arrow = positive ? "↑" : "↓";
  const color = positive ? "#1b5e20" : "#c02626";
  return (
    <span style={{ color, fontWeight: 600, fontSize: 14 }}>
      {arrow} {Math.abs(value).toFixed(1)}%
    </span>
  );
}