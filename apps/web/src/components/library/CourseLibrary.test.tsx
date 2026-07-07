import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseLibrary } from "./CourseLibrary";
import { makeCourseSummary } from "../../test/fixtures";
import type { CourseSummary } from "../../types/course";

const TWO_COURSES: CourseSummary[] = [
  makeCourseSummary({ id: "c-https", topic: "How HTTPS works", lessonTotal: 6 }),
  makeCourseSummary({
    id: "c-search",
    topic: "How binary search works",
    lessonTotal: 1,
    lessonsDone: 1,
    percent: 100,
    learnerStatus: "completed",
    level: "beginner",
  }),
];

function json(body: unknown) {
  return { ok: true, json: async () => body };
}

function renderLibrary(onNewCourse = vi.fn()) {
  render(
    <MemoryRouter>
      <CourseLibrary apiBaseUrl="http://test" onNewCourse={onNewCourse} />
    </MemoryRouter>,
  );
  return onNewCourse;
}

describe("CourseLibrary", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a card-shaped loading skeleton while the library is in flight", () => {
    // Arrange — a fetch that never resolves holds the loading state.
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    // Act
    renderLibrary();

    // Assert
    expect(screen.getByRole("list", { name: /loading courses/i })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("renders a linked card per course, with its lesson count", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(TWO_COURSES)));
    renderLibrary();

    // Assert — one real link per summary (not a hardcoded card), each into its own canvas.
    const https = await screen.findByRole("link", { name: /how https works/i });
    const search = screen.getByRole("link", { name: /how binary search works/i });
    expect(https).toHaveAttribute("href", "/courses/c-https");
    expect(search).toHaveAttribute("href", "/courses/c-search");
    expect(https).toHaveAccessibleName(/6 lessons/i);
    expect(search).toHaveAccessibleName(/1 lesson\b/i);
  });

  it("shows the designed empty state whose action starts a new course", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([])));
    const onNewCourse = renderLibrary();
    await screen.findByText(/no courses yet/i);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /new course/i }));

    // Assert
    expect(onNewCourse).toHaveBeenCalledTimes(1);
  });

  it("surfaces an HTTP failure as a recoverable error, then retries on Try again", async () => {
    // Arrange — the first load 503s, the retry succeeds.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) })
      .mockResolvedValueOnce(json(TWO_COURSES));
    vi.stubGlobal("fetch", fetchMock);
    renderLibrary();
    expect(await screen.findByRole("alert")).toHaveTextContent(/HTTP 503/);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    // Assert
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /how https works/i })).toBeInTheDocument(),
    );
  });

  it("surfaces a transport failure with the unreachable-library message", async () => {
    // Arrange — fetch rejects outright (server down, no HTTP response at all).
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));

    // Act
    renderLibrary();

    // Assert
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not reach the course library/i,
    );
  });
});
