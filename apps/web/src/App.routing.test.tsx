import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { courseFrame, makeCourse, makeRun, sseStreamResponse } from "./test/fixtures";

/** Minimal URL-routed fetch stub for shell/routing tests: enough for StudioApp's mount-time
 *  fetches (run history, settings capability probe) plus course-by-id opens and a build stream.
 *  Unhandled URLs reject, which the app's hooks treat as fail-closed (e.g. /api/me → not admin). */
function studioFetch(handlers: { runs?: unknown; course?: unknown; build?: unknown } = {}) {
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
    if (url.includes("/api/courses/stream")) {
      return Promise.resolve(handlers.build);
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

  it("deep-links to a course at /courses/:courseId and defaults to the Learn view", async () => {
    vi.stubGlobal("fetch", studioFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Learn" })).toBeChecked();
  });

  it("deep-links to the Map view at /courses/:courseId/map", async () => {
    vi.stubGlobal("fetch", studioFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test/map");

    render(<App />);

    expect(await screen.findByRole("radio", { name: "Map" })).toBeChecked();
  });

  it("switching the course view writes it to the URL", async () => {
    vi.stubGlobal("fetch", studioFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);
    await screen.findByRole("radio", { name: "Learn" });

    fireEvent.click(screen.getByRole("radio", { name: "Map" }));
    expect(window.location.pathname).toBe("/courses/course-test/map");

    fireEvent.click(screen.getByRole("radio", { name: "Learn" }));
    expect(window.location.pathname).toBe("/courses/course-test");
  });

  it("opening a run from the rail navigates to its course URL; back returns home", async () => {
    vi.stubGlobal("fetch", studioFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/");

    render(<App />);
    const history = await screen.findByRole("navigation", { name: /run history/i });
    fireEvent.click(within(history).getByText("How binary search works"));

    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");

    await act(async () => {
      window.history.back();
      // jsdom dispatches popstate asynchronously; yield a tick so the router observes it.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
  });

  it("a finished build hands the URL off to its course", async () => {
    vi.stubGlobal(
      "fetch",
      studioFetch({
        runs: [],
        build: sseStreamResponse([courseFrame(makeCourse())]),
      }),
    );
    window.history.pushState(null, "", "/");

    render(<App />);
    fireEvent.change(await screen.findByLabelText("Topic"), {
      target: { value: "binary search" },
    });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");
  });
});
