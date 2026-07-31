import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The product fork is a signed-in surface, so these tests drive the real App through the auth seam
// AuthGate.test.tsx established: mock the module's `useAuth` and pass `AuthProvider` through. The
// rest of the suite runs with Supabase unconfigured (auth transparent), which is why `/` still
// means Studio Home there — see AD4.
const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));
vi.mock("./hooks/useAuth", () => ({
  useAuth: useAuthMock,
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

import App from "./App";
import { makeCourse, makeRun, routedFetch } from "./test/fixtures";

/** A signed-in auth state whose account metadata is under the test's control. */
function signedIn(userMetadata: Record<string, unknown> = {}) {
  const user = { id: "u1", email: "learner@example.com", user_metadata: userMetadata };
  return {
    enabled: true,
    loading: false,
    session: { user },
    user,
    // Every method mirrors the real AuthState's Promise-returning signature. A bare vi.fn() returns
    // undefined, which silently diverges the moment production code awaits or .catch()es it.
    signIn: vi.fn().mockResolvedValue(undefined),
    signUp: vi.fn().mockResolvedValue({ needsConfirmation: false }),
    signOut: vi.fn().mockResolvedValue(undefined),
    updateDisplayName: vi.fn().mockResolvedValue(undefined),
    updateLastProduct: vi.fn().mockResolvedValue(undefined),
  };
}

describe("App — the product gateway and fork", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_API_URL", "http://test");
    vi.stubEnv("VITE_LIVE_ENABLED", "true");
    vi.stubGlobal("fetch", routedFetch());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    useAuthMock.mockReset();
  });

  it("offers both products at the root when the account has no remembered product", async () => {
    useAuthMock.mockReturnValue(signedIn());
    window.history.pushState(null, "", "/");

    render(<App />);

    const gateway = await screen.findByRole("region", { name: /choose a product/i });
    expect(within(gateway).getByRole("link", { name: /lunaris studio/i })).toBeInTheDocument();
    expect(within(gateway).getByRole("link", { name: /lunaris live/i })).toBeInTheDocument();
    // The root redirected rather than the gateway happening to render in place.
    await waitFor(() => expect(window.location.pathname).toBe("/gateway"));
  });

  it("lands the learner in Live — the walking skeleton's full path, gate to shell", async () => {
    useAuthMock.mockReturnValue(signedIn());
    window.history.pushState(null, "", "/");

    render(<App />);

    const gateway = await screen.findByRole("region", { name: /choose a product/i });
    fireEvent.click(within(gateway).getByRole("link", { name: /lunaris live/i }));

    expect(await screen.findByRole("heading", { name: "Lunaris Live" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe("/live"));
  });

  // The Studio leg is the loop hazard AD5 exists to guard: choosing Studio navigates to `/`, which
  // is itself the only redirect-eligible path. If the remembered choice did not take effect before
  // that render, the gateway would immediately redirect back to itself — forever.
  it("lands the learner at Studio Home when Studio is chosen, without bouncing back", async () => {
    useAuthMock.mockReturnValue(signedIn());
    window.history.pushState(null, "", "/");

    render(<App />);

    const gateway = await screen.findByRole("region", { name: /choose a product/i });
    fireEvent.click(within(gateway).getByRole("link", { name: /lunaris studio/i }));

    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(screen.queryByRole("region", { name: /choose a product/i })).not.toBeInTheDocument();
  });

  it("sends a returning Live learner straight to Live — zero choices, no gateway", async () => {
    useAuthMock.mockReturnValue(signedIn({ last_product: "live" }));
    window.history.pushState(null, "", "/");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Lunaris Live" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe("/live"));
    expect(screen.queryByRole("region", { name: /choose a product/i })).not.toBeInTheDocument();
  });

  it("leaves a returning Studio user on Studio Home — zero choices, no gateway", async () => {
    useAuthMock.mockReturnValue(signedIn({ last_product: "studio" }));
    window.history.pushState(null, "", "/");

    render(<App />);

    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(screen.queryByRole("region", { name: /choose a product/i })).not.toBeInTheDocument();
  });

  it("remembers a product entered directly, not only one picked at the gateway", async () => {
    // Someone who always deep-links into Live would otherwise never be remembered: the gateway
    // click is not the only way to enter a product.
    const auth = signedIn({ last_product: "studio" });
    useAuthMock.mockReturnValue(auth);
    window.history.pushState(null, "", "/live");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Lunaris Live" })).toBeInTheDocument();
    await waitFor(() => expect(auth.updateLastProduct).toHaveBeenCalledWith("live"));
  });

  it("does not treat arriving at the bare root as choosing Studio", async () => {
    // The root is ambiguous by design — the gateway resolves it. Recording Studio on arrival would
    // rob a first-time user of the choice before they ever made it.
    const auth = signedIn();
    useAuthMock.mockReturnValue(auth);
    window.history.pushState(null, "", "/");

    render(<App />);

    await screen.findByRole("region", { name: /choose a product/i });
    expect(auth.updateLastProduct).not.toHaveBeenCalled();
  });

  // ─── Structure and accessibility ─────────────────────────────────────────────────────────────

  it("gives the gateway one h1 and a heading per product", async () => {
    useAuthMock.mockReturnValue(signedIn());
    window.history.pushState(null, "", "/");

    render(<App />);

    await screen.findByRole("region", { name: /choose a product/i });
    // Exactly one h1 on the page, and it names the screen's job.
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent(/choose a product/i);
    // Each product is a real heading, not a styled span.
    expect(screen.getByRole("heading", { level: 2, name: "Lunaris Studio" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Lunaris Live" })).toBeInTheDocument();
  });

  it("gives the Live empty state a way onward rather than a dead end", async () => {
    useAuthMock.mockReturnValue(signedIn({ last_product: "live" }));
    window.history.pushState(null, "", "/live");

    render(<App />);

    await screen.findByRole("heading", { name: "Lunaris Live", level: 1 });
    expect(screen.getByRole("link", { name: /go to lunaris studio/i })).toBeInTheDocument();
  });

  // ─── Deep links never see the gateway ────────────────────────────────────────────────────────
  // The guarantee is structural: only the bare root is redirect-eligible, so no deeper path can
  // reach the gateway. These pin that down at the surface a user would actually hit.

  it("takes a Studio deep link straight to the course, gateway or no gateway", async () => {
    // No remembered product — the state that WOULD show the gateway at the root.
    useAuthMock.mockReturnValue(signedIn());
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /choose a product/i })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");
  });

  it("takes a Live deep link straight to Live, with no remembered product", async () => {
    useAuthMock.mockReturnValue(signedIn());
    window.history.pushState(null, "", "/live");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Lunaris Live" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /choose a product/i })).not.toBeInTheDocument();
  });

  it("holds the deep link across sign-in — the gateway never interposes", async () => {
    // There is no `?next=` handoff in this app, and deliberately so: AuthGate renders the login
    // screen in place at the deep-linked URL rather than bouncing through a login route, so the URL
    // is never lost and never has to be handed back. This proves the fork did not break that.
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");
    const signedOut = { ...signedIn(), session: null, user: null };
    useAuthMock.mockReturnValue(signedOut);

    const { rerender } = render(<App />);
    expect(
      screen.queryByRole("heading", { name: "How binary search works" }),
    ).not.toBeInTheDocument();

    // Sign-in completes: same URL, now with a session and no remembered product.
    useAuthMock.mockReturnValue(signedIn());
    rerender(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /choose a product/i })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");
  });

  it("records the choice so the next sign-in skips the gateway", async () => {
    const auth = signedIn();
    useAuthMock.mockReturnValue(auth);
    window.history.pushState(null, "", "/");

    render(<App />);

    const gateway = await screen.findByRole("region", { name: /choose a product/i });
    fireEvent.click(within(gateway).getByRole("link", { name: /lunaris live/i }));

    await waitFor(() => expect(auth.updateLastProduct).toHaveBeenCalledWith("live"));
  });
});
