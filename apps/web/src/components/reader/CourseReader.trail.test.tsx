import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse, makeLesson, routedFetch } from "../../test/fixtures";
import { CourseReader, READER_MODE_KEY } from "./CourseReader";

/** Today's ISO timestamp, so feed events land in the current local day for the XP window. */
function todayAt(hour: number): string {
  const d = new Date();
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

/** Trail (lesson-experience redesign phase 4): the motivation band. */
describe("CourseReader — Trail motivation band", () => {
  it("shows the streak and lesson position in Learn mode with a reachable API", async () => {
    // Arrange — a reachable activity snapshot with a live streak.
    const fetchMock = routedFetch({
      activity: {
        stats: { currentStreak: 6, longestStreak: 9, minutesThisWeek: 40, conceptsThisWeek: 3 },
        heat: [],
        week: [],
        feed: [],
      },
    });
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
      activity: {
        stats: { currentStreak: 2, longestStreak: 4, minutesThisWeek: 12, conceptsThisWeek: 1 },
        heat: [],
        week: [],
        feed: [
          { eventType: "completed", courseId: "course-test", occurredAt: todayAt(9) },
          {
            eventType: "mastered",
            courseId: "course-test",
            kcId: "binary_search",
            occurredAt: todayAt(10),
          },
        ],
      },
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
      activity: {
        stats: { currentStreak: 1, longestStreak: 1, minutesThisWeek: 5, conceptsThisWeek: 0 },
        heat: [],
        week: [],
        feed: [],
      },
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

  it("shows no band offline (no apiBaseUrl)", () => {
    // Arrange / Act — Learn mode, but no API to read activity from.
    render(<CourseReader course={makeCourse()} />);

    // Assert
    expect(screen.queryByRole("group", { name: /your progress/i })).not.toBeInTheDocument();
  });

  it("shows a skeleton band while activity is loading", () => {
    // Arrange — a fetch that never resolves keeps activity in the loading state.
    const fetchMock = routedFetch({ activity: { stats: {}, heat: [], week: [], feed: [] } });
    fetchMock.mockImplementation((input: Parameters<typeof fetch>[0]) => {
      if (/\/api\/activity(\?|$)/.test(String(input))) return new Promise(() => {});
      return Promise.resolve({ ok: true, status: 204, json: async () => ({}) });
    });
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);

    // Assert — the band is present and marked busy, with no metrics yet.
    const band = screen.getByRole("group", { name: /your progress/i });
    expect(band).toHaveAttribute("aria-busy", "true");
    expect(band).not.toHaveTextContent(/streak/i);
  });

  it("hides the band when the activity load errors", async () => {
    // Arrange — a rejected activity fetch.
    const fetchMock = routedFetch({ activity: { stats: {}, heat: [], week: [], feed: [] } });
    fetchMock.mockImplementation((input: Parameters<typeof fetch>[0]) => {
      if (/\/api\/activity(\?|$)/.test(String(input))) return Promise.reject(new Error("down"));
      return Promise.resolve({ ok: true, status: 204, json: async () => ({}) });
    });
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);

    // Assert — reading is unaffected; the band never appears, no error surfaced.
    await waitFor(() => {
      expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("group", { name: /your progress/i })).not.toBeInTheDocument();
  });

  it("shows no band in Read mode", async () => {
    // Arrange — pin Read; activity is reachable but the band is a Learn-mode layer.
    localStorage.setItem(READER_MODE_KEY, "read");
    const fetchMock = routedFetch({
      activity: {
        stats: { currentStreak: 6, longestStreak: 9, minutesThisWeek: 40, conceptsThisWeek: 3 },
        heat: [],
        week: [],
        feed: [],
      },
    });
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
