import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

/** Minimal URL-routed fetch stub for shell/routing tests: enough for StudioApp's mount-time
 *  fetches (run history, settings capability probe) plus course-by-id opens. Unhandled URLs
 *  reject, which the app's hooks treat as fail-closed (e.g. /api/me → not admin). */
function studioFetch(handlers: { runs?: unknown; course?: unknown } = {}) {
  return vi.fn((input: Parameters<typeof fetch>[0]) => {
    const url = input instanceof Request ? input.url : String(input);
    if (/\/api\/runs\/[^/]+\/events$/.test(url)) {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    if (url.includes("/api/runs")) {
      return Promise.resolve({ ok: true, json: async () => handlers.runs ?? [] });
    }
    if (url.includes("/api/settings")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: false }),
      });
    }
    if (/\/api\/courses\/[^/?]+$/.test(url)) {
      return Promise.resolve({ ok: true, json: async () => handlers.course });
    }
    return Promise.reject(new Error(`studioFetch: unhandled URL ${url}`));
  });
}

describe("App — URL routing (live studio)", () => {
  beforeEach(() => vi.stubEnv("VITE_API_URL", "http://test"));
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("deep-links straight to the Settings canvas at /settings", async () => {
    vi.stubGlobal("fetch", studioFetch());
    window.history.pushState(null, "", "/settings");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/settings");
  });

  it("rail Settings navigation updates the URL; Done returns to the composer", async () => {
    vi.stubGlobal("fetch", studioFetch());
    window.history.pushState(null, "", "/");

    render(<App />);
    expect(await screen.findByText(/no runs yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/settings");

    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("renders a designed not-found state for an unknown URL", async () => {
    vi.stubGlobal("fetch", studioFetch());
    window.history.pushState(null, "", "/no-such-page");

    render(<App />);

    expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
  });
});
