import type { StatusTone } from "../components/primitives/StatusDot";
import type { RunStatus } from "../types/course";

/** Run lifecycle → the house status convention (dot + uppercase-mono label). Only RUNNING is live.
 *  Shared by the sidebar run list and the composer's recent-builds table so they never drift. */
export const RUN_STATUS_TONE: Record<RunStatus, { tone: StatusTone; live: boolean }> = {
  running: { tone: "accent", live: true },
  completed: { tone: "success", live: false },
  failed: { tone: "danger", live: false },
  // A deliberate stop, not an error — neutral, so it doesn't read as a failure.
  cancelled: { tone: "neutral", live: false },
};
