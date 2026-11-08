import { useState } from "react";
import type { FormEvent } from "react";
import {
  createAdminProduct,
  deleteAdminProduct,
  listAdminProducts,
  updateAdminProduct,
} from "../../../api/admin";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import { useToast } from "../../../hooks/useToast";
import { getErrorMessage } from "../../../utils/errors";
import { formatMoney } from "../../../utils/format";
import type {
  ProductListItem,
  ProductStatus,
} from "../../../types/product";
import type { AdminProductListParams } from "../../../types/admin";
import styles from "../Admin.module.css";

const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: ProductStatus | ""; label: string }[] = [
  { value: "", label: "Все" },
  { value: "available", label: "В наличии" },
  { value: "out_of_stock", label: "Нет в наличии" },
  { value: "discontinued", label: "Снят с производства" },
];

interface EditState {
  id: number;
  name: string;
  cost: string;
  status: ProductStatus;
}

export function AdminProductsPage() {
  const { showToast } = useToast();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<ProductStatus | "">("");
  const [query, setQuery] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [pending, setPending] = useState(false);
  const [editing, setEditing] = useState<EditState | null>(null);

  // Create form
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCost, setNewCost] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newCategoryId, setNewCategoryId] = useState("");

  const params: AdminProductListParams = {
    page,
    page_size: PAGE_SIZE,
    q: query.trim() || undefined,
    status: status || undefined,
  };

  const q = useApiQuery(
    JSON.stringify({ page, status, query, reloadKey }),
    () => listAdminProducts(params)
  );

  function reload() {
    setReloadKey((k) => k + 1);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newName.trim() || !newCost.trim() || !newCategoryId.trim()) {
      showToast("Заполните имя, цену и категорию", "error");
      return;
    }
    setPending(true);
    try {
      await createAdminProduct({
        name: newName.trim(),
        description: newDescription.trim() || "—",
        cost: newCost.trim(),
        category_id: Number(newCategoryId),
        status: "available",
      });
      showToast("Товар создан", "success");
      setNewName("");
      setNewCost("");
      setNewDescription("");
      setNewCategoryId("");
      setCreating(false);
      reload();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  async function handleSave(edit: EditState) {
    setPending(true);
    try {
      await updateAdminProduct(edit.id, {
        name: edit.name,
        cost: edit.cost,
        status: edit.status,
      });
      showToast("Товар обновлён", "success");
      setEditing(null);
      reload();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm("Удалить товар безвозвратно?")) return;
    setPending(true);
    try {
      await deleteAdminProduct(id);
      showToast("Товар удалён", "info");
      reload();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <div className={styles.heading}>
        <div>
          <h1 className={styles.title}>Товары</h1>
          <p className={styles.subtitle}>
            Все товары (включая soft-deleted). Удаление — безвозвратно, только
            если товар не в заказах.
          </p>
        </div>
        <button
          type="button"
          className={styles.primaryButton}
          onClick={() => setCreating((v) => !v)}
        >
          {creating ? "Отмена" : "+ Создать"}
        </button>
      </div>

      {creating && (
        <form className={styles.form} onSubmit={handleCreate}>
          <input
            className={styles.input}
            placeholder="Название"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
          <input
            className={styles.input}
            placeholder="Цена (напр. 1999.99)"
            value={newCost}
            onChange={(e) => setNewCost(e.target.value)}
            required
          />
          <input
            className={styles.input}
            placeholder="ID категории"
            value={newCategoryId}
            onChange={(e) => setNewCategoryId(e.target.value)}
            required
          />
          <input
            className={styles.input}
            placeholder="Описание (опц.)"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
          />
          <button type="submit" className={styles.primaryButton} disabled={pending}>
            Создать
          </button>
        </form>
      )}

      <div className={styles.form} style={{ marginBottom: "1rem" }}>
        <input
          className={styles.input}
          placeholder="Поиск по имени/описанию/категории"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
        <select
          className={styles.select}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as ProductStatus | "");
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
            <p className={styles.muted}>Товаров нет.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Название</th>
                    <th>Цена</th>
                    <th>Статус</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((p: ProductListItem) => {
                    const isEditing = editing?.id === p.id;
                    return (
                      <tr key={p.id}>
                        <td>{p.id}</td>
                        <td>
                          {isEditing ? (
                            <input
                              className={styles.input}
                              value={editing.name}
                              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                            />
                          ) : p.name}
                        </td>
                        <td>
                          {isEditing ? (
                            <input
                              className={styles.input}
                              value={editing.cost}
                              onChange={(e) => setEditing({ ...editing, cost: e.target.value })}
                            />
                          ) : formatMoney(p.cost)}
                        </td>
                        <td>
                          {isEditing ? (
                            <select
                              className={styles.select}
                              value={editing.status}
                              onChange={(e) => setEditing({ ...editing, status: e.target.value as ProductStatus })}
                            >
                              <option value="available">В наличии</option>
                              <option value="out_of_stock">Нет в наличии</option>
                              <option value="discontinued">Снят с производства</option>
                            </select>
                          ) : p.status}
                        </td>
                        <td>
                          {isEditing ? (
                            <>
                              <button
                                className={styles.primaryButton}
                                onClick={() => void handleSave(editing)}
                                disabled={pending}
                              >
                                Сохранить
                              </button>
                              <button
                                className={styles.secondaryButton}
                                onClick={() => setEditing(null)}
                                disabled={pending}
                                style={{ marginLeft: "0.4rem" }}
                              >
                                Отмена
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                className={styles.secondaryButton}
                                onClick={() => setEditing({
                                  id: p.id, name: p.name, cost: String(p.cost), status: p.status,
                                })}
                              >
                                Редактировать
                              </button>
                              <button
                                className={styles.dangerButton}
                                onClick={() => void handleDelete(p.id)}
                                disabled={pending}
                                style={{ marginLeft: "0.4rem" }}
                              >
                                Удалить
                              </button>
                            </>
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