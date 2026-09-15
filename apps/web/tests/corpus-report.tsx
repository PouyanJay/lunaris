import { createRoot } from "react-dom/client";
import {
  CorpusPreparationReport,
  type CorpusReviewGraph,
} from "../src/components/live/CorpusPreparationReport";
import "../src/index.css";

const digest = "a".repeat(64);
const graph: CorpusReviewGraph = {
  corpus: { title: "Understanding patient data", digest, status: "verified" },
  nodes: [
    {
      id: "privacy",
      name: "Patient privacy",
      requires: ["records"],
      assets: [
        { locator: "quiz:privacy", title: "Who may access a patient record?", kind: "assessment" },
      ],
    },
    { id: "records", name: "Electronic health records", requires: [] },
  ],
  groundingReport: {
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
    runId: "fixture-review",
    mapperVersion: "mapping-v1",
    verifierVersion: "mapping-verifier-v1",
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
  nodes: [{ id: "privacy", name: "Patient privacy", requires: [] }],
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
