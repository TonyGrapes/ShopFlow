import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { ToastContainer } from "../../components/ToastContainer";
import styles from "./AdminLayout.module.css";

function navClass({ isActive }: { isActive: boolean }): string {
  return isActive ? `${styles.link} ${styles.linkActive}` : styles.link;
}

export function AdminLayout() {
  const { user, logout } = useAuth();

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link to="/admin" className={styles.brand}>
          ShopFlow <span>Admin</span>
        </Link>

        <nav className={styles.nav} aria-label="Админ-навигация">
          <NavLink to="/admin" end className={navClass}>
            Обзор
          </NavLink>
          <NavLink to="/admin/orders" className={navClass}>
            Заказы
          </NavLink>
          <NavLink to="/admin/categories" className={navClass}>
            Категории
          </NavLink>
          <NavLink to="/admin/products" className={navClass}>
            Товары
          </NavLink>
          <NavLink to="/admin/users" className={navClass}>
            Пользователи
          </NavLink>
        </nav>

        <div className={styles.actions}>
          <Link to="/" className={styles.storeLink}>
            В магазин
          </Link>
          <span className={styles.user}>{user?.first_name}</span>
          <button type="button" className={styles.logout} onClick={() => void logout()}>
            Выйти
          </button>
        </div>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>
      <ToastContainer />
    </div>
  );
}
