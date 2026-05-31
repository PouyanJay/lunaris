import type { AgentEvent, AgentTodo } from "../types/course";

/** A rendered transcript entry: a block of reasoning, or a tool call paired with its result. */
export type TranscriptEntry =
  | { kind: "reasoning"; key: string; text: string }
  | {
      kind: "tool";
      key: string;
      tool: string;
      args: Record<string, unknown> | null;
      result: string | null;
    };

/**
 * Fold the raw agent-event stream into ordered render entries: reasoning blocks and tool cards,
 * each tool_call paired with the tool_result that follows it (matched by tool name, first card
 * still awaiting a result). `todo` events are excluded — the live plan renders separately from
 * {@link latestTodos}. Empty reasoning chunks are dropped so a stray blank beat adds no noise.
 */
export function groupAgentEvents(events: AgentEvent[]): TranscriptEntry[] {
  const entries: TranscriptEntry[] = [];

  for (const event of events) {
    if (event.kind === "reasoning") {
      if (event.text && event.text.trim()) {
        entries.push({ kind: "reasoning", key: `r-${event.sequence}`, text: event.text });
      }
    } else if (event.kind === "tool_call") {
      entries.push({
        kind: "tool",
        key: `t-${event.sequence}`,
        tool: event.tool ?? "tool",
        args: event.toolArgs,
        result: null,
      });
    } else if (event.kind === "tool_result") {
      const tool = event.tool ?? "tool";
      const pending = findPendingToolCard(entries, tool);
      if (pending) {
        pending.result = event.result ?? "";
      } else {
        // A result with no preceding call (e.g. a reconnect mid-stream) still gets shown.
        entries.push({
          kind: "tool",
          key: `t-${event.sequence}`,
          tool,
          args: null,
          result: event.result ?? "",
        });
      }
    }
  }

  return entries;
}

/** The most recent tool card for `tool` still awaiting its result, scanning newest-first. */
function findPendingToolCard(
  entries: TranscriptEntry[],
  tool: string,
): Extract<TranscriptEntry, { kind: "tool" }> | undefined {
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    const entry = entries[i];
    if (entry && entry.kind === "tool" && entry.tool === tool && entry.result === null) {
      return entry;
    }
  }
  return undefined;
}

/** The current plan: the todos from the latest `todo` event, or null if the agent hasn't planned. */
export function latestTodos(events: AgentEvent[]): AgentTodo[] | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event && event.kind === "todo" && event.todos) return event.todos;
  }
  return null;
}
