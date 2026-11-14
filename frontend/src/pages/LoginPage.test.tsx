import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LoginPage } from "./LoginPage";
import { renderWithProviders } from "../test/render";
import { ApiError } from "../api/client";

// LoginPage импортирует из ../api/auth только resendVerification
// (вызывается в handleResend). Сам login идёт через useAuth().login —
// поэтому мок auth.login в renderWithProviders, а не loginUser здесь.
// vi.mock оставляем как safety net: если компонент случайно дёрнет
// ../api/auth напрямую — тест не пойдёт в сеть.
vi.mock("../api/auth", () => ({
  loginUser: vi.fn(),
  registerUser: vi.fn(),
  logoutUser: vi.fn(),
  fetchMe: vi.fn(),
  refreshSession: vi.fn(),
  resendVerification: vi.fn(),
  verifyEmail: vi.fn(),
  verifyEmailOnce: vi.fn(),
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
}));

describe("LoginPage", () => {
  it("валидирует email до сабмита", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    // "a@b" проходит HTML5-валидацию input[type=email] (WHATWG допускает
    // domain без TLD), но НЕ проходит наш EMAIL_RE — он требует ".tld".
    // Если бы взяли "not-an-email", браузер/jsdom заблокировали бы submit
    // раньше, чем handleSubmit получил управление, — и setFormError
    // не сработал бы.
    await user.type(screen.getByLabelText(/Email/i), "a@b");
    await user.type(screen.getByLabelText(/Пароль/i), "some-password");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    expect(
      await screen.findByText("Введите корректный email")
    ).toBeInTheDocument();
  });

  it("показывает detail из ApiError при неверных учётных данных", async () => {
    const user = userEvent.setup();
    const loginReject = vi.fn().mockRejectedValueOnce(
      new ApiError(401, "Invalid credentials")
    );
    renderWithProviders(<LoginPage />, {
      auth: { login: loginReject },
    });

    await user.type(screen.getByLabelText(/Email/i), "user@example.com");
    await user.type(screen.getByLabelText(/Пароль/i), "wrong-password");
    await user.click(screen.getByRole("button", { name: /Войти/i }));

    await waitFor(() =>
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument()
    );
    expect(loginReject).toHaveBeenCalledTimes(1);
    expect(loginReject).toHaveBeenCalledWith({
      email: "user@example.com",
      password: "wrong-password",
    });
  });
});