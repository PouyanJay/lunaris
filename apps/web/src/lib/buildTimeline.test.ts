import { describe, expect, it } from "vitest";

import { makeAgentEvent, makeProgressEvent } from "../test/fixtures";
import { buildTimeline, latestPlan, type TimelinePhase } from "./buildTimeline";

/** Find a phase by its label, failing loudly if absent. */
function phase(phases: TimelinePhase[], label: string): TimelinePhase {
  const found = phases.find((p) => p.label === label);
  if (!found) throw new Error(`no "${label}" phase in [${phases.map((p) => p.label).join(", ")}]`);
  return found;
}

describe("buildTimeline", () => {
  it("buckets agent events under the phase active when they fired, pairing call+result", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("concepts_extracted", 1, { kcCount: 21, label: "21 concepts" }),
      makeProgressEvent("graph_built", 2),
    ];
    const agentEvents = [
      makeAgentEvent("reasoning", 0, { stage: "run_started", text: "Planning the build…" }),
      makeAgentEvent("tool_call", 1, {
        stage: "run_started",
        tool: "extract_concepts",
        toolArgs: { topic: "HTTPS" },
      }),
      // The result lands in the NEXT phase — the pair must follow the result's stage (Concepts).
      makeAgentEvent("tool_result", 2, {
        stage: "concepts_extracted",
        tool: "extract_concepts",
        result: "21 concepts",
      }),
      makeAgentEvent("tool_call", 3, {
        stage: "concepts_extracted",
        tool: "build_prerequisite_graph",
      }),
      makeAgentEvent("tool_result", 4, {
        stage: "graph_built",
        tool: "build_prerequisite_graph",
        result: "ok",
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    // The pre-stage beat is in the leading "Start" node.
    const intro = phase(phases, "Start");
    expect(intro.entries).toEqual([
      expect.objectContaining({ kind: "reasoning", text: "Planning the build…" }),
    ]);

    // extract_concepts pairs into Concepts (by the result's stage), carrying its result; done.
    const concepts = phase(phases, "Concepts");
    expect(concepts.status).toBe("done");
    expect(concepts.summary).toBe("21 concepts");
    expect(concepts.entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "extract_concepts", result: "21 concepts" }),
    ]);

    // The graph tool pairs into Graph; it's the latest reached phase → active.
    const graph = phase(phases, "Graph");
    expect(graph.status).toBe("active");
    expect(graph.entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "build_prerequisite_graph", result: "ok" }),
    ]);

    // Unreached phases are pending and empty.
    expect(phase(phases, "Curriculum").status).toBe("pending");
    expect(phase(phases, "Curriculum").entries).toHaveLength(0);
  });

  it("buckets the interpret_request beats under a leading Brief phase, ahead of Concepts", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("brief_interpreted", 1, { label: "Interpreted the goal: reach CLB 10" }),
      makeProgressEvent("concepts_extracted", 2, { label: "18 concepts" }),
    ];
    const agentEvents = [
      makeAgentEvent("tool_call", 0, {
        stage: "run_started",
        tool: "interpret_request",
        toolArgs: { request: "Improve my English to CLB 10" },
      }),
      makeAgentEvent("tool_result", 1, {
        stage: "brief_interpreted",
        tool: "interpret_request",
        result: '{"subject":"English"}',
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    // Brief is the FIRST coarse phase on the spine, ahead of Concepts (the new front of the
    // pipeline) — no intro "Start" node here, so it leads.
    const labels = phases.map((p) => p.label);
    expect(labels[0]).toBe("Brief");
    expect(labels.indexOf("Brief")).toBeLessThan(labels.indexOf("Concepts"));

    // The interpret_request call+result pair buckets into Brief (by the result's stage), done with
    // its progress summary.
    const brief = phase(phases, "Brief");
    expect(brief.status).toBe("done");
    expect(brief.summary).toBe("Interpreted the goal: reach CLB 10");
    expect(brief.entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "interpret_request" }),
    ]);
  });

  it("buckets the model_learner beats under the Learner phase, between Research and Concepts", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("brief_interpreted", 1),
      makeProgressEvent("learner_modeled", 2, { label: "Modeled the learner: 2 known area(s)" }),
      makeProgressEvent("concepts_extracted", 3, { label: "12 concepts" }),
    ];
    const agentEvents = [
      makeAgentEvent("tool_call", 0, { stage: "brief_interpreted", tool: "model_learner" }),
      makeAgentEvent("tool_result", 1, {
        stage: "learner_modeled",
        tool: "model_learner",
        result: '{"frontier":["the alphabet","basic vocabulary"],"count":2}',
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    // Learner sits between Research and Concepts on the spine.
    const labels = phases.map((p) => p.label);
    expect(labels.indexOf("Research")).toBeLessThan(labels.indexOf("Learner"));
    expect(labels.indexOf("Learner")).toBeLessThan(labels.indexOf("Concepts"));

    const learner = phase(phases, "Learner");
    expect(learner.status).toBe("done");
    expect(learner.summary).toBe("Modeled the learner: 2 known area(s)");
    expect(learner.entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "model_learner" }),
    ]);
  });

  it("buckets the research_standard beats under the Research phase, between Brief and Learner", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("brief_interpreted", 1),
      makeProgressEvent("standard_researched", 2, {
        label: "Researched the standard: complete, 2 competency descriptor(s)",
      }),
      makeProgressEvent("learner_modeled", 3, { label: "Modeled the learner: 2 known area(s)" }),
    ];
    const agentEvents = [
      makeAgentEvent("tool_call", 0, { stage: "brief_interpreted", tool: "research_standard" }),
      makeAgentEvent("tool_result", 1, {
        stage: "standard_researched",
        tool: "research_standard",
        result: '{"status":"complete","competencies":["hear implied intent"],"sources":[]}',
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    // Research sits between Brief and Learner on the spine (interpret → research → model learner).
    const labels = phases.map((p) => p.label);
    expect(labels.indexOf("Brief")).toBeLessThan(labels.indexOf("Research"));
    expect(labels.indexOf("Research")).toBeLessThan(labels.indexOf("Learner"));

    const research = phase(phases, "Research");
    expect(research.status).toBe("done");
    expect(research.summary).toBe("Researched the standard: complete, 2 competency descriptor(s)");
    expect(research.entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "research_standard" }),
    ]);
  });

  it("marks every phase done once the run completes", () => {
    const phases = buildTimeline([makeProgressEvent("run_completed", 9)], []);

    expect(phase(phases, "Concepts").status).toBe("done");
    expect(phase(phases, "Publish").status).toBe("done");
  });

  it("keeps a still-running tool call in its phase, unpaired", () => {
    const phases = buildTimeline(
      [makeProgressEvent("module_authored", 4)],
      [makeAgentEvent("tool_call", 0, { stage: "module_authored", tool: "task" })],
    );

    expect(phase(phases, "Lessons").entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "task", result: null }),
    ]);
  });

  it("returns the coarse pending phases (no intro node) for an empty build", () => {
    const phases = buildTimeline([], []);

    expect(phases.map((p) => p.label)).toEqual([
      "Brief",
      "Research",
      "Learner",
      "Concepts",
      "Graph",
      "Curriculum",
      "Seeding",
      "Grounding",
      "Lessons",
      "Verify",
      "Resources",
      "Coverage",
      "Videos",
      "Publish",
    ]);
    expect(phases.every((p) => p.status === "pending" && p.entries.length === 0)).toBe(true);
  });

  it("surfaces a Videos phase with per-lesson beats, between Coverage and Publish", () => {
    const events = [
      makeProgressEvent("coverage_verified", 0),
      makeProgressEvent("lesson_videos", 1, {
        label: "3 lesson videos ready",
        videosTotal: 3,
        videosDegraded: 0,
      }),
    ];
    const agentEvents = [
      makeAgentEvent("reasoning", 0, {
        stage: "lesson_videos",
        text: "Explainer video for “Routing” is ready.",
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    const labels = phases.map((p) => p.label);
    expect(labels.indexOf("Coverage")).toBeLessThan(labels.indexOf("Videos"));
    expect(labels.indexOf("Videos")).toBeLessThan(labels.indexOf("Publish"));

    const videos = phase(phases, "Videos");
    expect(videos.summary).toBe("3 lesson videos ready");
    expect(videos.summaryTone).toBeUndefined(); // none degraded → no amber
    expect(videos.entries).toEqual([
      expect.objectContaining({ kind: "reasoning", text: "Explainer video for “Routing” is ready." }),
    ]);
  });

  it("tints the Videos phase amber when a lesson video degraded", () => {
    const phases = buildTimeline(
      [
        makeProgressEvent("lesson_videos", 0, {
          label: "3 lesson videos · 2 ready · 1 needs a retry",
          videosTotal: 3,
          videosDegraded: 1,
        }),
      ],
      [],
    );

    const videos = phase(phases, "Videos");
    expect(videos.summary).toBe("3 lesson videos · 2 ready · 1 needs a retry");
    expect(videos.summaryTone).toBe("warning");
    // The amber tone is scoped to the Videos phase — no other phase picks it up.
    expect(phases.filter((p) => p.label !== "Videos").every((p) => p.summaryTone === undefined)).toBe(
      true,
    );
  });

  it("buckets the seed_grounding beats under the Seeding phase, between Curriculum and Grounding", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("curriculum_designed", 1, { label: "Designed curriculum: 3 modules" }),
      makeProgressEvent("grounding_seeded", 2, { label: "Seeded the corpus from research" }),
      makeProgressEvent("grounding_discovered", 3, { label: "Prepared the grounding corpus" }),
    ];
    const agentEvents = [
      makeAgentEvent("tool_call", 0, { stage: "curriculum_designed", tool: "seed_grounding" }),
      makeAgentEvent("tool_result", 1, {
        stage: "grounding_seeded",
        tool: "seed_grounding",
        result: '{"status":"ready","sourceCount":3,"chunksIngested":27}',
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    // seed first, discover the gaps next — the two corpus phases are intentionally ordered.
    const labels = phases.map((p) => p.label);
    expect(labels.indexOf("Curriculum")).toBeLessThan(labels.indexOf("Seeding"));
    expect(labels.indexOf("Seeding")).toBeLessThan(labels.indexOf("Grounding"));

    const seeding = phase(phases, "Seeding");
    expect(seeding.status).toBe("done");
    expect(seeding.summary).toBe("Seeded the corpus from research");
    expect(seeding.entries).toEqual([
      expect.objectContaining({
        kind: "tool",
        tool: "seed_grounding",
        result: expect.stringContaining("ready"),
      }),
    ]);
  });

  it("buckets the discover_grounding beats under the Grounding phase, between Curriculum and Lessons", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("curriculum_designed", 1, { label: "Designed curriculum: 3 modules" }),
      makeProgressEvent("grounding_discovered", 2, { label: "Prepared the grounding corpus" }),
      makeProgressEvent("module_authored", 3, { label: "Authored lesson: Module" }),
    ];
    const agentEvents = [
      makeAgentEvent("tool_call", 0, { stage: "curriculum_designed", tool: "discover_grounding" }),
      makeAgentEvent("tool_result", 1, {
        stage: "grounding_discovered",
        tool: "discover_grounding",
        result: '{"status":"ready","sourceCount":0}',
      }),
    ];

    const phases = buildTimeline(events, agentEvents);

    // Grounding sits between Curriculum and Lessons on the spine (the P6 evidence step).
    const labels = phases.map((p) => p.label);
    expect(labels.indexOf("Curriculum")).toBeLessThan(labels.indexOf("Grounding"));
    expect(labels.indexOf("Grounding")).toBeLessThan(labels.indexOf("Lessons"));

    const grounding = phase(phases, "Grounding");
    expect(grounding.status).toBe("done");
    expect(grounding.summary).toBe("Prepared the grounding corpus");
    expect(grounding.entries).toEqual([
      expect.objectContaining({
        kind: "tool",
        tool: "discover_grounding",
        result: expect.stringContaining("ready"),
      }),
    ]);
  });

  it("pairs a result with the most recent open call of the same tool", () => {
    const events = [makeProgressEvent("module_authored", 4)];
    const agentEvents = [
      makeAgentEvent("tool_call", 0, { stage: "module_authored", tool: "task" }),
      makeAgentEvent("tool_call", 1, { stage: "module_authored", tool: "task" }),
      makeAgentEvent("tool_result", 2, {
        stage: "module_authored",
        tool: "task",
        result: "module 2 done",
      }),
    ];

    // Two open calls, one result → the newest call is paired; the older stays open.
    expect(phase(buildTimeline(events, agentEvents), "Lessons").entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "task", result: null }),
      expect.objectContaining({ kind: "tool", tool: "task", result: "module 2 done" }),
    ]);
  });

  it("times each DONE phase from its stage arrival back to the previous stage", () => {
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("brief_interpreted", 1),
      makeProgressEvent("standard_researched", 2),
      makeProgressEvent("learner_modeled", 3),
      makeProgressEvent("concepts_extracted", 4),
      makeProgressEvent("graph_built", 5),
    ];
    // Brief spanned run_started→brief (0.5s); Research brief→research (0.5s); Learner
    // research→learner (0.3s); Concepts learner→concepts (1.5s); Graph is still active.
    const stageTimes = {
      run_started: 1_000,
      brief_interpreted: 1_500,
      standard_researched: 2_000,
      learner_modeled: 2_300,
      concepts_extracted: 3_800,
      graph_built: 4_300,
    };

    const phases = buildTimeline(events, [], stageTimes);

    expect(phase(phases, "Brief").durationMs).toBe(500);
    expect(phase(phases, "Research").durationMs).toBe(500);
    expect(phase(phases, "Learner").durationMs).toBe(300);
    expect(phase(phases, "Concepts").durationMs).toBe(1_500);
    // The active phase shows "running…", not a duration; every unreached phase has none either.
    expect(phase(phases, "Graph").durationMs).toBeNull();
    expect(phases.filter((p) => p.status === "pending").every((p) => p.durationMs === null)).toBe(
      true,
    );
  });

  it("leaves a done phase's duration null when its lower-boundary stage time is missing", () => {
    // The client reconnected after run_started fired: Concepts' completion time is known, its start
    // (run_started) is not → no honest span to show.
    const phases = buildTimeline(
      [makeProgressEvent("concepts_extracted", 1), makeProgressEvent("graph_built", 2)],
      [],
      { concepts_extracted: 5_000, graph_built: 6_000 },
    );

    expect(phase(phases, "Concepts").status).toBe("done");
    expect(phase(phases, "Concepts").durationMs).toBeNull();
  });

  it("leaves durations null when no stage times are provided", () => {
    const phases = buildTimeline([makeProgressEvent("run_completed", 9)], []);

    expect(phases.every((p) => p.durationMs === null)).toBe(true);
  });

  it("surfaces an orphan tool result that has no preceding call", () => {
    const phases = buildTimeline(
      [makeProgressEvent("graph_built", 2)],
      [
        makeAgentEvent("tool_result", 0, {
          stage: "graph_built",
          tool: "build_prerequisite_graph",
          result: "ok",
        }),
      ],
    );

    expect(phase(phases, "Graph").entries).toEqual([
      expect.objectContaining({ kind: "tool", tool: "build_prerequisite_graph", result: "ok" }),
    ]);
  });

  it("accumulates consecutive reasoning deltas into one growing streaming beat", () => {
    const phases = buildTimeline(
      [makeProgressEvent("run_started", 0)],
      [
        makeAgentEvent("reasoning", 0, { stage: "run_started", delta: "Let me " }),
        makeAgentEvent("reasoning", 1, { stage: "run_started", delta: "extract " }),
        makeAgentEvent("reasoning", 2, { stage: "run_started", delta: "the concepts." }),
      ],
    );

    // One beat, keyed by the first delta, carrying the concatenated (untrimmed) text + a stream flag.
    expect(phase(phases, "Start").entries).toEqual([
      { kind: "reasoning", key: "r-0", text: "Let me extract the concepts.", streaming: true },
    ]);
  });

  it("splits reasoning deltas into separate beats when a tool call interleaves them", () => {
    const phases = buildTimeline(
      [makeProgressEvent("concepts_extracted", 1)],
      [
        makeAgentEvent("reasoning", 0, { stage: "concepts_extracted", delta: "First " }),
        makeAgentEvent("reasoning", 1, { stage: "concepts_extracted", delta: "thought." }),
        makeAgentEvent("tool_call", 2, { stage: "concepts_extracted", tool: "extract_concepts" }),
        makeAgentEvent("reasoning", 3, { stage: "concepts_extracted", delta: "Second thought." }),
      ],
    );

    // The tool ends the first streaming run; the later delta begins a fresh beat (distinct key).
    expect(phase(phases, "Concepts").entries).toEqual([
      { kind: "reasoning", key: "r-0", text: "First thought.", streaming: true },
      expect.objectContaining({ kind: "tool", tool: "extract_concepts" }),
      { kind: "reasoning", key: "r-3", text: "Second thought.", streaming: true },
    ]);
  });

  it("keeps whole-text reasoning beats non-streaming (the deterministic path)", () => {
    const phases = buildTimeline(
      [makeProgressEvent("run_started", 0)],
      [makeAgentEvent("reasoning", 0, { stage: "run_started", text: "Planning the build." })],
    );

    const [entry] = phase(phases, "Start").entries;
    expect(entry).toEqual({ kind: "reasoning", key: "r-0", text: "Planning the build." });
    expect(entry).not.toHaveProperty("streaming", true);
  });

  it("folds source_evaluated events into source entries under the Grounding phase", () => {
    const phases = buildTimeline(
      [
        makeProgressEvent("run_started", 0),
        makeProgressEvent("grounding_discovered", 1, { label: "Finding evidence" }),
      ],
      [
        makeAgentEvent("source_evaluated", 0, {
          stage: "grounding_discovered",
          source: {
            kcId: "dijkstra",
            domain: "study.example",
            trustTier: "reputable",
            credibility: 0.75,
            sourceType: "web",
            accepted: true,
            reason: "On topic.",
          },
        }),
        makeAgentEvent("source_evaluated", 1, {
          stage: "grounding_discovered",
          source: {
            kcId: "dijkstra",
            domain: "spam.example",
            trustTier: "open",
            credibility: 0.3,
            sourceType: "web",
            accepted: false,
            reason: "Off topic.",
          },
        }),
      ],
    );

    const entries = phase(phases, "Grounding").entries;
    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({
      kind: "source",
      source: { domain: "study.example", accepted: true },
    });
    expect(entries[1]).toMatchObject({
      kind: "source",
      source: { domain: "spam.example", accepted: false },
    });
  });

  it("ignores a source_evaluated event whose source payload is absent", () => {
    const phases = buildTimeline(
      [makeProgressEvent("grounding_discovered", 0)],
      [makeAgentEvent("source_evaluated", 0, { stage: "grounding_discovered", source: null })],
    );

    expect(phase(phases, "Grounding").entries).toHaveLength(0);
  });
});

describe("buildTimeline — completion override", () => {
  it("marks every phase done once the run is complete, even without run_completed", () => {
    // The terminal course frame can land before (or instead of) the tail progress events — the
    // live view used to freeze Verify as active forever (the P8 Verify-freeze fix).
    const events = [
      makeProgressEvent("run_started", 0),
      makeProgressEvent("claims_verified", 1, { label: "18 of 21 supported" }),
    ];

    const phases = buildTimeline(events, [], {}, { complete: true });

    expect(phase(phases, "Verify").status).toBe("done");
    expect(phase(phases, "Publish").status).toBe("done");
    expect(phases.every((p) => p.status === "done")).toBe(true);
  });

  it("keeps the normal single-active-phase model while the run is incomplete", () => {
    const events = [makeProgressEvent("run_started", 0), makeProgressEvent("claims_verified", 1)];

    const phases = buildTimeline(events, [], {}, { complete: false });

    expect(phase(phases, "Verify").status).toBe("active");
    expect(phase(phases, "Resources").status).toBe("pending");
  });
});

describe("latestPlan", () => {
  it("returns the most recent plan the agent emitted (latest write_todos wins)", () => {
    const plan = latestPlan([
      makeAgentEvent("todo", 0, {
        todos: [
          { content: "a", status: "in_progress" },
          { content: "b", status: "pending" },
        ],
      }),
      makeAgentEvent("reasoning", 1, { text: "working…" }),
      makeAgentEvent("todo", 2, { todos: [{ content: "a", status: "completed" }] }),
    ]);

    expect(plan).toEqual([{ content: "a", status: "completed" }]);
  });

  it("returns null before the agent has emitted a plan", () => {
    expect(latestPlan([makeAgentEvent("reasoning", 0, { text: "thinking" })])).toBeNull();
  });
});
