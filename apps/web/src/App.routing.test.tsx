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

  it("rail Settings navigation updates the URL; Done returns Home", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/");

    render(<App />);
    expect(await screen.findByText(/no runs yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/settings");

    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening)/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("Done from a cold /settings deep-link falls back to Home", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/settings");

    render(<App />);
    await screen.findByRole("heading", { name: "Settings" });

    // No in-app history to return to — Done falls back to Home (the dashboard at /).
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening)/i }),
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

  it("library header offers a New course action that opens the composer at /new", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/courses");

    render(<App />);
    await screen.findByRole("heading", { name: "My courses" });

    // Scoped to the header band — the sidebar carries its own New course button.
    fireEvent.click(within(screen.getByRole("banner")).getByRole("button", { name: "New course" }));

    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/new");
  });

  it("resumes an in-progress course from the Home hero straight into the reader", async () => {
    const summary = makeCourseSummary({
      id: "course-test",
      topic: "How binary search works",
      learnerStatus: "in_progress",
    });
    vi.stubGlobal(
      "fetch",
      routedFetch({
        library: [summary],
        runs: [makeRun()],
        course: makeCourse(),
        progress: {
          courseId: "course-test",
          objectives: [],
          lessons: [],
          lastLessonId: "m-binary_search-l0",
        },
      }),
    );
    window.history.pushState(null, "", "/");

    render(<App />);

    // Wait for the hero to enrich (the resume lesson is known) before resuming — clicking earlier
    // gracefully falls back to the Overview. Then Resume opens the reader at the resume lesson's URL.
    await screen.findByText(/lesson 1 of 1/i);
    fireEvent.click(screen.getByRole("button", { name: /resume lesson/i }));
    await screen.findByRole("heading", { name: "How binary search works", level: 1 });
    // The URL settles on the resume lesson itself — reading positions are addressable (P6).
    await waitFor(() =>
      expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0"),
    );
    expect(screen.getByRole("radio", { name: "Lessons" })).toBeChecked();
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

  it("deep-links to a course at /courses/:courseId and lands on the Overview tab", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Overview" })).toBeChecked();
  });

  it("resolves the legacy learn URL to the Lessons view", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test/learn");

    render(<App />);

    expect(await screen.findByRole("radio", { name: "Lessons" })).toBeChecked();
  });

  it("an Overview lesson row deep-links into the reader at that lesson", async () => {
    const first = makeCourse().modules[0]!;
    const course = makeCourse({
      modules: [
        first,
        {
          ...first,
          id: "m-two",
          title: "Module two",
          lessons: [{ ...first.lessons[0]!, id: "m-two-l0" }],
        },
      ],
    });
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);
    const rows = await screen.findAllByRole("button", { name: /lesson \d/i });
    fireEvent.click(rows[1]!);

    expect(await screen.findByText(/lesson 2 of 2/i)).toBeInTheDocument();
    // The row's target lesson lands in the URL — the deep link is shareable (P6).
    await waitFor(() =>
      expect(window.location.pathname).toBe("/courses/course-test/lessons/m-two-l0"),
    );
  });

  it("Overview's CTAs navigate to the reader and the map", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /continue learning/i }));
    expect(await screen.findByText(/find a word in a dictionary/i)).toBeInTheDocument();
    // Continue lands on the reader; the URL canonicalises to the focused lesson (P6).
    await waitFor(() =>
      expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0"),
    );

    fireEvent.click(screen.getByRole("radio", { name: "Overview" }));
    fireEvent.click(await screen.findByRole("button", { name: /view the map/i }));
    // waitFor lets the map's progress fetch (P7 mastery badges) settle inside act.
    await waitFor(() => expect(window.location.pathname).toBe("/courses/course-test/map"));
  });

  it("deep-links to a specific lesson at /courses/:courseId/lessons/:lessonId", async () => {
    const first = makeCourse().modules[0]!;
    const course = makeCourse({
      modules: [
        first,
        {
          ...first,
          id: "m-two",
          title: "Module two",
          lessons: [{ ...first.lessons[0]!, id: "m-two-l0" }],
        },
      ],
    });
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course }));
    window.history.pushState(null, "", "/courses/course-test/lessons/m-two-l0");

    render(<App />);

    expect(await screen.findByText(/lesson 2 of 2/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test/lessons/m-two-l0");
  });

  it("selecting a lesson in the outline writes it to the URL; back returns", async () => {
    const first = makeCourse().modules[0]!;
    const course = makeCourse({
      modules: [
        first,
        {
          ...first,
          id: "m-two",
          title: "Module two",
          lessons: [{ ...first.lessons[0]!, id: "m-two-l0" }],
        },
      ],
    });
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course }));
    window.history.pushState(null, "", "/courses/course-test/lessons");

    render(<App />);
    const outline = await screen.findByRole("navigation", { name: /course outline/i });
    // The bare reader URL canonicalises (replace) to the focused lesson so every reading
    // position is addressable and back/forward walk lessons.
    await waitFor(() =>
      expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0"),
    );

    fireEvent.click(within(outline).getByRole("button", { name: /lesson 2/i }));
    expect(await screen.findByText(/lesson 2 of 2/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test/lessons/m-two-l0");

    act(() => window.history.back());
    expect(await screen.findByText(/lesson 1 of 2/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0");
  });

  it("the reader's Next/Previous walk the lesson URL", async () => {
    const first = makeCourse().modules[0]!;
    const course = makeCourse({
      modules: [
        first,
        {
          ...first,
          id: "m-two",
          title: "Module two",
          lessons: [{ ...first.lessons[0]!, id: "m-two-l0" }],
        },
      ],
    });
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course }));
    window.history.pushState(null, "", "/courses/course-test/lessons/m-binary_search-l0");

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /next lesson/i }));
    expect(await screen.findByText(/lesson 2 of 2/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test/lessons/m-two-l0");

    fireEvent.click(screen.getByRole("button", { name: /previous lesson/i }));
    expect(await screen.findByText(/lesson 1 of 2/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0");
  });

  it("a stale lesson URL falls back to the first lesson and canonicalises", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test/lessons/gone-lesson");

    render(<App />);

    expect(await screen.findByText(/lesson 1 of 1/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0"),
    );
  });

  it("the reader's Overview exit returns to the landing tab end-to-end", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test/lessons");

    render(<App />);
    // Let the reader finish canonicalising the bare /lessons URL first — clicking inside that
    // sub-frame window would race the pending replace against the exit navigation (a timing no
    // real click can hit; it flaked on slower CI runners).
    await waitFor(() =>
      expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0"),
    );
    fireEvent.click(await screen.findByRole("button", { name: /back to overview/i }));

    await waitFor(() => expect(window.location.pathname).toBe("/courses/course-test"));
    expect(await screen.findByRole("button", { name: /continue learning/i })).toBeInTheDocument();
  });

  it("records the open touch on the bare course URL — the Overview landing is a course open", async () => {
    // Pre-T4 the bare path was the reader (excluded from the App-level touch); now it's Overview,
    // which must count toward last-opened like every non-reader view.
    const fetchMock = routedFetch({ runs: [makeRun()], course: makeCourse() });
    vi.stubGlobal("fetch", fetchMock);
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);
    await screen.findByRole("heading", { name: "How binary search works", level: 1 });

    await waitFor(() => {
      const opened = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).endsWith("/api/courses/course-test/progress/opened") &&
          (init?.method ?? "GET").toUpperCase() === "PUT",
      );
      expect(opened).toBeTruthy();
    });
  });

  it("records a bare course-open touch when a non-reader view is visited", async () => {
    // The Map view has no lesson to record, so the App-level effect fires the bare touch
    // (the reader view records its own positioned touch — proven in CourseReader tests).
    const fetchMock = routedFetch({ runs: [makeRun()], course: makeCourse() });
    vi.stubGlobal("fetch", fetchMock);
    window.history.pushState(null, "", "/courses/course-test/map");

    render(<App />);
    await screen.findByRole("heading", { name: "How binary search works", level: 1 });

    // The open-touch feeds the library's last-opened sort; it must fire for the visited course.
    await waitFor(() => {
      const opened = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).endsWith("/api/courses/course-test/progress/opened") &&
          (init?.method ?? "GET").toUpperCase() === "PUT",
      );
      expect(opened).toBeTruthy();
    });
  });

  it("deep-links to the Map view at /courses/:courseId/map", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test/map");

    render(<App />);

    expect(await screen.findByRole("radio", { name: "Map" })).toBeChecked();
  });

  it("lights the Map with the learner's live mastery from the progress snapshot", async () => {
    // The P2 kcMastery field reaches the map end-to-end (P7): comparison mastered → its
    // dependent sorted_order is up next; binary_search (the goal) stays behind it.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun()],
        course: makeCourse(),
        progress: {
          courseId: "course-test",
          objectives: [],
          lessons: [],
          kcMastery: { comparison: true },
        },
      }),
    );
    window.history.pushState(null, "", "/courses/course-test/map");

    render(<App />);

    // The node cards announce their states in their labels. Asserted on the aria-label
    // attribute: React Flow keeps nodes visibility:hidden until measured (never, under jsdom's
    // stubbed ResizeObserver), which blanks accessible-name computation for role queries.
    const nodeLabelled = (fragments: string[]) =>
      document.querySelector(fragments.map((f) => `[aria-label*="${f}"]`).join(""));
    await waitFor(() => expect(nodeLabelled(["Comparison.", "Mastered."])).not.toBeNull());
    expect(nodeLabelled(["Sorted Order.", "Up next."])).not.toBeNull();
    expect(nodeLabelled(["Binary Search.", "Course goal.", "Locked"])).not.toBeNull();
  });

  it("switching the course view writes it to the URL", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/courses/course-test");

    render(<App />);
    await screen.findByRole("radio", { name: "Overview" });

    fireEvent.click(screen.getByRole("radio", { name: "Lessons" }));
    // The reader canonicalises its bare URL to the focused lesson (P6).
    await waitFor(() =>
      expect(window.location.pathname).toBe("/courses/course-test/lessons/m-binary_search-l0"),
    );

    fireEvent.click(screen.getByRole("radio", { name: "Map" }));
    expect(window.location.pathname).toBe("/courses/course-test/map");

    fireEvent.click(screen.getByRole("radio", { name: "Overview" }));
    expect(window.location.pathname).toBe("/courses/course-test");
  });

  it("opening a run from the rail navigates to its course URL; back returns home", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [makeRun()], course: makeCourse() }));
    window.history.pushState(null, "", "/");

    render(<App />);
    const history = await screen.findByRole("navigation", { name: /run history/i });
    fireEvent.click(within(history).getByText("How binary search works"));

    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");

    // jsdom dispatches popstate asynchronously; findByRole polls until the router re-renders.
    act(() => window.history.back());
    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening)/i }),
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
    // A user with no history gets the Activity screen's designed empty state, not zero-tiles.
    expect(await screen.findByText(/no activity yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Bookmarks" }));
    expect(window.location.pathname).toBe("/bookmarks");
    // A user with no saves gets the Bookmarks screen's designed empty state.
    expect(await screen.findByText(/no bookmarks yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Home" }));
    expect(window.location.pathname).toBe("/");
    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening)/i }),
    ).toBeInTheDocument();
  });

  it("renders the composer at /new (its own place, no longer normalized to /)", async () => {
    vi.stubGlobal("fetch", routedFetch());
    window.history.pushState(null, "", "/new");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/new");
  });

  it("renders the Home dashboard at / — the greeting, not the composer", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [makeCourseSummary()] }));
    window.history.pushState(null, "", "/");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening)/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: /what do you want to learn/i }),
    ).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("shows the first-run hero on Home when the library is empty", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [] }));
    window.history.pushState(null, "", "/");

    render(<App />);

    // No dead end: an empty Home funnels to the composer at /new.
    expect(await screen.findByText(/build your first course/i)).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("main")).getByRole("button", { name: /new course/i }));
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/new");
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

  it("the composer at /new shows idle again after a build hands off to its course", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse([courseFrame(makeCourse())]),
        course: makeCourse(),
      }),
    );
    window.history.pushState(null, "", "/new");

    render(<App />);
    fireEvent.change(await screen.findByLabelText("Topic"), {
      target: { value: "binary search" },
    });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    await screen.findByRole("heading", { name: "How binary search works", level: 1 });
    expect(window.location.pathname).toBe("/courses/course-test");

    // Regression: the composer is usable again after a build — New course returns to an idle /new,
    // never re-hosting the finished build.
    fireEvent.click(screen.getByRole("button", { name: /new course/i }));
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/new");
  });

  it("a finished build hands the URL off to its course", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse([courseFrame(makeCourse())]),
      }),
    );
    window.history.pushState(null, "", "/new");

    render(<App />);
    fireEvent.change(await screen.findByLabelText("Topic"), {
      target: { value: "binary search" },
    });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/course-test");
  });
});
