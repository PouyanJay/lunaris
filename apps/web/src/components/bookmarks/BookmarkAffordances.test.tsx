import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnnotationRail } from "../reader/AnnotationRail";
import { CourseReader } from "../reader/CourseReader";
import { KcDetailPanel } from "../graph/KcDetailPanel";
import { makeCourse } from "../../test/fixtures";
import type { Annotation } from "../reader/annotations";
import { BookmarksProvider } from "./BookmarksContext";

/** The three save sites, wired for real: each toggle must send its kind's draft. */

function bookmarksFetch() {
  const writes: { method: string; body?: unknown }[] = [];
  const mock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes("/api/bookmarks")) {
      if (method === "GET") return Promise.resolve({ ok: true, json: async () => [] });
      writes.push({ method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return Promise.resolve({ ok: true, status: 204 });
    }
    // The reader's ambient calls (progress GET/PUTs, heartbeat) succeed silently.
    if (method === "GET") {
      return Promise.resolve({ ok: true, json: async () => ({ courseId: "", objectives: [], lessons: [] }) });
    }
    return Promise.resolve({ ok: true, status: 204 });
  });
  return { mock, writes };
}

afterEach(() => vi.unstubAllGlobals());

describe("bookmark affordances", () => {
  it("the reader's lesson header saves a lesson draft", async () => {
    // Arrange
    const { mock, writes } = bookmarksFetch();
    vi.stubGlobal("fetch", mock);
    render(
      <BookmarksProvider apiBaseUrl="http://test">
        <CourseReader course={makeCourse()} apiBaseUrl="http://test" />
      </BookmarksProvider>,
    );
    const toggle = await screen.findByRole("button", { name: /^bookmark lesson 1/i });
    await waitFor(() => expect(toggle).toBeEnabled());

    // Act
    fireEvent.click(toggle);

    // Assert — kind + the natural key + the reader's own labeling.
    await waitFor(() =>
      expect(writes).toContainEqual(
        expect.objectContaining({
          method: "PUT",
          body: expect.objectContaining({
            kind: "lesson",
            courseId: "course-test",
            title: expect.stringMatching(/^Lesson 1 · /),
          }),
        }),
      ),
    );
  });

  it("the KC inspector saves a concept draft with its tier", async () => {
    // Arrange
    const { mock, writes } = bookmarksFetch();
    vi.stubGlobal("fetch", mock);
    const course = makeCourse();
    const kc = course.graph.nodes[0]!;
    render(
      <BookmarksProvider apiBaseUrl="http://test">
        <KcDetailPanel course={course} selectedId={kc.id} onClose={() => {}} />
      </BookmarksProvider>,
    );
    const toggle = await screen.findByRole("button", {
      name: new RegExp(`bookmark ${kc.label}`, "i"),
    });
    await waitFor(() => expect(toggle).toBeEnabled());

    // Act
    fireEvent.click(toggle);

    // Assert
    await waitFor(() =>
      expect(writes).toContainEqual(
        expect.objectContaining({
          method: "PUT",
          body: expect.objectContaining({
            kind: "concept",
            targetId: kc.id,
            title: kc.label,
            conceptTier: expect.any(Number),
          }),
        }),
      ),
    );
  });

  it("a cited claim card saves a source draft keyed on the citation", async () => {
    // Arrange
    const { mock, writes } = bookmarksFetch();
    vi.stubGlobal("fetch", mock);
    const annotation: Annotation = {
      id: "demonstrate-0",
      phaseKey: "demonstrate",
      phaseLabel: "Strategies & worked example",
      claim: { text: "HTTPS encrypts data in transit.", supportedBy: "cite-42", verifierStatus: "supported" },
      citation: {
        id: "cite-42",
        title: "RFC 8446 — TLS 1.3",
        url: "https://example.org/rfc8446",
        snippet: "TLS 1.3 …",
        trustTier: "official",
        credibility: 0.94,
      },
      matchedSentence: null,
    };
    render(
      <BookmarksProvider apiBaseUrl="http://test">
        <AnnotationRail
          annotations={[annotation]}
          activeClaimId={null}
          onSelect={() => {}}
          sourceContext={{ courseId: "course-1", courseTitle: "How HTTPS works", lessonId: "m-1-l0" }}
        />
      </BookmarksProvider>,
    );
    const toggle = await screen.findByRole("button", { name: /bookmark rfc 8446/i });
    await waitFor(() => expect(toggle).toBeEnabled());

    // Act
    fireEvent.click(toggle);

    // Assert — keyed on the citation, quoting the claim, carrying the trust grade.
    await waitFor(() =>
      expect(writes).toContainEqual(
        expect.objectContaining({
          method: "PUT",
          body: expect.objectContaining({
            kind: "source",
            targetId: "cite-42",
            snippet: "HTTPS encrypts data in transit.",
            trustTier: "official",
            credibility: 0.94,
            lessonId: "m-1-l0",
          }),
        }),
      ),
    );
  });

  it("offers no source save without a source context (offline posture)", () => {
    vi.stubGlobal("fetch", bookmarksFetch().mock);
    const annotation: Annotation = {
      id: "demonstrate-0",
      phaseKey: "demonstrate",
      phaseLabel: "Strategies & worked example",
      claim: { text: "Claim.", supportedBy: "cite-1", verifierStatus: "supported" },
      citation: { id: "cite-1", title: "Source", url: null, snippet: null },
      matchedSentence: null,
    };
    render(
      <BookmarksProvider apiBaseUrl="http://test">
        <AnnotationRail annotations={[annotation]} activeClaimId={null} onSelect={() => {}} />
      </BookmarksProvider>,
    );

    expect(screen.queryByRole("button", { name: /bookmark source/i })).not.toBeInTheDocument();
  });
});
