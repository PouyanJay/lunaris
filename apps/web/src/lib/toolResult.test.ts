import { describe, expect, it } from "vitest";

import { parseToolResult } from "./toolResult";

describe("parseToolResult", () => {
  it("parses an intact JSON object result into a record", () => {
    expect(parseToolResult('{"status":"published","moduleCount":4}')).toEqual({
      status: "published",
      moduleCount: 4,
    });
  });

  it("returns null for a result the tap truncated mid-JSON (the big graph payload)", () => {
    // The graph result is ~3.7KB and the tap clips it at 600 chars → invalid JSON.
    const truncated = '{"nodes": [{"id": "kc0", "label": "Concept 0", "definition": "a long';
    expect(parseToolResult(truncated)).toBeNull();
  });

  it("returns null for a plain non-JSON summary string", () => {
    expect(parseToolResult("21 concepts extracted")).toBeNull();
    expect(parseToolResult("ok")).toBeNull();
    expect(parseToolResult("done")).toBeNull();
  });

  it("returns null for a still-running call (null), an empty, or a whitespace-only result", () => {
    expect(parseToolResult(null)).toBeNull();
    expect(parseToolResult("")).toBeNull();
    expect(parseToolResult("   ")).toBeNull();
  });

  it("returns null for non-object JSON (arrays, scalars) — no tool returns those", () => {
    expect(parseToolResult("[1,2,3]")).toBeNull();
    expect(parseToolResult("42")).toBeNull();
    expect(parseToolResult('"a string"')).toBeNull();
    expect(parseToolResult("null")).toBeNull();
  });
});
