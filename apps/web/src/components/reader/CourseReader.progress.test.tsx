import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CourseReader, READER_MODE_KEY } from "./CourseReader";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";

/** Two modules (one lesson each) so the footer's Next/Previous cross a module boundary. */
function twoLessonCourse() {
  return makeCourse({
    modules: [
      makeModule({ id: "m-one", title: "Module one", lessons: [makeLesson({ id: "m-one-l0" })] }),
      makeModule({ id: "m-two", title: "Module two", lessons: [makeLesson({ id: "m-two-l0" })] }),
    ],
  });
}

/** Serves the progress GET and records progress PUTs; everything else is unexpected. */
function progressFetch(
  snapshot: unknown = { courseId: "course-test", objectives: [], lessons: [] },
) {
  const puts: { url: string; body: unknown }[] = [];
  const mock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "PUT" && url.includes("/progress/")) {
      puts.push({ url, body: JSON.parse(String(init?.body)) });
      return Promise.resolve({ ok: true, status: 204 });
    }
    if (/\/progress$/.test(url)) {
      return Promise.resolve({ ok: true, json: async () => snapshot });
    }
    return Promise.reject(new Error(`progressFetch: unhandled ${method} ${url}`));
  });
  return { mock, puts };
}

// Progress persistence is mode-independent, but per-lesson footer paging (Next / Finish) lives in
// Watch mode now that Read is retired — pin Watch so those actions are on screen. The lessons ship
// no video, so Watch opens on the generate affordance with the footer beneath it.
beforeEach(() => {
  localStorage.setItem(READER_MODE_KEY, "watch");
});

describe("CourseReader — learner progress", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the outline's numbered chips with each lesson's progress state", async () => {
    // The rail mirrors the Overview's chip language (P6): ✓ on a done lesson, the lesson
    // number otherwise, with the state also in the entry's accessible name — never color alone.
    const { mock } = progressFetch({
      courseId: "course-test",
      objectives: [],
      lessons: [{ lessonId: "m-one-l0", state: "done", updatedAt: "2026-07-07T00:00:00Z" }],
    });
    vi.stubGlobal("fetch", mock);

    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);

    const outline = await screen.findByRole("navigation", { name: /course outline/i });
    await waitFor(() =>
      expect(within(outline).getByRole("button", { name: /lesson 1.*done/i })).toBeInTheDocument(),
    );
    expect(within(outline).getByRole("button", { name: /lesson 1.*done/i })).toHaveTextContent("✓");
    // The second lesson has no mark — its chip stays the plain number.
    expect(within(outline).getByRole("button", { name: /^lesson 2/i })).toHaveTextContent("2");
  });

  it("marks the opened lesson in_progress once its progress loads", async () => {
    const { mock, puts } = progressFetch();
    vi.stubGlobal("fetch", mock);

    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);

    await waitFor(() =>
      expect(puts).toContainEqual({
        url: "http://test/api/courses/course-test/progress/lesson",
        body: { lessonId: "m-one-l0", state: "in_progress" },
      }),
    );
  });

  it("does not re-mark a lesson that already has a state", async () => {
    const { mock, puts } = progressFetch({
      courseId: "course-test",
      objectives: [],
      lessons: [{ lessonId: "m-one-l0", state: "done", updatedAt: "2026-07-07T00:00:00Z" }],
    });
    vi.stubGlobal("fetch", mock);

    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);

    // The snapshot must have loaded (the outline chip reflects the done state) without any
    // LESSON-state PUT firing — the open-recency touch (…/progress/opened) is expected on every
    // visit and asserted in its own tests below.
    const outline = await screen.findByRole("navigation", { name: /course outline/i });
    await waitFor(() =>
      expect(within(outline).getByRole("button", { name: /lesson 1.*done/i })).toBeInTheDocument(),
    );
    expect(puts.filter((put) => put.url.endsWith("/progress/lesson"))).toEqual([]);
  });

  it("records the reading position on every lesson view, even a revisited done lesson", async () => {
    // Arrange — the lesson is already done; recency must still move on a re-read.
    const { mock, puts } = progressFetch({
      courseId: "course-test",
      objectives: [],
      lessons: [{ lessonId: "m-one-l0", state: "done", updatedAt: "2026-07-07T00:00:00Z" }],
    });
    vi.stubGlobal("fetch", mock);

    // Act
    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);

    // Assert — the open-recency touch carries the viewed lesson's id.
    await waitFor(() =>
      expect(puts).toContainEqual({
        url: "http://test/api/courses/course-test/progress/opened",
        body: { lastLessonId: "m-one-l0" },
      }),
    );
  });

  it("moves the recorded position to the next lesson on navigation", async () => {
    // Arrange
    const { mock, puts } = progressFetch();
    vi.stubGlobal("fetch", mock);
    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);
    await waitFor(() => expect(puts.length).toBeGreaterThan(0));

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Next lesson" }));

    // Assert — the touch re-fires with the NEW lesson id (recency follows the reader).
    await waitFor(() =>
      expect(puts).toContainEqual({
        url: "http://test/api/courses/course-test/progress/opened",
        body: { lastLessonId: "m-two-l0" },
      }),
    );
  });

  it("advancing marks the lesson done and the next one in_progress", async () => {
    const { mock, puts } = progressFetch();
    vi.stubGlobal("fetch", mock);

    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);
    await waitFor(() => expect(puts.length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Next lesson" }));

    await waitFor(() =>
      expect(puts).toContainEqual({
        url: "http://test/api/courses/course-test/progress/lesson",
        body: { lessonId: "m-one-l0", state: "done" },
      }),
    );
    await waitFor(() =>
      expect(puts).toContainEqual({
        url: "http://test/api/courses/course-test/progress/lesson",
        body: { lessonId: "m-two-l0", state: "in_progress" },
      }),
    );
  });

  it("Finish course marks the last lesson done", async () => {
    const { mock, puts } = progressFetch();
    vi.stubGlobal("fetch", mock);

    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);
    fireEvent.click(await screen.findByRole("button", { name: "Next lesson" }));

    const finish = await screen.findByRole("button", { name: "Finish course" });
    fireEvent.click(finish);

    await waitFor(() =>
      expect(puts).toContainEqual({
        url: "http://test/api/courses/course-test/progress/lesson",
        body: { lessonId: "m-two-l0", state: "done" },
      }),
    );
  });

  // Objective-understanding persistence (markObjective → …/progress/objective) is now evidenced
  // through the Learn-mode Try First challenge rather than a Read-mode objectives panel; the
  // full-stack PUT assertion lives in CourseReader.focusflow.test.tsx ("evidences the assessed
  // objective…"). The reader integration for lesson marks / recency / heartbeat stays here.

  it("beats the study-minutes heartbeat while mounted", async () => {
    // An open reader is a study session: the mount must fire the first heartbeat (the per-minute
    // cadence + visibility pause are proven in useStudyHeartbeat.test.ts).
    const beats: string[] = [];
    const { mock } = progressFetch();
    const withHeartbeat = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/activity/heartbeat") && init?.method === "PUT") {
        beats.push(url);
        return Promise.resolve({ ok: true, status: 204 });
      }
      return mock(input, init);
    });
    vi.stubGlobal("fetch", withHeartbeat);

    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);

    await waitFor(() => expect(beats).toHaveLength(1));
    expect(beats[0]).toBe("http://test/api/activity/heartbeat");
  });
});
