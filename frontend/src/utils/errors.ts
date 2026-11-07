// frontend/src/utils/errors.ts
import { ApiError } from "../api/client";

/**
 * Человекочитаемое сообщение для любого исключения.
 */
export function getErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.detail;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "Неизвестная ошибка";
}
