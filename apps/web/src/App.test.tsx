import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  agentFrame,
  courseFrame,
  makeAgentEvent,
  makeBriefResponse,
  makeCourse,
  makeProgressEvent,
  makeRun,
  makeRunEvent,
  progressFrame,
  routedFetch,
  sseStreamResponse,
  waitForRunsFetch,
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
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
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
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
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
  beforeEach(() => {
    vi.stubEnv("VITE_API_URL", "http://test");
    // The composer lives at /new; Home is the dashboard at /. These tests drive the composer and
    // build flow, so they start on the composer route (a build streams there until URL handoff).
    window.history.pushState(null, "", "/new");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("opens on the topic form, not an auto-generated course", async () => {
    const fetchMock = routedFetch({ runs: [] });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(screen.getByRole("heading", { name: /what do you want to learn/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generate course/i })).toBeInTheDocument();
    await waitForRunsFetch(fetchMock);
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

    // The rail interprets the goal and offers the confirm questions.
    expect(await screen.findByText(/reach CLB 10/i)).toBeInTheDocument();
    // Set the target level via the composer's options bar (maps onto the clarification).
    const level = screen.getByRole("radiogroup", { name: "Level" });
    fireEvent.click(within(level).getByRole("radio", { name: "Advanced" }));

    // Build from the confirmed brief → the stream resolves to the ready course.
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    expect(
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
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
    const fetchMock = routedFetch({ runs: [] });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    // The rail replaces the old buried Personalize modal — it sits beside the form, always visible.
    expect(screen.getByRole("complementary", { name: /course setup/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open settings/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /what do you want to learn/i })).toBeInTheDocument();
    await waitForRunsFetch(fetchMock);
  });

  it("opens the Settings canvas from the rail's operator pointer", async () => {
    // The Settings canvas mounts the config + trusted-sources panels, which fetch their own
    // endpoints — route them all so their async state settles within the awaited assertions.
    const fetchMock = vi.fn((input: Parameters<typeof fetch>[0]) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/settings")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ secrets: [], pipeline: "stub", supportsLessonRegeneration: true }),
        });
      }
      if (url.includes("/api/source-authorities")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url.includes("/api/config")) {
        return Promise.resolve({ ok: true, json: async () => ({ settings: [] }) });
      }
      if (url.includes("/api/runs")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      throw new Error(`unhandled URL ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await waitForRunsFetch(fetchMock);

    // The operator tier points to Settings rather than duplicating admin controls in the rail.
    fireEvent.click(screen.getByRole("button", { name: /open settings/i }));

    // findBy awaits the canvas switch + the panels' fetches settling (no act warnings).
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /done/i })).toBeInTheDocument();
  });

  it("collapses the sidebar to a mini icon rail and expands it again", async () => {
    // Asserts on DOM presence: the collapsed rail drops the resize splitter from the tree
    // (conditional render), not via CSS — jsdom doesn't apply CSS, so absence here is real absence.
    // The brand ("Lunaris") lives in the always-present top bar, so it stays through collapse.
    const fetchMock = routedFetch({ runs: [] });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await screen.findByText("Lunaris");

    // Expanded: the brand wordmark shows and the resize splitter is present; the toggle collapses.
    expect(screen.getByText("Lunaris")).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: /resize sidebar/i })).toBeInTheDocument();

    // Collapse → mini rail: the splitter is gone, the toggle now expands, the brand persists in the
    // top bar, and the rail actions stay as icons.
    fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
    expect(screen.getByText("Lunaris")).toBeInTheDocument();
    expect(screen.queryByRole("separator", { name: /resize sidebar/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /expand sidebar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new course/i })).toBeInTheDocument();
    // Exact match scopes to the sidebar's "Settings" — the idle rail also has an "Open Settings…".
    // Navigation entries are real links (they route to /settings), not buttons.
    expect(screen.getByRole("link", { name: /^settings$/i })).toBeInTheDocument();

    // Expand → the splitter returns.
    fireEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));
    expect(screen.getByText("Lunaris")).toBeInTheDocument();
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
      await screen.findByRole("heading", { name: "How binary search works", level: 1 }),
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

  it("buckets a full multi-phase build into branded, timed phases", async () => {
    // The end-to-end Phase A path: a representative build streams every moat + the author handoff
    // through SSE → useCourseStream → BuildTimeline. Each tool's payload must reach its branded
    // renderer (no raw JSON), bucketed under the phase it completed in. Kept open so Lessons stays
    // the active, streaming phase.
    const concepts = [
      { id: "tcp", label: "TCP" },
      { id: "tls", label: "TLS handshake" },
      { id: "https", label: "HTTPS" },
    ];
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
      // The run history still fetches at the shell level; it no longer surfaces in this view, so a
      // bare empty list is enough to let the effect settle.
      if (url.includes("/api/runs")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "HTTPS" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // The control room is live; the full branded transcript sits one toggle away (P8) — these
    // assertions exercise that lens, proving the `task` payload flowed SSE → timeline unchanged.
    expect(await screen.findByRole("region", { name: /building HTTPS/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("radio", { name: "Transcript" }));
    expect(await screen.findByText("module-author")).toBeInTheDocument();
    expect(await screen.findByText(/Author the Foundations module/i)).toBeInTheDocument();
    // No tool's payload leaks as raw JSON anywhere — including the deliberately truncated graph result.
    expect(screen.queryByText(/"nodes":/)).not.toBeInTheDocument();

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

  it("holds the control room open, all phases done, while videos finish (Verify-freeze fix)", async () => {
    // The stream's last progress event is claims_verified — the tail events coalesced with the
    // terminal course frame, the exact shape that used to freeze Verify as active forever. The
    // course carries a lesson video still rendering, so the canvas holds on "finishing videos".
    const course = makeCourse();
    course.modules[0]!.lessons[0]!.video = {
      kind: "lesson",
      status: "queued",
      jobId: "v1",
      provenance: null,
      narrated: false,
    };
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
        return Promise.resolve(
          sseStreamResponse([
            progressFrame("run_started", 0),
            progressFrame("claims_verified", 1, {
              claimsTotal: 4,
              claimsSupported: 4,
              claimsCut: 0,
            }),
            courseFrame(course),
          ]),
        );
      }
      if (url.endsWith("/videos")) {
        // One video, still rendering — the meter stays unsettled.
        return Promise.resolve({
          ok: true,
          json: async () => [{ jobId: "v1", kind: "lesson", lessonId: "l1", status: "running" }],
        });
      }
      if (url.includes("/api/runs")) return Promise.resolve({ ok: true, json: async () => [] });
      throw new Error(`unhandled ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // The control room stays mounted (titled by the finished course) with the videos meter
    // docked in its rail…
    expect(
      await screen.findByRole("region", { name: /building how binary search works/i }),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText("Video generation progress")).toBeInTheDocument();

    // …and every pipeline phase reads done, even though the last streamed stage was Verify.
    const pipeline = screen.getByRole("region", { name: /pipeline/i });
    for (const label of ["Verify", "Resources", "Coverage", "Videos", "Publish"]) {
      expect(within(pipeline).getByText(label).closest("[data-status]")).toHaveAttribute(
        "data-status",
        "done",
      );
    }
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

  it("offers the regenerate action when the pipeline supports it", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun({ id: "c-1", topic: "queues" })],
        course: makeCourse({ id: "c-1", topic: "queues" }),
        settings: { secrets: [], pipeline: "stub", supportsLessonRegeneration: true },
      }),
    );
    window.history.pushState(null, "", "/courses/c-1");
    render(<App />);

    await screen.findByRole("heading", { name: "queues", level: 1 });
    // A course lands on Overview; the regenerate action lives in the reader.
    fireEvent.click(screen.getByRole("radio", { name: /lessons/i }));

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
    window.history.pushState(null, "", "/courses/c-1");
    render(<App />);

    await screen.findByRole("heading", { name: "queues", level: 1 });
    // Enter the reader — asserting absence on the Overview tab would be vacuous.
    fireEvent.click(screen.getByRole("radio", { name: /lessons/i }));
    await screen.findByText(/find a word in a dictionary/i);

    // waitFor drains the capability-fetch microtask, so the absence reflects
    // supportsLessonRegeneration === false — not merely an unresolved fetch (canRegenerate
    // defaults to false). The paired "offers" test proves the button CAN appear.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /regenerate lesson/i })).not.toBeInTheDocument(),
    );
  });

  it("reattaches a still-running run to its live build timeline — not a 404 error", async () => {
    // The course isn't persisted until the run finishes, so opening a RUNNING run must not fetch it
    // (which would 404 into a broken-looking error). Instead it reattaches to the live event log and
    // shows progress. No `course` handler is wired, so routedFetch would throw on any course fetch —
    // proving the running run never triggers one.
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun({ id: "c-1", topic: "queues", status: "running" })],
        events: [
          makeRunEvent(0, makeProgressEvent("run_started", 0)),
          makeRunEvent(1, makeAgentEvent("reasoning", 1, { text: "Mapping the prerequisites." })),
        ],
      }),
    );
    window.history.pushState(null, "", "/courses/c-1");
    render(<App />);

    // The live timeline renders the in-flight log — not the static placeholder, not a 404 alert.
    expect(await screen.findByRole("region", { name: /building queues/i })).toBeInTheDocument();
    expect(await screen.findByText("Mapping the prerequisites.")).toBeInTheDocument();
    // The canvas Cancel action.
    expect(screen.getByRole("button", { name: /^cancel build$/i })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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
      // The reattached running run polls its live event log — keep it out of the run-history count.
      if (/\/api\/runs\/[^/]+\/events$/.test(url)) {
        return Promise.resolve({ ok: true, json: async () => [] });
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
    window.history.pushState(null, "", "/courses/c-1");
    render(<App />);

    // Open the running run via its URL → live build canvas, then cancel from the canvas.
    await screen.findByRole("region", { name: /building graphs/i });
    fireEvent.click(screen.getByRole("button", { name: /^cancel build$/i }));

    // The cancel is POSTed by run_id.
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/runs/run-1/cancel"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
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

  it("re-runs the identical failed build (incl. Official-sources-only) on Try again", async () => {
    // Arrange — every build fails; the composer has the trust switch turned on.
    const fetchMock = routedFetch({ runs: [], build: { ok: false, status: 500, body: null } });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(screen.getByRole("switch", { name: /official sources only/i }));
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // Act — the build errors; retry it.
    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    // Assert — the retry re-issued the build stream carrying official_only=true (retry parity end
    // to end), not a defaulted rebuild that silently dropped the trust switch.
    await waitFor(() => {
      const streamCalls = fetchMock.mock.calls.filter(([input]) =>
        String(input).includes("/api/courses/stream"),
      );
      expect(streamCalls.length).toBeGreaterThanOrEqual(2);
      expect(String(streamCalls.at(-1)?.[0])).toContain("official_only=true");
    });
  });

  it("lands a ready course on its Overview tab, not the reader or the graph", async () => {
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

    // Assert — Overview is the landing tab: the Continue CTA renders, the reader prose and the
    // graph stay absent until chosen…
    expect(await screen.findByRole("button", { name: /continue learning/i })).toBeInTheDocument();
    expect(screen.queryByText(/find a word in a dictionary/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("application", { name: /prerequisite graph/i }),
    ).not.toBeInTheDocument();
    // …and the tab bar shows Overview selected.
    expect(screen.getByRole("radio", { name: /overview/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /lessons/i })).not.toBeChecked();
  });

  it("toggles the ready canvas between the reader (Lessons) and the graph (Map)", async () => {
    // Arrange — a ready course on the canvas, opened into the reader.
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
    fireEvent.click(await screen.findByRole("radio", { name: /lessons/i }));
    await screen.findByText(/find a word in a dictionary/i);

    // Act — switch to Map. Assert — the graph canvas shows, the prose is gone.
    fireEvent.click(screen.getByRole("radio", { name: /map/i }));
    expect(
      await screen.findByRole("application", { name: /prerequisite graph/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/find a word in a dictionary/i)).not.toBeInTheDocument();

    // Act — switch back to Lessons. Assert — the reader returns.
    fireEvent.click(screen.getByRole("radio", { name: /lessons/i }));
    expect(await screen.findByText(/find a word in a dictionary/i)).toBeInTheDocument();
  });

  it("deletes the course you're viewing from its Overview danger zone, then returns Home", async () => {
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
      // Home (the post-delete destination) reads the courses library.
      if (/\/api\/courses$/.test(url) && method === "GET") {
        return Promise.resolve({ ok: true, json: async () => [] });
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
    window.history.pushState(null, "", "/courses/c-1");
    render(<App />);

    // Open the course, then delete it from its Overview danger zone.
    await screen.findByRole("heading", { name: "queues", level: 1 });
    fireEvent.click(await screen.findByRole("button", { name: /delete course/i }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: /^delete course$/i }),
    );

    // The canvas drops the deleted course and returns to Home (the dashboard at /).
    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening)/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "queues" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/courses/c-1"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
