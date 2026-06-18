import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchAdminUsersMock, deleteAdminUserMock } = vi.hoisted(() => ({
  fetchAdminUsersMock: vi.fn(),
  deleteAdminUserMock: vi.fn(),
}));
vi.mock("../../lib/adminUsers", () => ({
  fetchAdminUsers: fetchAdminUsersMock,
  deleteAdminUser: deleteAdminUserMock,
}));

import { AdminUsersSection } from "./AdminUsersSection";

const ADMIN = {
  id: "a",
  email: "owner@x.test",
  createdAt: "2026-06-01T12:00:00Z",
  lastSignInAt: "2026-06-02T12:00:00Z",
  emailConfirmed: true,
  isAdmin: true,
  isSelf: true,
};
const MEMBER = {
  id: "b",
  email: "member@x.test",
  createdAt: "2026-06-01T12:00:00Z",
  lastSignInAt: null,
  emailConfirmed: false,
  isAdmin: false,
  isSelf: false,
};

describe("AdminUsersSection", () => {
  beforeEach(() => {
    fetchAdminUsersMock.mockReset();
    deleteAdminUserMock.mockReset();
    deleteAdminUserMock.mockResolvedValue(undefined);
  });

  it("lists accounts with admin/you badges and a pending status", async () => {
    fetchAdminUsersMock.mockResolvedValue([ADMIN, MEMBER]);
    render(<AdminUsersSection apiBaseUrl="http://api.test" />);

    expect(await screen.findByText("owner@x.test")).toBeInTheDocument();
    expect(screen.getByText("member@x.test")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    // The current admin's own row can't be deleted; a member's row can.
    expect(screen.queryByRole("button", { name: "Delete owner@x.test" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete member@x.test" })).toBeInTheDocument();
  });

  it("deletes a member after an inline confirm and refreshes the list", async () => {
    fetchAdminUsersMock.mockResolvedValueOnce([ADMIN, MEMBER]).mockResolvedValue([ADMIN]);
    render(<AdminUsersSection apiBaseUrl="http://api.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete member@x.test" }));
    // The inline confirm appears; the actual delete fires only on the second click.
    expect(await screen.findByText("Delete?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(deleteAdminUserMock).toHaveBeenCalledWith("http://api.test", "b"));
    await waitFor(() => expect(screen.queryByText("member@x.test")).not.toBeInTheDocument());
  });

  it("cancels a delete without calling the API", async () => {
    fetchAdminUsersMock.mockResolvedValue([ADMIN, MEMBER]);
    render(<AdminUsersSection apiBaseUrl="http://api.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete member@x.test" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.getByText("member@x.test")).toBeInTheDocument();
    expect(deleteAdminUserMock).not.toHaveBeenCalled();
  });

  it("surfaces an error when delete fails and keeps the row in the list", async () => {
    fetchAdminUsersMock.mockResolvedValue([ADMIN, MEMBER]);
    deleteAdminUserMock.mockRejectedValueOnce(new Error("Could not delete the account."));
    render(<AdminUsersSection apiBaseUrl="http://api.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete member@x.test" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not delete the account.");
    // The row must survive a failed delete — no premature removal.
    expect(screen.getByText("member@x.test")).toBeInTheDocument();
  });

  it("shows an empty state when there are no accounts", async () => {
    fetchAdminUsersMock.mockResolvedValue([]);
    render(<AdminUsersSection apiBaseUrl="http://api.test" />);

    expect(await screen.findByText("No accounts yet.")).toBeInTheDocument();
  });

  it("surfaces a load failure with a retry", async () => {
    fetchAdminUsersMock.mockRejectedValueOnce(new Error("Admin access required"));
    render(<AdminUsersSection apiBaseUrl="http://api.test" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Admin access required");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
