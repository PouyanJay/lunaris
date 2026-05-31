import type { ProgressEvent, ProgressStage } from "../../types/course";
import styles from "./StageRail.module.css";

type PhaseStatus = "pending" | "active" | "done";

const PHASES: { stage: ProgressStage; label: string }[] = [
  { stage: "concepts_extracted", label: "Concepts" },
  { stage: "graph_built", label: "Graph" },
  { stage: "curriculum_designed", label: "Curriculum" },
  { stage: "module_authored", label: "Lessons" },
  { stage: "claims_verified", label: "Verify" },
  { stage: "run_completed", label: "Publish" },
];

const PHASE_INDEX = new Map(PHASES.map((phase, index) => [phase.stage, index]));

function phaseStatus(index: number, currentIndex: number): PhaseStatus {
  // run_completed is the last phase, so reaching it marks every phase done.
  const allDone = currentIndex >= PHASES.length - 1;
  if (allDone || index < currentIndex) return "done";
  if (index === currentIndex) return "active";
  return "pending";
}

interface StageRailProps {
  events: ProgressEvent[];
}

/** A compact horizontal rail of the coarse pipeline stages — the backbone that frames the
 *  fine-grained transcript. The accent (and the only motion) marks the single in-flight stage. */
export function StageRail({ events }: StageRailProps) {
  const last = events.at(-1);
  const currentIndex =
    last && last.stage !== "run_started" ? (PHASE_INDEX.get(last.stage) ?? -1) : -1;

  return (
    <div className={styles.rail}>
      <ol className={styles.phases}>
        {PHASES.map((phase, index) => {
          const status = phaseStatus(index, currentIndex);
          return (
            <li key={phase.stage} className={styles.phase} data-status={status}>
              <span className={styles.dot} data-status={status} aria-hidden="true" />
              <span className={styles.phaseLabel}>{phase.label}</span>
            </li>
          );
        })}
      </ol>
      <p className={`mono ${styles.live}`} role="status" aria-live="polite">
        {last?.label ?? "Starting…"}
      </p>
    </div>
  );
}
