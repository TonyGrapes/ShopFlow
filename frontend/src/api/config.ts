// frontend/src/api/config.ts
/**
 * Базовый URL API.
 *
 * VITE_API_URL задаётся в .env (dev: http://localhost:8000).
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";
