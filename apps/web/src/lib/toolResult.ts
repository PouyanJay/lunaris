/**
 * Parse a tool-result summary string into a structured record when it is intact JSON.
 *
 * The harness serialises a tool's return value with `json.dumps`, and the event tap clips the
 * string at 600 chars before streaming it — so large results (e.g. the prerequisite graph, ~3.7KB)
 * arrive truncated and unparseable. Returns the object on a clean parse, or `null` for a truncated
 * payload, a plain summary string ("ok", "21 concepts"), a non-object JSON value, or an absent
 * result. Callers fall back to the (full, untruncated) tool call args or the phase summary.
 */
export function parseToolResult(result: string | null): Record<string, unknown> | null {
  if (!result) return null;
  try {
    const parsed: unknown = JSON.parse(result);
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}
