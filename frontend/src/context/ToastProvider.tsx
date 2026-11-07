// frontend/src/context/ToastProvider.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ToastContext } from "./toastContext";
import type { ToastItem, ToastType } from "./toastContext";

interface Props {
  children: ReactNode;
}

const TOAST_TTL_MS = 3500;

export function ToastProvider({ children }: Props) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timersRef = useRef<Set<number>>(new Set());
  const nextIdRef = useRef(1);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = "info") => {
      const id = nextIdRef.current;
      nextIdRef.current += 1;

      setToasts((prev) => [...prev, { id, message, type }]);

      const timer = window.setTimeout(() => {
        timersRef.current.delete(timer);
        removeToast(id);
      }, TOAST_TTL_MS);
      timersRef.current.add(timer);
    },
    [removeToast]
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const timer of timers) {
        window.clearTimeout(timer);
      }
      timers.clear();
    };
  }, []);

  const value = useMemo(
    () => ({ toasts, showToast, removeToast }),
    [toasts, showToast, removeToast]
  );

  return (
    <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
  );
}
