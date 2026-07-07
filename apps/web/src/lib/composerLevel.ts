import type { Clarification, Level } from "../types/clarifier";

/** The composer's Level control: "recommended" lets the agent infer the level (today's default);
 *  the concrete choices map onto the clarifier's target-level answer. */
export type ComposerLevel = "recommended" | "beginner" | "intermediate" | "advanced";

const TARGET_LEVEL: Record<Exclude<ComposerLevel, "recommended">, Level> = {
  beginner: "novice",
  intermediate: "intermediate",
  advanced: "advanced",
};

/** The clarifier target level a composer choice implies, or undefined for "recommended" (no
 *  override — the interpreter infers the level, unchanged from today's one-click build). */
export function composerLevelToTarget(level: ComposerLevel): Level | undefined {
  return level === "recommended" ? undefined : TARGET_LEVEL[level];
}

/** Fold the composer's Level choice into the clarification the build carries: a concrete level
 *  overrides the target level (mapping, not duplicating, the brief's level answer); "recommended"
 *  leaves the clarification untouched. Returns undefined when there's nothing to send (no brief and
 *  no explicit level) so the build stays inference-only. */
export function applyComposerLevel(
  base: Clarification | undefined,
  level: ComposerLevel,
): Clarification | undefined {
  const target = composerLevelToTarget(level);
  if (target === undefined) return base;
  return { ...(base ?? {}), targetLevel: target };
}
