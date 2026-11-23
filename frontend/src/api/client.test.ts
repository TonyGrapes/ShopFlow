import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  ApiError,
  apiGet,
  apiPost,
  apiPatch,
  apiDelete,
  API_BASE_URL,
} from "./client";
import {
  getAccessToken,
  notifyUnauthorized,
  refreshAccessToken,
} from "./session";
import type { TokenResponse } from "../types/auth";

vi.mock("./session", () => ({
  getAccessToken: vi.fn(),
  notifyUnauthorized: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

const mockedGetToken = vi.mocked(getAccessToken);
const mockedNotify = vi.mocked(notifyUnauthorized);
const mockedRefresh = vi.mocked(refreshAccessToken);

const TOKEN: TokenResponse = {
  access_token: "new-token",
  token_type: "bearer",
  expires_in: 60,
};

/** Минимальный Response-двойник: client использует только эти поля. */
function makeResponse(init: {
  status?: number;
  statusText?: string;
  text?: () => Promise<string>;
}): Response {
  const status = init.status ?? 200;
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: init.statusText ?? "",
    text: init.text ?? (async () => ""),
  } as unknown as Response;
}

function jsonResponse(body: unknown, status = 200, statusText = "OK"): Response {
  return makeResponse({
    status,
    statusText,
    text: async () => JSON.stringify(body),
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function fetchCall(index = 0): { url: string; init: RequestInit } {
  const call = fetchMock.mock.calls[index];
  return { url: call[0] as string, init: call[1] as RequestInit };
}

function headersOf(index = 0): Record<string, string> {
  return fetchCall(index).init.headers as Record<string, string>;
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  mockedGetToken.mockReset();
  mockedGetToken.mockReturnValue(null);
  mockedNotify.mockReset();
  mockedRefresh.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiGet — URL и параметры", () => {
  it("собирает query-параметры и отбрасывает пустые", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await apiGet("/api/v1/products", {
      q: "phone",
      page: 2,
      skip: "",
      nil: null,
      undef: undefined,
    });

    const { url, init } = fetchCall();
    expect(url).toBe(`${API_BASE_URL}/api/v1/products?q=phone&page=2`);
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("include");
    expect(init.body).toBeUndefined();
    expect(headersOf().Accept).toBe("application/json");
  });

  it("без параметров не добавляет '?'", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));

    await apiGet("/api/v1/cart");

    expect(fetchCall().url).toBe(`${API_BASE_URL}/api/v1/cart`);
  });
});

describe("авторизация", () => {
  it("добавляет Bearer, если токен есть", async () => {
    mockedGetToken.mockReturnValue("tok");
    fetchMock.mockResolvedValue(jsonResponse({}));

    await apiGet("/api/v1/auth/me");

    expect(headersOf().Authorization).toBe("Bearer tok");
  });

  it("не добавляет Authorization при auth:false", async () => {
    mockedGetToken.mockReturnValue("tok");
    fetchMock.mockResolvedValue(jsonResponse({}));

    await apiPost("/api/v1/auth/login", { email: "a" }, { auth: false });

    expect(headersOf().Authorization).toBeUndefined();
  });

  it("не добавляет Authorization без токена", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));

    await apiGet("/api/v1/products");

    expect(headersOf().Authorization).toBeUndefined();
  });
});

describe("методы и тело запроса", () => {
  it("apiPost сериализует тело и ставит Content-Type", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));

    await apiPost("/api/v1/orders", { total: 100 });

    const { init } = fetchCall();
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ total: 100 }));
    expect(headersOf()["Content-Type"]).toBe("application/json");
  });

  it("apiPatch использует PATCH", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));

    await apiPatch("/api/v1/cart/items/1", { quantity: 3 });

    expect(fetchCall().init.method).toBe("PATCH");
  });

  it("apiDelete использует DELETE без тела", async () => {
    fetchMock.mockResolvedValue(makeResponse({ status: 204 }));

    await apiDelete("/api/v1/favorites/1");

    const { init } = fetchCall();
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });

  it("прокидывает кастомные заголовки (Idempotency-Key)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));

    await apiPost("/api/v1/orders", {}, { headers: { "Idempotency-Key": "k1" } });

    expect(headersOf()["Idempotency-Key"]).toBe("k1");
  });
});

describe("парсинг успешного ответа", () => {
  it("возвращает распарсенный JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 7 }));

    await expect(apiGet("/api/v1/products/7")).resolves.toEqual({ id: 7 });
  });

  it("204 → undefined", async () => {
    fetchMock.mockResolvedValue(makeResponse({ status: 204 }));

    await expect(apiDelete("/api/v1/cart")).resolves.toBeUndefined();
  });

  it("пустое тело → undefined", async () => {
    fetchMock.mockResolvedValue(
      makeResponse({ status: 200, text: async () => "" })
    );

    await expect(apiGet("/api/v1/ping")).resolves.toBeUndefined();
  });
});

describe("обёртка ошибок (ApiError)", () => {
  it("JSON detail/code/extra", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "bad", code: "LIMIT", field: "qty" },
        400,
        "Bad Request"
      )
    );

    const err = (await apiGet("/x").catch((e) => e)) as ApiError;

    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.detail).toBe("bad");
    expect(err.code).toBe("LIMIT");
    expect(err.extra).toEqual({ field: "qty" });
  });

  it("FastAPI validation array → человекочитаемый detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: [
            { loc: ["body", "email"], msg: "invalid email" },
            { msg: "required" },
          ],
        },
        422,
        "Unprocessable Entity"
      )
    );

    const err = (await apiGet("/x").catch((e) => e)) as ApiError;

    expect(err.detail).toBe("body.email: invalid email; required");
  });

  it("не-JSON тело → detail = текст", async () => {
    fetchMock.mockResolvedValue(
      makeResponse({
        status: 500,
        statusText: "Internal Server Error",
        text: async () => "plain failure",
      })
    );

    const err = (await apiGet("/x").catch((e) => e)) as ApiError;

    expect(err.detail).toBe("plain failure");
  });

  it("объект без detail → detail = statusText", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ foo: "bar" }, 400, "Bad Request"));

    const err = (await apiGet("/x").catch((e) => e)) as ApiError;

    expect(err.detail).toBe("Bad Request");
    expect(err.extra).toEqual({ foo: "bar" });
  });

  it("недоступное тело → detail = statusText", async () => {
    fetchMock.mockResolvedValue(
      makeResponse({
        status: 400,
        statusText: "Bad",
        text: async () => {
          throw new Error("no body");
        },
      })
    );

    const err = (await apiGet("/x").catch((e) => e)) as ApiError;

    expect(err.detail).toBe("Bad");
  });

  it("сетевая ошибка → Error('Network error: …')", async () => {
    fetchMock.mockRejectedValue(new Error("boom"));

    await expect(apiGet("/x")).rejects.toThrow("Network error: boom");
  });

  it("не-Error rejection → 'Network error: unknown'", async () => {
    fetchMock.mockRejectedValue("nope");

    await expect(apiGet("/x")).rejects.toThrow("Network error: unknown");
  });
});

describe("401 → refresh → replay", () => {
  it("обновляет токен и повторяет запрос один раз", async () => {
    mockedRefresh.mockResolvedValue(TOKEN);
    fetchMock
      .mockResolvedValueOnce(
        makeResponse({
          status: 401,
          statusText: "Unauthorized",
          text: async () => JSON.stringify({ detail: "expired" }),
        })
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    await expect(apiGet("/api/v1/auth/me")).resolves.toEqual({ ok: true });

    expect(mockedRefresh).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(mockedNotify).not.toHaveBeenCalled();
  });

  it("refresh вернул null → notifyUnauthorized + ApiError", async () => {
    mockedRefresh.mockResolvedValue(null);
    fetchMock.mockResolvedValue(
      makeResponse({
        status: 401,
        statusText: "Unauthorized",
        text: async () => JSON.stringify({ detail: "no session" }),
      })
    );

    await expect(apiGet("/x")).rejects.toBeInstanceOf(ApiError);
    expect(mockedNotify).toHaveBeenCalledTimes(1);
  });

  it("повторный 401 (после refresh) → notify, без второго refresh", async () => {
    mockedRefresh.mockResolvedValue(TOKEN);
    fetchMock.mockResolvedValue(
      makeResponse({
        status: 401,
        statusText: "Unauthorized",
        text: async () => JSON.stringify({ detail: "still" }),
      })
    );

    await expect(apiGet("/x")).rejects.toBeInstanceOf(ApiError);

    expect(mockedRefresh).toHaveBeenCalledTimes(1);
    expect(mockedNotify).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("skipAuthRefresh:true → refresh не вызывается", async () => {
    fetchMock.mockResolvedValue(
      makeResponse({ status: 401, statusText: "Unauthorized", text: async () => "" })
    );

    await expect(
      apiPost("/api/v1/auth/login", {}, { skipAuthRefresh: true })
    ).rejects.toBeInstanceOf(ApiError);

    expect(mockedRefresh).not.toHaveBeenCalled();
    expect(mockedNotify).not.toHaveBeenCalled();
  });

  it("auth:false → refresh не вызывается", async () => {
    fetchMock.mockResolvedValue(
      makeResponse({ status: 401, statusText: "Unauthorized", text: async () => "" })
    );

    await expect(
      apiPost("/api/v1/auth/logout", undefined, { auth: false })
    ).rejects.toBeInstanceOf(ApiError);

    expect(mockedRefresh).not.toHaveBeenCalled();
  });
});
