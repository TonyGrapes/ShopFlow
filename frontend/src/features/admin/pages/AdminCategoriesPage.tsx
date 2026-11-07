import { useState } from "react";
import {
  createCategory,
  deleteCategory,
  type CategoryWrite,
} from "../../../api/admin";
import { fetchCategories } from "../../../api/categories";
import { useApiQuery } from "../../../shared/hooks/useApiQuery";
import { useToast } from "../../../hooks/useToast";
import { getErrorMessage } from "../../../utils/errors";
import styles from "../Admin.module.css";

export function AdminCategoriesPage() {
  const { showToast } = useToast();
  const query = useApiQuery("categories", fetchCategories, []);
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [pending, setPending] = useState(false);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;

    const payload: CategoryWrite = { category_name: name.trim() };
    if (parentId) payload.parent_id = Number(parentId);

    setPending(true);
    try {
      await createCategory(payload);
      showToast("Категория создана", "success");
      setName("");
      setParentId("");
      query.refetch();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  async function handleDelete(id: number) {
    setPending(true);
    try {
      await deleteCategory(id);
      showToast("Категория удалена", "success");
      query.refetch();
    } catch (err) {
      showToast(getErrorMessage(err), "error");
    } finally {
      setPending(false);
    }
  }

  const categories = query.data ?? [];

  return (
    <div>
      <div className={styles.heading}>
        <div>
          <h1 className={styles.title}>Категории</h1>
          <p className={styles.subtitle}>
            Дерево каталога. Удаление доступно только для пустых листьев.
          </p>
        </div>
      </div>

      <form className={styles.form} onSubmit={handleCreate}>
        <input
          className={styles.input}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Название категории"
          aria-label="Название категории"
          required
        />
        <select
          className={styles.select}
          value={parentId}
          onChange={(event) => setParentId(event.target.value)}
          aria-label="Родительская категория"
        >
          <option value="">Корневая категория</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.category_name}
            </option>
          ))}
        </select>
        <button type="submit" className={styles.primaryButton} disabled={pending}>
          Создать
        </button>
      </form>

      {query.loading && <p className={styles.muted}>Загрузка…</p>}
      {query.error && <p className={styles.error}>{query.error}</p>}

      {!query.loading && !query.error && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Название</th>
                <th>Path</th>
                <th>Родитель</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {categories.map((category) => (
                <tr key={category.id}>
                  <td>{category.id}</td>
                  <td>{category.category_name}</td>
                  <td className={styles.mono}>{category.path}</td>
                  <td>{category.parent_id ?? "—"}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.dangerButton}
                      disabled={pending}
                      onClick={() => void handleDelete(category.id)}
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
