import type { AgentEvent, ProgressEvent, SourceEvaluation, TrustTier } from "../types/course";

/** The build's grounding tallies (P8 instrument rail): claim verdict sums across the per-module
 *  CLAIMS_VERIFIED events, and the accepted discovery sources with their trust mix. */
export interface GroundingLedger {
  supported: number;
  cut: number;
  sources: number;
  /** Accepted sources per trust tier, ordered by count (descending); pct of accepted sources. */
  trustMix: { tier: TrustTier; count: number; pct: number }[];
}

function acceptedSources(agentEvents: AgentEvent[]): SourceEvaluation[] {
  return agentEvents
    .filter((event) => event.kind === "source_evaluated" && event.source?.accepted)
    .map((event) => event.source as SourceEvaluation);
}

function claimVerdicts(events: ProgressEvent[]): ProgressEvent[] {
  return events.filter((event) => event.stage === "claims_verified");
}

/** Null until any grounding signal exists — an instrument with no reading shows nothing. */
export function groundingLedger(
  events: ProgressEvent[],
  agentEvents: AgentEvent[],
): GroundingLedger | null {
  const verdicts = claimVerdicts(events);
  const accepted = acceptedSources(agentEvents);
  if (verdicts.length === 0 && accepted.length === 0) return null;

  const counts = new Map<TrustTier, number>();
  for (const source of accepted) {
    if (source.trustTier) counts.set(source.trustTier, (counts.get(source.trustTier) ?? 0) + 1);
  }
  const trustMix = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([tier, count]) => ({ tier, count, pct: Math.round((count / accepted.length) * 100) }));

  return {
    supported: verdicts.reduce((sum, event) => sum + (event.claimsSupported ?? 0), 0),
    cut: verdicts.reduce((sum, event) => sum + (event.claimsCut ?? 0), 0),
    sources: accepted.length,
    trustMix,
  };
}

/** One honest gauge: a real number off the wire, never a threshold the harness didn't compute.
 *  Tones state facts (claims were cut, gaps exist), not invented pass/fail gates. */
export interface ScorecardGauge {
  key: "grounding" | "coverage" | "structure" | "trust";
  label: string;
  value: string;
  detail: string;
  tone: "success" | "warning" | "neutral";
  /** 0..100 for the ring where the value is a share; null renders a plain tile. */
  pct: number | null;
}

function groundingGauge(events: ProgressEvent[]): ScorecardGauge | null {
  const verdicts = claimVerdicts(events);
  if (verdicts.length === 0) return null;
  const total = verdicts.reduce((sum, event) => sum + (event.claimsTotal ?? 0), 0);
  const supported = verdicts.reduce((sum, event) => sum + (event.claimsSupported ?? 0), 0);
  const cut = verdicts.reduce((sum, event) => sum + (event.claimsCut ?? 0), 0);
  const pct = total > 0 ? Math.round((supported / total) * 100) : null;
  return {
    key: "grounding",
    label: "Grounding",
    value: pct !== null ? `${pct}%` : "—",
    detail: `${supported} of ${total} claims supported`,
    tone: cut > 0 ? "warning" : "success",
    pct,
  };
}

function coverageGauge(events: ProgressEvent[]): ScorecardGauge | null {
  const coverage = [...events].reverse().find((event) => event.stage === "coverage_verified");
  if (!coverage || coverage.gapCount == null) return null;
  return {
    key: "coverage",
    label: "Coverage",
    value: coverage.gapCount === 0 ? "no gaps" : `${coverage.gapCount} gaps`,
    detail: "promised competencies built",
    tone: coverage.gapCount === 0 ? "success" : "warning",
    pct: null,
  };
}

function structureGauge(events: ProgressEvent[]): ScorecardGauge | null {
  const graphEvent = [...events]
    .reverse()
    .find((event) => event.stage === "graph_built" && event.graph);
  if (!graphEvent?.graph) return null;
  return {
    key: "structure",
    label: "Structure",
    value: graphEvent.graph.isAcyclic ? "acyclic" : "cyclic",
    detail: `${graphEvent.graph.nodes.length} concepts · ${graphEvent.graph.edges.length} edges`,
    tone: graphEvent.graph.isAcyclic ? "success" : "warning",
    pct: null,
  };
}

function trustGauge(agentEvents: AgentEvent[]): ScorecardGauge | null {
  const accepted = acceptedSources(agentEvents);
  const credible = accepted.filter((source) => source.credibility != null);
  if (credible.length === 0) return null;
  const mean =
    credible.reduce((sum, source) => sum + (source.credibility as number), 0) / credible.length;
  const pct = Math.round(mean * 100);
  return {
    key: "trust",
    label: "Trust",
    value: `${pct}%`,
    detail: `mean credibility · ${accepted.length} sources`,
    tone: "neutral",
    pct,
  };
}

/** The readiness scorecard (P8): each gauge appears only once its source event has arrived. */
export function readinessScorecard(
  events: ProgressEvent[],
  agentEvents: AgentEvent[],
): ScorecardGauge[] {
  return [
    groundingGauge(events),
    coverageGauge(events),
    structureGauge(events),
    trustGauge(agentEvents),
  ].filter((gauge): gauge is ScorecardGauge => gauge !== null);
}
