import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";

import { ProfilePage } from "./ProfilePage";
import { renderWithProviders } from "../test/render";
import type { AuthContextValue } from "../context/authContext";
import type { UserResponse } from "../types/auth";

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

import { changePassword, updateProfile } from "../api/auth";

const mUpdateProfile = vi.mocked(updateProfile);
const mChangePassword = vi.mocked(changePassword);

const USER: UserResponse = {
  public_id: "u-1",
  email: "ann@example.com",
  first_name: "Ann",
  last_name: "Lee",
  phone_number: "+7 999 000-00-00",
  role: "customer",
  status: "active",
  is_email_verified: true,
  created_at: "2026-01-01T00:00:00Z",
};

function PathProbe() {
  const location = useLocation();
  return <div data-testid="path">{location.pathname}</div>;
}

function renderProfile(
  auth: Partial<AuthContextValue> = {},
  showToast = vi.fn()
) {
  return renderWithProviders(
    <Routes>
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="*" element={<PathProbe />} />
    </Routes>,
    {
      route: "/profile",
      auth: { user: USER, loading: false, ...auth },
      toast: { showToast },
    }
  );
}

function submitProfile() {
  const form = screen
    .getByRole("button", { name: "Сохранить" })
    .closest("form");
  fireEvent.submit(form as HTMLFormElement);
}

function submitPassword() {
  const form = screen
    .getByRole("button", { name: "Сменить пароль" })
    .closest("form");
  fireEvent.submit(form as HTMLFormElement);
}

function fillPasswords(oldPassword: string, next: string, confirm = next) {
  fireEvent.change(screen.getByLabelText("Текущий пароль"), {
    target: { value: oldPassword },
  });
  fireEvent.change(screen.getByLabelText("Новый пароль"), {
    target: { value: next },
  });
  fireEvent.change(screen.getByLabelText("Подтверждение пароля"), {
    target: { value: confirm },
  });
}

beforeEach(() => {
  mUpdateProfile.mockReset();
  mChangePassword.mockReset();
});

describe("ProfilePage", () => {
  it("loading → LoadingState", () => {
    renderProfile({ loading: true });

    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
  });

  it("user === null → ничего не рендерит", () => {
    const { container } = renderProfile({ user: null });

    expect(container).toBeEmptyDOMElement();
  });

  it("показывает профиль с заполненными полями и readonly email", () => {
    renderProfile();

    expect(screen.getByRole("heading", { name: "Профиль" })).toBeInTheDocument();
    const email = screen.getByLabelText("Email (не редактируется)");
    expect(email).toHaveValue("ann@example.com");
    expect(email).toBeDisabled();
    expect(email).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Имя")).toHaveValue("Ann");
    expect(screen.getByLabelText("Фамилия")).toHaveValue("Lee");
    expect(screen.getByLabelText("Телефон")).toHaveValue("+7 999 000-00-00");
    expect(
      screen.getByRole("link", { name: "← В каталог" })
    ).toHaveAttribute("href", "/");
  });

  it("пустое имя → ошибка", () => {
    renderProfile();

    fireEvent.change(screen.getByLabelText("Имя"), {
      target: { value: "   " },
    });
    submitProfile();

    expect(
      screen.getByText("Имя должно быть от 1 до 100 символов")
    ).toBeInTheDocument();
    expect(mUpdateProfile).not.toHaveBeenCalled();
  });

  it("пустая фамилия → ошибка", () => {
    renderProfile();

    fireEvent.change(screen.getByLabelText("Фамилия"), {
      target: { value: "   " },
    });
    submitProfile();

    expect(
      screen.getByText("Фамилия должна быть от 1 до 100 символов")
    ).toBeInTheDocument();
  });

  it("некорректный телефон → ошибка", () => {
    renderProfile();

    fireEvent.change(screen.getByLabelText("Телефон"), {
      target: { value: "abc" },
    });
    submitProfile();

    expect(
      screen.getByText("Введите телефон в формате +7 999 000-00-00")
    ).toBeInTheDocument();
  });

  it("сохранение профиля: триминг, refreshUser и toast", async () => {
    const user = userEvent.setup();
    const refreshUser = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    mUpdateProfile.mockResolvedValue(USER);
    renderProfile({ refreshUser }, showToast);

    fireEvent.change(screen.getByLabelText("Имя"), {
      target: { value: "  Bob  " },
    });
    fireEvent.change(screen.getByLabelText("Фамилия"), {
      target: { value: "  Smith  " },
    });
    fireEvent.change(screen.getByLabelText("Телефон"), {
      target: { value: " +1 555 000-00-00 " },
    });
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(mUpdateProfile).toHaveBeenCalledWith({
        first_name: "Bob",
        last_name: "Smith",
        phone_number: "+1 555 000-00-00",
      })
    );
    expect(refreshUser).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith("Профиль сохранён", "success");
  });

  it("ошибка сохранения профиля показывается", async () => {
    const user = userEvent.setup();
    mUpdateProfile.mockRejectedValue(new Error("profile boom"));
    renderProfile();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("profile boom")).toBeInTheDocument();
  });

  it("во время сохранения профиля кнопка disabled", async () => {
    const user = userEvent.setup();
    let resolveProfile: (value: UserResponse) => void = () => undefined;
    mUpdateProfile.mockReturnValue(
      new Promise<UserResponse>((resolve) => {
        resolveProfile = resolve;
      })
    );
    renderProfile();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      screen.getByRole("button", { name: "Сохраняем..." })
    ).toBeDisabled();

    resolveProfile(USER);
    await waitFor(() => expect(mUpdateProfile).toHaveBeenCalledTimes(1));
  });

  it("пустой текущий пароль → ошибка", () => {
    renderProfile();

    fillPasswords("", "password123");
    submitPassword();

    expect(screen.getByText("Введите текущий пароль")).toBeInTheDocument();
  });

  it("короткий новый пароль → ошибка", () => {
    renderProfile();

    fillPasswords("old-password", "short");
    submitPassword();

    expect(
      screen.getByText("Новый пароль должен быть от 8 до 128 символов")
    ).toBeInTheDocument();
  });

  it("пароли не совпадают → ошибка", () => {
    renderProfile();

    fillPasswords("old-password", "password123", "password456");
    submitPassword();

    expect(screen.getByText("Пароли не совпадают")).toBeInTheDocument();
  });

  it("смена пароля: API, toast, logout и переход на /login", async () => {
    const user = userEvent.setup();
    const logout = vi.fn().mockResolvedValue(undefined);
    const showToast = vi.fn();
    mChangePassword.mockResolvedValue({ message: "ok" });
    renderProfile({ logout }, showToast);

    fillPasswords("old-password", "password123");
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));

    await waitFor(() =>
      expect(mChangePassword).toHaveBeenCalledWith({
        old_password: "old-password",
        new_password: "password123",
      })
    );
    expect(showToast).toHaveBeenCalledWith(
      "Пароль изменён. Войдите снова.",
      "success"
    );
    expect(logout).toHaveBeenCalledTimes(1);
    expect(await screen.findByTestId("path")).toHaveTextContent("/login");
  });

  it("ошибка смены пароля показывается, logout не вызывается", async () => {
    const user = userEvent.setup();
    const logout = vi.fn().mockResolvedValue(undefined);
    mChangePassword.mockRejectedValue(new Error("password boom"));
    renderProfile({ logout });

    fillPasswords("old-password", "password123");
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));

    expect(await screen.findByText("password boom")).toBeInTheDocument();
    expect(logout).not.toHaveBeenCalled();
  });

  it("во время смены пароля кнопка disabled", async () => {
    const user = userEvent.setup();
    let resolvePassword: (value: { message: string }) => void = () => undefined;
    mChangePassword.mockReturnValue(
      new Promise<{ message: string }>((resolve) => {
        resolvePassword = resolve;
      })
    );
    renderProfile();

    fillPasswords("old-password", "password123");
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));

    expect(
      screen.getByRole("button", { name: "Меняем..." })
    ).toBeDisabled();

    resolvePassword({ message: "ok" });
    await waitFor(() => expect(mChangePassword).toHaveBeenCalledTimes(1));
  });
});
