import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  agentFrame,
  courseFrame,
  makeCourse,
  makeRun,
  progressFrame,
  sseStreamResponse,
} from "./test/fixtures";

function stubFetchResolving(course = makeCourse()) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => course }));
}

describe("App", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders a loading skeleton before the course arrives", () => {
    stubFetchResolving();
    render(<App />);
    expect(screen.getByRole("status", { name: /loading prerequisite graph/i })).toBeInTheDocument();
  });

  it("renders the graph, course topic and metrics once loaded", async () => {
    stubFetchResolving();
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    // Metric band + status.
    expect(screen.getByText("REVIEW")).toBeInTheDocument();
    // The goal KC node renders on the canvas. Its label ("Binary Search") is distinct from the
    // course topic heading, so this fails specifically if graph nodes stop rendering. (Queried
    // by text, not role: React Flow leaves nodes visibility:hidden until measured, and jsdom's
    // stubbed ResizeObserver never measures them, so they're absent from the accessibility tree.)
    expect(screen.getByText("Binary Search")).toBeInTheDocument();
  });

  it("shows a recoverable error state when the course fails to load", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/http 500/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("recovers when the user retries after a load error", async () => {
    // First attempt fails; the retry succeeds.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500 })
      .mockResolvedValue({ ok: true, json: async () => makeCourse() });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows an empty state when the course has no concepts", async () => {
    const empty = makeCourse();
    empty.graph.nodes = [];
    empty.graph.edges = [];
    empty.graph.topoOrder = [];
    stubFetchResolving(empty);
    render(<App />);

    expect(await screen.findByText("No concepts yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload course/i })).toBeInTheDocument();
  });
});

describe("App — live studio (VITE_API_URL set)", () => {
  beforeEach(() => vi.stubEnv("VITE_API_URL", "http://test"));
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  /** StudioApp fetches GET /api/runs (sidebar) + GET /api/settings (regenerate capability) on mount
   *  AND streams the build, so the fetch mock routes by URL: run history + settings are JSON, the
   *  build is an SSE stream. ``settings`` defaults to a regenerate-capable pipeline. */
  function routedFetch(handlers: {
    runs?: unknown;
    build?: unknown;
    course?: unknown;
    settings?: unknown;
  }) {
    return vi.fn((input: Parameters<typeof fetch>[0]) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/runs")) {
        return Promise.resolve({ ok: true, json: async () => handlers.runs ?? [] });
      }
      if (url.includes("/api/settings")) {
        const settings = handlers.settings ?? {
          secrets: [],
          pipeline: "stub",
          supportsLessonRegeneration: true,
        };
        return Promise.resolve({ ok: true, json: async () => settings });
      }
      if (url.includes("/api/courses/stream")) {
        return Promise.resolve(handlers.build);
      }
      if (/\/api\/courses\/[^/?]+$/.test(url)) {
        // course-by-id: exactly one path segment after /courses/, no query (≠ the stream URL)
        return Promise.resolve({ ok: true, json: async () => handlers.course });
      }
      throw new Error(`routedFetch: unhandled URL ${url}`);
    });
  }

  it("opens on the topic form, not an auto-generated course", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [] }));
    render(<App />);

    expect(screen.getByRole("heading", { name: /what do you want to learn/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate course/i })).toBeInTheDocument();
    // Let the sidebar's run-history fetch settle (empty) so its state update is awaited.
    expect(await screen.findByText(/no runs yet/i)).toBeInTheDocument();
  });

  it("shows the run-history sidebar with prior runs", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ runs: [makeRun({ topic: "queues", status: "completed" })] }),
    );
    render(<App />);

    // The persistent sidebar: brand, the primary action, and the recorded run.
    expect(screen.getByRole("button", { name: /new course/i })).toBeInTheDocument();
    expect(screen.getByText("Recent runs")).toBeInTheDocument();
    expect(await screen.findByText("queues")).toBeInTheDocument();
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
  });

  it("streams the agent transcript, lands on the ready reader, and Map shows the graph", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse([
          progressFrame("run_started", 0),
          agentFrame("tool_call", 1, { tool: "extract_concepts", toolArgs: { topic: "graphs" } }),
          agentFrame("tool_result", 2, { tool: "extract_concepts", result: "16 concepts" }),
          progressFrame("graph_built", 3, { kcCount: 3, edgeCount: 2 }),
          courseFrame(makeCourse()),
        ]),
      }),
    );
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // The stream resolves and hands off to the ready course (reader by default).
    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();
    // Map surfaces the generated prerequisite graph.
    fireEvent.click(screen.getByRole("radio", { name: /map/i }));
    expect(
      await screen.findByRole("application", { name: /prerequisite graph/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Binary Search")).toBeInTheDocument();
  });

  it("shows the live agent transcript while the build streams", async () => {
    // A build that emits a tool call then stalls (no terminal course) so the transcript stays up.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse(
          [
            progressFrame("run_started", 0),
            agentFrame("reasoning", 1, { text: "Mapping the prerequisites." }),
            agentFrame("tool_call", 2, { tool: "extract_concepts", toolArgs: { topic: "graphs" } }),
          ],
          { open: true }, // stay streaming so the transcript is visible to assert
        ),
      }),
    );
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // Reasoning + the tool-call card render in the canvas transcript (a labelled, focusable region).
    expect(await screen.findByText("Mapping the prerequisites.")).toBeInTheDocument();
    expect(screen.getByText("extract_concepts")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /agent transcript/i })).toBeInTheDocument();
  });

  it("cancels an in-flight build and returns to the topic form", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse(
          [
            progressFrame("run_started", 0),
            agentFrame("reasoning", 1, { text: "Mapping the prerequisites." }),
          ],
          { open: true }, // stay streaming so Cancel has something to abort
        ),
      }),
    );
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    await screen.findByText("Mapping the prerequisites.");

    // Act — cancel mid-build.
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));

    // Assert — back on the topic form, transcript gone.
    expect(screen.getByRole("heading", { name: /what do you want to learn/i })).toBeInTheDocument();
    expect(screen.queryByText("Mapping the prerequisites.")).not.toBeInTheDocument();
  });

  it("opens a course in the canvas when a run is selected from the sidebar", async () => {
    const fetchMock = routedFetch({
      runs: [makeRun({ id: "c-1", topic: "queues" })],
      course: makeCourse({ id: "c-1", topic: "queues" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // Click the run in the sidebar history.
    fireEvent.click(await screen.findByRole("button", { name: /queues/i }));

    // The canvas opens that run's course on the reader; its title heading shows.
    expect(await screen.findByRole("heading", { name: "queues" })).toBeInTheDocument();
    // Map surfaces a graph node from the opened course.
    fireEvent.click(screen.getByRole("radio", { name: /map/i }));
    expect(await screen.findByText("Binary Search")).toBeInTheDocument();
    // Opened by the run's course_id, not a re-build.
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/courses/c-1"),
      expect.anything(),
    );
  });

  it("offers the regenerate action when the pipeline supports it", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun({ id: "c-1", topic: "queues" })],
        course: makeCourse({ id: "c-1", topic: "queues" }),
        settings: { secrets: [], pipeline: "stub", supportsLessonRegeneration: true },
      }),
    );
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /queues/i }));
    await screen.findByRole("heading", { name: "queues" });

    // The capability fetch resolves to true, so the reader offers the per-lesson regenerate action.
    expect(await screen.findByRole("button", { name: /regenerate lesson/i })).toBeInTheDocument();
  });

  it("hides the regenerate action when the pipeline can't regenerate", async () => {
    // The agent pipeline 501s on regenerate; the reader must not surface a button that always fails.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun({ id: "c-1", topic: "queues" })],
        course: makeCourse({ id: "c-1", topic: "queues" }),
        settings: { secrets: [], pipeline: "agent", supportsLessonRegeneration: false },
      }),
    );
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /queues/i }));
    await screen.findByRole("heading", { name: "queues" });

    // waitFor drains the capability-fetch microtask, so the absence reflects
    // supportsLessonRegeneration === false — not merely an unresolved fetch (canRegenerate
    // defaults to false). The paired "offers" test proves the button CAN appear.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /regenerate lesson/i })).not.toBeInTheDocument(),
    );
  });

  it("switches the canvas to a selected run even while a build is streaming", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun({ id: "c-1", topic: "queues" })],
        build: sseStreamResponse(
          [progressFrame("run_started", 0), agentFrame("reasoning", 1, { text: "Mapping KCs…" })],
          { open: true },
        ),
        course: makeCourse({ id: "c-1", topic: "queues" }),
      }),
    );
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    await screen.findByText("Mapping KCs…"); // transcript is up

    // Open a historical run mid-build — the opened run takes the canvas (priority over the build).
    fireEvent.click(screen.getByRole("button", { name: /queues/i }));

    expect(await screen.findByRole("heading", { name: "queues" })).toBeInTheDocument();
    expect(screen.queryByText("Mapping KCs…")).not.toBeInTheDocument();
  });

  it("shows a recoverable error when the build fails mid-stream", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({ runs: [], build: { ok: false, status: 500, body: null } }),
    );
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/http 500/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("defaults the ready canvas to the lesson reader (Learn), not the graph", async () => {
    // Arrange — a build that resolves straight to a ready course.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse([progressFrame("run_started", 0), courseFrame(makeCourse())]),
      }),
    );
    render(<App />);

    // Act — generate the course.
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // Assert — the reader is the default ready view: lesson prose renders, the graph is absent…
    expect(await screen.findByText(/find a word in a dictionary/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("application", { name: /prerequisite graph/i }),
    ).not.toBeInTheDocument();
    // …and the Learn | Map toggle shows Learn selected.
    expect(screen.getByRole("radio", { name: /learn/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /map/i })).not.toBeChecked();
  });

  it("toggles the ready canvas between the reader (Learn) and the graph (Map)", async () => {
    // Arrange — a ready course on the canvas.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [],
        build: sseStreamResponse([progressFrame("run_started", 0), courseFrame(makeCourse())]),
      }),
    );
    render(<App />);
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    await screen.findByText(/find a word in a dictionary/i);

    // Act — switch to Map. Assert — the graph canvas shows, the prose is gone.
    fireEvent.click(screen.getByRole("radio", { name: /map/i }));
    expect(
      await screen.findByRole("application", { name: /prerequisite graph/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/find a word in a dictionary/i)).not.toBeInTheDocument();

    // Act — switch back to Learn. Assert — the reader returns.
    fireEvent.click(screen.getByRole("radio", { name: /learn/i }));
    expect(await screen.findByText(/find a word in a dictionary/i)).toBeInTheDocument();
  });
});
