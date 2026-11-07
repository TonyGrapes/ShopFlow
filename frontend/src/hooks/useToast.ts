// frontend/src/hooks/useToast.ts
import { useContext } from "react";
import { ToastContext } from "../context/toastContext";

export function useToast() {
  const context = useContext(ToastContext);
  if (context === null) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
