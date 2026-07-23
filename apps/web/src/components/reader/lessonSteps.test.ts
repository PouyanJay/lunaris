import { describe, expect, it } from "vitest";

import { makeCourse, makeLesson } from "../../test/fixtures";
import { buildLessonSteps, stepIndexForClaim, type LessonStep } from "./lessonSteps";

const PHASES = [
  { key: "activate", label: "Warm-up", cue: "Reconnect with what you already know" },
  { key: "demonstrate", label: "Strategies & worked example", cue: "See the approach" },
  { key: "apply", label: "Practice", cue: "Try it yourself" },
  { key: "integrate", label: "Make it your own", cue: "Transfer it" },
] as const;

function words(count: number, prefix = "w"): string {
  return Array.from({ length: count }, (_, i) => `${prefix}${i}`).join(" ");
}

describe("buildLessonSteps", () => {
  it("assembles the arc in order: intro, phase content, resources, checks, assessment", () => {
    // Arrange — the fixture lesson: expects, four one-paragraph phases, one demonstrate
    // resource, one self-check item; the fixture module's assessment has one item.
    const course = makeCourse();
    const lesson = course.modules[0]!.lessons[0]!;

    // Act
    const steps = buildLessonSteps({
      lesson,
      phases: PHASES,
      assessment: course.modules[0]!.assessment.items,
    });

    // Assert — kinds in reading order.
    expect(steps.map((step) => step.kind)).toEqual([
      "intro",
      "content",
      "content",
      "resources",
      "content",
      "content",
      "check",
      "assessment",
    ]);
    expect(steps.map((step) => step.sectionId)).toEqual([
      "expects",
      "activate",
      "demonstrate",
      "demonstrate",
      "apply",
      "integrate",
      "selfCheck",
      "assessment",
    ]);
  });

  it("packs paragraphs greedily to ~120 words without splitting any block", () => {
    // Arrange — five 60-word paragraphs → 120 + 120 + 60.
    const prose = [
      words(60, "a"),
      words(60, "b"),
      words(60, "c"),
      words(60, "d"),
      words(60, "e"),
    ].join("\n\n");
    const lesson = makeLesson({ expects: [], selfCheck: [] });
    lesson.segments.activate.prose = prose;
    lesson.segments.demonstrate.prose = "";
    lesson.segments.apply.prose = "";
    lesson.segments.integrate.prose = "";
    lesson.segments.demonstrate.resources = [];

    // Act
    const steps = buildLessonSteps({ lesson, phases: PHASES, assessment: [] });

    // Assert
    const chunks = steps.filter((step) => step.kind === "content");
    expect(chunks).toHaveLength(3);
    expect(chunks[0]!.markdown).toContain("a0");
    expect(chunks[0]!.markdown).toContain("b59");
    expect(chunks[2]!.markdown).toContain("e0");
  });

  it("keeps a fenced code block whole even when it contains blank lines", () => {
    // Arrange
    const lesson = makeLesson({ expects: [], selfCheck: [] });
    lesson.segments.activate.prose = `${words(110)}\n\n\`\`\`python\nfirst = 1\n\nsecond = 2\n\`\`\`\n\nafter paragraph`;
    lesson.segments.demonstrate.prose = "";
    lesson.segments.apply.prose = "";
    lesson.segments.integrate.prose = "";
    lesson.segments.demonstrate.resources = [];

    // Act
    const steps = buildLessonSteps({ lesson, phases: PHASES, assessment: [] });

    // Assert — the whole fence (with its interior blank line) lives inside exactly one step.
    const withFence = steps.filter((step) => step.markdown?.includes("```python"));
    expect(withFence).toHaveLength(1);
    expect(withFence[0]!.markdown).toContain("first = 1\n\nsecond = 2");
  });

  it("keeps a ::: directive container whole across its interior blank lines", () => {
    // Arrange
    const lesson = makeLesson({ expects: [], selfCheck: [] });
    lesson.segments.activate.prose = `intro paragraph\n\n:::deeper[More]\nfirst line\n\nsecond line\n:::\n\ntail paragraph`;
    lesson.segments.demonstrate.prose = "";
    lesson.segments.apply.prose = "";
    lesson.segments.integrate.prose = "";
    lesson.segments.demonstrate.resources = [];

    // Act
    const steps = buildLessonSteps({ lesson, phases: PHASES, assessment: [] });

    // Assert
    const withDirective = steps.filter((step) => step.markdown?.includes(":::deeper"));
    expect(withDirective).toHaveLength(1);
    expect(withDirective[0]!.markdown).toContain("first line\n\nsecond line");
    expect(withDirective[0]!.markdown).toContain(":::\n");
  });

  it("returns no steps for a lesson with nothing to teach", () => {
    // Arrange
    const empty = { prose: "", visuals: [], claims: [], resources: [] };
    const lesson = makeLesson({
      segments: { activate: empty, demonstrate: empty, apply: empty, integrate: empty },
      expects: [],
      selfCheck: [],
    });

    // Act / Assert
    expect(buildLessonSteps({ lesson, phases: PHASES, assessment: [] })).toEqual([]);
  });

  it("carries word counts on content steps for the time-left metric", () => {
    // Arrange
    const course = makeCourse();

    // Act
    const steps = buildLessonSteps({
      lesson: course.modules[0]!.lessons[0]!,
      phases: PHASES,
      assessment: [],
    });

    // Assert
    const content = steps.filter((step) => step.kind === "content");
    expect(content.every((step) => step.words > 0)).toBe(true);
  });
});

describe("stepIndexForClaim", () => {
  // A phase that spans two content chunks plus a resources step, framed by other sections — so the
  // returned index is an index into the FULL step list, not the phase.
  const steps: LessonStep[] = [
    { id: "expects:0", sectionId: "expects", sectionLabel: "Expects", kind: "intro", words: 3 },
    {
      id: "demonstrate:0",
      sectionId: "demonstrate",
      sectionLabel: "Strategies",
      kind: "content",
      markdown: "First, the setup. HTTP moves data across the web.",
      words: 9,
    },
    {
      id: "demonstrate:1",
      sectionId: "demonstrate",
      sectionLabel: "Strategies",
      kind: "content",
      markdown: "HTTPS is the secure version of HTTP. It adds a TLS layer.",
      words: 12,
    },
    {
      id: "demonstrate:2",
      sectionId: "demonstrate",
      sectionLabel: "Strategies",
      kind: "resources",
      words: 0,
    },
    { id: "apply:0", sectionId: "apply", sectionLabel: "Practice", kind: "content", markdown: "Try it.", words: 2 },
  ];

  it("targets the content step whose chunk contains the matched sentence", () => {
    expect(stepIndexForClaim(steps, "demonstrate", "HTTPS is the secure version of HTTP.")).toBe(2);
  });

  it("tolerates whitespace and case differences when matching the sentence", () => {
    expect(stepIndexForClaim(steps, "demonstrate", "https is   the SECURE version of http.")).toBe(2);
  });

  it("falls back to the phase's first step when there is no matched sentence", () => {
    expect(stepIndexForClaim(steps, "demonstrate", null)).toBe(1);
  });

  it("falls back to the phase's first step when the sentence isn't found in any chunk", () => {
    expect(stepIndexForClaim(steps, "demonstrate", "An unrelated sentence about cats.")).toBe(1);
  });

  it("returns undefined for a phase with no steps", () => {
    expect(stepIndexForClaim(steps, "integrate", null)).toBeUndefined();
  });
});
