// frontend/src/components/Header.tsx
import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useCart } from "../hooks/useCart";
import { useFavorites } from "../hooks/useFavorites";
import { useToast } from "../hooks/useToast";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav__link nav__link--active" : "nav__link";
}

export function Header() {
  const { user, loading, logout } = useAuth();
  const { totalItems } = useCart();
  const { favorites } = useFavorites();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
      showToast("Вы вышли из аккаунта", "success");
      navigate("/");
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <header className="app__header">
      <Link to="/" className="app__brand">
        ShopFlow
      </Link>

      <nav className="nav" aria-label="Основная навигация">
        <NavLink to="/" end className={navLinkClass}>
          Каталог
        </NavLink>
        <NavLink to="/cart" className={navLinkClass}>
          Корзина
          {totalItems > 0 && (
            <span className="nav__badge">{totalItems > 99 ? "99+" : totalItems}</span>
          )}
        </NavLink>
        {user !== null && (
          <>
            <NavLink to="/favorites" className={navLinkClass}>
              Избранное
              {favorites.length > 0 && (
                <span className="nav__badge">{favorites.length}</span>
              )}
            </NavLink>
            <NavLink to="/orders" className={navLinkClass}>
              Заказы
            </NavLink>
            <NavLink to="/addresses" className={navLinkClass}>
              Адреса
            </NavLink>
            {(user.role === "admin" || user.role === "moderator") && (
              <NavLink to="/admin" className={navLinkClass}>
                Админка
              </NavLink>
            )}
          </>
        )}
      </nav>

      <div className="nav__actions">
        {loading ? (
          <span className="muted">Загрузка...</span>
        ) : user !== null ? (
          <>
            <span className="nav__user">{user.first_name}</span>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={handleLogout}
              disabled={loggingOut}
            >
              {loggingOut ? "Выход..." : "Выйти"}
            </button>
          </>
        ) : (
          <>
            <Link to="/login" className="btn btn--secondary btn--sm">
              Войти
            </Link>
            <Link to="/register" className="btn btn--primary btn--sm">
              Регистрация
            </Link>
          </>
        )}
      </div>
    </header>
  );
}
