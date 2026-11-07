// frontend/src/api/client.ts
/**
 * Типизированная обёртка над fetch.
 *
 * Принципы:
 * - Ошибки (4xx/5xx) → ApiError, не глотаем.
 * - Базовый URL — из VITE_API_URL.
 * - Все запросы идут с credentials: "include" (refresh/guest-cart cookies).
 * - 401 → однократный refresh + replay исходного запроса.
 * - Auth-эндпоинты помечаются skipAuthRefresh/auth:false, чтобы
 *   не получить рекурсию.
 */
import { API_BASE_URL } from "./config";
import {
  getAccessToken,
  notifyUnauthorized,
  refreshAccessToken,
} from "./session";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly code: string | null;
  readonly extra: Record<string, unknown>;

  constructor(
    status: number,
    detail: string,
    code: string | null = null,
    extra: Record<string, unknown> = {}
  ) {
    super(`API Error ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
    this.extra = extra;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE" | "PUT";
  body?: unknown;
  params?: object;
  headers?: Record<string, string>;
  /** Не пытаться обновлять токен при 401 (auth-эндпоинты). */
  skipAuthRefresh?: boolean;
  /** Не отправлять Authorization (login/register/logout). */
  auth?: boolean;
}

type WriteOptions = Omit<RequestOptions, "method" | "body" | "params">;

/**
 * Собирает URL с query-параметрами.
 *
 * undefined/null/"" не попадают в URL.
 */
function buildUrl(path: string, params?: object): string {
  const url = new URL(`${API_BASE_URL}${path}`);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.append(key, String(value));
      }
    }
  }

  return url.toString();
}

function formatDetail(raw: unknown): string {
  if (typeof raw === "string") return raw;

  // FastAPI ValidationError: detail — массив {loc, msg, type}.
  if (Array.isArray(raw)) {
    const messages = raw.map((item) => {
      if (typeof item === "object" && item !== null) {
        const record = item as Record<string, unknown>;
        const msg =
          typeof record.msg === "string" ? record.msg : "Validation error";
        const loc = Array.isArray(record.loc)
          ? record.loc.map((part) => String(part)).join(".")
          : "";
        return loc ? `${loc}: ${msg}` : msg;
      }
      return String(item);
    });
    return messages.join("; ");
  }

  return "Request failed";
}

async function buildApiError(response: Response): Promise<ApiError> {
  let text = "";
  try {
    text = await response.text();
  } catch {
    // Тело недоступно — остаётся statusText.
  }

  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      // Не JSON — используем текст как detail.
    }
  }

  let detail = response.statusText || "Request failed";
  let code: string | null = null;
  const extra: Record<string, unknown> = {};

  if (typeof body === "object" && body !== null && !Array.isArray(body)) {
    const record = body as Record<string, unknown>;
    if ("detail" in record) {
      detail = formatDetail(record.detail);
    }
    if (typeof record.code === "string") {
      code = record.code;
    }
    for (const [key, value] of Object.entries(record)) {
      if (key !== "detail" && key !== "code") {
        extra[key] = value;
      }
    }
  } else if (text) {
    detail = text;
  }

  return new ApiError(response.status, detail, code, extra);
}

async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
  retried = false
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...options.headers,
  };

  const token = getAccessToken();
  if (token !== null && options.auth !== false) {
    headers.Authorization = `Bearer ${token}`;
  }

  let body: string | undefined;
  if (options.body !== undefined) {
    body = JSON.stringify(options.body);
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.params), {
      method,
      headers,
      body,
      credentials: "include",
    });
  } catch (err) {
    throw new Error(
      `Network error: ${err instanceof Error ? err.message : "unknown"}`
    );
  }

  if (!response.ok) {
    const shouldTryRefresh =
      response.status === 401 &&
      !options.skipAuthRefresh &&
      options.auth !== false;

    if (shouldTryRefresh) {
      if (!retried) {
        const refreshed = await refreshAccessToken();
        if (refreshed !== null) {
          return apiRequest<T>(path, options, true);
        }
      }
      notifyUnauthorized();
    }

    throw await buildApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

export function apiGet<T>(path: string, params?: object): Promise<T> {
  return apiRequest<T>(path, { method: "GET", params });
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  options?: WriteOptions
): Promise<T> {
  return apiRequest<T>(path, { ...options, method: "POST", body });
}

export function apiPatch<T>(
  path: string,
  body?: unknown,
  options?: WriteOptions
): Promise<T> {
  return apiRequest<T>(path, { ...options, method: "PATCH", body });
}

export function apiDelete<T>(
  path: string,
  options?: WriteOptions
): Promise<T> {
  return apiRequest<T>(path, { ...options, method: "DELETE" });
}

export { API_BASE_URL };
