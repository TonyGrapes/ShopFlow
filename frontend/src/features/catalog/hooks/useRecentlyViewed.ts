import { useCallback, useState } from "react";

const STORAGE_KEY = "shopflow.recently-viewed";
const LIMIT = 8;

function readIds(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is number => Number.isInteger(id)).slice(0, LIMIT);
  } catch {
    return [];
  }
}

export function useRecentlyViewed() {
  const [ids, setIds] = useState<number[]>(readIds);

  const push = useCallback((productId: number) => {
    setIds((prev) => {
      const next = [productId, ...prev.filter((id) => id !== productId)].slice(
        0,
        LIMIT
      );
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Private mode / storage full — history is non-critical.
      }
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setIds([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  return { ids, push, clear };
}
