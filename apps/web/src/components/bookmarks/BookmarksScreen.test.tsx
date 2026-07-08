import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Bookmark } from "../../lib/bookmarks";
import { BookmarksProvider } from "./BookmarksContext";
import { BookmarksScreen } from "./BookmarksScreen";

function renderScreen(overrides: Partial<Parameters<typeof BookmarksScreen>[0]> = {}) {
  return render(
    <BookmarksProvider apiBaseUrl="http://test">
      <BookmarksScreen
        onBrowseCourses={() => {}}
        onOpenLesson={() => {}}
        onOpenConcept={() => {}}
        onOpenCourse={() => {}}
        {...overrides}
      />
    </BookmarksProvider>,
  );
}

function okResponse(bookmarks: Bookmark[]) {
  return Promise.resolve({ ok: true, json: async () => bookmarks });
}

function lessonBookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    kind: "lesson",
    courseId: "course-1",
    targetId: "m-1-l0",
    courseTitle: "How HTTPS works",
    title: "Lesson 1 · Fundamentals",
    lessonId: "m-1-l0",
    savedAt: new Date().toISOString(),
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BookmarksScreen", () => {
  it("shows a loading skeleton while the list is in flight", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );

    renderScreen();

    expect(screen.getByLabelText(/loading bookmarks/i)).toBeInTheDocument();
  });

  it("renders the designed empty state with a next step", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse([])),
    );
    const onBrowseCourses = vi.fn();

    renderScreen({ onBrowseCourses });

    expect(await screen.findByText(/no bookmarks yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /browse my courses/i }));
    expect(onBrowseCourses).toHaveBeenCalled();
  });

  it("surfaces a fetch failure as a recoverable error state and retries", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error("network down"))
      .mockImplementation(() => okResponse([]) as Promise<Response>);
    vi.stubGlobal("fetch", fetchMock);

    renderScreen();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText(/no bookmarks yet/i)).toBeInTheDocument();
  });

  it("treats a malformed payload as a recoverable error, never a crash", async () => {
    // The trust boundary: an ok response whose body isn't a bookmark list.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ nonsense: true }) })),
    );

    renderScreen();

    expect(await screen.findByRole("alert")).toHaveTextContent(/unexpected response/i);
  });

  it("renders the three designed sections and deep-links each kind to its origin", async () => {
    // Arrange — one save of each kind.
    const saves: Bookmark[] = [
      lessonBookmark(),
      {
        kind: "concept",
        courseId: "course-1",
        targetId: "kc-a",
        courseTitle: "How HTTPS works",
        title: "Asymmetric encryption",
        conceptTier: 2,
        savedAt: new Date().toISOString(),
      },
      {
        kind: "source",
        courseId: "course-1",
        targetId: "cite-42",
        courseTitle: "How HTTPS works",
        title: "RFC 8446 — TLS 1.3",
        lessonId: "m-1-l0",
        snippet: "HTTPS encrypts data in transit.",
        trustTier: "official",
        credibility: 0.94,
        savedAt: new Date().toISOString(),
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse(saves)),
    );
    const onOpenLesson = vi.fn();
    const onOpenConcept = vi.fn();
    renderScreen({ onOpenLesson, onOpenConcept });

    // Assert — the three section labels with their designed items.
    const lessons = await screen.findByRole("region", { name: "Lessons" });
    const concepts = screen.getByRole("region", { name: "Concepts" });
    const sources = screen.getByRole("region", { name: "Sources" });
    expect(within(lessons).getByText("Lesson 1 · Fundamentals")).toBeInTheDocument();
    expect(within(concepts).getByText("Asymmetric encryption")).toBeInTheDocument();
    expect(within(sources).getByText("HTTPS encrypts data in transit.")).toBeInTheDocument();
    // Source trust grade rides along.
    expect(within(sources).getByText(/official/i)).toBeInTheDocument();

    // Act / Assert — each row deep-links to where it was saved.
    fireEvent.click(within(lessons).getByRole("button", { name: /open lesson 1/i }));
    expect(onOpenLesson).toHaveBeenCalledWith("course-1", "m-1-l0");
    fireEvent.click(
      within(concepts).getByRole("button", { name: /open asymmetric encryption on the map/i }),
    );
    expect(onOpenConcept).toHaveBeenCalledWith("course-1", "kc-a");
    fireEvent.click(within(sources).getByRole("button", { name: /open the lesson citing/i }));
    expect(onOpenLesson).toHaveBeenCalledWith("course-1", "m-1-l0");
  });

  it("filters sections with the pills", async () => {
    // Arrange
    const saves: Bookmark[] = [
      lessonBookmark(),
      {
        kind: "concept",
        courseId: "course-1",
        targetId: "kc-a",
        courseTitle: "How HTTPS works",
        title: "Asymmetric encryption",
        conceptTier: 2,
        savedAt: new Date().toISOString(),
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse(saves)),
    );
    renderScreen();
    await screen.findByRole("region", { name: "Lessons" });

    // Act — narrow to concepts.
    fireEvent.click(screen.getByRole("button", { name: "Concepts", pressed: false }));

    // Assert — only the concepts section remains; the pill reads pressed.
    expect(screen.queryByRole("region", { name: "Lessons" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Concepts" })).toBeInTheDocument();
  });

  it("a filtered-empty kind says so instead of a blank canvas", async () => {
    // Arrange — saves exist, but none of the filtered kind.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse([lessonBookmark()])),
    );
    renderScreen();
    await screen.findByRole("region", { name: "Lessons" });

    // Act
    fireEvent.click(screen.getByRole("button", { name: "Sources", pressed: false }));

    // Assert
    expect(screen.getByText(/no saved sources yet/i)).toBeInTheDocument();
  });

  it("a source without a recorded lesson falls back to the course overview", async () => {
    // Arrange
    const source: Bookmark = {
      kind: "source",
      courseId: "course-1",
      targetId: "cite-9",
      courseTitle: "How HTTPS works",
      title: "Some source",
      lessonId: null,
      snippet: "A claim.",
      savedAt: new Date().toISOString(),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse([source])),
    );
    const onOpenCourse = vi.fn();
    renderScreen({ onOpenCourse });

    // Act
    fireEvent.click(
      await screen.findByRole("button", { name: /open how https works/i }),
    );

    // Assert — honest fallback: no lesson recorded → the course, never a guess.
    expect(onOpenCourse).toHaveBeenCalledWith("course-1");
  });

  it("each row keeps its remove affordance — the leading glyph is the toggle", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: Parameters<typeof fetch>[0], init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        if (method === "GET") return okResponse([lessonBookmark()]);
        return Promise.resolve({ ok: true, status: 204 });
      }),
    );
    renderScreen();
    const lessons = await screen.findByRole("region", { name: "Lessons" });

    // Act — the accent glyph un-saves right here.
    fireEvent.click(within(lessons).getByRole("button", { name: /remove bookmark/i }));

    // Assert — optimistic removal empties the list into the designed empty state.
    expect(await screen.findByText(/no bookmarks yet/i)).toBeInTheDocument();
  });
});
