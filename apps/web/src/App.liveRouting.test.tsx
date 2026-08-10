import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Live is a signed-in surface, so these drive the real App through the auth seam AuthGate.test.tsx
// established. The rest of the suite runs with Supabase unconfigured, where the whole Live
// route-space is transparent and `/live` is simply Studio's not-found.
const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));
vi.mock("./hooks/useAuth", () => ({
  useAuth: useAuthMock,
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

import App from "./App";
import { makeCourse, makeRun, routedFetch } from "./test/fixtures";

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

describe("App — the Live route-space", () => {
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

  it("resolves a Live deep link to Live's shell", async () => {
    window.history.pushState(null, "", "/live");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Lunaris Live", level: 1 }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/live");
  });

  it("leaves Studio deep links untouched", async () => {
    // Phase 0.5 removed the remembered-product redirect, so `/` and every deeper Studio path mean
    // exactly what they always did. This pins that Live's arrival cost Studio no routing.
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");
  });

  it("holds a deep link across sign-in", async () => {
    // There is no `?next=` handoff in this app, deliberately: AuthGate renders the login screen in
    // place at the deep-linked URL rather than bouncing through a login route, so the URL is never
    // lost and never has to be handed back.
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");
    useAuthMock.mockReturnValue({ ...signedIn(), session: null, user: null });

    const { rerender } = render(<App />);
    expect(
      screen.queryByRole("heading", { name: "How binary search works" }),
    ).not.toBeInTheDocument();

    useAuthMock.mockReturnValue(signedIn());
    rerender(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");
  });

  it("gives Live's empty state a way onward rather than a dead end", async () => {
    window.history.pushState(null, "", "/live");

    render(<App />);

    // Phase 1 renamed the way out: with nothing to compile, the honest next step is to name a
    // topic, not to leave for Studio. What is pinned is that the empty state still has one.
    fireEvent.click(await screen.findByRole("link", { name: /name a topic/i }));

    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(
      screen.queryByRole("heading", { name: "Lunaris Live", level: 1 }),
    ).not.toBeInTheDocument();
  });

  it("makes /live Studio's not-found when Live is flagged off", async () => {
    vi.stubEnv("VITE_LIVE_ENABLED", "false");
    window.history.pushState(null, "", "/live");

    render(<App />);

    expect(await screen.findByRole("heading", { name: /page not found/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Lunaris Live", level: 1 }),
    ).not.toBeInTheDocument();
  });
});
