import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HomeDashboard } from "./HomeDashboard";
import { makeCourse, makeCourseSummary, makeRun, routedFetch } from "../../test/fixtures";

const EMPTY_ACTIVITY = {
  stats: { currentStreak: 0, longestStreak: 0, minutesThisWeek: 0, conceptsThisWeek: 0 },
  heat: [],
  week: [],
  feed: [],
};

/** A completed course summary — lands in the recent grid, not the continue section. */
function completed(overrides = {}) {
  return makeCourseSummary({
    learnerStatus: "completed",
    lessonsDone: 6,
    percent: 100,
    ...overrides,
  });
}

function renderHome(props: Partial<Parameters<typeof HomeDashboard>[0]> = {}) {
  const callbacks = {
    onNewCourse: vi.fn(),
    onResumeLesson: vi.fn(),
    onViewCourse: vi.fn(),
  };
  render(
    <MemoryRouter>
      <HomeDashboard
        apiBaseUrl="http://test"
        userName="Ada Lovelace"
        runs={[]}
        {...callbacks}
        {...props}
      />
    </MemoryRouter>,
  );
  return callbacks;
}

describe("HomeDashboard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("greets the signed-in learner by their display name", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [completed()] }));

    renderHome();

    expect(
      await screen.findByRole("heading", {
        name: /good (morning|afternoon|evening), ada lovelace/i,
      }),
    ).toBeInTheDocument();
    // The subline reflects real library progress (6 completed lessons on the one completed course).
    expect(await screen.findByText("6 lessons completed")).toBeInTheDocument();
  });

  it("leads the subline with the live streak once activity loads", async () => {
    // The P9 feedback loop: the streak figure from /api/activity joins the greeting. Progressive
    // enhancement — the library-derived subline renders first and the streak prefixes it.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        library: [completed()],
        activity: {
          stats: { currentStreak: 5, longestStreak: 11, minutesThisWeek: 30, conceptsThisWeek: 2 },
          heat: [],
          week: [],
          feed: [],
        },
      }),
    );

    renderHome();

    expect(await screen.findByText("5-day streak · 6 lessons completed")).toBeInTheDocument();
  });

  it("keeps the honest subline when the activity fetch fails", async () => {
    // No invented figures: a dead activity backend must not break or decorate the greeting.
    vi.stubGlobal(
      "fetch",
      vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.includes("/api/activity")) return Promise.reject(new Error("down"));
        return routedFetch({ library: [completed()] })(input, init);
      }),
    );

    renderHome();

    expect(await screen.findByText("6 lessons completed")).toBeInTheDocument();
  });

  it("renders the natural fallback name in the greeting", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [] }));

    renderHome({ userName: "there" });

    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening), there/i }),
    ).toBeInTheDocument();
  });

  it("shows a loading skeleton region while the library is in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderHome();

    expect(
      screen.getByRole("heading", { name: /good (morning|afternoon|evening)/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/loading your courses/i)).toBeInTheDocument();
  });

  it("renders a recoverable error when the library fails to load", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    renderHome();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("offers a first-run hero that funnels to the composer when there are no courses", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [] }));

    const { onNewCourse } = renderHome();

    fireEvent.click(await screen.findByRole("button", { name: /new course/i }));
    expect(onNewCourse).toHaveBeenCalledOnce();
  });

  it("shows only the recent grid when nothing is in progress (no continue section)", async () => {
    const courses = [
      completed({ id: "c-1", topic: "How HTTPS works" }),
      completed({ id: "c-2", topic: "How binary search works", learnerStatus: "not_started" }),
    ];
    vi.stubGlobal("fetch", routedFetch({ library: courses }));

    renderHome();

    const first = await screen.findByRole("link", { name: /how https works/i });
    expect(first).toHaveAttribute("href", "/courses/c-1");
    expect(screen.getByRole("link", { name: /how binary search works/i })).toHaveAttribute(
      "href",
      "/courses/c-2",
    );
    // No in-progress course → the continue section is absent, not an empty hero.
    expect(screen.queryByRole("heading", { name: "Continue learning" })).not.toBeInTheDocument();
    // Two courses fit on Home — no need for a "view all" escape hatch.
    expect(screen.queryByRole("link", { name: /view all courses/i })).not.toBeInTheDocument();
  });

  it("surfaces a live-build banner for a running run, linking into its canvas", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [completed()] }));

    renderHome({
      runs: [makeRun({ id: "course-live", status: "running", topic: "Quantum computing" })],
    });

    const banner = await screen.findByRole("link", { name: /building.*quantum computing/i });
    expect(banner).toHaveAttribute("href", "/courses/course-live");
  });

  it("shows no live-build banner when every run is terminal", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [completed()] }));

    renderHome({ runs: [makeRun({ status: "completed" }), makeRun({ status: "failed" })] });

    await screen.findByRole("heading", { name: /good (morning|afternoon|evening)/i });
    expect(screen.queryByRole("link", { name: /building/i })).not.toBeInTheDocument();
  });

  it("shows a View-all hatch when the library holds more than Home surfaces", async () => {
    const courses = Array.from({ length: 5 }, (_, i) =>
      completed({ id: `c-${i}`, topic: `Course ${i}` }),
    );
    vi.stubGlobal("fetch", routedFetch({ library: courses }));

    renderHome();

    await waitFor(() =>
      expect(screen.getByRole("link", { name: /view all courses/i })).toHaveAttribute(
        "href",
        "/courses",
      ),
    );
    // Only three recent cards on Home; the library holds the rest.
    expect(screen.getAllByRole("link", { name: /^course \d/i })).toHaveLength(3);
  });

  it("deletes a course from its Home recent-grid card: confirm → DELETE → the card leaves", async () => {
    // Arrange — a stateful fake: DELETE empties the library; the reload GET reflects it.
    let library = [completed({ id: "c-https", topic: "How HTTPS works" })];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "DELETE" && /\/api\/courses\/[^/?]+$/.test(url)) {
        library = [];
        return { ok: true, status: 204, json: async () => ({}) };
      }
      if (/\/api\/activity(\?|$)/.test(url)) {
        return { ok: true, json: async () => EMPTY_ACTIVITY };
      }
      if (/\/api\/courses$/.test(url)) return { ok: true, json: async () => library };
      throw new Error(`unhandled ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderHome();
    await screen.findByRole("link", { name: /how https works/i });

    // Act — the recent-grid card's recycle bin, then confirm in the dialog.
    fireEvent.click(screen.getByRole("button", { name: /delete course: how https works/i }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^delete$/i }));

    // Assert — the DELETE hit the course id, and the card leaves Home after the reload.
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/courses\/c-https$/),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: /how https works/i })).not.toBeInTheDocument(),
    );
  });

  describe("continue-learning hero", () => {
    it("resumes the most-recent in-progress course at its resume lesson", async () => {
      const summary = makeCourseSummary({
        id: "course-test",
        topic: "How binary search works",
        learnerStatus: "in_progress",
        lessonsDone: 0,
        lessonTotal: 1,
        percent: 0,
      });
      const lessonId = "m-binary_search-l0";
      vi.stubGlobal(
        "fetch",
        routedFetch({
          library: [summary],
          course: makeCourse(),
          progress: { courseId: "course-test", objectives: [], lessons: [], lastLessonId: lessonId },
        }),
      );

      const { onResumeLesson } = renderHome();

      // The hero enriches to the real resume position once the course loads.
      expect(await screen.findByText(/lesson 1 of 1/i)).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Continue learning" })).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /resume lesson/i }));
      expect(onResumeLesson).toHaveBeenCalledWith("course-test", lessonId);
    });

    it("still resumes at the right lesson when only the progress call fails", async () => {
      const summary = makeCourseSummary({
        id: "course-test",
        topic: "How binary search works",
        learnerStatus: "in_progress",
      });
      const lessonId = "m-binary_search-l0";
      // Course loads (200); progress 500s — the resume point still resolves from the course itself.
      vi.stubGlobal(
        "fetch",
        vi.fn((input: Parameters<typeof fetch>[0]) => {
          const url = input instanceof Request ? input.url : String(input);
          if (/\/api\/courses$/.test(url)) {
            return Promise.resolve({ ok: true, json: async () => [summary] });
          }
          if (/\/api\/courses\/[^/]+\/progress$/.test(url)) {
            return Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
          }
          if (/\/api\/courses\/[^/?]+$/.test(url)) {
            return Promise.resolve({ ok: true, json: async () => makeCourse() });
          }
          return Promise.resolve({ ok: true, json: async () => ({}) });
        }),
      );

      const { onResumeLesson } = renderHome();

      expect(await screen.findByText(/lesson 1 of 1/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /resume lesson/i }));
      expect(onResumeLesson).toHaveBeenCalledWith("course-test", lessonId);
    });

    it("opens the Overview from the hero's View course action", async () => {
      const summary = makeCourseSummary({ id: "course-test", learnerStatus: "in_progress" });
      vi.stubGlobal(
        "fetch",
        routedFetch({ library: [summary], course: makeCourse(), progress: undefined }),
      );

      const { onViewCourse } = renderHome();

      fireEvent.click(await screen.findByRole("button", { name: /view course/i }));
      expect(onViewCourse).toHaveBeenCalledWith("course-test");
    });

    it("degrades to a summary-only hero when the course can't be loaded", async () => {
      const summary = makeCourseSummary({
        id: "course-test",
        topic: "How binary search works",
        learnerStatus: "in_progress",
      });
      // Library loads; the hero's deep course fetch 500s → resume falls back to the Overview.
      vi.stubGlobal(
        "fetch",
        vi.fn((input: Parameters<typeof fetch>[0]) => {
          const url = input instanceof Request ? input.url : String(input);
          if (/\/api\/courses$/.test(url)) {
            return Promise.resolve({ ok: true, json: async () => [summary] });
          }
          if (/\/api\/courses\/[^/?]+$/.test(url)) {
            return Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
          }
          if (/\/api\/courses\/[^/]+\/progress$/.test(url)) {
            return Promise.resolve({ ok: true, json: async () => ({ lessons: [] }) });
          }
          return Promise.resolve({ ok: true, json: async () => ({}) });
        }),
      );

      const { onResumeLesson, onViewCourse } = renderHome();

      // The hero still renders from the summary; Resume routes to Overview (no lesson known).
      fireEvent.click(await screen.findByRole("button", { name: /resume lesson/i }));
      expect(onViewCourse).toHaveBeenCalledWith("course-test");
      expect(onResumeLesson).not.toHaveBeenCalled();
    });

    it("shows the continue section and the recent grid together", async () => {
      const courses = [
        makeCourseSummary({ id: "c-hero", topic: "In-progress course", learnerStatus: "in_progress" }),
        completed({ id: "c-done", topic: "Finished course" }),
      ];
      vi.stubGlobal(
        "fetch",
        routedFetch({ library: courses, course: makeCourse(), progress: undefined }),
      );

      renderHome();

      expect(
        await screen.findByRole("heading", { name: "Continue learning" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Recent courses" })).toBeInTheDocument();
      // The completed course sits in the recent grid, not the continue section.
      expect(screen.getByRole("link", { name: /finished course/i })).toHaveAttribute(
        "href",
        "/courses/c-done",
      );
    });

    it("renders compact rows for the other in-progress courses, linking to each Overview", async () => {
      const courses = [
        makeCourseSummary({ id: "c-hero", topic: "Hero course", learnerStatus: "in_progress" }),
        makeCourseSummary({ id: "c-row", topic: "Second course", learnerStatus: "in_progress" }),
      ];
      vi.stubGlobal(
        "fetch",
        routedFetch({ library: courses, course: makeCourse(), progress: undefined }),
      );

      renderHome();

      // The hero (c-hero) is a button pair; the other in-progress course is a compact row link.
      const row = await screen.findByRole("link", { name: /second course/i });
      expect(row).toHaveAttribute("href", "/courses/c-row");
    });
  });
});
