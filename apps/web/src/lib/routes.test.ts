import { describe, expect, it } from "vitest";

import { coursePath, resolveRoute } from "./routes";

describe("resolveRoute", () => {
  it.each([
    ["/", "home"],
    ["/new", "home"],
    ["/settings", "settings"],
    ["/admin", "admin"],
    ["/courses", "library"],
    ["/activity", "activity"],
    ["/bookmarks", "bookmarks"],
    ["/nope", "not-found"],
    ["/courses/c1/bogus", "not-found"],
    ["/courses/c1/map/extra", "not-found"],
  ])("resolves %s to %s", (pathname, kind) => {
    expect(resolveRoute(pathname).kind).toBe(kind);
  });

  it("resolves a course path with the Overview default and explicit views", () => {
    expect(resolveRoute("/courses/c1")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "overview",
    });
    expect(resolveRoute("/courses/c1/overview")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "overview",
    });
    expect(resolveRoute("/courses/c1/lessons")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "lessons",
    });
    expect(resolveRoute("/courses/c1/map")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "map",
    });
  });

  it("keeps the legacy learn spelling resolving to the Lessons view", () => {
    // Pre-P3 bookmarks and shared links spelled the reader segment "learn".
    expect(resolveRoute("/courses/c1/learn")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "lessons",
    });
  });
});

describe("coursePath", () => {
  it("keeps Overview as the bare course URL and views as segments", () => {
    expect(coursePath("c1")).toBe("/courses/c1");
    expect(coursePath("c1", "overview")).toBe("/courses/c1");
    expect(coursePath("c1", "lessons")).toBe("/courses/c1/lessons");
    expect(coursePath("c1", "corpus")).toBe("/courses/c1/corpus");
  });
});
