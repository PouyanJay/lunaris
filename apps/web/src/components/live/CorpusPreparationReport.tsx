import { useId } from "react";
import { Button } from "../primitives/Button";
import styles from "./CorpusPreparationReport.module.css";

interface ReviewNode {
  id: string;
  name: string;
  requires: string[];
  assets?: { locator: string; title: string; kind: string }[];
}
interface NodeSupport {
  nodeId: string;
  classification: "source" | "prerequisite" | "unsupported";
  locators: string[];
  rationale: string;
}
interface Mapping {
  nodeId: string;
  locator: string;
  status: "approved" | "rejected";
  reason: string;
  evidence: string[];
}
interface MappingReport {
  status: "passed" | "failed";
  sourceDigest: string;
  runId: string;
  mapperVersion: string;
  verifierVersion: string;
  mappings: Mapping[];
  gaps: { nodeId?: string | null; locator?: string | null; reason: string }[];
  issues: string[];
}
/** Read-only preparation evidence needed to review a course before starting a session. */
export interface CorpusReviewGraph {
  corpus: { title: string; digest: string; status: "pending" | "verified" | "failed" };
  nodes: ReviewNode[];
  groundingReport?: {
    status: "passed" | "failed";
    sourceDigest: string;
    nodes: NodeSupport[];
    uncoveredLocators: string[];
    omittedLocators: string[];
    issues: string[];
  } | null;
  mappingReport?: MappingReport | null;
}
interface ReportProps {
  graph: CorpusReviewGraph | null;
  previousGraph?: CorpusReviewGraph | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}
const REASONS: Record<string, string> = {
  verified: "Supports this concept.",
  verifier_rejected: "Does not support this concept.",
  invalid_evidence: "The source evidence could not be confirmed.",
  missing_verdict: "This material has not been verified.",
  node_without_material: "No supporting materials are available.",
  unmapped_candidate: "No matching concept was found for this material.",
  candidate_limit: "Some materials remain outside this preparation's review limit.",
  context_limit: "Some source content remains outside this preparation's review limit.",
  video_unavailable: "A usable video clip is not available.",
  invalid_proposal: "The proposed material match could not be validated.",
  invalid_verdict: "The material verification could not be validated.",
  untrusted_grounding: "Course support must be verified before materials can be matched.",
  mapping_failed: "Supporting materials could not be prepared.",
  source_text_truncated: "Some course text was too long to include in this review.",
  unsupported_nodes: "Some concepts could not be supported by the course.",
  invalid_node_coverage: "Some concepts have not been reviewed correctly.",
  incomplete_teaching_specs: "Some concepts still need teaching or assessment content.",
};
function reasonText(reason: string): string {
  return REASONS[reason] ?? "This part of the preparation needs another review.";
}
function sourceMismatch(graph: CorpusReviewGraph): boolean {
  return [graph.groundingReport, graph.mappingReport].some(
    (report) => report && report.sourceDigest !== graph.corpus.digest,
  );
}
function reportStatus(graph: CorpusReviewGraph): string {
  const { groundingReport: grounding, mappingReport: mapping } = graph;
  if (
    sourceMismatch(graph) ||
    graph.corpus.status === "failed" ||
    grounding?.status === "failed" ||
    mapping?.status === "failed"
  )
    return "Needs review";
  if (!grounding || !mapping || graph.corpus.status === "pending") return "Awaiting verification";
  const covered = new Set(grounding.nodes.map((node) => node.nodeId));
  if (
    !graph.nodes.length ||
    covered.size !== graph.nodes.length ||
    graph.nodes.some((node) => !covered.has(node.id)) ||
    grounding.nodes.some((node) => node.classification === "unsupported") ||
    grounding.issues.length ||
    mapping.issues.length ||
    grounding.uncoveredLocators.length ||
    grounding.omittedLocators.length
  )
    return "Needs review";
  return "Ready for review";
}
function materialSignature(graph: CorpusReviewGraph, nodeId: string): string {
  return JSON.stringify(
    (graph.mappingReport?.mappings ?? [])
      .filter((item) => item.nodeId === nodeId)
      .map((item) => [item.locator, item.status, item.reason].join("\n"))
      .sort(),
  );
}
function conceptSignature(graph: CorpusReviewGraph, node: ReviewNode): string {
  const support = graph.groundingReport?.nodes.find((item) => item.nodeId === node.id);
  return JSON.stringify([
    node.name,
    [...node.requires].sort(),
    support?.classification,
    [...(support?.locators ?? [])].sort(),
    support?.rationale,
  ]);
}
function changesBetween(graph: CorpusReviewGraph, previous: CorpusReviewGraph): string[] {
  const changes: string[] = [];
  if (graph.corpus.digest !== previous.corpus.digest)
    changes.push("The course content has changed.");
  const before = new Map(previous.nodes.map((node) => [node.id, node]));
  const after = new Map(graph.nodes.map((node) => [node.id, node]));
  for (const node of graph.nodes) {
    const old = before.get(node.id);
    if (!old) changes.push(`Added: ${node.name}`);
    else if (conceptSignature(graph, node) !== conceptSignature(previous, old))
      changes.push(`Updated: ${node.name}`);
  }
  for (const node of previous.nodes) if (!after.has(node.id)) changes.push(`Removed: ${node.name}`);
  for (const [nodeId, node] of new Map([...before, ...after])) {
    if (materialSignature(graph, nodeId) !== materialSignature(previous, nodeId))
      changes.push(`Supporting materials changed for ${node.name}.`);
  }
  return changes;
}
function Changes({ graph, previous }: { graph: CorpusReviewGraph; previous: CorpusReviewGraph }) {
  const changes = changesBetween(graph, previous);
  return (
    <section aria-label="Changes since the previous preparation" className={styles.section}>
      <h3>Changes since the previous preparation</h3>
      {changes.length ? (
        <ul>
          {changes.map((change, index) => (
            <li key={index}>{change}</li>
          ))}
        </ul>
      ) : (
        <p>No source, concept or supporting material changes were found.</p>
      )}
    </section>
  );
}
function materialKind(kind: string | undefined): string {
  if (kind === "lesson") return "Lesson excerpt";
  if (kind === "assessment") return "Practice question";
  if (kind === "video_clip") return "Video clip";
  return "Course material";
}
function ApprovedMaterials({ node, mappings }: { node: ReviewNode; mappings: Mapping[] }) {
  const approved = mappings.filter((mapping) => mapping.status === "approved");
  if (!approved.length) return null;
  return (
    <ul aria-label="Approved materials">
      {approved.map((mapping, index) => {
        const asset = node.assets?.find((candidate) => candidate.locator === mapping.locator);
        return (
          <li key={index}>
            {asset?.title && (
              <>
                <span>{asset.title}</span>
                {" · "}
              </>
            )}
            <span className={styles.status}>{materialKind(asset?.kind)}</span>
          </li>
        );
      })}
    </ul>
  );
}
function ConceptReview({ node, graph }: { node: ReviewNode; graph: CorpusReviewGraph }) {
  const id = useId();
  const support = graph.groundingReport?.nodes.find((item) => item.nodeId === node.id);
  const mappings = graph.mappingReport?.mappings.filter((item) => item.nodeId === node.id) ?? [];
  const approved = mappings.filter((item) => item.status === "approved").length;
  const prerequisites = node.requires.map(
    (required) =>
      graph.nodes.find((item) => item.id === required)?.name ?? "Unavailable prerequisite",
  );
  const classification = sourceMismatch(graph) ? "unsupported" : support?.classification;
  const label =
    classification === "source"
      ? "Supported by this course"
      : classification === "prerequisite"
        ? "Additional prerequisite"
        : "Unverified concept";
  return (
    <section aria-labelledby={id} className={styles.concept}>
      <h4 id={id}>{node.name}</h4>
      <p className={styles.status}>{label}</p>
      {prerequisites.length > 0 && <p>Learn first: {prerequisites.join(", ")}</p>}
      {classification === "prerequisite" && support?.rationale && <p>{support.rationale}</p>}
      {graph.mappingReport?.sourceDigest === graph.corpus.digest ? (
        <p>
          {approved.toLocaleString()} approved {approved === 1 ? "material" : "materials"}
        </p>
      ) : (
        <p>Materials await current source verification.</p>
      )}
      {graph.mappingReport?.sourceDigest === graph.corpus.digest && (
        <ApprovedMaterials node={node} mappings={mappings} />
      )}
      {mappings
        .filter((item) => item.status === "rejected")
        .map((item, index) => (
          <p key={index}>Excluded material: {reasonText(item.reason)}</p>
        ))}
    </section>
  );
}
function Gaps({ graph }: { graph: CorpusReviewGraph }) {
  const grounding = graph.groundingReport;
  const gaps = graph.mappingReport?.gaps ?? [];
  const issues = [
    ...new Set([...(grounding?.issues ?? []), ...(graph.mappingReport?.issues ?? [])]),
  ];
  const uncovered = grounding?.uncoveredLocators.length ?? 0;
  const omitted = grounding?.omittedLocators.length ?? 0;
  if (!gaps.length && !issues.length && !uncovered && !omitted && !sourceMismatch(graph))
    return null;
  return (
    <section aria-label="Gaps and exclusions" className={styles.section}>
      <h3>Gaps and exclusions</h3>
      {sourceMismatch(graph) && (
        <p>
          Some results refer to a different version of the course. Prepare the current course again.
        </p>
      )}
      {uncovered > 0 && (
        <p>
          {uncovered.toLocaleString()} course {uncovered === 1 ? "section is" : "sections are"} not
          covered.
        </p>
      )}
      {omitted > 0 && (
        <p>
          {omitted.toLocaleString()} course {omitted === 1 ? "section was" : "sections were"}{" "}
          omitted from this review.
        </p>
      )}
      {issues.map((issue) => (
        <p key={issue}>{reasonText(issue)}</p>
      ))}
      {gaps.map((gap, index) => (
        <p key={index}>
          {graph.nodes.find((node) => node.id === gap.nodeId)?.name ?? "Course material"}:{" "}
          {reasonText(gap.reason)}
        </p>
      ))}
    </section>
  );
}
function SourceDetails({ graph }: { graph: CorpusReviewGraph }) {
  return (
    <details className={styles.section}>
      <summary>Source details</summary>
      <dl className={styles.details}>
        <dt>Source version</dt>
        <dd>{graph.corpus.digest}</dd>
        {graph.mappingReport && (
          <>
            <dt>Material matching version</dt>
            <dd>{graph.mappingReport.mapperVersion}</dd>
            <dt>Material verification version</dt>
            <dd>{graph.mappingReport.verifierVersion}</dd>
          </>
        )}
      </dl>
    </details>
  );
}

/** Human-readable review of preparation evidence; viewing this report starts no learning activity. */
export function CorpusPreparationReport({
  graph,
  previousGraph,
  loading = false,
  error,
  onRetry,
}: ReportProps) {
  const id = useId();
  if (loading)
    return (
      <section aria-label="Course preparation" aria-busy="true" className={styles.root}>
        <p role="status">Preparing course…</p>
        <div className={styles.placeholder} aria-hidden="true" />
      </section>
    );
  if (error)
    return (
      <section aria-label="Course preparation" className={styles.root}>
        <p role="alert">
          Could not load the preparation report. Retry, or prepare the course again.
        </p>
        {onRetry && <Button onClick={onRetry}>Retry report</Button>}
      </section>
    );
  if (!graph) return <p>Choose a course and prepare it to review its learning plan.</p>;
  return (
    <section aria-labelledby={id} className={styles.root}>
      <header className={styles.section}>
        <h2 id={id}>{graph.corpus.title}</h2>
        <p role="status" className={styles.status}>
          {reportStatus(graph)}
        </p>
        <p>Review the concepts, supporting materials and any gaps before starting.</p>
      </header>
      {previousGraph && <Changes graph={graph} previous={previousGraph} />}
      <section aria-label="Learning plan" className={styles.section}>
        <h3>Learning plan</h3>
        {graph.nodes.length ? (
          graph.nodes.map((node) => <ConceptReview key={node.id} node={node} graph={graph} />)
        ) : (
          <p>No concepts are available yet. Prepare the course again to build its learning plan.</p>
        )}
      </section>
      <Gaps graph={graph} />
      <SourceDetails graph={graph} />
    </section>
  );
}
