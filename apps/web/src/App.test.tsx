import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  agentFrame,
  courseFrame,
  makeBriefResponse,
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
    brief?: unknown;
  }) {
    return vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (/\/api\/runs\/[^/]+\/cancel$/.test(url) && method === "POST") {
        return Promise.resolve({ ok: true, status: 202 });
      }
      if (url.includes("/api/briefs")) {
        return Promise.resolve({ ok: true, json: async () => handlers.brief });
      }
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

  it("personalizes the build through the rail: read the brief, confirm, then stream to ready", async () => {
    const fetchMock = routedFetch({
      runs: [],
      brief: makeBriefResponse(),
      build: sseStreamResponse([progressFrame("run_started", 0), courseFrame(makeCourse())]),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // Name a topic, then personalize it from the always-visible setup rail (not a buried modal).
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));

    // The rail interprets the goal and offers the confirm questions (inferred level pre-picked).
    expect(await screen.findByText(/reach CLB 10/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /intermediate/i })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: /advanced/i }));

    // Build from the confirmed brief → the stream resolves to the ready course.
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    expect(
      await screen.findByRole("heading", { name: "How binary search works" }),
    ).toBeInTheDocument();

    // The confirmed clarification was threaded into the build stream URL (the core wiring contract).
    const streamCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes("/api/courses/stream"),
    );
    expect(streamCall).toBeDefined();
    const params = new URL(String(streamCall![0]), "http://test").searchParams;
    expect(JSON.parse(params.get("clarification") ?? "null")).toMatchObject({
      targetLevel: "advanced",
      goalType: "credential",
    });
  });

  it("shows the persistent course-setup rail beside the topic form in the idle state", async () => {
    vi.stubGlobal("fetch", routedFetch({ runs: [] }));
    render(<App />);

    // The rail replaces the old buried Personalize modal — it sits beside the form, always visible.
    expect(screen.getByRole("complementary", { name: /course setup/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open settings/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /what do you want to learn/i })).toBeInTheDocument();
    await screen.findByText(/no runs yet/i);
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

  it("collapses the sidebar to a mini icon rail and expands it again", async () => {
    // Asserts on DOM presence: the collapsed rail removes the history + splitter from the tree
    // (conditional render), not via CSS — jsdom doesn't apply CSS, so absence here is real absence.
    vi.stubGlobal("fetch", routedFetch({ runs: [] }));
    render(<App />);
    await screen.findByText(/no runs yet/i);

    // Expanded: the run history + resize splitter are shown; the toggle collapses.
    expect(screen.getByText("Recent runs")).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: /resize sidebar/i })).toBeInTheDocument();

    // Collapse → mini rail: history + splitter gone, the toggle now expands, actions stay as icons.
    fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
    expect(screen.queryByText("Recent runs")).not.toBeInTheDocument();
    expect(screen.queryByRole("separator", { name: /resize sidebar/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /expand sidebar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new course/i })).toBeInTheDocument();
    // Exact match scopes to the sidebar's "Settings" — the idle rail also has an "Open Settings…".
    expect(screen.getByRole("button", { name: /^settings$/i })).toBeInTheDocument();

    // Expand → the run history + splitter return.
    fireEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));
    expect(screen.getByText("Recent runs")).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: /resize sidebar/i })).toBeInTheDocument();
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

    // Reasoning + the tool-call card render in the live build timeline (a labelled, focusable region).
    expect(await screen.findByText("Mapping the prerequisites.")).toBeInTheDocument();
    expect(screen.getByText("extract_concepts")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /building graphs/i })).toBeInTheDocument();
  });

  it("buckets a full multi-phase build into branded, timed phases and threads the run_id", async () => {
    // The end-to-end Phase A path: a representative build streams every moat + the author handoff
    // through SSE → useCourseStream → BuildTimeline. Each tool's payload must reach its branded
    // renderer (no raw JSON), bucketed under the phase it completed in, with the run_id threading
    // into the sidebar. Kept open so Lessons stays the active, streaming phase.
    const concepts = [
      { id: "tcp", label: "TCP" },
      { id: "tls", label: "TLS handshake" },
      { id: "https", label: "HTTPS" },
    ];
    let buildStarted = false;
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "agent", supportsLessonRegeneration: false }),
        });
      }
      if (url.includes("/api/courses/stream")) {
        buildStarted = true;
        return Promise.resolve(
          sseStreamResponse(
            [
              progressFrame("run_started", 0),
              // The call fires in run_started but its result lands in concepts_extracted — the fold
              // pairs them and buckets the pair under the result's (completion) phase.
              agentFrame("tool_call", 1, {
                stage: "run_started",
                tool: "extract_concepts",
                toolArgs: { topic: "HTTPS" },
              }),
              agentFrame("tool_result", 2, {
                stage: "concepts_extracted",
                tool: "extract_concepts",
                result: JSON.stringify({ goalId: "https", count: 3, concepts }),
              }),
              progressFrame("concepts_extracted", 3, { kcCount: 3, label: "Extracted 3 concepts" }),
              agentFrame("tool_call", 4, {
                stage: "concepts_extracted",
                tool: "build_prerequisite_graph",
                toolArgs: { concepts, goal: "https" },
              }),
              agentFrame("tool_result", 5, {
                stage: "graph_built",
                tool: "build_prerequisite_graph",
                result: '{"nodes": [{"id": "tcp", "label": "TCP", "definition": "a long', // truncated
              }),
              progressFrame("graph_built", 6, {
                kcCount: 3,
                edgeCount: 2,
                label: "Built prerequisite graph: 3 concepts, 2 edges",
              }),
              agentFrame("tool_call", 7, {
                stage: "graph_built",
                tool: "design_curriculum",
                toolArgs: {},
              }),
              agentFrame("tool_result", 8, {
                stage: "curriculum_designed",
                tool: "design_curriculum",
                result: JSON.stringify({
                  moduleCount: 2,
                  modules: [
                    { id: "m0", title: "Foundations", kcs: ["tcp"], objectiveCount: 1 },
                    { id: "m1", title: "Securing HTTPS", kcs: ["tls", "https"], objectiveCount: 2 },
                  ],
                }),
              }),
              progressFrame("curriculum_designed", 9, {
                moduleCount: 2,
                label: "Designed curriculum: 2 modules",
              }),
              agentFrame("tool_call", 10, {
                stage: "module_authored",
                tool: "task",
                toolArgs: {
                  subagent_type: "module-author",
                  description: "Author the Foundations module",
                },
              }),
              progressFrame("module_authored", 11, {
                moduleId: "m0",
                label: "Authored module 1 of 2",
              }),
            ],
            { open: true },
          ),
        );
      }
      if (url.includes("/api/runs")) {
        const runs = buildStarted
          ? [makeRun({ id: "c-https", runId: "run-test", topic: "HTTPS", status: "running" })]
          : [];
        return Promise.resolve({ ok: true, json: async () => runs });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "HTTPS" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // The build timeline is live, and the active Lessons phase shows the delegated subagent — branded,
    // not raw JSON — proving the `task` payload flowed through the real SSE → timeline path.
    expect(await screen.findByRole("region", { name: /building HTTPS/i })).toBeInTheDocument();
    expect(await screen.findByText("module-author")).toBeInTheDocument();
    expect(await screen.findByText(/Author the Foundations module/i)).toBeInTheDocument();
    // No tool's payload leaks as raw JSON anywhere — including the deliberately truncated graph result.
    expect(screen.queryByText(/"nodes":/)).not.toBeInTheDocument();

    // The run_id on the first event threads into the sidebar, which lists the RUNNING run.
    const history = screen.getByRole("navigation", { name: /run history/i });
    expect(await within(history).findByText("HTTPS")).toBeInTheDocument();
    expect(await within(history).findByText("RUNNING")).toBeInTheDocument();

    // Phases are expanded by default, so the DONE Curriculum phase already shows its module list —
    // design_curriculum's parsed result, bucketed under the phase it completed in and rendered
    // branded (not raw JSON), straight off the live stream with no click needed.
    expect(await screen.findByText("Foundations")).toBeInTheDocument();
    expect(screen.getByText("Securing HTTPS")).toBeInTheDocument();

    // extract_concepts' parsed result reaches its branded chips too, scoped to the Concepts phase it
    // completed in (the same concept also chips under Graph from the call args — scoping avoids the
    // clash and pins the bucketing: the call fired in run_started, the pair landed in Concepts).
    const conceptsPhase = screen
      .getByRole("button", { name: /concepts — extracted 3 concepts/i })
      .closest("li");
    expect(within(conceptsPhase as HTMLElement).getByText("TLS handshake")).toBeInTheDocument();
  });

  it("surfaces a newly started build in the sidebar history without a manual refresh", async () => {
    // The run is recorded RUNNING server-side before the first event is emitted, so the run_id on
    // that first event is the cue to refetch the history. /api/runs is empty until the build starts,
    // then lists the running run — the sidebar must pick it up on its own (the reported bug was that
    // it only showed after a browser refresh).
    // The history is empty until the build has started (the stream was requested), then it lists
    // the running run — keyed on the causal event, not an ordinal call count.
    let buildStarted = false;
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (url.includes("/api/courses/stream")) {
        buildStarted = true;
        return Promise.resolve(
          sseStreamResponse(
            [
              progressFrame("run_started", 0),
              agentFrame("reasoning", 1, { text: "Mapping the prerequisites." }),
            ],
            { open: true }, // stay streaming so the run is still RUNNING when we assert
          ),
        );
      }
      if (url.includes("/api/runs")) {
        const runs = buildStarted
          ? [makeRun({ id: "c-9", runId: "run-test", topic: "graphs", status: "running" })]
          : [];
        return Promise.resolve({ ok: true, json: async () => runs });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // Empty history first, then start a build.
    await screen.findByText(/no runs yet/i);
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // The first streamed event lands the run_id → the sidebar refetches and shows the RUNNING run.
    // Scope to the run-history rail so we match the sidebar row, not the canvas's building header.
    const history = screen.getByRole("navigation", { name: /run history/i });
    expect(await within(history).findByText("graphs")).toBeInTheDocument();
    expect(within(history).getByText("RUNNING")).toBeInTheDocument();
  });

  it("terminates an in-flight build after confirming and returns to the topic form", async () => {
    // Arrange — a build streaming (kept open) so Terminate has something to stop.
    const fetchMock = routedFetch({
      runs: [],
      build: sseStreamResponse(
        [
          progressFrame("run_started", 0),
          agentFrame("reasoning", 1, { text: "Mapping the prerequisites." }),
        ],
        { open: true },
      ),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    await screen.findByText("Mapping the prerequisites.");

    // Act — Terminate goes through a confirmation dialog (not an immediate local abort).
    fireEvent.click(screen.getByRole("button", { name: /terminate/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^terminate$/i }));

    // Assert — back on the topic form, transcript gone, and the build was cancelled server-side by
    // run_id (so it lands CANCELLED, not the disconnect→FAILED path).
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Mapping the prerequisites.")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs/run-test/cancel"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("dismisses the terminate confirmation and keeps building", async () => {
    // Arrange — a build streaming.
    const fetchMock = routedFetch({
      runs: [],
      build: sseStreamResponse(
        [
          progressFrame("run_started", 0),
          agentFrame("reasoning", 1, { text: "Mapping the prerequisites." }),
        ],
        { open: true },
      ),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    await screen.findByText("Mapping the prerequisites.");

    // Act — open the terminate dialog, then dismiss it.
    fireEvent.click(screen.getByRole("button", { name: /terminate/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^cancel$/i }));

    // Assert — the build keeps streaming (transcript up), and no cancel was ever POSTed.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Mapping the prerequisites.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/cancel"),
      expect.anything(),
    );
  });

  it("opens a course in the canvas when a run is selected from the sidebar", async () => {
    const fetchMock = routedFetch({
      runs: [makeRun({ id: "c-1", topic: "queues" })],
      course: makeCourse({ id: "c-1", topic: "queues" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // Click the run in the sidebar history.
    fireEvent.click(await screen.findByRole("button", { name: /^queues/i }));

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

    fireEvent.click(await screen.findByRole("button", { name: /^queues/i }));
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

    fireEvent.click(await screen.findByRole("button", { name: /^queues/i }));
    await screen.findByRole("heading", { name: "queues" });

    // waitFor drains the capability-fetch microtask, so the absence reflects
    // supportsLessonRegeneration === false — not merely an unresolved fetch (canRegenerate
    // defaults to false). The paired "offers" test proves the button CAN appear.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /regenerate lesson/i })).not.toBeInTheDocument(),
    );
  });

  it("shows a building state — not a 404 error — when a still-running run is opened", async () => {
    // The course isn't persisted until the run finishes, so opening a RUNNING run must not fetch
    // and render the broken-looking "no longer available" error. No `course` handler is wired, so
    // routedFetch would throw on any course fetch — proving the running run never triggers one.
    vi.stubGlobal(
      "fetch",
      routedFetch({ runs: [makeRun({ id: "c-1", topic: "queues", status: "running" })] }),
    );
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /^queues/i }));

    expect(await screen.findByText(/still building this course/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /check again/i })).toBeInTheDocument();
    // The canvas Cancel action (exact name) — distinct from the sidebar's "Cancel build: <topic>".
    expect(screen.getByRole("button", { name: /^cancel build$/i })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("cancels a running run from the sidebar and the history flips to CANCELLED", async () => {
    let runsReads = 0;
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (/\/api\/runs\/[^/]+\/cancel$/.test(url) && method === "POST") {
        return Promise.resolve({ ok: true, status: 202 });
      }
      if (url.includes("/api/runs")) {
        runsReads += 1;
        const status = runsReads === 1 ? "running" : "cancelled";
        return Promise.resolve({
          ok: true,
          json: async () => [makeRun({ id: "c-1", runId: "run-1", topic: "graphs", status })],
        });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /cancel build: graphs/i }));

    // The cancel is POSTed by run_id and the refreshed history shows the terminal CANCELLED status.
    expect(await screen.findByText("CANCELLED")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs/run-1/cancel"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("cancels from the building canvas when a running run is open", async () => {
    let runsReads = 0;
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (/\/api\/runs\/[^/]+\/cancel$/.test(url) && method === "POST") {
        return Promise.resolve({ ok: true, status: 202 });
      }
      if (url.includes("/api/runs")) {
        runsReads += 1;
        const status = runsReads === 1 ? "running" : "cancelled";
        return Promise.resolve({
          ok: true,
          json: async () => [makeRun({ id: "c-1", runId: "run-1", topic: "graphs", status })],
        });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // Open the running run → building canvas, then cancel from the canvas (exact-name button).
    fireEvent.click(await screen.findByRole("button", { name: /^graphs/i }));
    await screen.findByText(/still building this course/i);
    fireEvent.click(screen.getByRole("button", { name: /^cancel build$/i }));

    // The cancel was POSTed by run_id and the refreshed history reflects CANCELLED.
    expect(await screen.findByText("CANCELLED")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs/run-1/cancel"),
      expect.objectContaining({ method: "POST" }),
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
    fireEvent.click(screen.getByRole("button", { name: /^queues/i }));

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

  it("deletes a run after confirmation, then refreshes the history", async () => {
    // The run is present on the first /api/runs read and gone after the DELETE; the second read
    // (triggered by the delete) returns an empty list, so the sidebar lands on its empty state.
    let runsReads = 0;
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (url.includes("/api/runs")) {
        runsReads += 1;
        const runs =
          runsReads === 1 ? [makeRun({ id: "c-1", topic: "queues", status: "completed" })] : [];
        return Promise.resolve({ ok: true, json: async () => runs });
      }
      if (/\/api\/courses\/c-1$/.test(url) && method === "DELETE") {
        return Promise.resolve({ ok: true, status: 204 });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // Reveal + click the run's delete action, then confirm in the dialog.
    fireEvent.click(await screen.findByRole("button", { name: /delete course: queues/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete course$/i }));

    // The history refetched empty → the sidebar shows its empty state, the run is gone, the dialog
    // closed, and a DELETE was issued.
    expect(await screen.findByText(/no runs yet/i)).toBeInTheDocument();
    expect(screen.queryByText("queues")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/courses/c-1"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("cancelling the delete keeps the run", async () => {
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (url.includes("/api/runs")) {
        return Promise.resolve({
          ok: true,
          json: async () => [makeRun({ id: "c-1", topic: "queues", status: "completed" })],
        });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /delete course: queues/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^cancel$/i }));

    // Dialog dismissed, run still listed — and no DELETE was issued (the mock would have thrown).
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("queues")).toBeInTheDocument();
  });

  it("keeps the dialog open with the reason when the API rejects the delete (409)", async () => {
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (url.includes("/api/runs")) {
        return Promise.resolve({
          ok: true,
          json: async () => [makeRun({ id: "c-1", topic: "queues", status: "completed" })],
        });
      }
      if (/\/api\/courses\/c-1$/.test(url) && method === "DELETE") {
        return Promise.resolve({ ok: false, status: 409 });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /delete course: queues/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete course$/i }));

    // The dialog stays open carrying the 409 reason; the run is not removed.
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/still building/i);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("queues")).toBeInTheDocument();
  });

  it("closes the open course's canvas when that run is deleted", async () => {
    let runsReads = 0;
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (url.includes("/api/runs")) {
        runsReads += 1;
        const runs =
          runsReads === 1 ? [makeRun({ id: "c-1", topic: "queues", status: "completed" })] : [];
        return Promise.resolve({ ok: true, json: async () => runs });
      }
      if (/\/api\/courses\/c-1$/.test(url) && method === "DELETE") {
        return Promise.resolve({ ok: true, status: 204 });
      }
      if (/\/api\/courses\/c-1$/.test(url)) {
        return Promise.resolve({
          ok: true,
          json: async () => makeCourse({ id: "c-1", topic: "queues" }),
        });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // Open the run in the canvas, then delete it.
    fireEvent.click(await screen.findByRole("button", { name: /^queues/i }));
    await screen.findByRole("heading", { name: "queues" });
    fireEvent.click(screen.getByRole("button", { name: /delete course: queues/i }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: /^delete course$/i }),
    );

    // The canvas drops the deleted course and returns to the build surface.
    expect(
      await screen.findByRole("heading", { name: /what do you want to learn/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "queues" })).not.toBeInTheDocument();
  });
});
