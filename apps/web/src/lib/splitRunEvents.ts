import type { AgentEvent, ProgressEvent, RunEvent } from "../types/course";

/** A persisted build log split back into the two streams the BuildTimeline renders. */
export interface ReplayTrace {
  events: ProgressEvent[];
  agentEvents: AgentEvent[];
}

/**
 * Split a run's persisted event log (one ordered stream, each row tagged `progress` or `agent`) back
 * into the two arrays `BuildTimeline` consumes. Rows arrive ordered by `seq`, so temporal order is
 * preserved without sorting; an unrecognised `kind` is skipped so a future event type never breaks
 * replay. `BuildTimeline` derives phase durations from wall-clock `stageTimes`, which a static replay
 * has no source for, so none is produced here.
 */
export function splitRunEvents(rows: RunEvent[]): ReplayTrace {
  const events: ProgressEvent[] = [];
  const agentEvents: AgentEvent[] = [];
  for (const row of rows) {
    if (row.kind === "progress") events.push(row.payload as ProgressEvent);
    else if (row.kind === "agent") agentEvents.push(row.payload as AgentEvent);
  }
  return { events, agentEvents };
}
