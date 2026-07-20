import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeCourse, makeLesson, routedFetch } from "../../test/fixtures";
import { CourseReader, READER_MODE_KEY } from "./CourseReader";

/** A frozen "now", so today-XP windowing is deterministic regardless of when the suite runs. */
const NOW = new Date("2026-07-20T18:00:00");
/** A timestamp on the frozen day, for feed events that must count toward "today". */
function todayAt(hour: number): string {
  const d = new Date(NOW);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

function activityView(overrides: Record<string, unknown> = {}) {
  return {
    stats: { currentStreak: 6, longestStreak: 9, minutesThisWeek: 40, conceptsThisWeek: 3 },
    heat: [],
    week: [],
    feed: [],
    ...overrides,
  };
}

/** routedFetch with a well-formed progress snapshot, then override just the /api/activity route. */
function trailFetch(activityRoute: (input: unknown) => Promise<unknown>) {
  const base = routedFetch({ progress: { courseId: "course-test", objectives: [], lessons: [] } });
  return vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) =>
    /\/api\/activity(\?|$)/.test(String(input))
      ? activityRoute(input)
      : base(input as never, init as never),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

/** Trail (lesson-experience redesign phase 4): the motivation band. */
describe("CourseReader — Trail motivation band", () => {
  it("shows the streak and lesson position in Learn mode with a reachable API", async () => {
    // Arrange
    const fetchMock = routedFetch({ activity: activityView() });
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);

    // Assert — a labelled motivation band carrying the real streak + course position.
    const band = await screen.findByRole("group", { name: /your progress/i });
    expect(band).toHaveTextContent(/6 day/i);
    expect(band).toHaveTextContent(/lesson 1 of 1/i);
  });

  it("derives today's XP toward the goal from the real event feed", async () => {
    // Arrange — one completed lesson (10) + one mastered concept (5) today → 15 / 30.
    const fetchMock = routedFetch({
      activity: activityView({
        feed: [
          { eventType: "completed", courseId: "course-test", occurredAt: todayAt(9) },
          {
            eventType: "mastered",
            courseId: "course-test",
            kcId: "binary_search",
            occurredAt: todayAt(10),
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);

    // Assert
    const band = await screen.findByRole("group", { name: /your progress/i });
    expect(band).toHaveTextContent(/15 \/ 30 XP/i);
    const meter = within(band).getByRole("progressbar", { name: /today's goal/i });
    expect(meter).toHaveAttribute("aria-valuenow", "15");
  });

  it("reloads activity when a lesson is completed", async () => {
    // Arrange — two lessons; count the activity fetches.
    const fetchMock = routedFetch({
      progress: { courseId: "course-test", objectives: [], lessons: [] },
      activity: activityView({
        stats: { currentStreak: 1, longestStreak: 1, minutesThisWeek: 5, conceptsThisWeek: 0 },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const course = makeCourse();
    course.modules[0]!.lessons = [makeLesson(), makeLesson({ id: "m-binary_search-l1" })];
    render(<CourseReader course={course} apiBaseUrl="http://api.test" />);
    await screen.findByRole("group", { name: /your progress/i });
    const activityCalls = () =>
      fetchMock.mock.calls.filter((call) => /\/api\/activity(\?|$)/.test(String(call[0]))).length;
    const before = activityCalls();

    // Act — walk to the end of lesson 1 (7 steps) and complete it.
    for (let i = 0; i < 6; i += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "Next lesson" }));

    // Assert — completion triggered a fresh activity read.
    await waitFor(() => {
      expect(activityCalls()).toBeGreaterThan(before);
    });
  });

  it("shows a skeleton band while activity is loading", async () => {
    // Arrange — the activity route never settles; other routes resolve normally.
    const fetchMock = trailFetch(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);

    // Assert — the band is present and marked busy, with no metrics yet.
    await waitFor(() => {
      expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
    });
    const band = screen.getByRole("group", { name: /your progress/i });
    expect(band).toHaveAttribute("aria-busy", "true");
    expect(band).not.toHaveTextContent(/streak/i);
  });

  it("hides the band when the activity load errors", async () => {
    // Arrange — the activity route rejects; other routes resolve normally.
    const fetchMock = trailFetch(() => Promise.reject(new Error("down")));
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);

    // Assert — reading is unaffected; the band never appears, no error surfaced.
    await waitFor(() => {
      expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("group", { name: /your progress/i })).not.toBeInTheDocument();
  });

  it("shows no band offline (no apiBaseUrl)", async () => {
    // Arrange / Act — Learn mode, but no API: useActivity settles to error without fetching.
    render(<CourseReader course={makeCourse()} />);

    // Assert
    await waitFor(() => {
      expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("group", { name: /your progress/i })).not.toBeInTheDocument();
  });

  it("shows no band in Read mode", async () => {
    // Arrange — pin Read; activity is reachable but the band is a Learn-mode layer.
    localStorage.setItem(READER_MODE_KEY, "read");
    const fetchMock = routedFetch({ activity: activityView() });
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);

    // Assert
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Warm-up" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("group", { name: /your progress/i })).not.toBeInTheDocument();
  });
});
