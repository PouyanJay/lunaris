import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CorpusPreparationReport, type CorpusReviewGraph } from "./CorpusPreparationReport";

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
      assets: [verifiedAsset],
    },
    { ...nodeDefaults, id: "records", name: "Electronic records", requires: [] },
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
        rationale: "Records are needed to explain privacy.",
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
    mapperVersion: "map-v1",
    verifierVersion: "verify-v1",
    mappings: [
      {
        nodeId: "privacy",
        locator: "quiz:privacy",
        status: "approved",
        reason: "verified",
        evidence: ["private evidence should not render"],
      },
    ],
    gaps: [],
    issues: [],
  },
};

it("leads with source and readable concepts, prerequisites and approved support", () => {
  render(<CorpusPreparationReport graph={graph} />);
  expect(screen.getByRole("status")).toHaveTextContent("Ready for review");
  expect(screen.getByRole("heading", { name: "Understanding patient data" })).toBeVisible();
  const privacy = screen.getByRole("region", { name: "Patient privacy" });
  expect(within(privacy).getByText("Supported by this course")).toBeVisible();
  expect(within(privacy).getByText("Learn first: Electronic records")).toBeVisible();
  expect(within(privacy).getByText("1 approved material")).toBeVisible();
  expect(screen.getByText("Additional prerequisite")).toBeVisible();
  expect(screen.queryByText("private evidence should not render")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Start/ })).not.toBeInTheDocument();
});

it("keeps pending and mismatched-source results from appearing ready", () => {
  const { rerender } = render(
    <CorpusPreparationReport graph={{ ...graph, mappingReport: null }} />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Awaiting verification");
  rerender(
    <CorpusPreparationReport
      graph={{ ...graph, mappingReport: { ...graph.mappingReport!, sourceDigest: "b".repeat(64) } }}
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Needs review");
  expect(screen.getByText(/different version of the course/)).toBeVisible();
});

it("explains unverified concepts, rejected material and coverage gaps without raw evidence", () => {
  render(
    <CorpusPreparationReport
      graph={{
        ...graph,
        groundingReport: {
          ...graph.groundingReport!,
          status: "failed",
          nodes: [
            { nodeId: "privacy", classification: "unsupported", locators: [], rationale: "" },
          ],
          uncoveredLocators: ["lesson:other"],
          issues: ["unsupported_nodes"],
        },
        mappingReport: {
          ...graph.mappingReport!,
          status: "failed",
          mappings: [
            {
              nodeId: "privacy",
              locator: "quiz:privacy",
              status: "rejected",
              reason: "verifier_rejected",
              evidence: [],
            },
          ],
          gaps: [{ nodeId: "records", reason: "node_without_material" }],
          issues: [],
        },
      }}
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Needs review");
  expect(screen.getAllByText("Unverified concept")).toHaveLength(2);
  expect(screen.getByText("Excluded material: Does not support this concept.")).toBeVisible();
  expect(
    screen.getByText("Electronic records: No supporting materials are available."),
  ).toBeVisible();
  expect(screen.getByText("1 course section is not covered.")).toBeVisible();
});

it("shows meaningful reimport changes including renamed and removed concepts", () => {
  const previous = {
    ...graph,
    corpus: { ...graph.corpus, digest: "b".repeat(64) },
    nodes: [
      { ...nodeDefaults, id: "privacy", name: "Old title", requires: [] },
      { ...nodeDefaults, id: "old", name: "Legacy topic", requires: [] },
    ],
    mappingReport: { ...graph.mappingReport!, mappings: [] },
  };
  render(<CorpusPreparationReport graph={graph} previousGraph={previous} />);
  const changes = screen.getByRole("region", { name: "Changes since the previous preparation" });
  expect(within(changes).getByText("The course content has changed.")).toBeVisible();
  expect(within(changes).getByText("Added: Electronic records")).toBeVisible();
  expect(within(changes).getByText("Removed: Legacy topic")).toBeVisible();
  expect(within(changes).getByText("Updated: Patient privacy")).toBeVisible();
  expect(
    within(changes).getByText("Supporting materials changed for Patient privacy."),
  ).toBeVisible();
});

it("offers actionable loading, empty and error states", () => {
  const retry = vi.fn();
  const { rerender } = render(<CorpusPreparationReport graph={null} loading />);
  expect(screen.getByRole("status")).toHaveTextContent("Preparing course…");
  rerender(<CorpusPreparationReport graph={null} />);
  expect(
    screen.getByText("Choose a course and prepare it to review its learning plan."),
  ).toBeVisible();
  rerender(<CorpusPreparationReport graph={null} error="Service unavailable" onRetry={retry} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Could not load the preparation report.");
  fireEvent.click(screen.getByRole("button", { name: "Retry report" }));
  expect(retry).toHaveBeenCalledOnce();
});

it("does not count approvals from a different source version", () => {
  render(
    <CorpusPreparationReport
      graph={{ ...graph, mappingReport: { ...graph.mappingReport!, sourceDigest: "b".repeat(64) } }}
    />,
  );
  expect(screen.queryByText("1 approved material")).not.toBeInTheDocument();
  expect(screen.getAllByText("Materials await current source verification.")).toHaveLength(2);
});

it("flags changed concept support during reimport review", () => {
  const previous = {
    ...graph,
    groundingReport: {
      ...graph.groundingReport!,
      nodes: graph.groundingReport!.nodes.map((node) => ({
        ...node,
        classification: "unsupported" as const,
      })),
    },
  };
  render(<CorpusPreparationReport graph={graph} previousGraph={previous} />);
  const changes = screen.getByRole("region", { name: "Changes since the previous preparation" });
  expect(within(changes).getByText("Updated: Patient privacy")).toBeVisible();
});

it("identifies approved material by title and kind without exposing locator or content", () => {
  const nodes = graph.nodes.map((node) =>
    node.id === "privacy"
      ? {
          ...node,
          assets: [
            {
              ...verifiedAsset,
              title: "Who may access a patient record?",
              kind: "assessment" as const,
            },
          ],
        }
      : node,
  );
  render(<CorpusPreparationReport graph={{ ...graph, nodes }} />);
  const privacy = screen.getByRole("region", { name: "Patient privacy" });
  expect(within(privacy).getByText("Who may access a patient record?")).toBeVisible();
  expect(within(privacy).getByText("Practice question")).toBeVisible();
  expect(screen.queryByText("quiz:privacy")).not.toBeInTheDocument();
});

it.each([
  { ...graph, nodes: graph.nodes.map((node) => ({ ...node, assets: [] })) },
  { ...graph, mappingReport: { ...graph.mappingReport!, runId: "another-run" } },
  { ...graph, groundingReport: { ...graph.groundingReport!, runId: "another-run" } },
  {
    ...graph,
    nodes: graph.nodes.map((node) => ({
      ...node,
      assets:
        node.assets?.map((asset) => ({
          ...asset,
          verification: { ...verifiedAsset.verification, verifierVersion: "another-verifier" },
        })) ?? [],
    })),
  },
])("rejects incomplete or mismatched verification evidence %#", (incomplete) => {
  render(<CorpusPreparationReport graph={incomplete} />);
  expect(screen.getByRole("status")).toHaveTextContent("Needs review");
});
