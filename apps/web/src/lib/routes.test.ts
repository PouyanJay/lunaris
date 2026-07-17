import { describe, expect, it } from "vitest";

import { coursePath, lessonPath, resolveRoute, settingsPath } from "./routes";

describe("resolveRoute", () => {
  it.each([
    ["/", "home"],
    ["/new", "composer"],
    ["/settings", "settings"],
    ["/settings/llm", "settings"],
    ["/settings/bogus", "not-found"],
    ["/account", "account"],
    ["/account/admin-portal", "account"],
    ["/account/bogus", "not-found"],
    ["/profile", "account"],
    ["/admin", "account"],
    ["/courses", "library"],
    ["/activity", "activity"],
    ["/bookmarks", "bookmarks"],
    ["/nope", "not-found"],
    ["/courses/c1/bogus", "not-found"],
    ["/courses/c1/map/extra", "not-found"],
  ])("resolves %s to %s", (pathname, kind) => {
    expect(resolveRoute(pathname).kind).toBe(kind);
  });

  it("defaults bare /settings to the System section and deep-links a named section", () => {
    expect(resolveRoute("/settings")).toEqual({ kind: "settings", section: "system" });
    expect(resolveRoute("/settings/llm")).toEqual({ kind: "settings", section: "llm" });
    expect(resolveRoute("/settings/sources")).toEqual({ kind: "settings", section: "sources" });
  });

  it("treats an unknown settings section as not-found (never a silent default)", () => {
    expect(resolveRoute("/settings/nope").kind).toBe("not-found");
  });

  it("resolves the Account sections, the legacy /profile, and /admin folding into Admin Portal", () => {
    expect(resolveRoute("/account")).toEqual({ kind: "account", section: "user-account" });
    expect(resolveRoute("/profile")).toEqual({ kind: "account", section: "user-account" });
    expect(resolveRoute("/account/admin-portal")).toEqual({
      kind: "account",
      section: "admin-portal",
    });
    // /admin is folded into the Account surface's Admin Portal section.
    expect(resolveRoute("/admin")).toEqual({ kind: "account", section: "admin-portal" });
    expect(resolveRoute("/account/nope").kind).toBe("not-found");
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

  it("resolves a lesson deep-link under the Lessons view only", () => {
    // The selected lesson is a URL segment (P6) — but only the reader has one; a trailing
    // segment under any other view stays not-found.
    expect(resolveRoute("/courses/c1/lessons/l2")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "lessons",
      lessonId: "l2",
    });
    expect(resolveRoute("/courses/c1/learn/l2")).toEqual({
      kind: "course",
      courseId: "c1",
      view: "lessons",
      lessonId: "l2",
    });
    expect(resolveRoute("/courses/c1/map/l2").kind).toBe("not-found");
    expect(resolveRoute("/courses/c1/overview/l2").kind).toBe("not-found");
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

describe("lessonPath", () => {
  it("addresses a lesson inside the reader", () => {
    expect(lessonPath("c1", "l2")).toBe("/courses/c1/lessons/l2");
  });
});

describe("settingsPath", () => {
  it("builds the deep-link URL for a section", () => {
    expect(settingsPath("system")).toBe("/settings/system");
    expect(settingsPath("voice")).toBe("/settings/voice");
  });
});
