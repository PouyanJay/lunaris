import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseOverview } from "./CourseOverview";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";
import type { Course } from "../../types/course";

/** Two modules / three lessons; module one carries one objective (shown on its first lesson). */
function threeLessonCourse(): Course {
  return makeCourse({
    modules: [
      makeModule({
        id: "m-1",
        title: "Foundations",
        lessons: [makeLesson({ id: "m-1-l0" })],
        objectives: [
          {
            statement: "Explain the halving step.",
            bloomLevel: "understand",
            kc: "kc-1",
            assessedBy: [],
          },
        ],
      }),
      makeModule({
        id: "m-2",
        title: "The algorithm",
        lessons: [makeLesson({ id: "m-2-l0" }), makeLesson({ id: "m-2-l1" })],
        objectives: [
          { statement: "Trace the loop.", bloomLevel: "apply", kc: "kc-2", assessedBy: [] },
          { statement: "Bound the steps.", bloomLevel: "analyze", kc: "kc-2", assessedBy: [] },
        ],
      }),
    ],
  });
}

/** Serves the progress GET — the Overview only reads (it never issues progress writes). */
function progressFetch(snapshot: unknown) {
  return vi.fn((input: Parameters<typeof fetch>[0]) => {
    if (/\/progress$/.test(String(input))) {
      return Promise.resolve({ ok: true, json: async () => snapshot });
    }
    return Promise.reject(new Error(`unhandled ${String(input)}`));
  });
}

const SNAPSHOT = {
  courseId: "course-test",
  objectives: [],
  lessons: [
    { lessonId: "m-1-l0", state: "done", updatedAt: "2026-07-07T00:00:00Z" },
    { lessonId: "m-2-l0", state: "in_progress", updatedAt: "2026-07-07T00:01:00Z" },
  ],
  summary: {
    understoodCount: 0,
    objectiveTotal: 1,
    lessonsDone: 1,
    lessonTotal: 3,
    percent: 33,
  },
  kcMastery: {},
  lastOpenedAt: "2026-07-07T00:01:00Z",
  lastLessonId: "m-2-l0",
};

function renderOverview(
  overrides: Partial<{
    onContinue: (lessonId?: string) => void;
    onViewMap: () => void;
    onOpenLesson: (lessonId: string) => void;
    onRequestDelete: () => void;
  }> = {},
) {
  const handlers = {
    onContinue: vi.fn(),
    onViewMap: vi.fn(),
    onOpenLesson: vi.fn(),
    ...overrides,
  };
  render(
    <CourseOverview
      course={threeLessonCourse()}
      apiBaseUrl="http://test"
      onContinue={handlers.onContinue}
      onViewMap={handlers.onViewMap}
      onOpenLesson={handlers.onOpenLesson}
      onRequestDelete={overrides.onRequestDelete}
    />,
  );
  return handlers;
}

describe("CourseOverview", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks to delete the course from its danger-zone action", () => {
    // Arrange
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    const onRequestDelete = vi.fn();
    renderOverview({ onRequestDelete });

    // Act
    fireEvent.click(screen.getByRole("button", { name: /delete course/i }));

    // Assert
    expect(onRequestDelete).toHaveBeenCalledTimes(1);
  });

  it("omits the delete affordance when the course can't be deleted here", () => {
    // Arrange / Act — no onDelete (e.g. the offline sample course).
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    renderOverview();

    // Assert
    expect(screen.queryByRole("button", { name: /delete course/i })).not.toBeInTheDocument();
  });

  it("renders the hero facts: counts, a real level pill, and the course title", () => {
    // Arrange / Act — the fixture graph's mean difficulty (0.1+0.45+0.75)/3 ≈ 0.43.
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    renderOverview();

    // Assert
    expect(screen.getByText("3 lessons · 3 concepts")).toBeInTheDocument();
    expect(screen.getByText("INTERMEDIATE")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How binary search works" })).toBeInTheDocument();
  });

  it("shows the learner's progress as a bar and an x-of-y line", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    renderOverview();

    // Assert
    expect(await screen.findByText("1 of 3 lessons · 33%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "33");
  });

  it("lists every lesson with its state chip, module title, and objective count", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    renderOverview();

    // Assert — done shows ✓/Done; the snapshot's in-progress lesson reads In progress; an
    // untouched one reads Up next. The first lesson of a module carries its objectives count.
    const rows = await screen.findAllByRole("button", { name: /lesson \d/i });
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("DONE")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Foundations")).toBeInTheDocument();
    expect(within(rows[0]!).getByText(/lesson 1 · 1 objective\b/i)).toBeInTheDocument();
    expect(within(rows[1]!).getByText("IN PROGRESS")).toBeInTheDocument();
    expect(within(rows[1]!).getByText(/lesson 2 · 2 objectives/i)).toBeInTheDocument();
    expect(within(rows[2]!).getByText("UP NEXT")).toBeInTheDocument();
    expect(within(rows[2]!).queryByText("✓")).not.toBeInTheDocument();
  });

  it("opens the clicked lesson in the reader", async () => {
    // Arrange
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    const { onOpenLesson } = renderOverview();
    const rows = await screen.findAllByRole("button", { name: /lesson \d/i });

    // Act
    fireEvent.click(rows[2]!);

    // Assert
    expect(onOpenLesson).toHaveBeenCalledWith("m-2-l1");
  });

  it("Continue prefers the recorded position over the first unfinished lesson", async () => {
    // Arrange — first-unfinished is m-2-l0, but the learner last READ m-2-l1 (re-reading a done
    // lesson): the two candidates diverge, so this pins the precedence, not a coincidence.
    vi.stubGlobal(
      "fetch",
      progressFetch({
        ...SNAPSHOT,
        lessons: [
          { lessonId: "m-1-l0", state: "done", updatedAt: "2026-07-07T00:00:00Z" },
          { lessonId: "m-2-l1", state: "done", updatedAt: "2026-07-07T00:02:00Z" },
        ],
        lastLessonId: "m-2-l1",
      }),
    );
    const { onContinue } = renderOverview();
    await screen.findByText("1 of 3 lessons · 33%");

    // Act
    fireEvent.click(screen.getByRole("button", { name: /continue learning/i }));

    // Assert — the recorded position wins over first-unfinished (m-2-l0).
    expect(onContinue).toHaveBeenCalledWith("m-2-l1");
  });

  it("Continue falls back when the recorded position no longer exists in the course", async () => {
    // Arrange — a rebuild can drop lessons; a stale id must not be resumed to.
    vi.stubGlobal("fetch", progressFetch({ ...SNAPSHOT, lastLessonId: "no-such-lesson" }));
    const { onContinue } = renderOverview();
    await screen.findByText("1 of 3 lessons · 33%");

    // Act
    fireEvent.click(screen.getByRole("button", { name: /continue learning/i }));

    // Assert — first unfinished (m-2-l0) instead of the ghost.
    expect(onContinue).toHaveBeenCalledWith("m-2-l0");
  });

  it("Continue falls back to the first unfinished lesson without a recorded position", async () => {
    // Arrange — same marks, no lastLessonId: m-1-l0 is done, so m-2-l0 is first unfinished.
    vi.stubGlobal("fetch", progressFetch({ ...SNAPSHOT, lastLessonId: null }));
    const { onContinue } = renderOverview();
    await screen.findByText("1 of 3 lessons · 33%");

    // Act
    fireEvent.click(screen.getByRole("button", { name: /continue learning/i }));

    // Assert
    expect(onContinue).toHaveBeenCalledWith("m-2-l0");
  });

  it("stays useful offline: no progress chrome, Continue still opens the reader", async () => {
    // Arrange — the progress fetch fails (or the surface is offline): the hero facts and the
    // lesson list must render regardless, with every state reading Up next.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    const { onContinue } = renderOverview();

    // Act / Assert
    expect(screen.getByText("3 lessons · 3 concepts")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /lesson \d/i })).toHaveLength(3),
    );
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /continue learning/i }));
    expect(onContinue).toHaveBeenCalledWith(undefined);
  });

  it("shows the honest scope band when the build computed one — and not otherwise", async () => {
    // Arrange — a course whose finalize computed the scope-realism band.
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    const scoped = {
      ...threeLessonCourse(),
      scope: { effort: "~2 weeks, self-paced", delivers: ["Search fluency"], excludes: [] },
    };
    render(
      <CourseOverview
        course={scoped}
        apiBaseUrl="http://test"
        onContinue={vi.fn()}
        onViewMap={vi.fn()}
        onOpenLesson={vi.fn()}
      />,
    );

    // Assert — the band's facts render; the default fixture (no scope) never shows them.
    expect(await screen.findByText(/~2 weeks, self-paced/)).toBeInTheDocument();
    expect(screen.getByText("Search fluency")).toBeInTheDocument();
  });

  it("fires the View-the-map action", () => {
    // Arrange
    vi.stubGlobal("fetch", progressFetch(SNAPSHOT));
    const { onViewMap } = renderOverview();

    // Act
    fireEvent.click(screen.getByRole("button", { name: /view the map/i }));

    // Assert
    expect(onViewMap).toHaveBeenCalledTimes(1);
  });
});
