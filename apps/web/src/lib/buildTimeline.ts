import type { AgentEvent, AgentTodo, ProgressEvent, ProgressStage } from "../types/course";

/** A phase's lifecycle on the build timeline. Only the single in-flight phase is `active`. */
export type PhaseStatus = "pending" | "active" | "done";

/** A rendered entry inside a phase: a reasoning beat, or a tool call paired with its result. */
export type TimelineEntry =
  | { kind: "reasoning"; key: string; text: string }
  | {
      kind: "tool";
      key: string;
      tool: string;
      args: Record<string, unknown> | null;
      result: string | null;
    };

/** One node on the timeline: a major pipeline phase, its status, a one-line summary, and the
 *  fine-grained events that fired while it was active (the live plan, if any, rides along). */
export interface TimelinePhase {
  key: string;
  label: string;
  status: PhaseStatus;
  summary: string | null;
  entries: TimelineEntry[];
  todos: AgentTodo[] | null;
}

/** The six coarse phases shown on the spine (run_started is folded into the intro "Plan" node). */
const PHASES: { stage: ProgressStage; label: string }[] = [
  { stage: "concepts_extracted", label: "Concepts" },
  { stage: "graph_built", label: "Graph" },
  { stage: "curriculum_designed", label: "Curriculum" },
  { stage: "module_authored", label: "Lessons" },
  { stage: "claims_verified", label: "Verify" },
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

/** Fold the agent events into staged entries: reasoning beats, and tool calls paired with their
 *  result. A pair follows the result's stage (a tool emits its boundary stage as it completes), so
 *  e.g. extract_concepts lands in Concepts even though its call fired during run_started. */
function stagedEntries(agentEvents: AgentEvent[]): StagedEntry[] {
  const staged: StagedEntry[] = [];
  for (const event of agentEvents) {
    const phaseKey = phaseKeyForStage(event.stage);
    if (event.kind === "reasoning") {
      const text = event.text?.trim();
      if (text) {
        staged.push({ entry: { kind: "reasoning", key: `r-${event.sequence}`, text }, phaseKey });
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

/** The latest plan (todos) seen per phase. */
function todosByPhase(agentEvents: AgentEvent[]): Map<string, AgentTodo[]> {
  const byPhase = new Map<string, AgentTodo[]>();
  for (const event of agentEvents) {
    if (event.kind === "todo" && event.todos)
      byPhase.set(phaseKeyForStage(event.stage), event.todos);
  }
  return byPhase;
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

/**
 * Fold the coarse progress stream + the fine agent-event stream into an ordered list of timeline
 * phases — the data the {@link BuildTimeline} renders. Each phase carries its status (the single
 * in-flight one is `active`), a one-line summary, the bucketed reasoning/tool entries, and the live
 * plan. An intro "Plan" node leads only when there are pre-stage beats to show.
 */
export function buildTimeline(events: ProgressEvent[], agentEvents: AgentEvent[]): TimelinePhase[] {
  const staged = stagedEntries(agentEvents);
  const todos = todosByPhase(agentEvents);
  const current = currentPhaseIndex(events);
  const entriesFor = (key: string) => staged.filter((s) => s.phaseKey === key).map((s) => s.entry);

  const phases: TimelinePhase[] = [];
  const introEntries = entriesFor(INTRO_KEY);
  const introTodos = todos.get(INTRO_KEY) ?? null;
  if (introEntries.length > 0 || introTodos) {
    phases.push({
      key: INTRO_KEY,
      label: "Plan",
      status: current < 0 ? "active" : "done",
      summary: null,
      entries: introEntries,
      todos: introTodos,
    });
  }
  PHASES.forEach((phase, index) => {
    phases.push({
      key: phase.stage,
      label: phase.label,
      status: statusFor(index, current),
      summary: summaryForStage(events, phase.stage),
      entries: entriesFor(phase.stage),
      todos: todos.get(phase.stage) ?? null,
    });
  });
  return phases;
}
