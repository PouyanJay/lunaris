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
      { kind: "prose", text: "A diagram helps here." },
      { kind: "json", source: '{"type":"flow"}', closed: true },
      { kind: "prose", text: "Done." },
    ]);
  });

  it("lifts a JSON object on its own line as a single artifact", () => {
    const blob = '{"modules":[{"title":"Networking"},{"title":"Crypto"}]}';
    const segments = parseReasoning(`Now designing the curriculum.\n${blob}\nThen verify.`);

    expect(segments).toEqual([
      { kind: "prose", text: "Now designing the curriculum." },
      { kind: "json", source: blob, closed: true },
      { kind: "prose", text: "Then verify." },
    ]);
  });

  it("keeps a multi-line pretty-printed object together (lone closing brace included)", () => {
    const blob = '{\n  "modules": ["Networking", "Crypto"]\n}';
    const segments = parseReasoning(`Here is the curriculum:\n${blob}\nLet me verify.`);

    expect(segments).toEqual([
      { kind: "prose", text: "Here is the curriculum:" },
      { kind: "json", source: blob, closed: true },
      { kind: "prose", text: "Let me verify." },
    ]);
  });

  it("does not start a region on a quoted prose line", () => {
    const text = '"Requirements are clear."\nNow let me proceed.';
    expect(parseReasoning(text)).toEqual([{ kind: "prose", text }]);
  });

  it("marks a still-opening object as a streaming artifact", () => {
    const segments = parseReasoning('Judging:\n{"is_prereq": true, "strength":');

    expect(segments).toEqual([
      { kind: "prose", text: "Judging:" },
      { kind: "json", source: '{"is_prereq": true, "strength":', closed: false },
    ]);
  });

  it("collapses a flood of small objects into ONE group, even with ragged fences/labels/fragments", () => {
    // The real shape: ```json labels, bare `json` lines, and a leftover fragment between objects.
    const text = [
      "Let me judge the prerequisite pairs.",
      "```json",
      '{"is_prereq": false, "strength": 0.95}',
      "```",
      "json",
      '{"is_prereq": true, "strength": 0.85}',
      '{"is_prereq": false, "strength": 0.15}',
      '": true, "strength": 0.85}', // a stray fragment — must be absorbed, not shown as prose
    ].join("\n");

    const segments = parseReasoning(text);

    // One prose line, then ONE group of the three clean objects (the fragment is dropped).
    expect(segments).toEqual([
      { kind: "prose", text: "Let me judge the prerequisite pairs." },
      {
        kind: "jsonGroup",
        sources: [
          '{"is_prereq": false, "strength": 0.95}',
          '{"is_prereq": true, "strength": 0.85}',
          '{"is_prereq": false, "strength": 0.15}',
        ],
        closed: true,
      },
    ]);
  });

  it("treats a flood that ends mid-object as a still-streaming group", () => {
    const text = [
      '{"is_prereq": true, "strength": 0.85}',
      '{"is_prereq": false, "strength": 0.15}',
      '{"is_prereq": true, "strength":', // streaming tail
    ].join("\n");

    const segments = parseReasoning(text);

    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ kind: "jsonGroup", closed: false });
    expect((segments[0] as { sources: string[] }).sources).toHaveLength(3);
  });

  it("leaves a short inline bracket in the prose (a long sentence, not a JSON line)", () => {
    const text = "Replace {n} with the count and keep going.";
    expect(parseReasoning(text)).toEqual([{ kind: "prose", text }]);
  });

  it("does not miscount braces inside JSON string values", () => {
    const blob = '{"label":"a }] tricky string","ok":true,"note":"another { brace"}';
    const segments = parseReasoning(`Here:\n${blob}\nend`);

    expect(segments).toEqual([
      { kind: "prose", text: "Here:" },
      { kind: "json", source: blob, closed: true },
      { kind: "prose", text: "end" },
    ]);
  });
});
