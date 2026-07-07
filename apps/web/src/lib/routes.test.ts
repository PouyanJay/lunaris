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

  it("resolves a course path with the Learn default and explicit views", () => {
    expect(resolveRoute("/courses/c1")).toEqual({ kind: "course", courseId: "c1", view: "learn" });
    expect(resolveRoute("/courses/c1/map")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "map",
    });
  });
});

describe("coursePath", () => {
  it("keeps Learn as the bare course URL and views as segments", () => {
    expect(coursePath("c1")).toBe("/courses/c1");
    expect(coursePath("c1", "learn")).toBe("/courses/c1");
    expect(coursePath("c1", "corpus")).toBe("/courses/c1/corpus");
  });
});
