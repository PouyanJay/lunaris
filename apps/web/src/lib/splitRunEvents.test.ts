import { describe, expect, it } from "vitest";

import { makeAgentEvent, makeProgressEvent, makeRunEvent } from "../test/fixtures";
import type { RunEvent } from "../types/course";
import { splitRunEvents } from "./splitRunEvents";

describe("splitRunEvents", () => {
  it("splits an ordered log into the two timeline streams, preserving order", () => {
    const rows = [
      makeRunEvent(0, makeProgressEvent("run_started", 0)),
      makeRunEvent(1, makeAgentEvent("reasoning", 0, { text: "Planning…" })),
      makeRunEvent(2, makeProgressEvent("concepts_extracted", 1, { label: "21 concepts" })),
      makeRunEvent(3, makeAgentEvent("tool_call", 1, { tool: "extract_concepts" })),
    ];

    const { events, agentEvents } = splitRunEvents(rows);

    expect(events.map((e) => e.stage)).toEqual(["run_started", "concepts_extracted"]);
    expect(agentEvents.map((e) => e.kind)).toEqual(["reasoning", "tool_call"]);
    expect(events[1]?.label).toBe("21 concepts");
  });

  it("returns empty streams for an empty log (a course with no build record)", () => {
    expect(splitRunEvents([])).toEqual({ events: [], agentEvents: [] });
  });

  it("skips an unrecognised kind so a future event type never breaks replay", () => {
    const rows = [
      makeRunEvent(0, makeProgressEvent("run_started", 0)),
      { runId: "r", courseId: "c", seq: 1, kind: "grounding", payload: {} } as unknown as RunEvent,
    ];

    const { events, agentEvents } = splitRunEvents(rows);

    expect(events).toHaveLength(1);
    expect(agentEvents).toHaveLength(0);
  });
});
