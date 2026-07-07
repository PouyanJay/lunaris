import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseReader } from "./CourseReader";
import { makeCourse, makeLesson, makeModule } from "../../test/fixtures";

/** Two modules (one lesson each) so Prev/Next crosses a lesson boundary; the first carries
 *  objectives so the understanding toggles render. */
function twoLessonCourse() {
  return makeCourse({
    modules: [
      makeModule({
        id: "m-one",
        title: "Module one",
        lessons: [makeLesson({ id: "m-one-l0" })],
        objectives: [
          {
            statement: "Explain the halving step.",
            bloomLevel: "understand",
            kc: "kc-1",
            assessedBy: [],
          },
          { statement: "Trace a full search.", bloomLevel: "apply", kc: "kc-2", assessedBy: [] },
        ],
      }),
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

describe("CourseReader — learner progress", () => {
  afterEach(() => vi.unstubAllGlobals());

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

    // The snapshot must have loaded (counter visible) without any LESSON-state PUT firing —
    // the open-recency touch (…/progress/opened) is expected on every visit and asserted in
    // its own tests below.
    expect(await screen.findByText(/of \d+ understood/)).toBeInTheDocument();
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

  it("toggling an objective updates the counter optimistically and persists it", async () => {
    const { mock, puts } = progressFetch();
    vi.stubGlobal("fetch", mock);

    render(<CourseReader course={twoLessonCourse()} apiBaseUrl="http://test" />);
    const toggle = (await screen.findAllByRole("button", { name: /mark understood/i }))[0]!;

    fireEvent.click(toggle);

    expect(await screen.findByText(/1 of \d+ understood/)).toBeInTheDocument();
    await waitFor(() =>
      expect(puts).toContainEqual({
        url: "http://test/api/courses/course-test/progress/objective",
        body: { moduleId: "m-one", objectiveIndex: 0, understood: true },
      }),
    );
  });
});
