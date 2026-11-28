import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdminUsersPage } from "./AdminUsersPage";
import { renderWithProviders } from "../../../test/render";
import type { AuthContextValue } from "../../../context/authContext";
import type { AdminUserListItem } from "../../../types/admin";
import type { Paginated } from "../../../types/common";
import type { UserResponse } from "../../../types/auth";

vi.mock("../../../api/admin", () => ({
  listAdminUsers: vi.fn(),
  updateUserRole: vi.fn(),
  updateUserStatus: vi.fn(),
}));

import {
  listAdminUsers,
  updateUserRole,
  updateUserStatus,
} from "../../../api/admin";

const mList = vi.mocked(listAdminUsers);
const mRole = vi.mocked(updateUserRole);
const mStatus = vi.mocked(updateUserStatus);

function makeUser(
  overrides: Partial<AdminUserListItem> = {}
): AdminUserListItem {
  return {
    public_id: "u-1",
    email: "ann@example.com",
    first_name: "Ann",
    last_name: "Lee",
    phone_number: "+10000000000",
    role: "customer",
    status: "active",
    is_email_verified: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeMe(overrides: Partial<UserResponse> = {}): UserResponse {
  return {
    public_id: "me-1",
    email: "me@example.com",
    first_name: "Admin",
    last_name: "Root",
    phone_number: "+10000000001",
    role: "admin",
    status: "active",
    is_email_verified: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makePage(
  items: AdminUserListItem[],
  total = items.length
): Paginated<AdminUserListItem> {
  return { items, total, page: 1, page_size: 20 };
}

function renderPage(
  auth: Partial<AuthContextValue> = { user: makeMe() },
  showToast = vi.fn()
) {
  return renderWithProviders(<AdminUsersPage />, {
    auth,
    toast: { showToast },
  });
}

async function rowByEmail(email: string) {
  const row = (await screen.findByText(email)).closest("tr");
  if (row === null) throw new Error("row not found");
  return row;
}

beforeEach(() => {
  mList.mockReset().mockResolvedValue(makePage([makeUser()]));
  mRole.mockReset();
  mStatus.mockReset();
});

describe("AdminUsersPage", () => {
  it("loading → «Загрузка…»", () => {
    mList.mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  it("ошибка загрузки показывается", async () => {
    mList.mockRejectedValue(new Error("users boom"));
    renderPage();

    expect(await screen.findByText("users boom")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("пустой список → «Пользователей нет.»", async () => {
    mList.mockResolvedValue(makePage([], 0));
    renderPage();

    expect(
      await screen.findByText("Пользователей нет.")
    ).toBeInTheDocument();
  });

  it("админ видит select роли и кнопку бана для чужой строки", async () => {
    renderPage();

    expect(await screen.findByText("ann@example.com")).toBeInTheDocument();
    expect(screen.getByText("Ann Lee")).toBeInTheDocument();
    expect(screen.getAllByText("Клиент").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Активен").length).toBeGreaterThan(0);
    expect(screen.getByText(/2026/)).toBeInTheDocument();

    const row = await rowByEmail("ann@example.com");
    expect(within(row).getByRole("combobox")).toHaveValue("customer");
    expect(
      within(row).getByRole("button", { name: "Забанить" })
    ).toBeInTheDocument();
  });

  it("своя строка: роль текстом и без кнопки бана", async () => {
    mList.mockResolvedValue(makePage([makeMe()]));
    renderPage();

    const row = await rowByEmail("me@example.com");
    expect(await within(row).findByText("Админ")).toBeInTheDocument();
    expect(within(row).queryByRole("combobox")).not.toBeInTheDocument();
    expect(
      within(row).queryByRole("button", { name: /банить/ })
    ).not.toBeInTheDocument();
  });

  it("не-админ не получает select роли", async () => {
    renderPage({ user: makeMe({ role: "moderator" }) });

    const row = await rowByEmail("ann@example.com");
    expect(await within(row).findByText("Клиент")).toBeInTheDocument();
    expect(within(row).queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("смена роли: updateUserRole, toast и reload", async () => {
    const showToast = vi.fn();
    mRole.mockResolvedValue(makeUser({ role: "moderator" }));
    renderPage({ user: makeMe() }, showToast);

    const row = await rowByEmail("ann@example.com");
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "moderator" },
    });

    await waitFor(() =>
      expect(mRole).toHaveBeenCalledWith("u-1", { role: "moderator" })
    );
    expect(showToast).toHaveBeenCalledWith("Роль обновлена", "success");
    await waitFor(() => expect(mList).toHaveBeenCalledTimes(2));
  });

  it("ошибка смены роли → error-toast", async () => {
    const showToast = vi.fn();
    mRole.mockRejectedValue(new Error("role boom"));
    renderPage({ user: makeMe() }, showToast);

    const row = await rowByEmail("ann@example.com");
    fireEvent.change(within(row).getByRole("combobox"), {
      target: { value: "admin" },
    });

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("role boom", "error")
    );
  });

  it("бан активного пользователя → status banned, toast и reload", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mStatus.mockResolvedValue(makeUser({ status: "banned" }));
    renderPage({ user: makeMe() }, showToast);

    const row = await rowByEmail("ann@example.com");
    await user.click(within(row).getByRole("button", { name: "Забанить" }));

    await waitFor(() =>
      expect(mStatus).toHaveBeenCalledWith("u-1", { status: "banned" })
    );
    expect(showToast).toHaveBeenCalledWith(
      "Пользователь забанен",
      "success"
    );
    expect(mList).toHaveBeenCalledTimes(2);
  });

  it("разбан забаненного → status active и toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mList.mockResolvedValue(
      makePage([makeUser({ status: "banned", role: "seller" })])
    );
    mStatus.mockResolvedValue(makeUser({ status: "active" }));
    renderPage({ user: makeMe() }, showToast);

    const row = await rowByEmail("ann@example.com");
    expect(within(row).getByText("Забанен")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Разбанить" }));

    await waitFor(() =>
      expect(mStatus).toHaveBeenCalledWith("u-1", { status: "active" })
    );
    expect(showToast).toHaveBeenCalledWith(
      "Пользователь разбанен",
      "success"
    );
  });

  it("ошибка бана → error-toast", async () => {
    const user = userEvent.setup();
    const showToast = vi.fn();
    mStatus.mockRejectedValue(new Error("ban boom"));
    renderPage({ user: makeMe() }, showToast);

    const row = await rowByEmail("ann@example.com");
    await user.click(within(row).getByRole("button", { name: "Забанить" }));

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith("ban boom", "error")
    );
  });

  it("во время бана select и кнопка disabled", async () => {
    const user = userEvent.setup();
    let resolveStatus: (value: AdminUserListItem) => void = () => undefined;
    mStatus.mockReturnValue(
      new Promise<AdminUserListItem>((resolve) => {
        resolveStatus = resolve;
      })
    );
    renderPage({ user: makeMe() });

    const row = await rowByEmail("ann@example.com");
    await user.click(within(row).getByRole("button", { name: "Забанить" }));

    expect(within(row).getByRole("combobox")).toBeDisabled();
    expect(
      within(row).getByRole("button", { name: "Забанить" })
    ).toBeDisabled();

    resolveStatus(makeUser({ status: "banned" }));
    await waitFor(() => expect(mList).toHaveBeenCalledTimes(2));
  });

  it("фильтр роли передаёт role и сбрасывает страницу", async () => {
    mList.mockResolvedValue(makePage([makeUser()], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3");

    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: /Следующая/ }));
    expect(await screen.findByText("Страница 2 из 3")).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("Все роли"), {
      target: { value: "admin" },
    });

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, role: "admin" })
      )
    );
  });

  it("фильтр статуса передаёт status и сбрасывает страницу", async () => {
    mList.mockResolvedValue(makePage([makeUser()], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3");

    fireEvent.change(screen.getByDisplayValue("Все статусы"), {
      target: { value: "banned" },
    });

    await waitFor(() =>
      expect(mList).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, status: "banned" })
      )
    );
  });

  it("пагинация: вперёд/назад и границы", async () => {
    const user = userEvent.setup();
    mList.mockResolvedValue(makePage([makeUser()], 45));
    renderPage();
    await screen.findByText("Страница 1 из 3");

    expect(screen.getByRole("button", { name: /Предыдущая/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Следующая/ }));
    expect(await screen.findByText("Страница 2 из 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Следующая/ }));
    expect(await screen.findByText("Страница 3 из 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Следующая/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Предыдущая/ }));
    expect(await screen.findByText("Страница 2 из 3")).toBeInTheDocument();
  });
});
