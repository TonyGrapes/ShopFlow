import { Link } from "react-router-dom";
import { listAdminOrders } from "../../../api/admin";
import { fetchCategories } from "../../../api/categories";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import styles from "../Admin.module.css";

export function AdminDashboardPage() {
  const orders = useApiQuery("admin:orders:1", () =>
    listAdminOrders({ page: 1, page_size: 5 })
  );
  const categories = useApiQuery("categories", fetchCategories, []);

  return (
    <div>
      <div className={styles.heading}>
        <div>
          <h1 className={styles.title}>Обзор</h1>
          <p className={styles.subtitle}>
            Оперативная сводка по заказам и структуре каталога.
          </p>
        </div>
      </div>

      <div className={styles.cards}>
        <Link to="/admin/orders" className={styles.card}>
          <span className={styles.cardLabel}>Заказы</span>
          <strong className={styles.cardValue}>
            {orders.loading ? "…" : orders.data?.total ?? "—"}
          </strong>
          <span className={styles.cardHint}>Все заказы магазина</span>
        </Link>

        <Link to="/admin/categories" className={styles.card}>
          <span className={styles.cardLabel}>Категории</span>
          <strong className={styles.cardValue}>
            {categories.loading ? "…" : categories.data?.length ?? "—"}
          </strong>
          <span className={styles.cardHint}>Плоский список дерева</span>
        </Link>

        <div className={styles.card}>
          <span className={styles.cardLabel}>Последние заказы</span>
          <strong className={styles.cardValue}>
            {orders.data?.items.length ?? "—"}
          </strong>
          <span className={styles.cardHint}>На первой странице</span>
        </div>
      </div>

      <section className={styles.panel}>
        <div className={styles.panelHead}>
          <h2 className={styles.panelTitle}>Свежие заказы</h2>
          <Link to="/admin/orders" className={styles.link}>
            Все заказы →
          </Link>
        </div>

        {orders.loading && <p className={styles.muted}>Загрузка…</p>}
        {orders.error && <p className={styles.error}>{orders.error}</p>}
        {!orders.loading && !orders.error && (orders.data?.items.length ?? 0) === 0 && (
          <p className={styles.muted}>Заказов пока нет.</p>
        )}

        <ul className={styles.plainList}>
          {orders.data?.items.map((order) => (
            <li key={order.public_id} className={styles.plainRow}>
              <span>#{order.public_id.slice(0, 8)}</span>
              <span className={styles.muted}>{order.status}</span>
              <span>{order.items_count} поз.</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
