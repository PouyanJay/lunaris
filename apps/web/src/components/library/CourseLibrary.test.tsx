import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseLibrary } from "./CourseLibrary";
import { makeCourseSummary, makeRun } from "../../test/fixtures";
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

/** One card per learner status (plus a review-gated build) for the filter/facts tests. */
const THREE_COURSES: CourseSummary[] = [
  ...TWO_COURSES,
  makeCourseSummary({
    id: "c-merge",
    topic: "How merge sort works",
    lessonTotal: 5,
    lessonsDone: 0,
    percent: 0,
    learnerStatus: "not_started",
    level: "beginner",
    lastOpenedAt: null,
    courseStatus: "review",
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

  it("deletes a course from its card: confirm dialog → DELETE → the card leaves the grid", async () => {
    // Arrange — a stateful fake: GET lists the (shrinking) library; DELETE removes one course.
    let courses = [...TWO_COURSES];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const del = url.match(/\/api\/courses\/([^/?]+)$/);
      if (method === "DELETE" && del) {
        const deletedId = decodeURIComponent(del[1] ?? "");
        courses = courses.filter((c) => c.id !== deletedId);
        return { ok: true, status: 204, json: async () => ({}) };
      }
      return json(courses);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderLibrary();
    await screen.findByRole("link", { name: /how https works/i });

    // Act — open the card's delete affordance, then confirm in the dialog.
    fireEvent.click(screen.getByRole("button", { name: /delete course: how https works/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/how https works/i)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    // Assert — the DELETE hit the course's endpoint and the card left the grid after the reload.
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/courses\/c-https$/),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: /how https works/i })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: /how binary search works/i })).toBeInTheDocument();
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

  it("summarises the collection in the counts subline", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(THREE_COURSES)));
    renderLibrary();

    // Assert
    expect(
      await screen.findByText("3 courses · 1 in progress · 1 completed · 1 not started"),
    ).toBeInTheDocument();
  });

  it("filters the grid by learner status via the pills", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(THREE_COURSES)));
    renderLibrary();
    await screen.findByRole("link", { name: /how https works/i });

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Completed" }));

    // Assert — only the completed course remains; the active pill is pressed.
    expect(screen.getByRole("link", { name: /how binary search works/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /how https works/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Completed" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows a designed notice when a filter matches nothing", async () => {
    // Arrange — every course is in progress; the Completed filter has no matches.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([makeCourseSummary()])));
    renderLibrary();
    await screen.findByRole("link", { name: /how https works/i });

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Completed" }));

    // Assert — an explanation with a way out, never a silently blank grid.
    expect(screen.getByText(/no completed courses yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByRole("link", { name: /how https works/i })).toBeInTheDocument();
  });

  it("renders each card's facts: meta line, progress bar, status", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(THREE_COURSES)));
    renderLibrary();
    const card = await screen.findByRole("link", { name: /how https works/i });

    // Assert — "N lessons · Level" mono meta, a determinate bar at the real percent, and the
    // house dot + uppercase-mono status label.
    expect(card).toHaveAccessibleName(/6 lessons · Intermediate/i);
    const bar = within(card).getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "67");
    expect(within(card).getByText("IN PROGRESS")).toBeInTheDocument();
  });

  it("tones the progress bar by status: success once completed, accent while working", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(THREE_COURSES)));
    renderLibrary();
    const completed = await screen.findByRole("link", { name: /how binary search works/i });
    const working = screen.getByRole("link", { name: /how https works/i });

    // Assert — the fill's tone attribute drives the hue (colour is paired with the status text).
    expect(within(completed).getByRole("progressbar").firstChild).toHaveAttribute(
      "data-tone",
      "success",
    );
    expect(within(working).getByRole("progressbar").firstChild).toHaveAttribute(
      "data-tone",
      "accent",
    );
  });

  it("flags a review-gated course honestly", async () => {
    // Arrange / Act — c-merge's build finished in review (publish gates not met).
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(THREE_COURSES)));
    renderLibrary();
    const card = await screen.findByRole("link", { name: /how merge sort works/i });

    // Assert — the warning-tinted chip, not just any text.
    expect(within(card).getByText("REVIEW")).toHaveAttribute("data-category", "warning");
  });

  it("uses the singular form for a one-course library", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([makeCourseSummary()])));
    renderLibrary();

    // Assert
    expect(
      await screen.findByText("1 course · 1 in progress · 0 completed · 0 not started"),
    ).toBeInTheDocument();
  });

  it("shows a live-build banner for a running run, linking to its canvas", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(TWO_COURSES)));
    render(
      <MemoryRouter>
        <CourseLibrary
          apiBaseUrl="http://test"
          onNewCourse={vi.fn()}
          runs={[makeRun({ id: "course-live", status: "running", topic: "Quantum computing" })]}
        />
      </MemoryRouter>,
    );

    // Assert — the banner names the build and is a real link into the building course.
    const banner = await screen.findByRole("link", { name: /building.*quantum computing/i });
    expect(banner).toHaveAttribute("href", "/courses/course-live");
  });

  it("shows no banner for terminal runs — only a genuinely running build earns it", async () => {
    // Arrange / Act — completed/failed/cancelled rows must not read as live.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(TWO_COURSES)));
    render(
      <MemoryRouter>
        <CourseLibrary
          apiBaseUrl="http://test"
          onNewCourse={vi.fn()}
          runs={[
            makeRun({ id: "c-a", status: "completed" }),
            makeRun({ id: "c-b", status: "failed" }),
            makeRun({ id: "c-c", status: "cancelled" }),
          ]}
        />
      </MemoryRouter>,
    );
    await screen.findByRole("link", { name: /how https works/i });

    // Assert
    expect(screen.queryByRole("link", { name: /building/i })).not.toBeInTheDocument();
  });

  it("keeps the banner over the empty state when the very first build is running", async () => {
    // Arrange / Act — a first-time user mid-build: zero courses, one running run. The designed
    // "No courses yet" CTA would be wrong here; the banner is the honest state.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([])));
    render(
      <MemoryRouter>
        <CourseLibrary
          apiBaseUrl="http://test"
          onNewCourse={vi.fn()}
          runs={[makeRun({ id: "course-live", status: "running", topic: "Quantum computing" })]}
        />
      </MemoryRouter>,
    );

    // Assert
    expect(
      await screen.findByRole("link", { name: /building.*quantum computing/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/no courses yet/i)).not.toBeInTheDocument();
  });
});
