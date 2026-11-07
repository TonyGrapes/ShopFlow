import type { ReactNode } from "react";

interface Props {
  loading: boolean;
  error: string | null;
  empty: boolean;
  loadingText?: string;
  emptyText?: string;
  onRetry?: () => void;
  children: ReactNode;
}

/**
 * Shared three-state boundary for data-driven screens.
 * Feature-specific visuals can still use their own state components.
 */
export function AsyncState({
  loading,
  error,
  empty,
  loadingText = "Загрузка…",
  emptyText = "Нет данных",
  onRetry,
  children,
}: Props) {
  if (loading) return <p className="state">{loadingText}</p>;
  if (error) {
    return (
      <div className="state state--error" role="alert">
        <p>{error}</p>
        {onRetry && (
          <button type="button" className="btn btn--secondary btn--sm" onClick={onRetry}>
            Повторить
          </button>
        )}
      </div>
    );
  }
  if (empty) return <p className="state">{emptyText}</p>;
  return <>{children}</>;
}
