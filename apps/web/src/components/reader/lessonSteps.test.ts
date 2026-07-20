import { describe, expect, it } from "vitest";

import { makeCourse, makeLesson } from "../../test/fixtures";
import { buildLessonSteps } from "./lessonSteps";

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
