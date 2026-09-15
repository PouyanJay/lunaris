import { afterEach, expect, it, vi } from "vitest";
import { isConceptGraph, prepareCourseGraph } from "./liveGraph";
import { isCorpusGraphReady } from "./liveCorpusGraph";

const digest = "a".repeat(64);
const graph = {
  graphId: "g-course",
  topic: "Patient data",
  version: 1,
  isAcyclic: true,
  topoOrder: ["privacy"],
  nodes: [
    {
      id: "privacy",
      name: "Privacy",
      definition: "Patient privacy",
      requires: [],
      provenance: "compiled",
      aliases: [],
      teachingSpec: { objective: "Explain privacy", misconceptions: [], depth: "applied" },
      masteryCriteria: [{ kind: "explain", statement: "Explain privacy", needsSim: false }],
      assets: [
        {
          assetId: "privacy-lesson",
          kind: "lesson",
          origin: "ingested",
          locator: "lesson:privacy",
          sourceDigest: digest,
          title: "Privacy",
          excerpt: "Patient privacy",
          sourceLabel: "Patient data",
          clip: null,
          verification: {
            runId: "prepare-1",
            verifierVersion: "mapping-verifier-v1",
            sourceDigest: digest,
          },
        },
      ],
    },
  ],
  corpus: {
    courseId: "course-1",
    title: "Patient data",
    digest,
    runId: "prepare-1",
    adapterVersion: "studio-v1",
    status: "verified",
  },
  groundingReport: {
    sourceDigest: digest,
    runId: "prepare-1",
    status: "passed",
    nodes: [
      { nodeId: "privacy", classification: "source", locators: ["lesson:privacy"], rationale: "" },
    ],
    uncoveredLocators: [],
    omittedLocators: [],
    issues: [],
  },
  mappingReport: {
    sourceDigest: digest,
    runId: "prepare-1",
    status: "passed",
    mapperVersion: "mapping-v1",
    verifierVersion: "mapping-verifier-v1",
    mappings: [
      {
        nodeId: "privacy",
        locator: "lesson:privacy",
        status: "approved",
        reason: "verified",
        evidence: ["Patient privacy"],
      },
    ],
    gaps: [],
    issues: [],
  },
};
afterEach(() => vi.unstubAllGlobals());

it("prepares exactly the requested course and validates the returned source", async () => {
  const fetch = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(graph), { status: 201 }),
  );
  vi.stubGlobal("fetch", fetch);
  const prepared = await prepareCourseGraph("https://api.test", "course-1", "Patient data");
  expect(fetch).toHaveBeenCalledOnce();
  expect(JSON.parse(String(fetch.mock.calls[0]![1]?.body))).toEqual({
    topic: "Patient data",
    corpus: { courseId: "course-1" },
  });
  expect(isCorpusGraphReady(prepared)).toBe(true);
  await expect(
    prepareCourseGraph("https://api.test", "wrong-course", "Patient data"),
  ).rejects.toThrow("chosen course");
});

it.each([
  { corpus: { ...graph.corpus, status: "invented" } },
  {
    groundingReport: {
      ...graph.groundingReport,
      nodes: [{ nodeId: "privacy", classification: "source", locators: null }],
    },
  },
  {
    mappingReport: {
      ...graph.mappingReport,
      mappings: [
        { nodeId: "privacy", locator: "lesson:privacy", status: "approved", evidence: null },
      ],
    },
  },
  { nodes: [{ ...graph.nodes[0], assets: [{ kind: "video_clip", clip: { startS: NaN } }] }] },
])("rejects malformed course report fields at the graph boundary", (fields) => {
  expect(isConceptGraph({ ...graph, ...fields })).toBe(false);
});

it("never starts a pending, failed, incomplete or stale source graph", () => {
  expect(isConceptGraph(graph)).toBe(true);
  if (!isConceptGraph(graph)) throw new Error("Invalid fixture");
  expect(isCorpusGraphReady({ ...graph, corpus: { ...graph.corpus, status: "pending" } })).toBe(
    false,
  );
  expect(isCorpusGraphReady({ ...graph, mappingReport: null })).toBe(false);
  expect(
    isCorpusGraphReady({
      ...graph,
      mappingReport: { ...graph.mappingReport, sourceDigest: "b".repeat(64) },
    }),
  ).toBe(false);
  expect(
    isCorpusGraphReady({ ...graph, groundingReport: { ...graph.groundingReport, nodes: [] } }),
  ).toBe(false);
});

it("rejects orphaned source reports and malformed source teaching contracts", () => {
  expect(isConceptGraph({ ...graph, corpus: null })).toBe(false);
  expect(isConceptGraph({ ...graph, nodes: [{ ...graph.nodes[0], masteryCriteria: null }] })).toBe(
    false,
  );
  expect(
    isConceptGraph({ ...graph, nodes: [{ ...graph.nodes[0], teachingSpec: { objective: 1 } }] }),
  ).toBe(false);
});

it.each(["run", "asset", "approval", "verification"])(
  "does not admit inconsistent %s evidence even when status says verified",
  (variant) => {
    const candidate = structuredClone(graph);
    if (variant === "run") candidate.mappingReport.runId = "other-run";
    if (variant === "asset") candidate.nodes[0]!.assets = [];
    if (variant === "approval") candidate.mappingReport.mappings = [];
    if (variant === "verification") candidate.nodes[0]!.assets[0]!.verification.runId = "other-run";
    if (!isConceptGraph(candidate)) throw new Error("Invalid wire fixture");
    expect(isCorpusGraphReady(candidate)).toBe(false);
  },
);
