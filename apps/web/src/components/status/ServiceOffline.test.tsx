import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));
vi.mock("../../hooks/useAuth", () => ({ useAuth: useAuthMock }));

const { fetchMeMock } = vi.hoisted(() => ({ fetchMeMock: vi.fn() }));
vi.mock("../../lib/me", () => ({ fetchMe: fetchMeMock }));

// The switch itself is covered by PowerSwitch.test; here it only has to be offered to the right
// people, pointed at the control plane.
vi.mock("../admin/PowerSwitch", () => ({
  PowerSwitch: ({ controlBaseUrl }: { controlBaseUrl: string }) => (
    <p>power switch via {controlBaseUrl}</p>
  ),
}));

import { ServiceOffline } from "./ServiceOffline";

const CONTROL = "http://ctl.test";
const SESSION = { access_token: "jwt" };

function auth(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    loading: false,
    session: null,
    signIn: vi.fn().mockResolvedValue(undefined),
    signUp: vi.fn(),
    signOut: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function renderOffline({ checking = false, onRetry = vi.fn() } = {}) {
  return render(<ServiceOffline controlBaseUrl={CONTROL} checking={checking} onRetry={onRetry} />);
}

describe("ServiceOffline", () => {
  beforeEach(() => {
    useAuthMock.mockReset();
    fetchMeMock.mockReset();
    useAuthMock.mockReturnValue(auth());
  });

  it("tells a visitor the service is offline and how to request access", () => {
    renderOffline();

    expect(screen.getByRole("heading", { level: 1, name: "Lunaris is offline" })).toBeVisible();
    expect(screen.getByText("OFFLINE")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /email contact@pouyan\.ai/i })).toHaveAttribute(
      "href",
      "mailto:contact@pouyan.ai",
    );
    // An anonymous visitor never wakes the control plane.
    expect(fetchMeMock).not.toHaveBeenCalled();
  });

  it("re-checks on Try again, and shows that a check is in flight", () => {
    const onRetry = vi.fn();
    const { rerender } = renderOffline({ onRetry });

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    rerender(<ServiceOffline controlBaseUrl={CONTROL} checking onRetry={onRetry} />);
    expect(screen.getByRole("button", { name: "Checking…" })).toBeDisabled();
  });

  it("lets an administrator sign in from the offline screen, and go back", async () => {
    const signIn = vi.fn().mockResolvedValue(undefined);
    useAuthMock.mockReturnValue(auth({ signIn }));
    renderOffline();

    fireEvent.click(screen.getByRole("button", { name: "Administrator sign in" }));

    expect(screen.getByRole("heading", { name: "Administrator sign in" })).toBeVisible();
    // Accounts cannot be created while the service is offline.
    expect(screen.queryByRole("button", { name: "Create one" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@x.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret1" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(signIn).toHaveBeenCalledWith("admin@x.com", "secret1"));

    fireEvent.click(screen.getByRole("button", { name: "Back to status" }));
    expect(screen.getByRole("heading", { name: "Lunaris is offline" })).toBeVisible();
  });

  it("gives a signed-in administrator the power switch, verified by the control plane", async () => {
    useAuthMock.mockReturnValue(auth({ session: SESSION }));
    fetchMeMock.mockResolvedValue({ userId: "u1", isAdmin: true });
    renderOffline();

    expect(await screen.findByText(`power switch via ${CONTROL}`)).toBeInTheDocument();
    expect(fetchMeMock).toHaveBeenCalledWith(CONTROL, expect.any(AbortSignal));
    // Visitors still see the same notice above the console.
    expect(screen.getByRole("heading", { name: "Lunaris is offline" })).toBeVisible();
  });

  it("tells a signed-in non-administrator they cannot manage production", async () => {
    const signOut = vi.fn().mockResolvedValue(undefined);
    useAuthMock.mockReturnValue(auth({ session: SESSION, signOut }));
    fetchMeMock.mockResolvedValue({ userId: "u2", isAdmin: false });
    renderOffline();

    expect(await screen.findByText(/isn’t an administrator/i)).toBeInTheDocument();
    expect(screen.queryByText(/power switch via/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(signOut).toHaveBeenCalled());
  });

  it("offers a retry when the administrator check fails", async () => {
    useAuthMock.mockReturnValue(auth({ session: SESSION }));
    fetchMeMock
      .mockRejectedValueOnce(new Error("Could not load your identity (HTTP 502)."))
      .mockResolvedValueOnce({ userId: "u1", isAdmin: true });
    renderOffline();

    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));

    expect(await screen.findByText(`power switch via ${CONTROL}`)).toBeInTheDocument();
    expect(fetchMeMock).toHaveBeenCalledTimes(2);
  });

  it("offers no administrator entry when sign-in is not configured", () => {
    useAuthMock.mockReturnValue(auth({ enabled: false }));
    renderOffline();

    expect(screen.queryByRole("button", { name: "Administrator sign in" })).not.toBeInTheDocument();
  });
});
