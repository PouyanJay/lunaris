import type { Citation, Claim, MerrillSegments, VerifierStatus } from "../../types/course";
import type { StatusTone } from "../primitives/StatusDot";
import { matchClaimToSentence } from "./claimMatch";

export interface PhaseRef {
  key: keyof MerrillSegments;
  label: string;
}

/** The verifier's verdict → the house status tones. Shared so the mapping lives in one place. */
const VERIFIER_STATUS_TONE: Record<VerifierStatus, StatusTone> = {
  supported: "success",
  revise: "warning",
  cut: "danger",
  unverified: "neutral",
};

export function verifierStatusTone(status: VerifierStatus): StatusTone {
  return VERIFIER_STATUS_TONE[status];
}

/** One verifier annotation lifted out of the reading flow into the rail: a claim, its grounding
 *  citation (if any), the phase it belongs to, and — best-effort — the prose sentence it most likely
 *  refers to (`matchedSentence`), or null when no sentence is a confident match and the link falls
 *  back to the whole phase. */
export interface Annotation {
  id: string;
  phaseKey: keyof MerrillSegments;
  phaseLabel: string;
  claim: Claim;
  citation: Citation | undefined;
  matchedSentence: number | null;
}

/** Build the annotation list for one lesson — every phase's claims, each linked to its best-match
 *  prose sentence (or its phase). Stable ids `${phaseKey}-${index}` so highlight state survives
 *  re-render. */
export function buildAnnotations(
  segments: MerrillSegments,
  phases: PhaseRef[],
  citations: Map<string, Citation>,
): Annotation[] {
  const annotations: Annotation[] = [];
  for (const phase of phases) {
    const segment = segments[phase.key];
    segment.claims.forEach((claim, index) => {
      const match = matchClaimToSentence(claim.text, segment.prose);
      annotations.push({
        id: `${phase.key}-${index}`,
        phaseKey: phase.key,
        phaseLabel: phase.label,
        claim,
        citation: claim.supportedBy ? citations.get(claim.supportedBy) : undefined,
        matchedSentence: match ? match.index : null,
      });
    });
  }
  return annotations;
}

/** A run of annotations under one teaching phase — the rail's grouping unit. */
export interface AnnotationGroup {
  phaseKey: string;
  phaseLabel: string;
  items: Annotation[];
}

/** Group annotations by their phase, preserving order (annotations are already in phase order), so
 *  the rail mirrors the lesson's teaching rhythm. */
export function groupByPhase(annotations: Annotation[]): AnnotationGroup[] {
  const groups: AnnotationGroup[] = [];
  for (const annotation of annotations) {
    let group = groups.at(-1);
    if (!group || group.phaseKey !== annotation.phaseKey) {
      group = { phaseKey: annotation.phaseKey, phaseLabel: annotation.phaseLabel, items: [] };
      groups.push(group);
    }
    group.items.push(annotation);
  }
  return groups;
}
