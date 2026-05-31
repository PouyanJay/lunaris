import { describe, expect, it } from "vitest";

import { makeAgentEvent } from "../test/fixtures";
import { groupAgentEvents, latestTodos } from "./groupAgentEvents";

describe("groupAgentEvents", () => {
  it("pairs a tool_result with its preceding tool_call", () => {
    const events = [
      makeAgentEvent("tool_call", 0, { tool: "extract_concepts", toolArgs: { topic: "graphs" } }),
      makeAgentEvent("tool_result", 1, { tool: "extract_concepts", result: "16 concepts" }),
    ];

    const entries = groupAgentEvents(events);

    expect(entries).toEqual([
      {
        kind: "tool",
        key: "t-0",
        tool: "extract_concepts",
        args: { topic: "graphs" },
        result: "16 concepts",
      },
    ]);
  });

  it("leaves an in-flight call's result null until its result arrives", () => {
    const entries = groupAgentEvents([makeAgentEvent("tool_call", 0, { tool: "verify_claims" })]);

    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ kind: "tool", tool: "verify_claims", result: null });
  });

  it("keeps reasoning blocks in order and drops empty ones", () => {
    const events = [
      makeAgentEvent("reasoning", 0, { text: "First, map the prerequisites." }),
      makeAgentEvent("reasoning", 1, { text: "   " }),
      makeAgentEvent("tool_call", 2, { tool: "design_curriculum" }),
      makeAgentEvent("reasoning", 3, { text: "Now author the lessons." }),
    ];

    const entries = groupAgentEvents(events);

    expect(entries.map((e) => e.kind)).toEqual(["reasoning", "tool", "reasoning"]);
    expect(entries[0]).toMatchObject({ text: "First, map the prerequisites." });
  });

  it("pairs the most recent pending call when a tool is called twice", () => {
    const events = [
      makeAgentEvent("tool_call", 0, { tool: "verify_claims" }),
      makeAgentEvent("tool_call", 1, { tool: "verify_claims" }),
      makeAgentEvent("tool_result", 2, { tool: "verify_claims", result: "second result" }),
    ];

    const entries = groupAgentEvents(events);

    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({ kind: "tool", result: null }); // first call still pending
    expect(entries[1]).toMatchObject({ kind: "tool", result: "second result" });
  });

  it("renders a tool_result with no matching call as a standalone entry (reconnect)", () => {
    const entries = groupAgentEvents([
      makeAgentEvent("tool_result", 5, { tool: "verify_claims", result: "3 claims" }),
    ]);

    expect(entries).toEqual([
      { kind: "tool", key: "t-5", tool: "verify_claims", args: null, result: "3 claims" },
    ]);
  });

  it("excludes todo events from the entry feed", () => {
    const entries = groupAgentEvents([
      makeAgentEvent("todo", 0, { todos: [{ content: "plan", status: "pending" }] }),
    ]);

    expect(entries).toEqual([]);
  });
});

describe("latestTodos", () => {
  it("returns the most recent todo list", () => {
    const events = [
      makeAgentEvent("todo", 0, { todos: [{ content: "extract", status: "in_progress" }] }),
      makeAgentEvent("todo", 1, {
        todos: [
          { content: "extract", status: "completed" },
          { content: "graph", status: "in_progress" },
        ],
      }),
    ];

    expect(latestTodos(events)).toEqual([
      { content: "extract", status: "completed" },
      { content: "graph", status: "in_progress" },
    ]);
  });

  it("returns null when the agent hasn't planned yet", () => {
    expect(latestTodos([makeAgentEvent("reasoning", 0, { text: "hi" })])).toBeNull();
  });
});
