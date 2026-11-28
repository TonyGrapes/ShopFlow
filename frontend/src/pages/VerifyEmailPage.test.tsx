import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { VerifyEmailPage } from "./VerifyEmailPage";
import { renderWithProviders } from "../test/render";

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

import { verifyEmailOnce } from "../api/auth";

const mVerify = vi.mocked(verifyEmailOnce);

function renderPage(route = "/verify-email") {
  return renderWithProviders(<VerifyEmailPage />, { route });
}

function submitToken(token: string) {
  const input = screen.getByLabelText("Токен из письма");
  fireEvent.change(input, { target: { value: token } });
  const form = screen
    .getByRole("button", { name: "Подтвердить email" })
    .closest("form");
  fireEvent.submit(form as HTMLFormElement);
}

beforeEach(() => {
  mVerify.mockReset();
});

describe("VerifyEmailPage", () => {
  it("без токена в URL показывает форму", () => {
    renderPage();

    expect(
      screen.getByRole("heading", { name: "Подтверждение email" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Токен из письма")).toHaveValue("");
    expect(screen.getByLabelText("Токен из письма")).toHaveAttribute(
      "placeholder",
      "Вставьте токен подтверждения"
    );
    expect(
      screen.getByRole("button", { name: "Подтвердить email" })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ко входу" })).toHaveAttribute(
      "href",
      "/login"
    );
    expect(mVerify).not.toHaveBeenCalled();
  });

  it("токен в query: loading, затем success", async () => {
    mVerify.mockResolvedValue({ message: "ok" });
    renderPage("/verify-email?token=abc123");

    expect(
      screen.getByText("Проверяем токен подтверждения...")
    ).toBeInTheDocument();

    expect(
      await screen.findByText("Email подтверждён. Теперь можно войти.")
    ).toBeInTheDocument();
    expect(mVerify).toHaveBeenCalledWith("abc123");
    expect(
      screen.queryByLabelText("Токен из письма")
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Перейти ко входу" })
    ).toHaveAttribute("href", "/login");
  });

  it("токен в query: ошибка показывает сообщение и форму с токеном", async () => {
    mVerify.mockRejectedValue(new Error("bad token"));
    renderPage("/verify-email?token=abc123");

    expect(await screen.findByText("bad token")).toBeInTheDocument();
    expect(screen.getByLabelText("Токен из письма")).toHaveValue("abc123");
    expect(
      screen.getByRole("button", { name: "Подтвердить email" })
    ).toBeInTheDocument();
  });

  it("pending-проверка из query держит loading и скрывает форму", () => {
    mVerify.mockReturnValue(new Promise(() => undefined));
    renderPage("/verify-email?token=slow");

    expect(
      screen.getByText("Проверяем токен подтверждения...")
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Токен из письма")
    ).not.toBeInTheDocument();
  });

  it("пустой ручной токен → ошибка без запроса", () => {
    renderPage();

    submitToken("   ");

    expect(screen.getByText("Вставьте токен из письма")).toBeInTheDocument();
    expect(mVerify).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Токен из письма")).toBeInTheDocument();
  });

  it("ручной ввод: токен тримится, success", async () => {
    const user = userEvent.setup();
    mVerify.mockResolvedValue({ message: "ok" });
    renderPage();

    fireEvent.change(screen.getByLabelText("Токен из письма"), {
      target: { value: "  manual-token  " },
    });
    await user.click(
      screen.getByRole("button", { name: "Подтвердить email" })
    );

    expect(
      await screen.findByText("Email подтверждён. Теперь можно войти.")
    ).toBeInTheDocument();
    expect(mVerify).toHaveBeenCalledWith("manual-token");
  });

  it("ручной ввод: ошибка показывается, форма остаётся", async () => {
    const user = userEvent.setup();
    mVerify.mockRejectedValue(new Error("manual boom"));
    renderPage();

    fireEvent.change(screen.getByLabelText("Токен из письма"), {
      target: { value: "manual-token" },
    });
    await user.click(
      screen.getByRole("button", { name: "Подтвердить email" })
    );

    expect(await screen.findByText("manual boom")).toBeInTheDocument();
    expect(screen.getByLabelText("Токен из письма")).toBeInTheDocument();
  });

  it("во время ручной проверки показывается loading", async () => {
    const user = userEvent.setup();
    let resolveVerify: (value: { message: string }) => void = () => undefined;
    mVerify.mockReturnValue(
      new Promise<{ message: string }>((resolve) => {
        resolveVerify = resolve;
      })
    );
    renderPage();

    fireEvent.change(screen.getByLabelText("Токен из письма"), {
      target: { value: "manual-token" },
    });
    await user.click(
      screen.getByRole("button", { name: "Подтвердить email" })
    );

    expect(
      screen.getByText("Проверяем токен подтверждения...")
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Токен из письма")
    ).not.toBeInTheDocument();

    resolveVerify({ message: "ok" });
    expect(
      await screen.findByText("Email подтверждён. Теперь можно войти.")
    ).toBeInTheDocument();
  });
});
