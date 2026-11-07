import { useCallback, useEffect, useRef, useState } from "react";
import { getErrorMessage } from "../../utils/errors";

interface ApiQueryState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Minimal, dependency-free query hook.
 *
 * `key` is a stable serialization of every input that should trigger a
 * request. `loader` may be re-created on each render; only its latest version
 * is called. This keeps feature code ergonomic without adding TanStack Query.
 */
export function useApiQuery<T>(
  key: string,
  loader: () => Promise<T>,
  initialData: T | null = null
): ApiQueryState<T> {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const [data, setData] = useState<T | null>(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refetch = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    loaderRef
      .current()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [key, reloadToken]);

  return { data, loading, error, refetch };
}
