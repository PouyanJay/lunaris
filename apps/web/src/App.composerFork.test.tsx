import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The fork is a signed-in surface (it routes into Live, which needs an account), so these drive the
// real App through the same auth seam AuthGate.test.tsx established.
const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));
vi.mock("./hooks/useAuth", () => ({
  useAuth: useAuthMock,
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

import App from "./App";
import { routedFetch } from "./test/fixtures";

function signedIn() {
  const user = { id: "u1", email: "learner@example.com", user_metadata: {} };
  return {
    enabled: true,
    loading: false,
    session: { user },
    user,
    signIn: vi.fn().mockResolvedValue(undefined),
    signUp: vi.fn().mockResolvedValue({ needsConfirmation: false }),
    signOut: vi.fn().mockResolvedValue(undefined),
    updateDisplayName: vi.fn().mockResolvedValue(undefined),
  };
}

describe("Composer — the Studio | Live fork", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_API_URL", "http://test");
    vi.stubEnv("VITE_LIVE_ENABLED", "true");
    vi.stubGlobal("fetch", routedFetch());
    useAuthMock.mockReturnValue(signedIn());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    useAuthMock.mockReset();
  });

  it("starts a Live session from the composer instead of a Studio build", async () => {
    // The walking skeleton: the choice is made at the moment of intent, and Live's promise is a
    // session — so submitting must NOT drop the learner into the Studio build control room.
    window.history.pushState(null, "", "/new");

    render(<App />);

    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));
    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: "How transformers work" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start (a )?(live )?session/i }));

    await waitFor(() => expect(window.location.pathname).toBe("/live"));
    // The topic rides along — Live is about to compile a graph for it.
    expect(new URLSearchParams(window.location.search).get("topic")).toBe("How transformers work");
    expect(await screen.findByRole("heading", { name: "Lunaris Live" })).toBeInTheDocument();
  });

  it("keeps Studio the default, so the existing path is unchanged", async () => {
    window.history.pushState(null, "", "/new");

    render(<App />);

    expect(await screen.findByRole("radio", { name: "Studio" })).toBeChecked();
    expect(screen.getByRole("button", { name: /generate course/i })).toBeInTheDocument();
  });

  it("drops Studio-only build settings when Live is selected", async () => {
    // Live compiles a graph and teaches; it never researches sources. Offering a trust control that
    // cannot affect the outcome is worse than not offering it. Depth and Level stay — plan §5 puts
    // depth in a session's own config.
    window.history.pushState(null, "", "/new");

    render(<App />);

    expect(screen.getByText(/official sources only/i)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));

    expect(screen.queryByText(/official sources only/i)).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Standard" })).toBeInTheDocument();
  });

  it("stops promising a build in the feature cards when Live is selected", async () => {
    // The cards under the composer describe what submitting does. Under Live they described a
    // Studio build — researching sources and a build to watch — neither of which Live performs.
    window.history.pushState(null, "", "/new");

    render(<App />);

    expect(
      screen.getByRole("list", { name: /what a lunaris studio build does/i }),
    ).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));

    expect(
      screen.queryByRole("list", { name: /what a lunaris studio build does/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: /what a lunaris live session does/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/watch it build/i)).not.toBeInTheDocument();
  });

  it("carries the topic into Live's surface, which names it back", async () => {
    window.history.pushState(null, "", "/live?topic=How%20transformers%20work");

    render(<App />);

    await screen.findByRole("heading", { name: "Lunaris Live", level: 1 });
    expect(screen.getByText(/how transformers work/i)).toBeInTheDocument();
  });

  it("renders Live cleanly with no topic at all", async () => {
    window.history.pushState(null, "", "/live");

    render(<App />);

    await screen.findByRole("heading", { name: "Lunaris Live", level: 1 });
    // No stray "undefined" / empty quotes where a topic would go.
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
  });

  it("hides the fork entirely when Live is flagged off", async () => {
    vi.stubEnv("VITE_LIVE_ENABLED", "false");
    window.history.pushState(null, "", "/new");

    render(<App />);

    expect(await screen.findByRole("button", { name: /generate course/i })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Live" })).not.toBeInTheDocument();
  });
});
