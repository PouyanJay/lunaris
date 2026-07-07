import type { CourseLevel } from "../types/course";

// Mirrors the server's level buckets (apps/api: lunaris_api/library/derive_course_summary.py,
// AD3) so a deep-linked Overview shows the same pill the library card computed server-side:
// mean KC difficulty < 0.34 beginner, < 0.67 intermediate, else advanced.
const INTERMEDIATE_FLOOR = 0.34;
const ADVANCED_FLOOR = 0.67;

/** Bucket a graph's mean KC difficulty into the level pill — null when no concepts mapped
 *  (never an invented level). */
export function bucketLevel(nodes: readonly { difficulty: number }[]): CourseLevel | null {
  if (nodes.length === 0) return null;
  const mean = nodes.reduce((sum, kc) => sum + kc.difficulty, 0) / nodes.length;
  if (mean < INTERMEDIATE_FLOOR) return "beginner";
  if (mean < ADVANCED_FLOOR) return "intermediate";
  return "advanced";
}
