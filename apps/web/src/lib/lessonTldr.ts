import type { Objective } from "../types/course";

/** The learner-facing capability inside an objective statement: authored objectives lead with a
 *  condition + scaffolding ("Given X, the learner can …") that earns its place in an assessment
 *  rubric but buries the takeaway in a summary. Strip it deterministically; an unmatched
 *  statement passes through whole. */
function capabilityOf(statement: string): string {
  const stripped = statement.replace(/^given\s+[^,]+,\s*(?:the\s+learner\s+can\s+)?/i, "");
  if (!stripped) return statement;
  return stripped.charAt(0).toUpperCase() + stripped.slice(1);
}

/** Derive the lesson's "in 30 seconds" bullets from its module's objectives — the pipeline's own
 *  learner-facing statements, de-scaffolded and capped at three. No objectives → no summary
 *  (the panel hides rather than invent content). */
export function deriveTldr(objectives: Objective[]): string[] {
  return objectives.slice(0, 3).map((objective) => capabilityOf(objective.statement));
}
