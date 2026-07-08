import { describe, expect, it } from "vitest";

import { courseEntry, indexCourse, searchEntries } from "./searchIndex";
import type { SearchEntry } from "./searchIndex";
import { makeCourse, makeCourseSummary } from "../test/fixtures";

function entry(label: string, kind: SearchEntry["kind"] = "concept"): SearchEntry {
  return { kind, courseId: "c1", courseTitle: "Course", targetId: label, label };
}

describe("indexCourse", () => {
  it("indexes lessons under the reader's numbering and concepts under their KC labels", () => {
    const entries = indexCourse(makeCourse());

    const lessons = entries.filter((item) => item.kind === "lesson");
    const concepts = entries.filter((item) => item.kind === "concept");
    expect(lessons[0]?.label).toMatch(/^Lesson 1 · /);
    expect(concepts.map((item) => item.label)).toContain("Comparison");
  });

  it("builds a course row straight from a library summary", () => {
    const summary = makeCourseSummary({ id: "c-9", topic: "How HTTPS works" });

    expect(courseEntry(summary)).toMatchObject({
      kind: "course",
      courseId: "c-9",
      targetId: "c-9",
      label: "How HTTPS works",
    });
  });
});

describe("searchEntries", () => {
  it("ranks prefix over word-start over substring", () => {
    const entries = [entry("gradient descent"), entry("descent"), entry("condescending")];

    const { concepts } = searchEntries(entries, "descen");

    expect(concepts.map((item) => item.label)).toEqual([
      "descent",
      "gradient descent",
      "condescending",
    ]);
  });

  it("drops non-matches and caps each group", () => {
    const many = Array.from({ length: 9 }, (_, i) => entry(`tls handshake ${i}`));

    const { concepts } = searchEntries([...many, entry("unrelated")], "tls");

    expect(concepts).toHaveLength(5);
    expect(concepts.every((item) => item.label.startsWith("tls"))).toBe(true);
  });

  it("matches case-insensitively", () => {
    const { concepts } = searchEntries([entry("Asymmetric Encryption")], "aSYMMETRIC");

    expect(concepts).toHaveLength(1);
  });

  it("offers a browsable course list for the empty query, never fake matches", () => {
    const results = searchEntries(
      [entry("Course A", "course"), entry("Lesson 1 · X", "lesson")],
      "  ",
    );

    expect(results.courses).toHaveLength(1);
    expect(results.lessons).toHaveLength(0);
  });
});
