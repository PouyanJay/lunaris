import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { BookmarkDraft } from "../../lib/bookmarks";
import { BookmarksProvider } from "./BookmarksContext";
import { BookmarkToggle } from "./BookmarkToggle";

const DRAFT: BookmarkDraft = {
  kind: "lesson",
  courseId: "course-1",
  targetId: "m-1-l0",
  courseTitle: "How HTTPS works",
  title: "Lesson 1 · Fundamentals",
  lessonId: "m-1-l0",
};

function bookmarksFetch(initial: unknown[] = []) {
  const writes: { method: string; url: string; body?: unknown }[] = [];
  const mock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (!url.includes("/api/bookmarks")) throw new Error(`unhandled ${url}`);
    if (method === "GET") return Promise.resolve({ ok: true, json: async () => initial });
    writes.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return Promise.resolve({ ok: true, status: 204 });
  });
  return { mock, writes };
}

afterEach(() => vi.unstubAllGlobals());

describe("BookmarkToggle", () => {
  it("saves on first press and removes on the second, optimistically", async () => {
    // Arrange
    const { mock, writes } = bookmarksFetch();
    vi.stubGlobal("fetch", mock);
    render(
      <BookmarksProvider apiBaseUrl="http://test">
        <BookmarkToggle draft={DRAFT} subject="Lesson 1 · Fundamentals" />
      </BookmarksProvider>,
    );
    const toggle = await screen.findByRole("button", { name: /bookmark lesson 1/i });
    await waitFor(() => expect(toggle).toBeEnabled());

    // Act — save.
    fireEvent.click(toggle);

    // Assert — pressed immediately (optimistic) and the PUT carries the draft.
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await waitFor(() =>
      expect(writes).toContainEqual(
        expect.objectContaining({
          method: "PUT",
          body: expect.objectContaining({ kind: "lesson", targetId: "m-1-l0" }),
        }),
      ),
    );

    // Act — remove.
    fireEvent.click(screen.getByRole("button", { name: /remove bookmark/i }));

    // Assert
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await waitFor(() => expect(writes.some((write) => write.method === "DELETE")).toBe(true));
  });

  it("reflects an already-saved bookmark from the server", async () => {
    // Arrange — the list already holds this natural key.
    const { mock } = bookmarksFetch([{ ...DRAFT, savedAt: new Date().toISOString() }]);
    vi.stubGlobal("fetch", mock);

    // Act
    render(
      <BookmarksProvider apiBaseUrl="http://test">
        <BookmarkToggle draft={DRAFT} subject="Lesson 1 · Fundamentals" />
      </BookmarksProvider>,
    );

    // Assert
    const toggle = await screen.findByRole("button", { name: /remove bookmark/i });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("renders nothing outside a provider — saving is impossible offline", () => {
    render(<BookmarkToggle draft={DRAFT} subject="Lesson 1 · Fundamentals" />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("reconciles a failed save by refetching — the optimistic press reverts", async () => {
    // Arrange — GET serves an empty list; the PUT is down.
    const mock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (!url.includes("/api/bookmarks")) throw new Error(`unhandled ${url}`);
      if (method === "GET") return Promise.resolve({ ok: true, json: async () => [] });
      return Promise.reject(new Error("network down"));
    });
    vi.stubGlobal("fetch", mock);
    render(
      <BookmarksProvider apiBaseUrl="http://test">
        <BookmarkToggle draft={DRAFT} subject="Lesson 1 · Fundamentals" />
      </BookmarksProvider>,
    );
    const toggle = await screen.findByRole("button", { name: /bookmark lesson 1/i });
    await waitFor(() => expect(toggle).toBeEnabled());

    // Act — the press is optimistic, then the failed write reconciles by refetch (A4).
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    // Assert — truth returns: the server never saved it, so the press reverts.
    await waitFor(() => expect(toggle).toHaveAttribute("aria-pressed", "false"));
  });
});
