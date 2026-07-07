import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  courseFrame,
  makeCourse,
  makeCourseSummary,
  makeRun,
  routedFetch,
  sseStreamResponse,
} from "./test/fixtures";

describe("App — URL routing (live studio)", () => {
  beforeEach(() => vi.stubEnv("VITE_API_URL", "http://test"));
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("deep-links straight to the Settings canvas at /settings", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/settings");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/settings");
  });

  it("rail Settings navigation updates the URL; Done returns to the composer", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/");

    render(<App />);
    expect(await screen.findByText(/no runs yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/settings");

    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("Done from a cold /settings deep-link falls back to home", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/settings");

    render(<App />);
    await screen.findByRole("heading", { name: "Settings" });

    // No in-app history to return to — Done falls back to the composer.
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("renders the Admin Portal at /admin once /api/me confirms an admin", async () => {
    vi.stubGlobal("fetch", routedFetch({ me: { isAdmin: true } }));
    window.history.pushState(null, "", "/admin");

    render(<App />);

    // The fail-closed notice may flash while /api/me resolves; it must then yield to the portal.
    await waitFor(() =>
      expect(screen.queryByText(/admin access required/i)).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("heading", { name: "Admin Portal" })).toBeInTheDocument();
  });

  it("renders a designed not-found state for an unknown URL", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/no-such-page");

    render(<App />);

    expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
  });

  it("renders the course library at /courses, linking the fetched course into its canvas", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [makeCourseSummary()] }));
    window.history.pushState(null, "", "/courses");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "My courses" })).toBeInTheDocument();
    // The card is a real link (Cmd/middle-click must work) into the course canvas.
    const card = await screen.findByRole("link", { name: /how https works/i });
    expect(card).toHaveAttribute("href", "/courses/course-lib");
  });

  it("deep-links to a course at /courses/:courseId and defaults to the Learn view", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Learn" })).toBeChecked();
  });

  it("deep-links to the Map view at /courses/:courseId/map", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test/map");

    render(<App />);

    expect(await screen.findByRole("radio", { name: "Map" })).toBeChecked();
  });

  it("switching the course view writes it to the URL", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);
    await screen.findByRole("radio", { name: "Learn" });

    fireEvent.click(screen.getByRole("radio", { name: "Map" }));
    expect(window.location.pathname).toBe("/courses/course-test/map");

    fireEvent.click(screen.getByRole("radio", { name: "Learn" }));
    expect(window.location.pathname).toBe("/courses/course-test");
  });

  it("opening a run from the rail navigates to its course URL; back returns home", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/");

    render(<App />);
    const history = await screen.findByRole("navigation", { name: /run history/i });
    fireEvent.click(within(history).getByText("How binary search works"));

    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");

    // jsdom dispatches popstate asynchronously; findByRole polls until the router re-renders.
    act(() => window.history.back());
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
  });

  it("routes the primary nav to My courses, Activity, and Bookmarks", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/");

    render(<App />);
    await screen.findByText(/no runs yet/i);

    fireEvent.click(screen.getByRole("link", { name: "My courses" }));
    expect(window.location.pathname).toBe("/courses");
    // An account with no builds gets the library's designed empty state, not a blank grid.
    expect(await screen.findByText(/no courses yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "My courses" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    fireEvent.click(screen.getByRole("link", { name: "Activity" }));
    expect(window.location.pathname).toBe("/activity");
    expect(await screen.findByText(/learning activity/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Bookmarks" }));
    expect(window.location.pathname).toBe("/bookmarks");
    expect(await screen.findByText(/saved lessons/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Home" }));
    expect(window.location.pathname).toBe("/");
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
  });

  it("normalizes /new to the composer at /", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/new");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("lands an unknown course id on the recoverable error canvas", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: Parameters<typeof fetch>[0]) => {
        const url = input instanceof Request ? input.url : String(input);
        if (/\/api\/courses\/[^/?]+$/.test(url)) {
          return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
        }
        return routedFetch()(input);
      }),
    );
    window.history.pushState(null, "", "/courses/no-such-course");

    render(<App />);

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("treats an unknown course view segment as not found", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test/bogus");

    render(<App />);

    expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
  });

  it("keeps /admin behind the restricted notice for non-admins", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/admin");

    render(<App />);

    expect(await screen.findByText(/admin access required/i)).toBeInTheDocument();
  });

  it("home shows the composer again after a build hands off to its course", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse([courseFrame(makeCourse())]),
        course: makeCourse(),
      }),
    );
    window.history.pushState(null, "", "/");

    render(<App />);
    fireEvent.change(await screen.findByLabelText("Topic"), {
      target: { value: "binary search" },
    });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    await screen.findByRole("heading", { name: "How binary search works" });
    expect(window.location.pathname).toBe("/courses/course-test");

    // Regression: home must not re-host the finished build — it's the composer again.
    fireEvent.click(screen.getByRole("link", { name: "Home" }));
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("a finished build hands the URL off to its course", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
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
