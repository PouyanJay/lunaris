import type { StatusTone } from "../components/primitives/StatusDot";
import type { CourseLevel, LearnerCourseStatus } from "../types/course";

/** How a learner-course status reads on a card and in the library filter pills — one source of
 *  truth so the card dot and the pill label never drift. */
export const LEARNER_STATUS_META: Record<LearnerCourseStatus, { label: string; tone: StatusTone }> =
  {
    in_progress: { label: "In progress", tone: "accent" },
    completed: { label: "Completed", tone: "success" },
    not_started: { label: "Not started", tone: "neutral" },
  };

/** The level pill wording, bucketed server-side from the graph's mean KC difficulty. */
export const LEVEL_LABELS: Record<CourseLevel, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};
