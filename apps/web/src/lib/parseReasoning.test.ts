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

  it("coalesces a run of small JSON blobs (with noise between) into one group", () => {
    // The flood case: many small judgments separated by stray ```json labels / fragments.
    const a = '{"is_prereq": true, "strength": 0.85, "pair": "a"}';
    const b = '{"is_prereq": false, "strength": 0.15, "pair": "b"}';
    const c = '{"is_prereq": true, "strength": 0.72, "pair": "c"}';
    const segments = parseReasoning(`${a} json ${b} ${c}`);

    expect(segments).toEqual([{ kind: "jsonGroup", sources: [a, b, c], closed: true }]);
  });

  it("coalesces a run of fenced JSON blobs (the real flood shape)", () => {
    // Fenced blobs are lifted at any size; these small ones then coalesce into one closed group.
    const fence = (body: string) => "```json\n" + body + "\n```";
    const segments = parseReasoning(
      `${fence('{"is_prereq": true}')}\n${fence('{"is_prereq": false}')}`,
    );

    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ kind: "jsonGroup", closed: true });
    expect((segments[0] as { sources: string[] }).sources).toHaveLength(2);
  });

  it("keeps a lone small JSON blob as an individual artifact", () => {
    const blob = '{"is_prereq": true, "strength": 0.85, "pair": "x"}';
    const segments = parseReasoning(`Judging the pair now: ${blob} and moving on.`);

    expect(segments).toEqual([
      { kind: "prose", text: "Judging the pair now: " },
      { kind: "json", source: blob, closed: true },
      { kind: "prose", text: " and moving on." },
    ]);
  });

  it("keeps consecutive LARGE blobs individual (only small ones group)", () => {
    // Each blob is well over the small-blob threshold, so they stay worth-their-own-artifact.
    const big = (n: number) => `{"module":${n},"detail":"${"x".repeat(220)}"}`;
    const a = big(1);
    const b = big(2);
    const segments = parseReasoning(`${a} ${b}`);

    expect(segments).toEqual([
      { kind: "json", source: a, closed: true },
      { kind: "prose", text: " " },
      { kind: "json", source: b, closed: true },
    ]);
  });
});
