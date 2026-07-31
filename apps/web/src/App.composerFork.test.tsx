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

  // ─── Variants ────────────────────────────────────────────────────────────────────────────────

  it.each([
    ["a topic with punctuation", "What's a B-tree? (and why)"],
    ["a topic with a slash", "TCP/IP layering"],
    ["a topic with an ampersand", "Merge & quick sort"],
    ["a unicode topic", "Qué es un árbol B"],
  ])("round-trips %s through the URL without mangling it", async (_case, topic) => {
    window.history.pushState(null, "", "/new");

    render(<App />);

    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));
    fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: topic } });
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));

    await waitFor(() => expect(window.location.pathname).toBe("/live"));
    // Encoded on the way out, decoded on the way in — the learner sees exactly what they typed.
    expect(new URLSearchParams(window.location.search).get("topic")).toBe(topic);
    expect(await screen.findByText(topic, { exact: false })).toBeInTheDocument();
  });

  it("refuses to start a session with an empty topic", async () => {
    // Live must not skip the validation Studio applies: submitting nothing should surface the
    // error, not navigate to a session about nothing.
    window.history.pushState(null, "", "/new");

    render(<App />);

    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/enter a topic/i);
    expect(window.location.pathname).toBe("/new");
  });

  it("trims a whitespace-only topic rather than starting a session on it", async () => {
    window.history.pushState(null, "", "/new");

    render(<App />);

    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));
    fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: /start session/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/new");
  });

  it("keeps the chosen mode while the topic is edited", async () => {
    // Editing the topic invalidates the brief; it must not silently drop the learner back to a
    // Studio build they did not ask for.
    window.history.pushState(null, "", "/new");

    render(<App />);

    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));
    fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "How HTTPS works" } });
    fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "How TLS works" } });

    expect(screen.getByRole("radio", { name: "Live" })).toBeChecked();
    expect(screen.getByRole("button", { name: /start session/i })).toBeInTheDocument();
  });

  it("restores the Studio-only settings when switching back from Live", async () => {
    window.history.pushState(null, "", "/new");

    render(<App />);

    fireEvent.click(await screen.findByRole("radio", { name: "Live" }));
    expect(screen.queryByText(/official sources only/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Studio" }));

    expect(screen.getByText(/official sources only/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate course/i })).toBeInTheDocument();
  });

  it("ignores a blank topic param on Live's surface", async () => {
    window.history.pushState(null, "", "/live?topic=%20%20");

    render(<App />);

    await screen.findByRole("heading", { name: "Lunaris Live", level: 1 });
    // A whitespace-only param must not render "You asked to learn ." with nothing in it.
    expect(screen.queryByText(/you asked to learn/i)).not.toBeInTheDocument();
  });
});
