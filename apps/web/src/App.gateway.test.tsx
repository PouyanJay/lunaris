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
import { routedFetch } from "./test/fixtures";

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
