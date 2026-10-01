// frontend/src/components/Pagination.tsx
interface Props {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  const canPrev = page > 1;
  const canNext = page < totalPages;

  return (
    <div className="pagination">
      <button
        disabled={!canPrev}
        onClick={() => onChange(page - 1)}
        aria-label="Предыдущая страница"
      >
        ← Предыдущая
      </button>

      <span className="pagination__info">
        Страница {page} из {totalPages} (всего {total})
      </span>

      <button
        disabled={!canNext}
        onClick={() => onChange(page + 1)}
        aria-label="Следующая страница"
      >
        Следующая →
      </button>
    </div>
  );
}