import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HomeDashboard } from "./HomeDashboard";
import { makeCourse, makeCourseSummary, makeRun, routedFetch } from "../../test/fixtures";

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
        userEmail="ada.lovelace@example.com"
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

  it("greets the signed-in learner by their derived name", async () => {
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

  it("falls back to a natural greeting when there is no signed-in email", async () => {
    vi.stubGlobal("fetch", routedFetch({ library: [] }));

    renderHome({ userEmail: null });

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

  it("renders the recent grid of non-in-progress courses as linked cover cards", async () => {
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
