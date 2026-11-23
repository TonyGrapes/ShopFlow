import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  setAccessToken,
  getAccessToken,
  setUnauthorizedHandler,
  notifyUnauthorized,
  refreshAccessToken,
} from "./session";
import { API_BASE_URL } from "./config";
import type { TokenResponse } from "../types/auth";

const TOKEN: TokenResponse = {
  access_token: "new-token",
  token_type: "bearer",
  expires_in: 60,
};

function makeResponse(init: {
  status?: number;
  json?: () => Promise<unknown>;
}): Response {
  const status = init.status ?? 200;
  return {
    ok: status >= 200 && status < 300,
    status,
    json: init.json ?? (async () => ({})),
  } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

function fetchCall(): { url: string; init: RequestInit } {
  const call = fetchMock.mock.calls[0];
  return { url: call[0] as string, init: call[1] as RequestInit };
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  setAccessToken(null);
  setUnauthorizedHandler(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("access token", () => {
  it("set/get", () => {
    setAccessToken("abc");
    expect(getAccessToken()).toBe("abc");

    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });
});

describe("notifyUnauthorized", () => {
  it("сбрасывает токен и вызывает handler", () => {
    setAccessToken("abc");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    notifyUnauthorized();

    expect(getAccessToken()).toBeNull();
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("без handler не бросает", () => {
    setUnauthorizedHandler(null);

    expect(() => notifyUnauthorized()).not.toThrow();
  });
});

describe("refreshAccessToken", () => {
  it("успех: обновляет токен и бьёт в /auth/refresh", async () => {
    fetchMock.mockResolvedValue(
      makeResponse({ status: 200, json: async () => TOKEN })
    );

    await expect(refreshAccessToken()).resolves.toEqual(TOKEN);
    expect(getAccessToken()).toBe("new-token");

    const { url, init } = fetchCall();
    expect(url).toBe(`${API_BASE_URL}/api/v1/auth/refresh`);
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect((init.headers as Record<string, string>).Accept).toBe(
      "application/json"
    );
  });

  it("не-ok ответ → null и сброс токена", async () => {
    setAccessToken("stale");
    fetchMock.mockResolvedValue(makeResponse({ status: 401 }));

    await expect(refreshAccessToken()).resolves.toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it("сетевая ошибка → null и сброс токена", async () => {
    setAccessToken("stale");
    fetchMock.mockRejectedValue(new Error("network down"));

    await expect(refreshAccessToken()).resolves.toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it("single-flight: параллельные вызовы → один fetch", async () => {
    let resolveFetch!: (r: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    fetchMock.mockReturnValue(pending);

    const p1 = refreshAccessToken();
    const p2 = refreshAccessToken();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(p2).toBe(p1);

    resolveFetch(makeResponse({ status: 200, json: async () => TOKEN }));

    await expect(p1).resolves.toEqual(TOKEN);
    await expect(p2).resolves.toEqual(TOKEN);
  });

  it("после завершения следующий вызов идёт в сеть заново", async () => {
    fetchMock.mockResolvedValue(
      makeResponse({ status: 200, json: async () => TOKEN })
    );

    await refreshAccessToken();
    await refreshAccessToken();

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
