import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CorpusSource } from "../../types/course";
import { CorpusPanel } from "./CorpusPanel";

function makeSource(overrides: Partial<CorpusSource> = {}): CorpusSource {
  return {
    sourceId: "a".repeat(32),
    courseId: "course-1",
    title: "Dijkstra notes",
    url: null,
    sourceType: null,
    trustTier: "vouched",
    credibility: null,
    acquisitionMode: "manual",
    fetchedAt: "2026-06-04T00:00:00Z",
    chunkCount: 2,
    ...overrides,
  };
}

function json(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  return { ok: init.ok ?? true, status: init.status ?? 200, json: async () => body };
}

/** A tiny in-memory corpus server so add/delete + the reload roundtrip behave end-to-end. */
function fakeServer(initial: CorpusSource[] = []) {
  let sources = [...initial];
  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.includes("/api/corpus/sources") && method === "POST") {
      const body = JSON.parse(init?.body as string) as {
        kind: string;
        title?: string;
        url?: string;
      };
      const added = makeSource({
        sourceId: "b".repeat(32),
        title: body.title || body.url || "Source",
        url: body.kind === "url" ? (body.url ?? null) : null,
      });
      sources = [...sources, added];
      return json(
        { accepted: true, sourceId: added.sourceId, chunks: 2, reason: null },
        { status: 201 },
      );
    }
    // The delete names its course (?courseId=…) so the server can verify ownership + membership.
    const deleteMatch = url.match(/\/api\/corpus\/([0-9a-f]{32})\?courseId=course-1$/);
    if (deleteMatch && method === "DELETE") {
      sources = sources.filter((s) => s.sourceId !== deleteMatch[1]);
      return { ok: true, status: 204 };
    }
    if (url.match(/\/api\/courses\/.+\/rebuild$/) && method === "POST") {
      return json({ id: "course-1", topic: "demo" });
    }
    if (url.includes("/api/corpus?")) {
      return json(sources);
    }
    return { ok: false, status: 404, json: async () => ({}) };
  });
}

function renderPanel() {
  return render(<CorpusPanel apiBaseUrl="http://test" courseId="course-1" />);
}

describe("CorpusPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a loading skeleton while the corpus is in flight", () => {
    // Arrange — a fetch that never resolves holds the loading state.
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    // Act
    renderPanel();

    // Assert
    expect(screen.getByRole("status", { name: /loading sources/i })).toBeInTheDocument();
  });

  it("shows the empty state when the course has no sources", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", fakeServer([]));
    renderPanel();

    // Assert
    await waitFor(() => expect(screen.getByText(/no sources yet/i)).toBeInTheDocument());
  });

  it("lists a source with its trust tier and chunk count", async () => {
    // Arrange / Act
    vi.stubGlobal("fetch", fakeServer([makeSource()]));
    renderPanel();

    // Assert
    await waitFor(() => expect(screen.getByText("Dijkstra notes")).toBeInTheDocument());
    expect(screen.getByText("vouched")).toBeInTheDocument();
    expect(screen.getByText("2 chunks")).toBeInTheDocument();
  });

  it("labels each source with its acquisition provenance, so mixed-mode corpora are auditable", async () => {
    // Arrange / Act — one source from each acquisition mode in the same course corpus.
    vi.stubGlobal(
      "fetch",
      fakeServer([
        makeSource({
          sourceId: "m".repeat(32),
          title: "Uploaded notes",
          acquisitionMode: "manual",
        }),
        makeSource({ sourceId: "s".repeat(32), title: "Researched page", acquisitionMode: "seed" }),
        makeSource({ sourceId: "u".repeat(32), title: "Discovered page", acquisitionMode: "auto" }),
      ]),
    );
    renderPanel();

    // Assert — each row carries its provenance word, one per acquisition mode.
    await waitFor(() => expect(screen.getByText("Researched page")).toBeInTheDocument());
    expect(screen.getByText("Manual")).toBeInTheDocument();
    expect(screen.getByText("Seeded")).toBeInTheDocument();
    expect(screen.getByText("Auto")).toBeInTheDocument();
  });

  it("surfaces a load error, then retries on Try again", async () => {
    // Arrange — the first list load fails, the retry succeeds (empty).
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) })
      .mockResolvedValueOnce(json([]));
    vi.stubGlobal("fetch", fetchMock);
    renderPanel();
    const retry = await screen.findByRole("button", { name: /try again/i });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    // Act
    fireEvent.click(retry);

    // Assert
    await waitFor(() => expect(screen.getByText(/no sources yet/i)).toBeInTheDocument());
  });

  it("adds a pasted source and shows it after the reload", async () => {
    // Arrange
    vi.stubGlobal("fetch", fakeServer([]));
    renderPanel();
    await waitFor(() => expect(screen.getByText(/no sources yet/i)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/title/i), { target: { value: "My notes" } });
    fireEvent.change(screen.getByPlaceholderText(/paste notes/i), {
      target: { value: "Dijkstra relaxes edges." },
    });

    // Act
    fireEvent.click(screen.getByRole("button", { name: /add source/i }));

    // Assert — the ingest is confirmed and the new source appears under its title.
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/2 chunks ingested/i));
    expect(screen.getByText("My notes")).toBeInTheDocument();
  });

  it("reports a declined source (e.g. a duplicate)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "POST") {
          return json(
            { accepted: false, sourceId: "x", chunks: 0, reason: "already in the corpus" },
            { status: 201 },
          );
        }
        return json([]);
      }),
    );
    renderPanel();
    await waitFor(() => expect(screen.getByText(/no sources yet/i)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/paste notes/i), { target: { value: "dup" } });

    // Act
    fireEvent.click(screen.getByRole("button", { name: /add source/i }));

    // Assert
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/already in the corpus/i),
    );
  });

  it("removes a source on Remove", async () => {
    // Arrange
    vi.stubGlobal("fetch", fakeServer([makeSource()]));
    renderPanel();
    await waitFor(() => expect(screen.getByText("Dijkstra notes")).toBeInTheDocument());

    // Act
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));

    // Assert
    await waitFor(() => expect(screen.getByText(/no sources yet/i)).toBeInTheDocument());
  });

  it("re-grounds the course and reloads it", async () => {
    // Arrange
    const onReground = vi.fn();
    const fetchMock = fakeServer([]);
    vi.stubGlobal("fetch", fetchMock);
    render(<CorpusPanel apiBaseUrl="http://test" courseId="course-1" onReground={onReground} />);
    await waitFor(() => expect(screen.getByText(/no sources yet/i)).toBeInTheDocument());

    // Act
    fireEvent.click(screen.getByRole("button", { name: /re-ground course/i }));

    // Assert — the rebuild endpoint was hit, the course is reloaded, and a confirmation is shown.
    await waitFor(() => expect(onReground).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/courses\/course-1\/rebuild$/),
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.getByText(/open Lessons to see/i)).toBeInTheDocument();
  });

  it("surfaces a delete failure and keeps the source", async () => {
    // Arrange — the list loads, but the DELETE fails.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "DELETE") return { ok: false, status: 503 };
        return json([makeSource()]);
      }),
    );
    renderPanel();
    await waitFor(() => expect(screen.getByText("Dijkstra notes")).toBeInTheDocument());

    // Act
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));

    // Assert — an error is shown and the source is still listed.
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText("Dijkstra notes")).toBeInTheDocument();
  });
});
