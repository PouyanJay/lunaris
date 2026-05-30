import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse } from "../test/fixtures";
import {
  CourseLoadError,
  generateCourse,
  loadCourse,
  parseCourse,
  resolveCourse,
} from "./loadCourse";

describe("parseCourse", () => {
  it("accepts a well-formed course payload", () => {
    const course = makeCourse();
    const parsed = parseCourse(course);
    expect(parsed).toEqual(course);
    // Falsifiable against a no-op parser: the graph really came through.
    expect(parsed.graph.nodes).toHaveLength(3);
  });

  it("rejects a non-object payload", () => {
    expect(() => parseCourse(null)).toThrow(CourseLoadError);
    expect(() => parseCourse("nope")).toThrow(CourseLoadError);
  });

  it("rejects a payload with no prerequisite graph", () => {
    expect(() => parseCourse({ id: "x", topic: "t" })).toThrow(/prerequisite graph/i);
  });

  it("rejects a node missing an id or label", () => {
    const bad = makeCourse();
    // @ts-expect-error — intentionally malformed for the test
    bad.graph.nodes[0] = { id: "comparison" };
    expect(() => parseCourse(bad)).toThrow(/knowledge component/i);
  });

  it("rejects an edge missing its endpoints", () => {
    const bad = makeCourse();
    // @ts-expect-error — intentionally malformed for the test
    bad.graph.edges[0] = { from: "comparison" };
    expect(() => parseCourse(bad)).toThrow(/prerequisite edge/i);
  });
});

describe("loadCourse", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("fetches and parses a course from the given url", async () => {
    const course = makeCourse();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => course }));

    await expect(loadCourse("/course.json")).resolves.toEqual(course);
  });

  it("surfaces an HTTP error as a CourseLoadError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    await expect(loadCourse()).rejects.toBeInstanceOf(CourseLoadError);
    await expect(loadCourse()).rejects.toThrow(/HTTP 503/);
  });

  it("surfaces a network failure as a CourseLoadError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(loadCourse()).rejects.toBeInstanceOf(CourseLoadError);
  });

  it("surfaces invalid JSON as a CourseLoadError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => {
          throw new SyntaxError("bad json");
        },
      }),
    );

    await expect(loadCourse()).rejects.toThrow(/not valid JSON/i);
  });
});

describe("generateCourse", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs the topic to the API and parses the generated course", async () => {
    const course = makeCourse();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => course });
    vi.stubGlobal("fetch", fetchMock);

    await expect(generateCourse("http://api.test", "binary search")).resolves.toEqual(course);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test/api/courses");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ topic: "binary search" });
  });

  it("surfaces a generation HTTP error as a CourseLoadError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await expect(generateCourse("http://api.test", "x")).rejects.toThrow(/HTTP 500/);
  });
});

describe("resolveCourse", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("uses the static seed when VITE_API_URL is unset", async () => {
    const course = makeCourse();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => course });
    vi.stubGlobal("fetch", fetchMock);

    await resolveCourse();

    expect(fetchMock.mock.calls[0]![0]).toBe("/sample-course.json");
  });

  it("generates via the API when VITE_API_URL is set", async () => {
    vi.stubEnv("VITE_API_URL", "http://api.test");
    const course = makeCourse();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => course });
    vi.stubGlobal("fetch", fetchMock);

    await resolveCourse();

    expect(fetchMock.mock.calls[0]![0]).toBe("http://api.test/api/courses");
    expect(fetchMock.mock.calls[0]![1].method).toBe("POST");
  });
});
