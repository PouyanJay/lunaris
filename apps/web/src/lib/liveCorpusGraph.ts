import type { ConceptGraph } from "./liveGraph";
import type { NodeAsset } from "./liveMaterials";

export interface CorpusProvenance {
  courseId: string;
  title: string;
  digest: string;
  runId: string;
  adapterVersion: string;
  status: "pending" | "verified" | "failed";
}
export interface GroundingReport {
  sourceDigest: string;
  runId: string;
  status: "passed" | "failed";
  nodes: {
    nodeId: string;
    classification: "source" | "prerequisite" | "unsupported";
    locators: string[];
    rationale: string;
  }[];
  uncoveredLocators: string[];
  omittedLocators: string[];
  issues: string[];
}
export interface MappingReport {
  sourceDigest: string;
  runId: string;
  status: "passed" | "failed";
  mapperVersion: string;
  verifierVersion: string;
  mappings: {
    nodeId: string;
    locator: string;
    status: "approved" | "rejected";
    reason: string;
    evidence: string[];
  }[];
  gaps: { nodeId?: string | null; locator?: string | null; reason: string }[];
  issues: string[];
}
function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function text(value: unknown): value is string {
  return typeof value === "string";
}
function oneOf(value: unknown, allowed: string[]): boolean {
  return typeof value === "string" && allowed.includes(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}
function digest(value: unknown): boolean {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}
function reportBase(value: Record<string, unknown>): boolean {
  return (
    digest(value.sourceDigest) &&
    text(value.runId) &&
    (value.status === "passed" || value.status === "failed") &&
    strings(value.issues)
  );
}
function provenance(value: unknown): boolean {
  return (
    record(value) &&
    text(value.courseId) &&
    text(value.title) &&
    digest(value.digest) &&
    text(value.runId) &&
    text(value.adapterVersion) &&
    (value.status === "pending" || value.status === "verified" || value.status === "failed")
  );
}
function grounding(value: unknown): boolean {
  return (
    record(value) &&
    reportBase(value) &&
    strings(value.uncoveredLocators) &&
    strings(value.omittedLocators) &&
    Array.isArray(value.nodes) &&
    value.nodes.every(
      (node: unknown) =>
        record(node) &&
        text(node.nodeId) &&
        oneOf(node.classification, ["source", "prerequisite", "unsupported"]) &&
        strings(node.locators) &&
        text(node.rationale),
    )
  );
}
function mapping(value: unknown): boolean {
  return (
    record(value) &&
    reportBase(value) &&
    text(value.mapperVersion) &&
    text(value.verifierVersion) &&
    Array.isArray(value.mappings) &&
    value.mappings.every(
      (item: unknown) =>
        record(item) &&
        text(item.nodeId) &&
        text(item.locator) &&
        (item.status === "approved" || item.status === "rejected") &&
        text(item.reason) &&
        strings(item.evidence),
    ) &&
    Array.isArray(value.gaps) &&
    value.gaps.every(
      (gap: unknown) =>
        record(gap) &&
        text(gap.reason) &&
        (gap.nodeId == null || text(gap.nodeId)) &&
        (gap.locator == null || text(gap.locator)),
    )
  );
}
/** Legacy topic graphs omit course fields; present fields must pass the report boundary. */
export function hasValidCorpusFields(value: Record<string, unknown>): boolean {
  if (value.corpus == null && (value.groundingReport != null || value.mappingReport != null))
    return false;
  return (
    (value.corpus == null || provenance(value.corpus)) &&
    (value.groundingReport == null || grounding(value.groundingReport)) &&
    (value.mappingReport == null || mapping(value.mappingReport))
  );
}
/** Course preparation requires complete teaching wire fields, including pending/null specs. */
export function hasValidCourseTeaching(value: unknown): boolean {
  if (
    !record(value) ||
    !strings(value.aliases) ||
    !oneOf(value.provenance, ["compiled", "extended"])
  )
    return false;
  const spec = value.teachingSpec;
  return (
    (spec === null ||
      (record(spec) &&
        text(spec.objective) &&
        strings(spec.misconceptions) &&
        oneOf(spec.depth, ["intuition_first", "formal", "applied"]))) &&
    Array.isArray(value.masteryCriteria) &&
    value.masteryCriteria.every(
      (criterion: unknown) =>
        record(criterion) &&
        oneOf(criterion.kind, ["predict", "manipulate", "explain"]) &&
        text(criterion.statement) &&
        typeof criterion.needsSim === "boolean",
    )
  );
}
function materialMatches(
  asset: NodeAsset,
  source: CorpusProvenance,
  report: MappingReport,
): boolean {
  return (
    asset.sourceDigest === source.digest &&
    asset.verification?.sourceDigest === source.digest &&
    asset.verification.runId === source.runId &&
    asset.verification.verifierVersion === report.verifierVersion
  );
}
function sourceNodesHaveMaterials(graph: ConceptGraph, support: GroundingReport): boolean {
  const sourceNodes = support.nodes.filter((node) => node.classification === "source");
  return (
    sourceNodes.length > 0 &&
    sourceNodes.every((source) =>
      graph.nodes.some(
        (node) =>
          node.id === source.nodeId &&
          node.assets?.some((asset) => asset.kind === "lesson" || asset.kind === "video_clip"),
      ),
    )
  );
}
function hasVerifiedMaterials(graph: ConceptGraph): boolean {
  const { corpus, mappingReport: report, groundingReport: support } = graph;
  if (!corpus || !report || !support) return false;
  const pair = (nodeId: string, locator: string) => JSON.stringify([nodeId, locator]);
  const approved = new Set(
    report.mappings
      .filter((item) => item.status === "approved")
      .map((item) => pair(item.nodeId, item.locator)),
  );
  const attached = new Set<string>();
  for (const node of graph.nodes) {
    for (const asset of node.assets ?? []) {
      if (!materialMatches(asset, corpus, report)) return false;
      attached.add(pair(node.id, asset.locator));
    }
  }
  return (
    approved.size === attached.size &&
    [...approved].every((key) => attached.has(key)) &&
    sourceNodesHaveMaterials(graph, support)
  );
}
/** UI admission mirrors verification evidence; the API independently enforces authorization. */
export function isCorpusGraphReady(graph: ConceptGraph): boolean {
  const { corpus, groundingReport: support, mappingReport: materials } = graph;
  if (
    !corpus ||
    corpus.status !== "verified" ||
    !support ||
    !materials ||
    support.status !== "passed" ||
    materials.status !== "passed" ||
    support.runId !== corpus.runId ||
    materials.runId !== corpus.runId ||
    support.sourceDigest !== corpus.digest ||
    materials.sourceDigest !== corpus.digest ||
    support.issues.length ||
    materials.issues.length ||
    support.uncoveredLocators.length ||
    support.omittedLocators.length ||
    !graph.isAcyclic ||
    !graph.nodes.length
  )
    return false;
  const reviewed = new Set(support.nodes.map((node) => node.nodeId));
  return (
    hasVerifiedMaterials(graph) &&
    reviewed.size === graph.nodes.length &&
    support.nodes.length === graph.nodes.length &&
    graph.nodes.every(
      (node) =>
        reviewed.has(node.id) &&
        !!node.teachingSpec &&
        Array.isArray(node.masteryCriteria) &&
        node.masteryCriteria.length > 0,
    ) &&
    support.nodes.every(
      (node) =>
        node.classification !== "unsupported" &&
        (node.classification === "source" ? node.locators.length > 0 : !!node.rationale.trim()),
    )
  );
}
