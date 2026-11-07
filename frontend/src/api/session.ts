// frontend/src/api/session.ts
/**
 * Сессия фронтенда.
 *
 * Принципы:
 * - Access-токен живёт ТОЛЬКО в памяти (никакого localStorage).
 * - Refresh-токен — httpOnly-cookie, поэтому для его ротации
 *   обязателен credentials: "include".
 * - Single-flight refresh: параллельные 401 ждут один запрос,
 *   иначе ротация cookie может сработать дважды и backend
 *   отзовёт всю семью refresh-токенов (reuse-detection).
 */
import type { TokenResponse } from "../types/auth";
import { API_BASE_URL } from "./config";

let accessToken: string | null = null;
let refreshPromise: Promise<TokenResponse | null> | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

/** Вызывается, когда refresh невозможен: сессия окончательно потеряна. */
export function notifyUnauthorized(): void {
  accessToken = null;
  unauthorizedHandler?.();
}

/**
 * Пытается обновить access-токен по httpOnly-cookie.
 *
 * Возвращает TokenResponse при успехе и null при любой ошибке.
 * Никогда не бросает — bootstrap приложения должен спокойно
 * трактовать отсутствие refresh-cookie как гостя.
 */
export function refreshAccessToken(): Promise<TokenResponse | null> {
  if (refreshPromise === null) {
    refreshPromise = (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { Accept: "application/json" },
          credentials: "include",
        });

        if (!response.ok) {
          accessToken = null;
          return null;
        }

        const data = (await response.json()) as TokenResponse;
        accessToken = data.access_token;
        return data;
      } catch {
        accessToken = null;
        return null;
      }
    })();

    // Сбрасываем single-flight promise после завершения, чтобы
    // следующий цикл «протух → refresh» мог начаться заново.
    refreshPromise.finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}
