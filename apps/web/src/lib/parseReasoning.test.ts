import { describe, expect, it } from "vitest";

import { parseReasoning } from "./parseReasoning";

describe("parseReasoning", () => {
  it("returns a single prose segment when there is no JSON", () => {
    expect(parseReasoning("Now I'll order the prerequisites.")).toEqual([
      { kind: "prose", text: "Now I'll order the prerequisites." },
    ]);
  });

  it("lifts a fenced code block out of the surrounding prose", () => {
    const segments = parseReasoning('A diagram helps here.\n```json\n{"type":"flow"}\n```\nDone.');

    expect(segments).toEqual([
      { kind: "prose", text: "A diagram helps here.\n" },
      { kind: "json", source: '{"type":"flow"}\n', closed: true },
      { kind: "prose", text: "\nDone." },
    ]);
  });

  it("marks an unterminated fenced block as still streaming", () => {
    const segments = parseReasoning('Designing it:\n```json\n{"modules":[');

    expect(segments).toEqual([
      { kind: "prose", text: "Designing it:\n" },
      { kind: "json", source: '{"modules":[', closed: false },
    ]);
  });

  it("lifts a large raw (unfenced) JSON object out of prose", () => {
    const blob = '{"modules":[{"title":"Networking"},{"title":"Crypto"},{"title":"Trust"}]}';
    const segments = parseReasoning(`Now designing the curriculum. ${blob} Then verify.`);

    expect(segments).toEqual([
      { kind: "prose", text: "Now designing the curriculum. " },
      { kind: "json", source: blob, closed: true },
      { kind: "prose", text: " Then verify." },
    ]);
  });

  it("lifts a trailing still-streaming raw JSON blob", () => {
    const segments = parseReasoning('Ordering them now: {"is_prereq": true, "strength": 0.85');

    expect(segments).toEqual([
      { kind: "prose", text: "Ordering them now: " },
      { kind: "json", source: '{"is_prereq": true, "strength": 0.85', closed: false },
    ]);
  });

  it("leaves short inline brackets in the prose", () => {
    // A small `{n}`-style placeholder is not JSON-ish/large enough to lift.
    const text = "Replace {n} with the count and keep going.";
    expect(parseReasoning(text)).toEqual([{ kind: "prose", text }]);
  });

  it("does not miscount braces that appear inside JSON string values", () => {
    const blob = '{"label":"a }] tricky string","ok":true,"note":"another { brace"}';
    const segments = parseReasoning(`Here: ${blob} end`);

    expect(segments).toEqual([
      { kind: "prose", text: "Here: " },
      { kind: "json", source: blob, closed: true },
      { kind: "prose", text: " end" },
    ]);
  });

  it("handles multiple large JSON blobs in one beat", () => {
    const a = '{"is_prereq": true, "strength": 0.85, "from": "tcp", "to": "tls"}';
    const b = '{"is_prereq": false, "strength": 0.15, "from": "tls", "to": "dns"}';
    const segments = parseReasoning(`${a} then ${b}`);

    expect(segments).toEqual([
      { kind: "json", source: a, closed: true },
      { kind: "prose", text: " then " },
      { kind: "json", source: b, closed: true },
    ]);
  });
});
