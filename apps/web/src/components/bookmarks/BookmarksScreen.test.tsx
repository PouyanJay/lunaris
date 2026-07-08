import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Bookmark } from "../../lib/bookmarks";
import { BookmarksScreen } from "./BookmarksScreen";

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

    render(<BookmarksScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

    expect(screen.getByLabelText(/loading bookmarks/i)).toBeInTheDocument();
  });

  it("renders the designed empty state with a next step", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse([])),
    );
    const onBrowseCourses = vi.fn();

    render(<BookmarksScreen apiBaseUrl="http://test" onBrowseCourses={onBrowseCourses} />);

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

    render(<BookmarksScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

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

    render(<BookmarksScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/unexpected response/i);
  });

  it("renders saved rows — the walking-skeleton path", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse([lessonBookmark()])),
    );

    render(<BookmarksScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

    expect(
      await screen.findByText(/lesson 1 · fundamentals — how https works/i),
    ).toBeInTheDocument();
  });
});
