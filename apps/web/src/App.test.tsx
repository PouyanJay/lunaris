import { fireEvent, render, screen } from "@testing-library/react";
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

  /** StudioApp now fetches GET /api/runs on mount (the sidebar) AND streams the build, so the
   *  fetch mock routes by URL: the run history is JSON, the build is an SSE stream. */
  function routedFetch(handlers: { runs?: unknown; build?: unknown; course?: unknown }) {
    return vi.fn((input: Parameters<typeof fetch>[0]) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/runs")) {
        return Promise.resolve({ ok: true, json: async () => handlers.runs ?? [] });
      }
      if (url.includes("/api/courses/stream")) {
        return Promise.resolve(handlers.build);
      }
      if (url.includes("/api/courses/")) {
        return Promise.resolve({ ok: true, json: async () => handlers.course });
      }
      return Promise.resolve(handlers.build);
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

  it("streams the agent transcript for a typed topic, then renders the generated graph", async () => {
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

    // The stream resolves and hands off to the explorer for the generated course.
    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
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

    // Reasoning + the tool-call card render in the canvas transcript.
    expect(await screen.findByText("Mapping the prerequisites.")).toBeInTheDocument();
    expect(screen.getByText("extract_concepts")).toBeInTheDocument();
  });

  it("opens a course in the canvas when a run is selected from the sidebar", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun({ id: "c-1", topic: "queues" })],
        course: makeCourse({ id: "c-1", topic: "queues" }),
      }),
    );
    render(<App />);

    // Click the run in the sidebar history.
    fireEvent.click(await screen.findByRole("button", { name: /queues/i }));

    // The canvas opens that run's course: its title heading + a graph node from the course.
    expect(await screen.findByRole("heading", { name: "queues" })).toBeInTheDocument();
    expect(screen.getByText("Binary Search")).toBeInTheDocument();
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
});
