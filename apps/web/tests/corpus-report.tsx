import { createRoot } from "react-dom/client";
import {
  CorpusPreparationReport,
  type CorpusReviewGraph,
} from "../src/components/live/CorpusPreparationReport";
import "../src/index.css";

const digest = "a".repeat(64);
const nodeDefaults = {
  definition: "Course concept",
  provenance: "compiled" as const,
  aliases: [],
  teachingSpec: { objective: "Explain the concept", misconceptions: [], depth: "applied" as const },
  masteryCriteria: [{ kind: "explain" as const, statement: "Explain it", needsSim: false }],
};
const verifiedAsset = {
  assetId: "lesson-privacy",
  locator: "quiz:privacy",
  title: "Patient privacy",
  kind: "lesson" as const,
  origin: "ingested" as const,
  sourceDigest: digest,
  sourceLabel: "Course source",
  excerpt: "Patient privacy",
  clip: null,
  verification: { sourceDigest: digest, runId: "review-1", verifierVersion: "verify-v1" },
};
const graph: CorpusReviewGraph = {
  graphId: "review-graph",
  topic: "Patient data",
  version: 1,
  isAcyclic: true,
  topoOrder: ["records", "privacy"],
  corpus: {
    courseId: "course-1",
    runId: "review-1",
    adapterVersion: "studio-v1",
    title: "Understanding patient data",
    digest,
    status: "verified",
  },
  nodes: [
    {
      ...nodeDefaults,
      id: "privacy",
      name: "Patient privacy",
      requires: ["records"],
      assets: [
        { ...verifiedAsset, title: "Who may access a patient record?", kind: "lesson" as const },
      ],
    },
    { ...nodeDefaults, id: "records", name: "Electronic health records", requires: [] },
  ],
  groundingReport: {
    runId: "review-1",
    status: "passed",
    sourceDigest: digest,
    nodes: [
      { nodeId: "privacy", classification: "source", locators: ["lesson:privacy"], rationale: "" },
      {
        nodeId: "records",
        classification: "prerequisite",
        locators: [],
        rationale: "Recognizing an electronic record helps explain how patient privacy applies.",
      },
    ],
    uncoveredLocators: [],
    omittedLocators: [],
    issues: [],
  },
  mappingReport: {
    status: "passed",
    sourceDigest: digest,
    runId: "review-1",
    mapperVersion: "mapping-v1",
    verifierVersion: "verify-v1",
    mappings: [
      {
        nodeId: "privacy",
        locator: "quiz:privacy",
        status: "approved",
        reason: "verified",
        evidence: ["Fixture-only evidence"],
      },
      {
        nodeId: "records",
        locator: "video:records",
        status: "rejected",
        reason: "verifier_rejected",
        evidence: [],
      },
    ],
    gaps: [{ nodeId: "records", reason: "video_unavailable" }],
    issues: [],
  },
};
const previous: CorpusReviewGraph = {
  ...graph,
  corpus: { ...graph.corpus, digest: "b".repeat(64) },
  nodes: [{ ...nodeDefaults, id: "privacy", name: "Patient privacy", requires: [] }],
  mappingReport: { ...graph.mappingReport!, mappings: [] },
};
/** Read-only browser fixture; no source fetches or learning mutations. */
export function ReportFixture() {
  return (
    <main>
      <h1>Review your course preparation</h1>
      <CorpusPreparationReport graph={graph} previousGraph={previous} />
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<ReportFixture />);
