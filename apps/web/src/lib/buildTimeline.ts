import type { AgentEvent, AgentTodo, ProgressEvent, ProgressStage } from "../types/course";

/** A phase's lifecycle on the build timeline. Only the single in-flight phase is `active`. */
export type PhaseStatus = "pending" | "active" | "done";

/** A rendered entry inside a phase: a reasoning beat, or a tool call paired with its result. A
 *  `streaming` reasoning beat is one being assembled live from token deltas (the live path); the
 *  UI grows its text in place and shows a caret while it is the active phase's latest beat. */
export type TimelineEntry =
  | { kind: "reasoning"; key: string; text: string; streaming?: boolean }
  | {
      kind: "tool";
      key: string;
      tool: string;
      args: Record<string, unknown> | null;
      result: string | null;
    };

/** One node on the timeline: a major pipeline phase, its status, a one-line summary, and the
 *  fine-grained reasoning/tool beats that fired while it was active. The agent's plan (todos) is no
 *  longer per-phase — it lives in the pinned top panel (see {@link latestPlan}). */
export interface TimelinePhase {
  key: string;
  label: string;
  status: PhaseStatus;
  summary: string | null;
  entries: TimelineEntry[];
  /** Wall-clock span of a DONE phase (ms), from its stage arrival back to the previous stage; null
   *  for active/pending phases or when stage arrival times were not captured. */
  durationMs: number | null;
}

/** Client-stamped wall-clock arrival time (ms) per pipeline stage, captured live as events stream. */
export type StageTimes = Partial<Record<ProgressStage, number>>;

/** The coarse phases shown on the spine (run_started is folded into the intro "Plan" node). */
const PHASES: { stage: ProgressStage; label: string }[] = [
  { stage: "brief_interpreted", label: "Brief" },
  { stage: "standard_researched", label: "Research" },
  { stage: "learner_modeled", label: "Learner" },
  { stage: "concepts_extracted", label: "Concepts" },
  { stage: "graph_built", label: "Graph" },
  { stage: "curriculum_designed", label: "Curriculum" },
  { stage: "grounding_discovered", label: "Grounding" },
  { stage: "module_authored", label: "Lessons" },
  { stage: "claims_verified", label: "Verify" },
  { stage: "resources_curated", label: "Resources" },
  { stage: "run_completed", label: "Publish" },
];

const INTRO_KEY = "intro";
const UNKNOWN_TOOL = "tool";

interface StagedEntry {
  entry: TimelineEntry;
  phaseKey: string;
}

/** Map an event's stage to its phase bucket: the six real phases by stage; run_started / null /
 *  unknown fold into the intro "Plan" node (the beats before the first real phase). */
function phaseKeyForStage(stage: ProgressStage | null): string {
  return stage && PHASES.some((phase) => phase.stage === stage) ? stage : INTRO_KEY;
}

/** Index of the most recent still-open tool entry for `tool` (newest-first), or -1. */
function pendingToolIndex(staged: StagedEntry[], tool: string): number {
  for (let i = staged.length - 1; i >= 0; i -= 1) {
    const found = staged[i];
    if (found?.entry.kind === "tool" && found.entry.tool === tool && found.entry.result === null) {
      return i;
    }
  }
  return -1;
}

/** Append a streaming token chunk to the in-progress reasoning beat, or start a new one. Consecutive
 *  deltas in the same phase grow one `<p>` (keyed by the first delta), so the reasoning forms in
 *  place rather than spawning a beat per token; any other entry (a tool, or a whole-text beat) ends
 *  the run, so a later delta begins a fresh streaming beat. */
function appendDelta(
  staged: StagedEntry[],
  delta: string,
  sequence: number,
  phaseKey: string,
): void {
  const last = staged[staged.length - 1];
  if (last?.entry.kind === "reasoning" && last.entry.streaming && last.phaseKey === phaseKey) {
    // Replace (not mutate) the entry so the fold's intermediate state stays obvious, mirroring the
    // call/result pairing below.
    staged[staged.length - 1] = {
      entry: { ...last.entry, text: last.entry.text + delta },
      phaseKey,
    };
  } else {
    staged.push({
      entry: { kind: "reasoning", key: `r-${sequence}`, text: delta, streaming: true },
      phaseKey,
    });
  }
}

/** Fold the agent events into staged entries: reasoning beats, and tool calls paired with their
 *  result. A pair follows the result's stage (a tool emits its boundary stage as it completes), so
 *  e.g. extract_concepts lands in Concepts even though its call fired during run_started. */
function stagedEntries(agentEvents: AgentEvent[]): StagedEntry[] {
  const staged: StagedEntry[] = [];
  for (const event of agentEvents) {
    const phaseKey = phaseKeyForStage(event.stage);
    if (event.kind === "reasoning") {
      if (event.delta) {
        appendDelta(staged, event.delta, event.sequence, phaseKey);
      } else {
        const text = event.text?.trim();
        if (text) {
          staged.push({ entry: { kind: "reasoning", key: `r-${event.sequence}`, text }, phaseKey });
        }
      }
    } else if (event.kind === "tool_call") {
      staged.push({
        entry: {
          kind: "tool",
          key: `t-${event.sequence}`,
          tool: event.tool ?? UNKNOWN_TOOL,
          args: event.toolArgs,
          result: null,
        },
        phaseKey,
      });
    } else if (event.kind === "tool_result") {
      const tool = event.tool ?? UNKNOWN_TOOL;
      const index = pendingToolIndex(staged, tool);
      const open = index !== -1 ? staged[index] : undefined;
      if (open && open.entry.kind === "tool") {
        // Promote the paired call to the result's phase, recording its result — replacing the entry
        // rather than mutating it in place, so the fold's intermediate state stays obvious.
        staged[index] = { entry: { ...open.entry, result: event.result ?? "" }, phaseKey };
      } else {
        // An orphan result (e.g. a mid-stream reconnect) still surfaces, on its own.
        staged.push({
          entry: {
            kind: "tool",
            key: `t-${event.sequence}`,
            tool,
            args: null,
            result: event.result ?? "",
          },
          phaseKey,
        });
      }
    }
  }
  return staged;
}

/** The most recent plan the agent emitted — the latest non-empty `write_todos`, scanning
 *  newest-first; its overall done/total is the build's coarse progress. Null until the agent has
 *  planned. (Where it renders — the pinned top panel — is the caller's concern.) */
export function latestPlan(agentEvents: AgentEvent[]): AgentTodo[] | null {
  for (let i = agentEvents.length - 1; i >= 0; i -= 1) {
    const event = agentEvents[i];
    if (event?.kind === "todo" && event.todos && event.todos.length > 0) return event.todos;
  }
  return null;
}

/** The active phase index from the latest progress stage: run_completed → all done (past the last),
 *  run_started / none → -1 (the intro is active). */
function currentPhaseIndex(events: ProgressEvent[]): number {
  const last = events.at(-1)?.stage ?? null;
  if (last === "run_completed") return PHASES.length;
  return PHASES.findIndex((phase) => phase.stage === last);
}

function statusFor(index: number, current: number): PhaseStatus {
  if (current >= PHASES.length || index < current) return "done";
  if (index === current) return "active";
  return "pending";
}

/** The latest progress label recorded for a stage (e.g. "21 concepts"), or null. */
function summaryForStage(events: ProgressEvent[], stage: ProgressStage): string | null {
  let summary: string | null = null;
  for (const event of events) if (event.stage === stage) summary = event.label;
  return summary;
}

/** A DONE phase's wall-clock span: its stage's arrival minus the previous stage's (run_started leads
 *  the first phase). Null for active/pending phases, or when either arrival time wasn't captured. */
function durationForPhase(
  index: number,
  status: PhaseStatus,
  stageTimes: StageTimes,
): number | null {
  if (status !== "done") return null;
  const stage = PHASES[index]?.stage;
  // PHASES is a fixed module constant and `index` comes from PHASES.forEach, so index-1 is in bounds.
  const prevStage: ProgressStage = index === 0 ? "run_started" : PHASES[index - 1]!.stage;
  const end = stage ? stageTimes[stage] : undefined;
  const start = stageTimes[prevStage];
  return end !== undefined && start !== undefined ? end - start : null;
}

/**
 * Fold the coarse progress stream + the fine agent-event stream into an ordered list of timeline
 * phases — the data the {@link BuildTimeline} renders. Each phase carries its status (the single
 * in-flight one is `active`), a one-line summary, the bucketed reasoning/tool entries, and its
 * duration. A leading "Start" node holds the agent's opening reasoning (the pre-stage beats), and
 * appears only when there is such reasoning to show; the plan itself rides the pinned top panel.
 */
export function buildTimeline(
  events: ProgressEvent[],
  agentEvents: AgentEvent[],
  stageTimes: StageTimes = {},
): TimelinePhase[] {
  const staged = stagedEntries(agentEvents);
  const current = currentPhaseIndex(events);
  const entriesFor = (key: string) => staged.filter((s) => s.phaseKey === key).map((s) => s.entry);

  const phases: TimelinePhase[] = [];
  const introEntries = entriesFor(INTRO_KEY);
  if (introEntries.length > 0) {
    phases.push({
      key: INTRO_KEY,
      label: "Start",
      status: current < 0 ? "active" : "done",
      summary: null,
      entries: introEntries,
      durationMs: null,
    });
  }
  PHASES.forEach((phase, index) => {
    const status = statusFor(index, current);
    phases.push({
      key: phase.stage,
      label: phase.label,
      status,
      summary: summaryForStage(events, phase.stage),
      entries: entriesFor(phase.stage),
      durationMs: durationForPhase(index, status, stageTimes),
    });
  });
  return phases;
}
