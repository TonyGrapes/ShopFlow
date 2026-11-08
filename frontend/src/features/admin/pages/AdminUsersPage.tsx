import { useState } from "react";
import {
  listAdminUsers,
  updateUserRole,
  updateUserStatus,
} from "../../../api/admin";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import { useAuth } from "../../../hooks/useAuth";
import { useToast } from "../../../hooks/useToast";
import { getErrorMessage } from "../../../utils/errors";
import { formatDate } from "../../../utils/format";
import { roleLabel, userStatusLabel } from "../../../utils/labels";
import type { UserRole, UserStatus } from "../../../types/auth";
import type { AdminUserListParams } from "../../../types/admin";
import styles from "../Admin.module.css";

const PAGE_SIZE = 20;

const ROLE_OPTIONS: { value: UserRole | ""; label: string }[] = [
  { value: "", label: "Все роли" },
  { value: "customer", label: "Клиент" },
  { value: "moderator", label: "Модератор" },
  { value: "admin", label: "Админ" },
  { value: "seller", label: "Продавец" },
];

const STATUS_OPTIONS: { value: UserStatus | ""; label: string }[] = [
  { value: "", label: "Все статусы" },
  { value: "active", label: "Активен" },
  { value: "banned", label: "Забанен" },
  { value: "pending", label: "Ожидает" },
];

export function AdminUsersPage() {
  const { user: me } = useAuth();
  const { showToast } = useToast();
  const [page, setPage] = useState(1);
  const [role, setRole] = useState<UserRole | "">("");
  const [status, setStatus] = useState<UserStatus | "">("");
  const [reloadKey, setReloadKey] = useState(0);
  const [pending, setPending] = useState<string | null>(null);

  const params: AdminUserListParams = {
    page,
    page_size: PAGE_SIZE,
    role: role || undefined,
    status: status || undefined,
  };

  const q = useApiQuery(
    JSON.stringify({ page, role, status, reloadKey }),
    () => listAdminUsers(params)
  );

  function reload() {
    setReloadKey((k) => k + 1);
  }

  async function handleRole(publicId: string, next: UserRole) {
    setPending(publicId);
    try {
      await updateUserRole(publicId, { role: next });
      showToast("Роль обновлена", "success");
      reload();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(null);
    }
  }

  async function handleBan(publicId: string, next: UserStatus) {
    setPending(publicId);
    try {
      await updateUserStatus(publicId, { status: next });
      showToast(next === "banned" ? "Пользователь забанен" : "Пользователь разбанен", "success");
      reload();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(null);
    }
  }

  const isAdmin = me?.role === "admin";

  return (
    <div>
      <div className={styles.heading}>
        <div>
          <h1 className={styles.title}>Пользователи</h1>
          <p className={styles.subtitle}>
            Управление ролями и статусами. Бан отзывает refresh-токены.
          </p>
        </div>
      </div>

      <div className={styles.form} style={{ marginBottom: "1rem" }}>
        <select
          className={styles.select}
          value={role}
          onChange={(e) => {
            setRole(e.target.value as UserRole | "");
            setPage(1);
          }}
        >
          {ROLE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          className={styles.select}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as UserStatus | "");
            setPage(1);
          }}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {q.loading && <p className={styles.muted}>Загрузка…</p>}
      {q.error && <p className={styles.error}>{q.error}</p>}

      {!q.loading && !q.error && q.data && (
        <>
          {q.data.items.length === 0 ? (
            <p className={styles.muted}>Пользователей нет.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Имя</th>
                    <th>Роль</th>
                    <th>Статус</th>
                    <th>Создан</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((u) => {
                    const isSelf = me?.public_id === u.public_id;
                    const isPending = pending === u.public_id;
                    return (
                      <tr key={u.public_id}>
                        <td>{u.email}</td>
                        <td>{u.first_name} {u.last_name}</td>
                        <td>
                          {isAdmin && !isSelf ? (
                            <select
                              className={styles.select}
                              value={u.role}
                              disabled={isPending}
                              onChange={(e) => void handleRole(u.public_id, e.target.value as UserRole)}
                            >
                              <option value="customer">Клиент</option>
                              <option value="moderator">Модератор</option>
                              <option value="admin">Админ</option>
                              <option value="seller">Продавец</option>
                            </select>
                          ) : (
                            roleLabel(u.role)
                          )}
                        </td>
                        <td>{userStatusLabel(u.status)}</td>
                        <td>{formatDate(u.created_at)}</td>
                        <td>
                          {!isSelf && (
                            u.status === "banned" ? (
                              <button
                                className={styles.secondaryButton}
                                onClick={() => void handleBan(u.public_id, "active")}
                                disabled={isPending}
                              >
                                Разбанить
                              </button>
                            ) : (
                              <button
                                className={styles.dangerButton}
                                onClick={() => void handleBan(u.public_id, "banned")}
                                disabled={isPending}
                              >
                                Забанить
                              </button>
                            )
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ marginTop: "1rem" }}>
            <button
              className={styles.secondaryButton}
              disabled={page <= 1}
              onClick={() => setPage((n) => Math.max(1, n - 1))}
            >
              ← Предыдущая
            </button>
            <span style={{ margin: "0 0.75rem" }}>
              Страница {page} из {Math.max(1, Math.ceil(q.data.total / PAGE_SIZE))}
            </span>
            <button
              className={styles.secondaryButton}
              disabled={page >= Math.ceil(q.data.total / PAGE_SIZE)}
              onClick={() => setPage((n) => n + 1)}
            >
              Следующая →
            </button>
          </div>
        </>
      )}
    </div>
  );
}