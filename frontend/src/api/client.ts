// frontend/src/api/client.ts
/**
 * Типизированная обёртка над fetch.
 *
 * Принципы:
 * - Ошибки (4xx/5xx) → ApiError, не глотаем.
 * - Базовый URL — из VITE_API_URL.
 * - JSON-парсинг с проверкой контента.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`API Error ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Query-параметры для GET-запросов.
 *
 * Используем `object`, а не `Record<string, unknown>`:
 * TypeScript НЕ пропускает interface без index signature в Record.
 * Типизация полей — на стороне вызывающего (ProductListParams).
 *
 * Значения: string | number | boolean | null | undefined.
 * undefined/null/"" — не попадают в URL.
 */
export async function apiGet<T>(
  path: string,
  params?: object
): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      // ✅ Пропускаем undefined, null и пустые строки
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.append(key, String(value));
      }
    }
  }

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "include",
    });
  } catch (err) {
    throw new Error(
      `Network error: ${err instanceof Error ? err.message : "unknown"}`
    );
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // не JSON — оставляем statusText
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}